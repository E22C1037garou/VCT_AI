# ベースとなる公式Pythonイメージを指定
FROM python:3.10-slim

# 依存関係のあるシステムツール (ffmpeg) をインストール
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# コンテナ内の作業ディレクトリを設定
WORKDIR /app

# requirements.txtをコンテナにコピー
COPY requirements.txt .

# requirements.txtに記載されたライブラリをインストール
RUN pip install --no-cache-dir -r requirements.txt

# プロジェクトの全てのファイルを作業ディレクトリにコピー
COPY . .

# アプリケーションの起動コマンド
# Renderは自動的にPORT環境変数を設定します
# Flask-SocketIOと連携するため、gunicornにeventletワーカーを指定します
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--bind", "0.0.0.0:${PORT:-10000}", "stream:app"]