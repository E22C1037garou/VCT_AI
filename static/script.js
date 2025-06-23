document.addEventListener('DOMContentLoaded', () => {
    // --- 要素取得 ---
    const socket = io();
    const startForm = document.getElementById('startForm');
    const urlInput = document.getElementById('urlInput');
    const stopButton = document.getElementById('stopButton');
    const videoFrame = document.getElementById('videoFrame');
    const subtitleOutput = document.getElementById('subtitle_output');
    const hamburger = document.querySelector('.hamburger');
    const nav = document.querySelector('.nav');

    // --- 設定用UI要素 ---
    const promptStyleSelect = document.getElementById('prompt_style');
    const subtitleSizeSelect = document.getElementById('subtitle_size');
    const subtitleColorSelect = document.getElementById('subtitle_color');
    const subtitleLangSelect = document.getElementById('subtitle_lang');

    let currentEn = '';
    let currentJa = '';

    // --- ハンバーガーメニューのロジック ---
    if (hamburger && nav) {
        hamburger.addEventListener('click', () => {
            hamburger.classList.toggle('active');
            nav.classList.toggle('active');
            const isOpen = hamburger.classList.contains('active');
            hamburger.setAttribute('aria-expanded', isOpen);
            nav.setAttribute('aria-hidden', !isOpen);
        });
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.nav') && !e.target.closest('.hamburger') && nav.classList.contains('active')) {
                hamburger.classList.remove('active');
                nav.classList.remove('active');
                hamburger.setAttribute('aria-expanded', false);
                nav.setAttribute('aria-hidden', true);
            }
        });
    }

    // --- 字幕表示を更新する関数 ---
    const updateSubtitleDisplay = () => {
        const selectedLang = subtitleLangSelect.value;
        subtitleOutput.textContent = selectedLang === 'ja' ? currentJa : currentEn;
        subtitleOutput.style.fontSize = subtitleSizeSelect.value;
        subtitleOutput.style.color = subtitleColorSelect.value;
    };

    // --- Socket.IOイベントリスナー ---
    socket.on('new_subtitle', (data) => {
        currentEn = data.en;
        currentJa = data.ja;
        updateSubtitleDisplay();
    });

    // --- フォームとボタンのイベントリスナー ---
    startForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const url = urlInput.value.trim();
        if (!url) return alert("URLを入力してください。");

        // 埋め込みURLを生成
        let embedUrl = url;
        if (url.includes('youtube.com') || url.includes('youtu.be')) {
            const videoId = url.match(/(?:v=|\/)([a-zA-Z0-9_-]{11})/).pop();
            if (videoId) embedUrl = `https://www.youtube.com/embed/${videoId}?autoplay=1`;
        } else if (url.includes('twitch.tv')) {
            const channel = url.match(/twitch\.tv\/([^\/]+)/).pop();
            if (channel) embedUrl = `https://player.twitch.tv/?channel=${channel}&parent=${window.location.hostname}&autoplay=true&muted=true`;
        }
        videoFrame.src = embedUrl;

        // フォームデータを取得してサーバーに送信
        const formData = new FormData(startForm);
        fetch('/start', { method: 'POST', body: formData });

        // 字幕をクリア
        currentEn = '';
        currentJa = '';
        updateSubtitleDisplay();
    });

    stopButton.addEventListener('click', () => {
        videoFrame.src = "about:blank";
        fetch('/stop', { method: 'POST' });
        currentEn = '';
        currentJa = '翻訳を停止しました';
        updateSubtitleDisplay();
    });
    
    // --- 設定変更のイベントリスナー ---
    subtitleSizeSelect.addEventListener('change', updateSubtitleDisplay);
    subtitleColorSelect.addEventListener('change', updateSubtitleDisplay);
    subtitleLangSelect.addEventListener('change', updateSubtitleDisplay);

    // --- 初期化 ---
    updateSubtitleDisplay(); // ページロード時に初期スタイルを適用
});