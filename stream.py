import os
import subprocess
import io
import wave
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from openai import AzureOpenAI, OpenAI

# .envファイルを読み込み
load_dotenv()

# === クライアント設定 ===
# Azure OpenAI Client (翻訳用)
azure_client = AzureOpenAI(
    azure_endpoint=os.getenv("ENDPOINT_URL"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version="2024-05-01-preview",
)
# OpenAI Client (Whisper文字起こし用)
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 翻訳プロンプトスタイル
PROMPT_STYLES = {
    "serious": "あなたはプロの同時通訳者です。発言内容を忠実に、かつ正確でフォーマルな日本語に翻訳してください。**【重要】元のテキストにない情報を補ったり、文章を完成・創作することは絶対に禁止です。入力された断片だけを忠実に翻訳してください。**【重要】元のテキストにない情報を補ったり、文章を完成・創作することは絶対に禁止です。**",
    "casual": "あなたは海外のライブ配信を一緒に見ている親しい友人です。話されている内容を、非常にカジュアルで親しみやすい日本語で教えてください。スラングなども自然な日本語に意訳し、絵文字を効果的に使って感情を表現してください。**【重要】元のテキストにない情報を補ったり、文章を完成・創作することは絶対に禁止です。**",
    "humorous": "あなたはユーモアのセンスに溢れた翻訳家です。話者の意図を汲み取りつつ、面白おかしく、時には気の利いたジョークやツッコミを交えながら日本語に翻訳してください。**【重要】元のテキストにない情報を補ったり、文章を完成・創作することは絶対に禁止です。**",
    "expert": "あなたは特定分野の専門家です。専門用語や複雑な概念も、その分野に詳しい人が聞いても納得できるような、正確かつ分かりやすい日本語で解説するように翻訳してください。**【重要】元のテキストにない情報を補ったり、文章を完成・創作することは絶対に禁止です。**"
}

app = Flask(__name__)
# Renderのヘルスチェック用エンドポイント
app.config['HEALTHZ_PATH'] = '/healthz'
# 非推奨の警告を抑制
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a_super_secret_key')
# Renderのドメインからの接続を許可するようにCORSを設定
socketio = SocketIO(app, cors_allowed_origins="*")

transcribe_running = False

def transcribe_audio_with_api(audio_chunk):
    """Whisper APIに音声データを送信して文字起こしする"""
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
        wf.writeframes(audio_chunk)
    wav_buffer.seek(0)
    
    try:
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=("audio.wav", wav_buffer),
            response_format="text"
        )
        return transcript.strip()
    except Exception as e:
        print(f"❌ Whisper API エラー: {e}")
        return ""

def translate_with_chatgpt(text, style="serious"):
    """Azure OpenAI APIを使って翻訳を実行"""
    system_prompt = PROMPT_STYLES.get(style, PROMPT_STYLES["serious"])
    try:
        response = azure_client.chat.completions.create(
            model=os.getenv("DEPLOYMENT_NAME"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ 翻訳AIエラー: {e}")
        return "翻訳エラー"

@app.route("/")
def index():
    return render_template("index.html", prompt_styles=PROMPT_STYLES)

# Renderのヘルスチェック用
@app.route("/healthz")
def healthz():
    return "OK", 200

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

    streamlink_cmd = ["streamlink", "--stdout", url, "best"]
    stream_proc = subprocess.Popen(streamlink_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    ffmpeg_cmd = ["ffmpeg", "-i", "pipe:0", "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", "pipe:1"]
    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=stream_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    chunk_duration = 4  # API呼び出しの頻度を少し下げる
    chunk_size = 16000 * 2 * 1 * chunk_duration
    
    while transcribe_running:
        audio_chunk_raw = ffmpeg_proc.stdout.read(chunk_size)
        if not audio_chunk_raw:
            break
            
        try:
            en_text = transcribe_audio_with_api(audio_chunk_raw)
            
            if en_text:
                print(f"📝 EN: {en_text}")
                ja_text = translate_with_chatgpt(en_text, style=style)
                print(f"🌐 JP (style: {style}): {ja_text}")
                # 英語と日本語を一つのイベントで送る
                socketio.emit("new_subtitle", {"en": en_text, "ja": ja_text})
                
        except Exception as e:
            print(f"❌ メインループエラー: {e}")
    
    # プロセスが終了したか確認し、killする
    if stream_proc.poll() is None:
        stream_proc.kill()
    if ffmpeg_proc.poll() is None:
        ffmpeg_proc.kill()
        
    transcribe_running = False
    print("🛑 停止しました")