#!/usr/bin/env bash
# exit on error
set -o errexit

# 1. Pythonライブラリのインストール
pip install -r requirements.txt

# 2. ffmpeg と streamlink を管理者権限でインストール
echo "Installing system dependencies with sudo: ffmpeg and streamlink..."
sudo apt-get install -y ffmpeg streamlink
echo "System dependencies installed successfully."