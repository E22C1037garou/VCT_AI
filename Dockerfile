# 1. ベースとなるOSとPythonのバージョンを指定
# Python 3.11 がプリインストールされた軽量なDebian OSイメージを使います
FROM python:3.11-slim

# 2. システムのパッケージリストを更新し、必要なツールをインストール
# この命令は 'root' ユーザーとして実行されるため、sudoは不要です
RUN apt-get update && apt-get install -y \
    ffmpeg \
    streamlink \
    && rm -rf /var/lib/apt/lists/*

# 3. アプリケーション用の作業ディレクトリを作成
WORKDIR /app

# 4. requirements.txtをコピーして、Pythonライブラリをインストール
# 先にこれだけをインストールすることで、アプリのコードを変更した際のビルドが高速化します
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. アプリケーションの全ファイルをコピー
COPY . .

# 6. Renderが使用するポート番号を指定 (Renderが自動で設定する$PORTを使います)
EXPOSE 10000

# 7. アプリケーションの起動コマンド
# Gunicornを使って、Socket.IO対応のワーカーでアプリを起動します
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--threads", "100", "--timeout", "120", "--bind", "0.0.0.0:10000", "stream:app"]