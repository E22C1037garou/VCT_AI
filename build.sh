#!/usr/bin/env bash
# exit on error
set -o errexit

# 1. Pythonライブラリのインストール
pip install -r requirements.txt

# 2. OSのパッケージリストを更新
apt-get update

# 3. ffmpeg と streamlink をインストール
# -y フラグは、インストールの確認プロンプトに自動で 'yes' と答えるためのものです
apt-get install -y ffmpeg streamlink