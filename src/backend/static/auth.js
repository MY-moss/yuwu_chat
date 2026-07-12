// ============================================================
// 文件: auth.js | 职责: 认证UI（登录/注册/登出/改密）、用量记录、专注模式、预览
// ============================================================
import { state } from './state.js';
import { $, toast, showAuthScreen, updateUserInfo, escapeHtml } from './utils.js';
import { api, setCsrfToken, startSessionHeartbeat, stopSessionHeartbeat } from './api.js';
import { renderMarkdown, highlightCode } from './renderer.js';
import { populateModels, loadAgents } from './chat.js';
import { loadWorlds } from './rpg.js';

export async function checkAuth() {
    try {
        const data = await api('/api/auth/me');
        state.currentUser = data;
        showMainScreen();
    } catch {
        showAuthScreen();
    }
}

export async function loadVersion() {
    try {
        const data = await api('/version');
        const verEl = $('versionDisplay');
        if (verEl) verEl.textContent = data.version || 'v1.0.0';
    } catch (e) {
        toast('版本信息加载失败', 'warn');
        console.error('[ERROR] fetchVersion:', e);
    }
}

export function showMainScreen() {
    $('authScreen').style.display = 'none';
    $('mainScreen').style.display = 'flex';
    updateUserInfo();
    populateModels();
    loadAgents();
    loadWorlds();
    document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
    document.querySelector('.mode-tab[data-mode="chat"]').classList.add('active');
    document.querySelectorAll('.mobile-tab-item[data-mode]').forEach(t => t.classList.remove('active'));
    const mobileChatTab = document.querySelector('.mobile-tab-item[data-mode="chat"]');
    if (mobileChatTab) mobileChatTab.classList.add('active');
    state.currentMode = 'chat';
    document.getElementById('chatMode').style.display = 'flex';
    document.getElementById('rpgMode').style.display = 'none';
}

async function login() {
    const username = $('loginUsername').value.trim();
    const password = $('loginPassword').value.trim();

    if (!username || !password) {
        showAuthError('请输入用户名和密码');
        return;
    }

    try {
        const data = await api('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({ username, password })
        });

        if (data.error) {
            showAuthError(data.error);
            return;
        }

        state.currentUser = data.user;
        if (data.csrf_token) setCsrfToken(data.csrf_token);
        if (data.password_reset_required) {
            state.currentUser = data.user;
            showForcePasswordChange();
            return;
        }
        showMainScreen();
        showAuthError('');
        startSessionHeartbeat();
    } catch (e) {
        showAuthError('登录失败，请重试');
        console.error('[ERROR] login:', e);
    }
}

async function register() {
    const username = $('regUsername').value.trim();
    const password = $('regPassword').value.trim();
    const password2 = $('regPassword2').value.trim();

    if (!username || !password) {
        showAuthError('请输入用户名和密码');
        return;
    }
    if (password !== password2) {
        showAuthError('两次输入的密码不一致');
        return;
    }
    if (password.length < 8) {
        showAuthError('密码长度至少8位');
        return;
    }
    if (!/[a-zA-Z]/.test(password)) {
        showAuthError('密码必须包含至少一个字母');
        return;
    }
    if (!/[0-9]/.test(password)) {
        showAuthError('密码必须包含至少一个数字');
        return;
    }

    try {
        const data = await api('/api/auth/register', {
            method: 'POST',
            body: JSON.stringify({ username, password })
        });

        if (data.error) {
            showAuthError(data.error);
            return;
        }

        state.currentUser = data.user;
        if (data.csrf_token) setCsrfToken(data.csrf_token);
        showMainScreen();
        showAuthError('');
        startSessionHeartbeat();
    } catch (e) {
        showAuthError('注册失败，请重试');
        console.error('[ERROR] register:', e);
    }
}

export async function logout() {
    try {
        const resp = await api('/api/auth/logout');
        if (resp && resp.csrf_token) {
            setCsrfToken(resp.csrf_token);
        }
    } catch (e) {
        console.error('[ERROR] logout:', e);
        toast('退出登录失败', 'warn');
    }
    stopSessionHeartbeat();
    state.currentUser = null;
    state.rpgState = { sessionId: null, world: null, playerName: '', storyline: [], sections: null };
    state.currentMode = 'chat';
    state.isShared = false;
    state.editingAgentId = null;
    state.editingWorldId = null;
    state.editingModelId = null;
    if (state.spectateTimer) { clearInterval(state.spectateTimer); state.spectateTimer = null; }
    if (state.spectateRefreshTimer) { clearInterval(state.spectateRefreshTimer); state.spectateRefreshTimer = null; }
    const chatBox = $('chatBox');
    if (chatBox) chatBox.innerHTML = '';
    const storyText = $('storyText');
    if (storyText) storyText.innerHTML = '';
    const choicesArea = $('choicesArea');
    if (choicesArea) choicesArea.innerHTML = '';
    showAuthScreen();
}

