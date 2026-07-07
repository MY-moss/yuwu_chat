// ============================================================
// 文件: api.js | 职责: API调用层（JSON/SSE流式）、CSRF Token管理
// ============================================================
import { state } from './state.js';
import { toast, showAuthScreen } from './utils.js';

export function getCsrfToken() {
    return state.csrfToken;
}

export function setCsrfToken(token) {
    state.csrfToken = token || '';
}

export async function fetchCsrfToken() {
    try {
        const res = await fetch('/api/csrf-token', { credentials: 'include' });
        const data = await res.json();
        state.csrfToken = data.csrf_token || '';
    } catch (e) {
        toast('安全令牌获取失败，部分功能可能不可用', 'warn');
        console.error('[ERROR] fetchCsrfToken:', e);
    }
}

export async function api(url, opts = {}) {
    const headers = { 'Content-Type': 'application/json' };
    if (state.csrfToken) {
        headers['X-CSRF-Token'] = state.csrfToken;
    }
    // [AUDIT-X04] ...opts 可覆盖 headers（含 CSRF Token），应 headers: { ...headers, ...opts.headers }
    const res = await fetch(url, {
        headers,
        credentials: 'include',
        ...opts
    });
    let data;
    try {
        data = await res.json();
    } catch (e) {
        console.error('[ERROR] api() failed to parse JSON:', e);
        if (res.status === 401 || res.status === 302) {
            state.currentUser = null;
            showAuthScreen();
            throw new Error('未登录');
        }
        return { error: '服务器响应格式错误' };
    }
    if (data.error === '未登录') {
        state.currentUser = null;
        showAuthScreen();
        throw new Error('未登录');
    }
    return data;
}

export async function apiStream(url, opts = {}) {
    const headers = { 'Content-Type': 'application/json' };
    if (state.csrfToken) {
        headers['X-CSRF-Token'] = state.csrfToken;
    }
    const res = await fetch(url, {
        headers,
        credentials: 'include',
        ...opts
    });
    if (!res.ok) {
        if (res.status === 401) {
            state.currentUser = null;
            showAuthScreen();
            throw new Error('未登录');
        }
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }
    return res;
}

// ===== END OF FILE =====
