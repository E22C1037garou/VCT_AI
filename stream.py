import os
import subprocess
import io
import wave
import collections
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from openai import AzureOpenAI, OpenAI

# .envファイルを読み込み
load_dotenv()

# === クライアント設定 ===
azure_client = AzureOpenAI(
    azure_endpoint=os.getenv("ENDPOINT_URL"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version="2024-05-01-preview",
)
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# === プロンプト定義の更新 ===
# AIに与える役割と指示をより具体的にし、文脈を考慮させるように変更
BASE_PROMPT_STYLES = {
    "serious": "あなたはプロの同時通訳者です。以下の会話の文脈を理解した上で、最後の行のテキストだけを、正確かつフォーマルな日本語に翻訳してください。文脈部分の翻訳は不要です。",
    "casual": "あなたはライブ配信の優秀な翻訳コメント投稿者です。以下の会話の文脈を理解した上で、最後の行のテキストだけを、絵文字を使いながら非常にカジュアルな日本語に翻訳してください。文脈部分の翻訳は不要です。",
    "humorous": "あなたはユーモアのセンスに溢れた翻訳家です。以下の会話の文脈を理解した上で、最後の行のテキストだけを、面白おかしく、時に気の利いたジョークを交えながら日本語に翻訳してください。文脈部分の翻訳は不要です。",
    "expert": "あなたは特定分野の専門家です。以下の会話の文脈を理解した上で、最後の行のテキストだけを、専門用語も正確に、分かりやすい日本語で解説するように翻訳してください。文脈部分の翻訳は不要です。"
}

# 共通の禁止事項ルール
PROMPT_RULE = "\n**【重要ルール】指示された最後の行以外の翻訳は絶対に出力せず、また、元のテキストにない情報を補ったり、文章を創作することも絶対に禁止です。**"

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a_super_secret_key_for_dev')
socketio = SocketIO(app, cors_allowed_origins="*")

transcribe_running = False

def transcribe_audio_with_api(audio_chunk):
    """Whisper APIで文字起こし"""
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
        wf.writeframes(audio_chunk)
    wav_buffer.seek(0)
    
    try:
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1", file=("audio.wav", wav_buffer), response_format="text"
        )
        return transcript.strip()
    except Exception as e:
        print(f"❌ Whisper API エラー: {e}")
        return ""

def translate_with_chatgpt(context_text, style="serious"):
    """Azure OpenAI APIを使い、文脈を考慮して翻訳"""
    system_prompt = BASE_PROMPT_STYLES.get(style, BASE_PROMPT_STYLES["serious"]) + PROMPT_RULE
    try:
        response = azure_client.chat.completions.create(
            model=os.getenv("DEPLOYMENT_NAME"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context_text}
            ],
            temperature=0.1, # 創造性を抑える
            max_tokens=150   # 出力長を制限
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ 翻訳AIエラー: {e}")
        return "翻訳エラー"

@app.route("/")
def index():
    return render_template("index.html", prompt_styles=BASE_PROMPT_STYLES)

# ... (start, stop ルートは変更なし)
@app.route("/start", methods=["POST"])
def start():
    global transcribe_running
    if not transcribe_running:
        transcribe_running = True
        url = request.form["stream_url"]
        style = request.form.get("prompt_style", "serious")
        socketio.start_background_task(target=transcribe_loop, url=url, style=style)
    return "リアルタイム文字起こしと翻訳を開始しました！"

@app.route("/stop", methods=["POST"])
def stop():
    global transcribe_running
    transcribe_running = False
    return "停止しました"

def transcribe_loop(url, style):
    global transcribe_running
    print(f"🔁 リアルタイム文字起こし開始 (スタイル: {style})")

    # ▼▼▼【問題Aの対策】デバッグログを有効化 ▼▼▼
    streamlink_cmd = ["streamlink", "--stdout", url, "best"]
    stream_proc = subprocess.Popen(streamlink_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    ffmpeg_cmd = ["ffmpeg", "-i", "pipe:0", "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", "pipe:1"]
    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=stream_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    chunk_duration = 4
    chunk_size = 16000 * 2 * 1 * chunk_duration

    # ▼▼▼【問題Bの対策】コンテキストバッファを作成 ▼▼▼
    # dequeを使うと、要素が最大数を超えたときに古いものから自動的に削除される
    context_buffer = collections.deque(maxlen=3)
    
    while transcribe_running:
        # streamlinkからのエラーがないかチェック
        stream_err = stream_proc.stderr.readline().decode('utf-8')
        if stream_err:
            print(f"❌ Streamlink エラー: {stream_err}")

        audio_chunk_raw = ffmpeg_proc.stdout.read(chunk_size)
        if not audio_chunk_raw:
            print("オーディオストリームが終了しました。")
            break
            
        try:
            en_text = transcribe_audio_with_api(audio_chunk_raw)
            
            if en_text:
                print(f"📝 EN: {en_text}")
                
                # コンテキストバッファに新しいテキストを追加
                context_buffer.append(en_text)
                # 翻訳APIに渡すための、改行で区切られたテキストを作成
                context_for_api = "\n".join(context_buffer)

                ja_text = translate_with_chatgpt(context_for_api, style=style)
                print(f"🌐 JP (style: {style}): {ja_text}")
                socketio.emit("new_subtitle", {"en": en_text, "ja": ja_text})
                
        except Exception as e:
            print(f"❌ メインループエラー: {e}")
    
    if stream_proc.poll() is None: stream_proc.kill()
    if ffmpeg_proc.poll() is None: ffmpeg_proc.kill()
        
    transcribe_running = False
    print("🛑 停止しました")