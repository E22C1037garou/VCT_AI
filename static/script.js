document.addEventListener('DOMContentLoaded', () => {
    // サーバーとの接続を確立
    const socket = io();

    // HTML要素の取得
    const startForm = document.getElementById("startForm");
    const urlInput = document.getElementById("urlInput");
    const stopButton = document.getElementById("stopButton");
    const videoFrame = document.getElementById("videoFrame");
    const enOutput = document.getElementById("en_output");
    const jaOutput = document.getElementById("ja_output");

    // AI分析結果を表示するための要素
    const categoryEl = document.getElementById("category");
    const genderEl = document.getElementById("gender");
    const personalityEl = document.getElementById("personality");

    // サーバーから新しい字幕テキストデータを受信するイベント
    socket.on("new_text", function (data) {
        if(enOutput) {
            enOutput.innerHTML += `<p>${data.en}</p>`;
            // 自動で一番下までスクロール
            enOutput.parentElement.scrollTop = enOutput.parentElement.scrollHeight;
        }
        if(jaOutput) {
            jaOutput.innerHTML += `<p>${data.ja}</p>`;
            // 自動で一番下までスクロール
            jaOutput.parentElement.scrollTop = jaOutput.parentElement.scrollHeight;
        }
    });

    // サーバーからAIの分析結果を受信するイベント
    socket.on("analysis_update", function (data) {
        console.log("Analysis Result Received:", data);
        if(categoryEl) categoryEl.textContent = `カテゴリ: ${data.category || 'N/A'}`;
        if(genderEl) genderEl.textContent = `声質: ${data.gender || 'N/A'}`;
        if(personalityEl) personalityEl.textContent = `性格: ${data.personality || 'N/A'}`;
    });

    // YouTubeの動画IDをURLから抽出する関数
    function getYouTubeVideoId(url) {
        const regex = /(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})/;
        const matches = url.match(regex);
        return matches ? matches[1] : null;
    }

    // Twitchのチャンネル名をURLから抽出する関数
    function getTwitchChannelName(url) {
        const regex = /(?:https?:\/\/)?(?:www\.)?twitch\.tv\/([^\/\n\s]+)/;
        const matches = url.match(regex);
        return matches ? matches[1] : null;
    }
    
    // 「開始」ボタンが押されたときの処理
    if (startForm) {
        startForm.addEventListener("submit", function (event) {
            // フォームのデフォルトの送信動作をキャンセル
            event.preventDefault();

            // UIを初期状態にリセット
            if(categoryEl) categoryEl.textContent = "カテゴリ: 分析中...";
            if(genderEl) genderEl.textContent = "声質: 分析中...";
            if(personalityEl) personalityEl.textContent = "性格: 分析中...";
            if(enOutput) enOutput.innerHTML = "";
            if(jaOutput) jaOutput.innerHTML = "";
            
            const url = urlInput.value.trim();
            if (!url) {
                alert("URLを入力してください。");
                return;
            }
            
            // サーバーに文字起こし開始のリクエストを送信
            const formData = new FormData();
            formData.append('stream_url', url);
    
            fetch("/start", {
                method: "POST",
                body: formData
            }).then(response => response.text()).then(console.log);
    
            // 動画プレイヤーの埋め込み処理
            let embedUrl = '';
            if (url.includes("youtube.com") || url.includes("youtu.be")) {
                const videoId = getYouTubeVideoId(url);
                if (videoId) {
                    embedUrl = `https://www.youtube.com/embed/${videoId}?autoplay=1`;
                }
            } else if (url.includes("twitch.tv")) {
                const channelName = getTwitchChannelName(url);
                if (channelName) {
                    // 'localhost'の部分は、もし別のドメインで実行する場合はそのドメイン名に変更
                    embedUrl = `https://player.twitch.tv/?channel=${channelName}&parent=localhost&autoplay=true&muted=true`;
                }
            }
    
            if (embedUrl) {
                videoFrame.src = embedUrl;
                videoFrame.style.display = "block";
            } else {
                alert("対応しているYouTubeまたはTwitchのURLを入力してください。");
            }
        });
    }

    // 「停止」ボタンが押されたときの処理
    if (stopButton) {
        stopButton.addEventListener("click", function () {
            // サーバーに停止リクエストを送信
            fetch("/stop", { method: "POST" })
                .then(response => response.text()).then(console.log);
            
            // 動画プレイヤーと字幕をクリア
            videoFrame.src = "";
            videoFrame.style.display = "none";
            urlInput.value = "";
        });
    }
});