function toggleFocusMode() {
    const main = $('mainScreen');
    if (!main) return;
    const isFocus = main.classList.toggle('focus-mode');
    if (isFocus) {
        const hint = document.createElement('div');
        hint.className = 'focus-exit-hint';
        hint.textContent = '🎭 专注模式 · 按 Esc 退出';
        hint.addEventListener('click', toggleFocusMode);
        main.appendChild(hint);
        toast('已进入专注模式，按 Esc 退出', 'info');
    } else {
        const hint = document.querySelector('.focus-exit-hint');
        if (hint) hint.remove();
    }
}

export function togglePreview() {
    const panel = $('previewPanel');
    const content = $('previewContent');
    if (!panel || !content) return;
    const isVisible = panel.style.display !== 'none';
    if (!isVisible) {
        const text = $('messageInput').value;
        content.innerHTML = text ? renderMarkdown(text) : '<span style="color:var(--text-dim);">输入内容后预览效果</span>';
        panel.style.display = 'block';
        setTimeout(() => highlightCode(content), 0);
    } else {
        panel.style.display = 'none';
    }
}

async function changePassword() {
    const oldPwd = $('oldPassword').value.trim();
    const newPwd = $('newPassword').value.trim();
    const newPwd2 = $('newPassword2').value.trim();
    const msgEl = $('changePwdMsg');

    if (!oldPwd || !newPwd) {
        msgEl.textContent = '请输入原密码和新密码';
        msgEl.style.color = 'var(--accent)';
        return;
    }
    if (newPwd.length < 8) {
        msgEl.textContent = '新密码长度至少8位';
        msgEl.style.color = 'var(--accent)';
        return;
    }
    if (newPwd !== newPwd2) {
        msgEl.textContent = '两次输入的新密码不一致';
        msgEl.style.color = 'var(--accent)';
        return;
    }

    try {
        const data = await api('/api/auth/change-password', {
            method: 'POST',
            body: JSON.stringify({ old_password: oldPwd, new_password: newPwd })
        });

        if (data.error) {
            msgEl.textContent = data.error;
            msgEl.style.color = 'var(--accent)';
        } else {
            if (data.csrf_token) {
                setCsrfToken(data.csrf_token);
            }
            msgEl.textContent = '密码修改成功！';
            msgEl.style.color = '#4CAF50';
            $('oldPassword').value = '';
            $('newPassword').value = '';
            $('newPassword2').value = '';
            setTimeout(() => {
                $('changePwdModal').classList.remove('show');
                msgEl.textContent = '';
            }, 1500);
        }
    } catch (e) {
        console.error('[ERROR] changePassword:', e);
        msgEl.textContent = '修改失败，请稍后重试';
        msgEl.style.color = 'var(--accent)';
    }
}

async function showForcePasswordChange() {
    const pwd = $("loginPassword").value.trim();
    if (!pwd || pwd.length < 8) {
        await logout();
        return;
    }
    toast("正在更新密码...");
    try {
        const data = await api("/api/auth/change-password", {
            method: "POST",
            body: JSON.stringify({ old_password: $("loginPassword").value, new_password: pwd })
        });
        if (data.error) { toast(data.error); await logout(); }
        else { toast("密码已更新，欢迎回来！"); showMainScreen(); }
    } catch (e) {
        toast("密码更新失败，请重试");
        await logout();
    }
}

function showAuthError(msg) {
    const el = $('authError');
    if (el) el.textContent = msg || '';
}

let usagePage = 1;

