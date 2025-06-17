import os
import subprocess
import io
import wave
import time
import numpy as np
import soundfile as sf
import librosa  # 音声解析ライブラリをインポート
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
import whisper
from openai import AzureOpenAI

# .envファイル読み込みとクライアント設定 
load_dotenv()
AZURE_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT = os.getenv("ENDPOINT_URL")
AZURE_DEPLOYMENT_NAME = os.getenv("DEPLOYMENT_NAME")
client = AzureOpenAI(
    azure_endpoint=AZURE_ENDPOINT,
    api_key=AZURE_API_KEY,
    api_version="2024-05-01-preview",
)

# ベースとなる翻訳スタイル定義
BASE_PROMPT_STYLES = {
    "news": "あなたはニュース放送用のプロのリアルタイム字幕担当者です。与えられた英語の断片を、正確かつ客観的でフォーマルな日本語に翻訳してください。",
    "lecture": "あなたは講義用のプロのリアルタイム字幕担当者です。与えられた英語の断片を、専門用語も正確に、論理的で明快な日本語へ翻訳してください。",
    "gaming": "あなたはゲーム配信用のリアルタイム字幕担当者です。与えられた英語の断片を、ゲームの雰囲気に合ったカジュアルで生き生きとした日本語に翻訳してください。",
    "casual_conversation": "あなたは日常会話用のリアルタイム字幕担当者です。与えられた英語の断片を、非常にカジュアルで親しみやすい日本語へ翻訳してください。",
    "default": "あなたはプロのリアルタイム字幕担当者です。与えられた英語の断片を、中立的かつ正確な日本語へ翻訳してください。"
}

# Whisperモデル
# model = whisper.load_model("base")
model = whisper.load_model("tiny") #軽量モデル

app = Flask(__name__)
socketio = SocketIO(app)

transcribe_running = False

# === ここから分析用の新関数群 ===

def analyze_content_category(text):
    """テキスト内容を分析し、カテゴリを返す"""
    print("🤖 コンテンツカテゴリの分析を開始...")
    categories = ", ".join(BASE_PROMPT_STYLES.keys())
    try:
        # (分析用のAI呼び出しロジックは以前と同様)
        # ... (省略) ...
        return "gaming" # デモ用に固定
    except Exception as e:
        print(f"❌ カテゴリ分析エラー: {e}")
        return "default"

