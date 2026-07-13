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

let _csrfRetryCount = 0;

async function _handleCsrfFailure(url, opts) {
    if (_csrfRetryCount >= 2) {
        _csrfRetryCount = 0;
        toast('登录状态已过期，请重新登录', 'error');
        state.currentUser = null;
        showAuthScreen();
        throw new Error('CSRF 重试失败');
    }
    _csrfRetryCount++;
    await fetchCsrfToken();
    return api(url, opts);
}

let _authRefreshInProgress = false;

async function _tryRefreshAuth() {
    if (_authRefreshInProgress) {
        await new Promise(r => setTimeout(r, 200));
        return !!state.currentUser;
    }
    _authRefreshInProgress = true;
    try {
        await fetchCsrfToken();
        const res = await fetch('/api/auth/me', { credentials: 'include' });
        if (res.ok) {
            const data = await res.json();
            state.currentUser = data;
            return true;
        }
    } catch (e) {
        console.debug('[DEBUG] _tryRefreshAuth failed:', e);
    } finally {
        _authRefreshInProgress = false;
    }
    return false;
}

export async function api(url, opts = {}) {
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    if (state.csrfToken) {
        headers['X-CSRF-Token'] = state.csrfToken;
    }
    try {
        const res = await fetch(url, {
            ...opts,
            headers,
            credentials: 'include'
        });
        let data;
        try {
            data = await res.json();
        } catch (e) {
            console.error('[ERROR] api() failed to parse JSON:', e);
            if (res.status === 401 || res.status === 302) {
                if (state.currentUser && await _tryRefreshAuth()) {
                    return api(url, opts);
                }
                state.currentUser = null;
                showAuthScreen();
                throw new Error('未登录');
            }
            if (res.status === 403) {
                return _handleCsrfFailure(url, opts);
            }
            return { error: '服务器响应格式错误' };
        }
        if (data.error === '未登录') {
            if (state.currentUser && await _tryRefreshAuth()) {
                return api(url, opts);
            }
            state.currentUser = null;
            showAuthScreen();
            throw new Error('未登录');
        }
        if (data.error === 'CSRF token invalid') {
            return _handleCsrfFailure(url, opts);
        }
        _csrfRetryCount = 0;
        return data;
    } catch (e) {
        if (e.message === 'Failed to fetch') {
            toast('网络连接失败，请检查网络', 'error');
            throw new Error('网络错误');
        }
        throw e;
    }
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
            if (state.currentUser && await _tryRefreshAuth()) {
                return apiStream(url, opts);
            }
            state.currentUser = null;
            showAuthScreen();
            throw new Error('未登录');
        }
        if (res.status === 403) {
            if (_csrfRetryCount >= 2) {
                _csrfRetryCount = 0;
                toast('登录状态已过期，请重新登录', 'error');
                state.currentUser = null;
                showAuthScreen();
                throw new Error('CSRF 重试失败');
            }
            _csrfRetryCount++;
            await fetchCsrfToken();
            return apiStream(url, opts);
        }
        _csrfRetryCount = 0;
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }
    _csrfRetryCount = 0;
    return res;
}

export function startSessionHeartbeat() {
    if (state._heartbeatInterval) return;
    state._heartbeatInterval = setInterval(async () => {
        if (!state.currentUser) return;
        try {
            await fetch('/api/auth/ping', {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': state.csrfToken || ''
                }
            });
        } catch (e) {
            console.debug('[DEBUG] Heartbeat failed, session may have expired');
        }
    }, 300000);
}

export function stopSessionHeartbeat() {
    if (state._heartbeatInterval) {
        clearInterval(state._heartbeatInterval);
        state._heartbeatInterval = null;
    }
}

// ===== END OF FILE =====
