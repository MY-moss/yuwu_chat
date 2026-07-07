// ============================================================
// 文件: utils.js | 职责: 通用工具函数、DOM辅助、Loading、Toast
// ============================================================
import { state } from './state.js';

const HTML_ENTITY = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function $(id) {
    return document.getElementById(id);
}

export function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => HTML_ENTITY[c]);
}

export function formatDate(isoString) {
    if (!isoString) return '';
    try {
        const d = new Date(isoString);
        return d.toLocaleString('zh-CN', {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit'
        });
    } catch {
        return isoString;
    }
}

export function formatTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    const now = new Date();
    const diff = now - d;
    if (diff < 60000) return '刚刚';
    if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前';
    if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前';
    return d.toLocaleDateString('zh-CN');
}

export function toast(msg, type) {
    const c = document.getElementById('toastContainer');
    if (!c) return;
    const d = document.createElement('div');
    d.className = 'toast ' + (type || 'info');
    d.textContent = msg;
    c.appendChild(d);
    setTimeout(() => d.classList.add('show'), 10);
    setTimeout(() => { d.classList.remove('show'); setTimeout(() => d.remove(), 300); }, 3500);
}

export function showLoading(text, sub) {
    const loadingText = $('loadingText');
    const loadingSub = $('loadingSub');
    const loadingOverlay = $('loadingOverlay');
    if (!loadingOverlay) return;
    if (loadingText) loadingText.textContent = text || 'AI 正在编织故事...';
    if (loadingSub) loadingSub.textContent = sub || '请稍候';
    loadingOverlay.classList.add('show');
    const bar = $('loadingBarInner');
    if (bar) { bar.style.animation = 'none'; bar.style.width = '0%'; }
    const pct = $('loadingPct');
    if (pct) pct.textContent = '0%';
    const loadingStatus = $('loadingStatus');
    if (loadingStatus) loadingStatus.textContent = '';
}

export function hideLoading() {
    const loadingOverlay = $('loadingOverlay');
    if (loadingOverlay) loadingOverlay.classList.remove('show');
}

export function updateProgress(pct, label) {
    const bar = $('loadingBarInner');
    if (bar) bar.style.width = Math.min(100, pct) + '%';
    const pctEl = $('loadingPct');
    if (pctEl) pctEl.textContent = (label || Math.round(pct) + '%');
}

export function updateLoadingStatus(text) {
    const loadingStatus = $('loadingStatus');
    if (loadingStatus) loadingStatus.textContent = text || '';
}

export function showAuthScreen() {
    const authScreen = $('authScreen');
    const mainScreen = $('mainScreen');
    if (authScreen) authScreen.style.display = 'flex';
    if (mainScreen) mainScreen.style.display = 'none';
}

export function updateUserInfo() {
    if (!state.currentUser) return;
    const creditsEl = $('creditsDisplay');
    const usernameEl = $('usernameDisplay');
    const adminBtn = $('adminBtn');
    const dashboardBtn = $('dashboardBtn');
    if (creditsEl) creditsEl.textContent = `💰 ${state.currentUser.credits}`;
    if (usernameEl) usernameEl.textContent = state.currentUser.username;
    if (adminBtn) adminBtn.style.display = state.currentUser.role === 'admin' ? 'block' : 'none';
    if (dashboardBtn) dashboardBtn.style.display = state.currentUser.role === 'admin' ? 'block' : 'none';
    updateFreeModeDisplay(state.currentUser.has_personal_api);
}

export function updateFreeModeDisplay(hasApi) {
    const display = $('freeModeDisplay');
    if (display) display.style.display = hasApi ? 'inline' : 'none';
}

export function setManagedInterval(fn, ms) {
    const id = setInterval(fn, ms);
    state._timers.add(id);
    return id;
}

export function clearManagedTimer(id) {
    if (id) { clearInterval(id); state._timers.delete(id); }
}

export function getSelectedModel() {
    const sel = $('modelSelect');
    return sel ? sel.value : 'mimo-v2.5-free';
}

// ===== END OF FILE =====
