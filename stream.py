import os
import subprocess
import io
import wave
import collections
import numpy as np
import threading
import tempfile
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
import openai
# Streamlinkをライブラリとしてインポート
from streamlink import Streamlink, NoPluginError, PluginError

# .envファイルを読み込み
load_dotenv()

# APIキーとエンドポイントを変数として保持
AZURE_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT_URL = os.getenv("ENDPOINT_URL")
AZURE_DEPLOYMENT_NAME = os.getenv("DEPLOYMENT_NAME")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AZURE_API_VERSION = "2023-05-15"

# プロンプト定義
PROMPT_STYLES = {
    "serious": "Translate formally and accurately.",
    "casual": "Translate in a natural, casual style. Feel free to use appropriate emojis.",
    "humorous": "Translate with a sense of humor, using witty language where appropriate.",
    "expert": "Translate like an expert in the field, using precise technical terms."
}
PROMPT_RULE = (
    "\n**[IMPORTANT RULES]**\n"
    "1. Never output translations for anything other than the instructed last line.\n"
    "2. It is strictly forbidden to add information not present in the original text or to create new sentences.\n"
    "3. If the last line is untranslatable noise or meaningless words, you **must** return only an empty string without apologies or explanations."
)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a_super_secret_key')
socketio = SocketIO(app, cors_allowed_origins="*")

transcribe_running = False
client_settings = {}

def transcribe_audio_with_api(audio_chunk):
    if np.abs(np.frombuffer(audio_chunk, dtype=np.int16)).max() < 100:
        return ""
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
        wf.writeframes(audio_chunk)
    wav_buffer.seek(0)
    try:
        transcript = openai.Audio.transcribe(
            model="whisper-1", file=wav_buffer, file_name="audio.wav", api_key=OPENAI_API_KEY
        )
        return transcript["text"].strip()
    except Exception as e:
        print(f"❌ Whisper API エラー: {e}"); return ""

def detect_language_of_text(text):
    try:
        response = openai.ChatCompletion.create(
            engine=AZURE_DEPLOYMENT_NAME, api_key=AZURE_API_KEY, api_base=AZURE_ENDPOINT_URL,
            api_type="azure", api_version=AZURE_API_VERSION,
            messages=[
                {"role": "system", "content": "You are a language detection expert..."},
                {"role": "user", "content": text}
            ],
            temperature=0, max_tokens=5
        )
        return response["choices"][0]["message"]["content"].strip().lower()
    except Exception as e:
        print(f"❌ 言語検出AIエラー: {e}"); return "unknown"

def generate_dynamic_prompt(source_lang, target_lang, style):
    lang_map = {"ja": "Japanese", "en": "English", "ko": "Korean", "zh": "Chinese"}
    source_name = lang_map.get(source_lang, source_lang)
    target_name = lang_map.get(target_lang, target_lang)
    style_instruction = PROMPT_STYLES.get(style, PROMPT_STYLES["serious"])
    system_prompt = (f"You are a professional interpreter... Translate it {style_instruction}")
    return system_prompt + PROMPT_RULE

def translate_with_chatgpt(context_text, source_lang, target_lang, style):
    system_prompt = generate_dynamic_prompt(source_lang, target_lang, style)
    try:
        response = openai.ChatCompletion.create(
            engine=AZURE_DEPLOYMENT_NAME, api_key=AZURE_API_KEY, api_base=AZURE_ENDPOINT_URL,
            api_type="azure", api_version=AZURE_API_VERSION,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": context_text}],
            temperature=0.1, max_tokens=150
        )
        content = response["choices"][0]["message"]["content"].strip()
        if "I'm sorry" in content or "cannot" in content or "申し訳ありません" in content: return ""
        return content
    except Exception as e: print(f"❌ 翻訳AIエラー: {e}"); return ""

def pipe_stream_to_ffmpeg(stream_fd, ffmpeg_proc):
    """Streamlinkからのデータをffmpegに中継する関数"""
    try:
        while transcribe_running:
            chunk = stream_fd.read(4096)
            if not chunk:
                break
            ffmpeg_proc.stdin.write(chunk)
    except Exception as e:
        print(f"ERROR: Pipe stream failed: {e}")
    finally:
        print("INFO: Closing stream pipe to ffmpeg.")
        stream_fd.close()
        ffmpeg_proc.stdin.close()

def log_pipe(pipe, log_prefix):
    """サブプロセスの標準エラー出力を読み取り、ログに出力する関数"""
    try:
        for line in iter(pipe.readline, b''):
            print(f"[{log_prefix}] {line.decode('utf-8', errors='ignore').strip()}", flush=True)
    finally:
        pipe.close()

def transcribe_loop(url):
    global transcribe_running
    print("🔁 リアルタイム文字起こし開始 (yt-dlp モード)")

    # 変更点: streamlinkの代わりにyt-dlpを使用
    # -q: 進行状況などのメッセージを非表示に
    # -f ba: bestaudio (最適な音声のみ) を選択
    # -o -: 標準出力にデータを書き出す
    yt_dlp_cmd = [
        "yt-dlp",
        "--quiet",
        "-f", "ba",
        "-o", "-",
        url
    ]
    
    yt_dlp_proc = subprocess.Popen(yt_dlp_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    ffmpeg_cmd = ["ffmpeg", "-i", "pipe:0", "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", "pipe:1"]
    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=yt_dlp_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # yt-dlpとffmpegからのエラーをログに出力するためのスレッド
    threading.Thread(target=log_pipe, args=(yt_dlp_proc.stderr, "YT-DLP_ERR"), daemon=True).start()
    threading.Thread(target=log_pipe, args=(ffmpeg_proc.stderr, "FFMPEG_ERR"), daemon=True).start()

    context_buffer = collections.deque(maxlen=3)
    chunk_duration = 4
    chunk_size = 16000 * 2 * 1 * chunk_duration

    while transcribe_running:
        audio_chunk_raw = ffmpeg_proc.stdout.read(chunk_size)
        if not audio_chunk_raw:
            print("INFO: ffmpeg stream ended. Exiting loop.")
            break
        try:
            source_text = transcribe_audio_with_api(audio_chunk_raw)
            if not source_text:
                continue

            detected_lang = detect_language_of_text(source_text)
            print(f"📝 {detected_lang.upper()}: {source_text}")
            
            context_for_api = "\n".join(context_buffer)
            context_buffer.append(source_text) # 順番を修正

            for sid, settings in client_settings.copy().items():
                target_lang = settings.get('target_lang', 'ja')
                style = settings.get('style', 'serious')
                translated_text = source_text if detected_lang == target_lang else translate_with_chatgpt(context_for_api, detected_lang, target_lang, style)
                if translated_text and translated_text.strip():
                    socketio.emit("new_subtitle", {"original": source_text, "translated": translated_text}, room=sid)
        except Exception as e:
            print(f"❌ メインループエラー: {e}")

    if yt_dlp_proc.poll() is None: yt_dlp_proc.kill()
    if ffmpeg_proc.poll() is None: ffmpeg_proc.kill()
    transcribe_running = False
    print("🛑 停止しました")