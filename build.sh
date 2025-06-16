#!/usr/bin/env bash
# exit on error
set -o errexit

# 1. Pythonライブラリのインストール
pip install -r requirements.txt

# 2. ffmpeg と streamlink を直接インストール
echo "Installing system dependencies: ffmpeg and streamlink..."
apt-get install -y ffmpeg streamlink
echo "System dependencies installed successfully."