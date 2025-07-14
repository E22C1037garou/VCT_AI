# 1. ベースとなる公式Pythonイメージを選択
FROM python:3.10-slim

# 2. FFmpegをインストール（Whisperでの音声処理に必須）
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 3. アプリケーションを配置する作業ディレクトリを設定
WORKDIR /app

# 4. 最初にrequirements.txtをコピーしてライブラリをインストール
#    （このファイルを変更しない限り、再ビルドが高速になります）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. アプリケーションの全コードを作業ディレクトリにコピー
COPY . .

# 6. アプリケーションを起動するコマンドを設定
#    Renderは自動的にPORT環境変数を設定してくれます
#    ここでは、app.pyというファイル内の「app」という名前のFlaskインスタンスを起動する想定です
CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "app:app"]