document.addEventListener('DOMContentLoaded', () => {
    // --- 要素取得 ---
    const socket = io();
    const startForm = document.getElementById('startForm');
    const urlInput = document.getElementById('url');
    const stopBtn = document.getElementById('stopBtn');
    const videoFrame = document.getElementById('video-frame');
    const subtitleText = document.getElementById('subtitle-text');
    const originalHistory = document.getElementById('original-history');
    const translatedHistory = document.getElementById('translated-history');
    const hamburger = document.querySelector('.hamburger');
    const nav = document.querySelector('.nav');
    const subtitleBackgroundColorSelect = document.getElementById("subtitle_backgroundcolor");
    // --- 設定用UI要素 ---
    const promptStyleSelect = document.getElementById('prompt_style');
    const targetLangSelect = document.getElementById('subtitle_lang');  // 修正: 'target_lang' → 'subtitle_lang'（HTMLに合わせる）
    const subtitleSizeSelect = document.getElementById('subtitle-size');  // 修正: 'subtitle_size' → 'subtitle-size'（HTMLに合わせる）

    // --- 字幕データを保持する変数 ---
    let currentOriginal = '';
    let currentTranslated = '翻訳待機中...'; // 初期値を設定

    // --- ハンバーガーメニューのロジック ---
    if (hamburger && nav) {
        hamburger.addEventListener('click', () => {
            hamburger.classList.toggle('active');
            nav.classList.toggle('active');
            // 追加: aria-expanded属性の切り替え
            hamburger.setAttribute('aria-expanded', hamburger.classList.contains('active'));
        });
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.nav') && !e.target.closest('.hamburger') && nav.classList.contains('active')) {
                hamburger.classList.remove('active');
                nav.classList.remove('active');
                hamburger.setAttribute('aria-expanded', false);
            }
        });
    }

    // --- 字幕表示を更新するメイン関数 ---
    const updateSubtitleDisplay = () => {
        subtitleText.textContent = currentTranslated;
        subtitleText.style.fontSize = subtitleSizeSelect.value + "px";  // 修正: 単位(px)をつける行のみ残す
        // 削除: subtitleText.style.fontSize = subtitleSizeSelect.value;
    };

    // --- Socket.IOイベントリスナー ---
    socket.on('new_subtitle', (data) => {
        // サーバーからデータが送られてきて、かつその中身が有効な場合のみ更新する
        if (data && data.original) {
            currentOriginal = data.original;
            if (originalHistory) originalHistory.prepend(createElementWithText('p', currentOriginal));
        }
        if (data && data.translated && data.translated.trim() !== '') {
            currentTranslated = data.translated;
            if (translatedHistory) translatedHistory.prepend(createElementWithText('p', currentTranslated));
        }

        // 履歴が多すぎたら古いものから削除
        if (originalHistory && originalHistory.children.length > 50) {
            originalHistory.removeChild(originalHistory.lastChild);
            translatedHistory.removeChild(translatedHistory.lastChild);
        }
        
        updateSubtitleDisplay();
    });

    // --- フォームとボタンのイベントリスナー ---
    startForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const url = urlInput.value.trim();
        if (!url) { alert("配信URLを入力してください。"); return; }
        
        let embedUrl = url;
        try {
            if (url.includes('youtube.com') || url.includes('youtu.be')) {
                const videoIdMatch = url.match(/(?:v=|\/)([a-zA-Z0-9_-]{11})/);
                if (videoIdMatch) embedUrl = `https://www.youtube.com/embed/${videoIdMatch[1]}?autoplay=1`;
            } else if (url.includes('twitch.tv')) {
                const channelMatch = url.match(/twitch\.tv\/([^\/]+)/);
                if (channelMatch) embedUrl = `https://player.twitch.tv/?channel=${channelMatch[1]}&parent=${window.location.hostname}&autoplay=true&muted=true`;
            }
        } catch (err) { console.error("URLの解析に失敗:", err); }

        videoFrame.src = embedUrl;

        // UIリセット
        subtitleText.textContent = '翻訳を開始しています...';
        if (originalHistory) originalHistory.innerHTML = '';
        if (translatedHistory) translatedHistory.innerHTML = '';
        currentOriginal = '';
        currentTranslated = '翻訳を開始しています...';

        const formData = new FormData(startForm);
        fetch('/start', { method: 'POST', body: formData });
    });

    stopBtn.addEventListener('click', () => {
        videoFrame.src = 'about:blank';
        currentTranslated = '翻訳を停止しました。';
        updateSubtitleDisplay();
        fetch('/stop', { method: 'POST' });
    });
    
    // --- ヘルパー関数 ---
    function createElementWithText(tag, text) {
        const element = document.createElement(tag);
        element.textContent = text;
        return element;
    }

    // --- 設定変更のイベントリスナー ---
    function sendSettingsUpdate() {
        const settings = { style: promptStyleSelect.value, target_lang: targetLangSelect.value };
        socket.emit('update_settings', settings);
        console.log('設定をサーバーに送信しました:', settings);
    }
    
    promptStyleSelect.addEventListener('change', sendSettingsUpdate);
    targetLangSelect.addEventListener('change', sendSettingsUpdate);
    subtitleSizeSelect.addEventListener('change', updateSubtitleDisplay);

    /* ライトモード、ダークモードの切り替え */
    subtitleBackgroundColorSelect.addEventListener('change', function () {
        const selectedBcolorValue = this.value;

        if (selectedBcolorValue == 'white') {
            document.body.style.backgroundColor = '#fff';// 背景色を白色に
            document.querySelector('nav').style.backgroundColor = '#fff';// ハンバーガーの背景色を白色に
            document.querySelectorAll('.nav__item label').forEach(el => el.style.color = '#000');// ハンバーガーの文字の色を黒色に

        } else if (selectedBcolorValue == 'black') {
            document.body.style.backgroundColor = '#121212';// 背景色を黒色に
            document.querySelector('nav').style.backgroundColor = '#2c2c2c';// ハンバーガーの背景色
            document.querySelectorAll('.nav__item label').forEach(el => el.style.color = '#bb86fc');// ハンバーガーの文字の色を白色に
        }
    });

    // --- 初期化 ---
    updateSubtitleDisplay();
});
