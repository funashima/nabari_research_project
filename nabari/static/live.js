"use strict";
(() => {
  const root = document.documentElement;
  const get = key => { try { return localStorage.getItem('nabari-live-' + key); } catch { return null; } };
  const save = (key, value) => { try { localStorage.setItem('nabari-live-' + key, value); } catch {} };
  function size(value) {
    root.dataset.size = ['normal', 'large', 'largest'].includes(value) ? value : 'normal';
    document.querySelectorAll('[data-size-button]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.sizeButton === root.dataset.size)));
  }
  function contrast(value) {
    root.classList.toggle('high', value);
    document.getElementById('contrast')?.setAttribute('aria-pressed', String(value));
  }
  size(get('size')); contrast(get('contrast') === 'true');
  document.querySelectorAll('[data-size-button]').forEach(b => b.addEventListener('click', () => { size(b.dataset.sizeButton); save('size', b.dataset.sizeButton); }));
  document.getElementById('contrast')?.addEventListener('click', () => { const next = !root.classList.contains('high'); contrast(next); save('contrast', String(next)); });
  const status = text => { const el = document.getElementById('speech-status'); if (el) el.textContent = text; };
  document.getElementById('speak')?.addEventListener('click', () => {
    if (!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) { status('この環境では読み上げを利用できません。'); return; }
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(document.querySelector('.detail h1').textContent + '。' + document.getElementById('read-content').textContent);
    utterance.lang = 'ja-JP'; utterance.rate = 0.9;
    utterance.onend = () => status('読み上げが終わりました。');
    utterance.onerror = () => status('読み上げを利用できませんでした。');
    speechSynthesis.speak(utterance); status('読み上げています。');
  });
  document.getElementById('stop-speak')?.addEventListener('click', () => { window.speechSynthesis?.cancel(); status('読み上げを停止しました。'); });
  document.getElementById('print')?.addEventListener('click', () => window.print());
  window.addEventListener('pagehide', () => window.speechSynthesis?.cancel());
})();
