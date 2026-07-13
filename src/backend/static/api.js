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

let _authRefreshPromise = null;

async function _tryRefreshAuth() {
    if (_authRefreshPromise) return _authRefreshPromise;
    _authRefreshPromise = (async () => {
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
        }
        return false;
    })();
    const result = await _authRefreshPromise;
    _authRefreshPromise = null;
    return result;
}

async function _doCsrfRetry(headers) {
    await fetchCsrfToken();
    headers['X-CSRF-Token'] = state.csrfToken;
}

async function _authFail() {
    state.currentUser = null;
    showAuthScreen();
    throw new Error('未登录');
}

export async function api(url, opts = {}) {
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    if (state.csrfToken) {
        headers['X-CSRF-Token'] = state.csrfToken;
    }
    for (let csrfRetry = 0; csrfRetry <= 2; csrfRetry++) {
        try {
            const res = await fetch(url, { ...opts, headers, credentials: 'include' });
            let data;
            try {
                data = await res.json();
            } catch (e) {
                console.error('[ERROR] api() failed to parse JSON:', e);
                if (res.status === 401 || res.status === 302) {
                    if (state.currentUser && await _tryRefreshAuth()) {
                        headers['X-CSRF-Token'] = state.csrfToken;
                        return api(url, opts);
                    }
                    throw await _authFail();
                }
                return { error: '服务器响应格式错误' };
            }
            if (data.error === '未登录') {
                if (state.currentUser && await _tryRefreshAuth()) {
                    headers['X-CSRF-Token'] = state.csrfToken;
                    return api(url, opts);
                }
                throw await _authFail();
            }
            if (data.error === 'CSRF token invalid') {
                if (csrfRetry >= 2) {
                    toast('登录状态已过期，请重新登录', 'error');
                    throw await _authFail();
                }
                await _doCsrfRetry(headers);
                continue;
            }
            return data;
        } catch (e) {
            if (e.message === 'Failed to fetch') {
                toast('网络连接失败，请检查网络', 'error');
                throw new Error('网络错误');
            }
            if (e.message === '未登录') throw e;
            throw e;
        }
    }
}

export async function apiStream(url, opts = {}) {
    const headers = { 'Content-Type': 'application/json' };
    if (state.csrfToken) {
        headers['X-CSRF-Token'] = state.csrfToken;
    }
    for (let csrfRetry = 0; csrfRetry <= 2; csrfRetry++) {
        const res = await fetch(url, { headers, credentials: 'include', ...opts });
        if (res.ok) return res;
        if (res.status === 401) {
            if (state.currentUser && await _tryRefreshAuth()) {
                headers['X-CSRF-Token'] = state.csrfToken;
                return apiStream(url, opts);
            }
            throw await _authFail();
        }
        if (res.status === 403) {
            let errBody;
            try {
                errBody = await res.clone().json();
            } catch (_) {
                errBody = {};
            }
            if (errBody.error === 'CSRF token invalid') {
                if (csrfRetry >= 2) {
                    toast('登录状态已过期，请重新登录', 'error');
                    throw await _authFail();
                }
                await _doCsrfRetry(headers);
                continue;
            }
            throw new Error(`HTTP 403: ${errBody.error || res.statusText}`);
        }
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }
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