async function loadUsage(p) {
    usagePage = p || 1;
    try {
        const data = await api('/api/user/usage?page=' + usagePage + '&per_page=20');
        const list = $('usageList');
        const summary = $('usageSummary');
        if (data.total === 0) {
            list.innerHTML = '<div class="status-empty">暂无消耗记录</div>';
            summary.textContent = '';
            $('usagePagination').innerHTML = '';
            return;
        }
        let totalCost = 0, totalTokens = 0;
        data.logs.forEach(l => { totalCost += l.cost || 0; totalTokens += l.tokens || 0; });
        summary.textContent = '共 ' + data.total + ' 条记录 | 累计消耗 ' + totalCost + ' 积分 · ' + totalTokens + ' tokens';
        list.innerHTML = data.logs.map(l => {
            const t = l.time ? l.time.replace('T', ' ').slice(0, 19) : '--';
            const model = l.model || '--';
            const cost = l.cost !== undefined ? l.cost + ' 积分' : '--';
            const tokens = l.tokens || 0;
            return '<div class="usage-item" style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);font-size:13px;">' +
                '<span style="color:var(--text-dim);min-width:150px;">' + escapeHtml(t) + '</span>' +
                '<span style="flex:1;padding:0 12px;">' + escapeHtml(model) + '</span>' +
                '<span style="color:var(--gold);min-width:60px;text-align:right;">' + escapeHtml(String(cost)) + '</span>' +
                '<span style="color:var(--text-dim);min-width:60px;text-align:right;">' + tokens + ' tok</span>' +
                '</div>';
        }).join('');
        let phtml = '';
        for (let i = 1; i <= data.pages; i++) {
            phtml += '<button class="btn-sm ' + (i === data.page ? 'active' : '') + '" data-p="' + i + '" style="' + (i === data.page ? 'background:var(--gold);color:var(--bg);' : '') + '">' + i + '</button>';
        }
        $('usagePagination').innerHTML = phtml;
        $('usagePagination').querySelectorAll('button').forEach(b => {
            b.addEventListener('click', () => loadUsage(parseInt(b.dataset.p)));
        });
    } catch (e) {
        console.error('[ERROR] loadUsage:', e);
        $('usageList').innerHTML = '<div class="status-empty">加载失败</div>';
    }
}

export function initAuth() {
    document.querySelectorAll('.auth-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const mode = tab.dataset.mode;
            $('loginForm').style.display = mode === 'login' ? 'block' : 'none';
            $('registerForm').style.display = mode === 'register' ? 'block' : 'none';
        });
    });

    $('loginBtn')?.addEventListener('click', login);
    $('registerBtn')?.addEventListener('click', register);
    $('logoutBtn')?.addEventListener('click', logout);
    $('focusModeBtn')?.addEventListener('click', toggleFocusMode);
    $('previewBtn')?.addEventListener('click', togglePreview);
    $('previewCloseBtn')?.addEventListener('click', togglePreview);

    document.querySelectorAll('.pwd-toggle').forEach(btn => {
        btn.addEventListener('click', () => {
            const target = $(btn.dataset.target);
            if (!target) return;
            if (target.type === 'password') {
                target.type = 'text';
                btn.textContent = '🙈';
            } else {
                target.type = 'password';
                btn.textContent = '👁';
            }
        });
    });

    $('changePwdBtn')?.addEventListener('click', () => {
        $('changePwdModal').classList.add('show');
        $('changePwdMsg').textContent = '';
    });
    $('changePwdClose')?.addEventListener('click', () => {
        $('changePwdModal').classList.remove('show');
    });
    $('changePwdModal')?.addEventListener('click', e => {
        if (e.target === $('changePwdModal')) $('changePwdModal').classList.remove('show');
    });
    $('changePwdSubmit')?.addEventListener('click', changePassword);

    $('usageBtn')?.addEventListener('click', () => {
        $('usageModal').classList.add('show');
        loadUsage(1);
    });
    $('usageClose')?.addEventListener('click', () => {
        $('usageModal').classList.remove('show');
    });
    $('usageModal')?.addEventListener('click', e => {
        if (e.target === $('usageModal')) $('usageModal').classList.remove('show');
    });

    document.addEventListener('keydown', e => {
        const main = $('mainScreen');
        if (main && main.classList.contains('focus-mode') && e.key === 'Escape') {
            toggleFocusMode();
        }
    });

    const messageInput = $('messageInput');
    if (messageInput) {
        messageInput.oninput = () => {
            const panel = $('previewPanel');
            const content = $('previewContent');
            if (panel && content && panel.style.display !== 'none') {
                const text = messageInput.value;
                content.innerHTML = text ? renderMarkdown(text) : '<span style="color:var(--text-dim);">输入内容后预览效果</span>';
                setTimeout(() => highlightCode(content), 0);
            }
        };
    }
}

// ===== END OF FILE =====
