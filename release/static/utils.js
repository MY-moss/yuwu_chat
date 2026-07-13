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
    state.isSending = false;
    state.isSwitchingMode = false;
    state.isSwitchingAgent = false;
    state._rpgRequestActive = false;
    if (state.rpgAbortController) {
        state.rpgAbortController.abort();
        state.rpgAbortController = null;
    }
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

// ============================================================
// UI 美化增强：数字滚动动画 + 打字机效果（源自方案五）
// 动画工具函数放在 utils.js，renderer.js 负责渲染调用，保持模块职责清晰
// 关键设计决策：
// - requestAnimationFrame + easeOutCubic 缓动（AnimatedCounter）
// - setTimeout 链式而非 setInterval，避免标签页失焦后堆积（Typewriter）
// - 中文按字切分：[...text] 展开 Unicode 码点
// - 所有动效均尊重 prefers-reduced-motion，降级为直接显示终值
// ============================================================

const _prefersReducedMotion = () =>
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function _easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
}

/**
 * 数字滚动动画：从 0 平滑增长到目标值
 * @param {HTMLElement} el - 目标元素
 * @param {number} target - 目标数值
 * @param {object} [opts] - { duration=1.5s, prefix='', suffix='', decimals=0, useComma=false }
 */
export function animateCounter(el, target, opts = {}) {
    if (!el) return;
    const { duration = 1500, prefix = '', suffix = '', decimals = 0, useComma = false } = opts;

    const format = (val) => {
        const fixed = Number(val).toFixed(decimals);
        const display = useComma ? Number(fixed).toLocaleString('en-US', {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals
        }) : fixed;
        return prefix + display + suffix;
    };

    if (_prefersReducedMotion()) {
        el.textContent = format(target);
        return;
    }

    const start = performance.now();
    const step = (now) => {
        const elapsed = now - start;
        const progress = Math.min(elapsed / duration, 1);
        const eased = _easeOutCubic(progress);
        el.textContent = format(target * eased);
        if (progress < 1) {
            requestAnimationFrame(step);
        } else {
            el.textContent = format(target);
        }
    };
    requestAnimationFrame(step);
}

/**
 * 自动扫描带 data-count 属性的元素，滚动进入视口时触发数字动画
 * 用法: <span data-count="500" data-suffix="K+">0</span>
 */
export function initCounters() {
    const els = document.querySelectorAll('[data-count]');
    if (!els.length) return;

    if (_prefersReducedMotion() || !('IntersectionObserver' in window)) {
        els.forEach(el => {
            const target = parseFloat(el.dataset.count) || 0;
            animateCounter(el, target, {
                suffix: el.dataset.suffix || '',
                prefix: el.dataset.prefix || '',
                decimals: parseInt(el.dataset.decimals) || 0,
                useComma: el.dataset.comma === 'true'
            });
        });
        return;
    }

    const observer = new IntersectionObserver((entries, obs) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const el = entry.target;
                const target = parseFloat(el.dataset.count) || 0;
                animateCounter(el, target, {
                    suffix: el.dataset.suffix || '',
                    prefix: el.dataset.prefix || '',
                    decimals: parseInt(el.dataset.decimals) || 0,
                    useComma: el.dataset.comma === 'true'
                });
                obs.unobserve(el);
            }
        });
    }, { threshold: 0.5 });

    els.forEach(el => observer.observe(el));
}

/**
 * 打字机效果：逐字符揭示文本
 * @param {HTMLElement} el - 目标元素
 * @param {string} text - 要显示的文本
 * @param {object} [opts] - { speed=50ms, delay=0, cursor=true, onComplete }
 * @returns {Function} cancel 函数，调用可中断动画
 */
export function typewriter(el, text, opts = {}) {
    if (!el) return () => {};
    const { speed = 50, delay = 0, cursor = false, onComplete = null } = opts;

    if (_prefersReducedMotion()) {
        el.textContent = text;
        if (onComplete) onComplete();
        return () => {};
    }

    const chars = [...text];
    let index = 0;
    let cancelled = false;
    let timerId = null;

    el.textContent = '';
    if (cursor) el.classList.add('tw-cursor');

    const reveal = () => {
        if (cancelled) return;
        if (index < chars.length) {
            el.textContent += chars[index];
            index++;
            timerId = setTimeout(reveal, speed);
        } else {
            if (cursor) el.classList.remove('tw-cursor');
            if (onComplete) onComplete();
        }
    };

    timerId = setTimeout(reveal, delay);

    return () => {
        cancelled = true;
        if (timerId) clearTimeout(timerId);
        if (cursor) el.classList.remove('tw-cursor');
    };
}

// ===== END OF FILE =====