def analyze_voice_gender(audio_chunks, sample_rate):
    """音声チャンクのリストから声の高さを分析し、性別を推定する"""
    print("🎤 声質の分析を開始...")
    try:
        full_audio = np.concatenate(audio_chunks)
        f0, _, _ = librosa.pyin(full_audio, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7'))
        # f0が計算できたフレームの平均値を取る
        valid_f0 = f0[~np.isnan(f0)]
        if len(valid_f0) == 0:
            return "unknown"
        
        avg_f0 = np.mean(valid_f0)
        print(f"🎵 平均基本周波数: {avg_f0:.2f} Hz")

        if avg_f0 < 165: # 165Hzを閾値とする（一般的な参考値）
            return "male" # 低い声
        else:
            return "female" # 高い声
    except Exception as e:
        print(f"❌ 音声分析エラー: {e}")
        return "unknown"

def analyze_personality(text):
    """テキストから話者の性格・トーンを分析する"""
    print("🧐 性格・トーンの分析を開始...")
    personalities = "energetic, calm, witty, analytical, friendly"
    try:
        # (分析用のAI呼び出しロジック)
        # ... (省略) ...
        return "energetic" # デモ用に固定
    except Exception as e:
        print(f"❌ 性格分析エラー: {e}")
        return "unknown"

def generate_dynamic_prompt(category, gender, personality):
    """分析結果を基に、最終的な翻訳プロンプトを動的に生成する"""
    print(f"🛠️ プロンプト生成中 (カテゴリ: {category}, 声質: {gender}, 性格: {personality})")
    
    # 1. ベースとなるプロンプトを選択
    prompt = BASE_PROMPT_STYLES.get(category, BASE_PROMPT_STYLES["default"])

    # 2. 声質と性格に応じた指示を追加 (カジュアルなカテゴリの場合のみ)
    if category in ["gaming", "casual_conversation"]:
        gender_desc = ""
        if gender == "male":
            gender_desc = "低めの落ち着いた声"
        elif gender == "female":
            gender_desc = "高めの明るい声"

        personality_instruction = ""
        if personality == "energetic":
            personality_instruction = "会話の勢いやエネルギーを、感嘆符(!)や感情豊かな言葉遣いで表現してください。"
        elif personality == "calm":
            personality_instruction = "落ち着いたトーンを、平易で穏やかな言葉遣いで表現してください。"
        elif personality == "witty":
            personality_instruction = "機知に富んだ会話やジョークのニュアンスを、巧みな言葉選びで表現してください。"
        
        if gender_desc or personality_instruction:
            prompt += f"\n話者は「{gender_desc}」で「{personality}」な性格です。{personality_instruction}"
            prompt += "\n**ただし、翻訳文はステレオタイプな性別言葉(「〜だぜ」「〜だわ」等)を絶対に使わず、あくまで中性的にしてください。**"

    # 3. 共通の厳格なルールを追加
    prompt += "\n**【最重要ルール】元のテキストにない情報を補ったり、文章を完成・創作することは絶対に禁止です。入力された断片だけを忠実に翻訳してください。**"
    
    print(f"✅ 生成されたプロンプト: {prompt[:100]}...") # 長いので先頭だけ表示
    return prompt

def translate_with_chatgpt(text, system_prompt):
    """生成された動的プロンプトを使って翻訳を実行"""
    try:
        response = client.chat.completions.create(
            model=AZURE_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ 翻訳AIエラー: {e}")
        return "翻訳エラー"

# Flaskルートとメインループ
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/start", methods=["POST"])
def start():
    global transcribe_running
    if not transcribe_running:
        transcribe_running = True
        url = request.form["stream_url"]
        socketio.start_background_task(target=transcribe_loop, url=url)
    return "リアルタイム文字起こしと翻訳を開始しました！"

@app.route("/stop", methods=["POST"])
def stop():
    global transcribe_running
    transcribe_running = False
    return "停止しました"

def transcribe_loop(url):
    global transcribe_running
    print("🔁 リアルタイム文字起こし開始（AIハイブリッド分析モード）")

    # 分析用変数の初期化
    ANALYSIS_BUFFER_SECONDS = 30  # 分析時間を短縮
    time_elapsed = 0
    initial_transcripts = []
    initial_audio_chunks = []
    analysis_complete = False
    
    # 現在のプロンプトをグローバルに管理
    globals()['current_system_prompt'] = BASE_PROMPT_STYLES["default"]

    # (ffmpegなどのプロセス起動部分は変更なし)
    streamlink_cmd = ["streamlink", url, "best", "-O"]
    stream_proc = subprocess.Popen(streamlink_cmd, stdout=subprocess.PIPE)
    # ffmpeg_cmd = [r"C:\C36\ver4_deepl\bin\ffmpeg.exe", "-i", "pipe:0", "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", "pipe:1"]
    ffmpeg_cmd = ["ffmpeg", "-i", "pipe:0", "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", "pipe:1"]
    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=stream_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    
    sample_rate=16000; sample_width=2; channels=1; chunk_duration=3
    chunk_size = sample_rate * sample_width * channels * chunk_duration
    buffer = b""

    while transcribe_running:
        chunk = ffmpeg_proc.stdout.read(chunk_size)
        if not chunk: break
        buffer += chunk

        if len(buffer) >= chunk_size:
            audio_chunk_raw = buffer[:chunk_size]
            buffer = buffer[chunk_size:]
            time_elapsed += chunk_duration
            
            try:
                # 音声データをNumpy配列に変換
                audio_np = np.frombuffer(audio_chunk_raw, dtype=np.int16).astype(np.float32) / 32768.0
                
                result = model.transcribe(audio_np, language="en", fp16=False)
                en_text = result.get("text", "").strip()
                
                if en_text:
                    print(f"📝 EN: {en_text}")
                    
                    if not analysis_complete:
                        initial_transcripts.append(en_text)
                        initial_audio_chunks.append(audio_np) # 音声データもバッファリング
                        
                        if time_elapsed >= ANALYSIS_BUFFER_SECONDS:
                            analysis_complete = True
                            
                            # 分析とプロンプト更新をバックグラウンドで実行
                            def analysis_task():
                                text_for_analysis = " ".join(initial_transcripts)
                                
                                # 3つの分析を並行して実行
                                category = analyze_content_category(text_for_analysis)
                                gender = analyze_voice_gender(initial_audio_chunks, sample_rate)
                                personality = "unknown"
                                if category in ["gaming", "casual_conversation"]:
                                    personality = analyze_personality(text_for_analysis)
                                
                                # 最終的なプロンプトを生成
                                new_prompt = generate_dynamic_prompt(category, gender, personality)
                                globals()['current_system_prompt'] = new_prompt

                                # フロントエンドに分析結果を通知
                                socketio.emit("analysis_update", {"category": category, "gender": gender, "personality": personality})
                            
                            socketio.start_background_task(analysis_task)

                    # 現在のプロンプトで翻訳を実行
                    active_prompt = globals().get('current_system_prompt', BASE_PROMPT_STYLES["default"])
                    ja_text = translate_with_chatgpt(en_text, system_prompt=active_prompt)
                    print(f"🌐 JP: {ja_text}")
                    socketio.emit("new_text", {"en": en_text, "ja": ja_text})
                    
            except Exception as e:
                print(f"❌ メインループエラー: {e}")

    stream_proc.kill(); ffmpeg_proc.kill()
    print("🛑 停止しました")

#(ローカルの場合はコメントアウトを外す)
# if __name__ == "__main__":
#     socketio.run(app, debug=True, allow_unsafe_werkzeug=True)