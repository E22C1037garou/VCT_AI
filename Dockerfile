# 1. ベースとなるOSとPythonのバージョンを指定
FROM python:3.11-slim

# 2. システムのパッケージリストを更新し、必要なツールをインストール
RUN apt-get update && apt-get install -y \
    ffmpeg \
    streamlink \
    && rm -rf /var/lib/apt/lists/*

# 3. アプリケーション用の作業ディレクトリを作成
WORKDIR /app

# 4. requirements.txtをコピーして、Pythonライブラリをインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. アプリケーションの全ファイルをコピー
COPY . .

# 6. Renderが使用するポート番号を指定
EXPOSE 10000

# 7. アプリケーションの起動コマンド
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--threads", "100", "--timeout", "120", "--bind", "0.0.0.0:10000", "stream:app"]