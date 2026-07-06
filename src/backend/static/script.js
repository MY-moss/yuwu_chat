// ============================================================
// 文件: script.js | 职责: 前端主逻辑 | 区块数: 18
// ============================================================

// ============================================================
// 区块 01 · 全局状态与DOM引用
// ============================================================
let currentMode = 'chat';
let rpgState = { sessionId: null, world: null, playerName: '', storyline: [] };
let currentUser = null;
let isShared = false;
let rpgAbortController = null;
let _rpgRequestActive = false;
let _gameStarting = false;
let isSwitchingMode = false;
let isSwitchingAgent = false;

const agentState = {};
let currentAgentId = null;

// ============================================================
// 区块 02 · 工具函数与Loading
// ============================================================
function toast(msg, type) {
    const c = document.getElementById('toastContainer');
    if (!c) return;
    const d = document.createElement('div');
    d.className = 'toast ' + (type || 'info');
    d.textContent = msg;
    c.appendChild(d);
    setTimeout(() => d.classList.add('show'), 10);
    setTimeout(() => { d.classList.remove('show'); setTimeout(() => d.remove(), 300); }, 3500);
}

// --- Utils ---
function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
}

// --- DOM Refs ---
const $ = id => document.getElementById(id);
const chatBox = $('chatBox');
const messageInput = $('messageInput');
const sendBtn = $('sendBtn');
const agentSelect = $('agentSelect');
const worldGrid = $('worldGrid');
const worldSelectScreen = $('worldSelectScreen');
const gameScreen = $('gameScreen');
const storyBox = $('storyBox');
const storyText = $('storyText');
const choicesArea = $('choicesArea');
const personalContent = $('personalContent');
const gameWorldName = $('gameWorldName');
const gamePlayerName = $('gamePlayerName');

// --- Loading Overlay ---
const loadingOverlay = $('loadingOverlay');
const loadingText = $('loadingText');
const loadingSub = $('loadingSub');
const loadingStatus = $('loadingStatus');

function showLoading(text, sub) {
    loadingText.textContent = text || 'AI 正在编织故事...';
    loadingSub.textContent = sub || '请稍候';
    loadingOverlay.classList.add('show');
    const bar = $('loadingBarInner');
    bar.style.animation = 'none';
    bar.style.width = '0%';
    const pct = $('loadingPct');
    if (pct) pct.textContent = '0%';
    if (loadingStatus) loadingStatus.textContent = '';
}

function hideLoading() {
    loadingOverlay.classList.remove('show');
}

function updateProgress(pct, label) {
    const bar = $('loadingBarInner');
    if (bar) bar.style.width = Math.min(100, pct) + '%';
    const pctEl = $('loadingPct');
    if (pctEl) pctEl.textContent = (label || Math.round(pct) + '%');
}

function updateLoadingStatus(text) {
    if (loadingStatus) loadingStatus.textContent = text || '';
}

function saveCurrentAgentState() {
    if (!currentAgentId || !chatBox) return;
    const keys = Object.keys(agentState);
    if (keys.length > 50) {
        const sorted = keys.sort((a, b) => (agentState[a].timestamp || 0) - (agentState[b].timestamp || 0));
        sorted.slice(0, sorted.length - 50).forEach(k => delete agentState[k]);
    }
    agentState[currentAgentId] = {
        scrollTop: chatBox.scrollTop,
        scrollHeight: chatBox.scrollHeight,
        messages: chatBox.innerHTML,
        timestamp: Date.now()
    };
}

function restoreAgentState(agentId) {
    if (!agentState[agentId] || !chatBox) return;
    const state = agentState[agentId];
    chatBox.innerHTML = state.messages;
    chatBox.scrollTop = state.scrollTop;
}

async function switchMode(newMode) {
    if (isSwitchingMode || currentMode === newMode) return;
    isSwitchingMode = true;

    if (currentMode === 'rpg' && newMode !== 'rpg') {
        if (rpgAbortController) {
            rpgAbortController.abort();
            rpgAbortController = null;
        }
        _rpgRequestActive = false;
        hideLoading();
    }

    try {
        const chatModeEl = document.getElementById('chatMode');
        const rpgModeEl = document.getElementById('rpgMode');

        chatModeEl.style.opacity = '0';
        rpgModeEl.style.opacity = '0';

        await new Promise(resolve => setTimeout(resolve, 300));

        currentMode = newMode;

        document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
        document.querySelector(`.mode-tab[data-mode="${newMode}"]`)?.classList.add('active');

        document.querySelectorAll('.mobile-tab-item[data-mode]').forEach(t => t.classList.remove('active'));
        document.querySelector(`.mobile-tab-item[data-mode="${newMode}"]`)?.classList.add('active');

        if (currentMode === 'chat') {
            chatModeEl.style.display = 'flex';
            rpgModeEl.style.display = 'none';
            setTimeout(() => { chatModeEl.style.opacity = '1'; }, 50);
        } else if (currentMode === 'rpg') {
            chatModeEl.style.display = 'none';
            rpgModeEl.style.display = 'flex';
            setTimeout(() => { rpgModeEl.style.opacity = '1'; }, 50);
            loadWorlds();
            if (rpgState.sessionId) {
                gameScreen.style.display = 'flex';
                worldSelectScreen.style.display = 'none';
                if (!storyText.textContent || storyText.textContent.includes('服务器内部错误')) {
                    resumeGame(rpgState.sessionId).catch(e => {
                        console.error('[ERROR] resumeGame on tab switch:', e);
                        rpgState.sessionId = null;
                        gameScreen.style.display = 'none';
                        worldSelectScreen.style.display = 'block';
                    });
                }
            } else {
                gameScreen.style.display = 'none';
                worldSelectScreen.style.display = 'block';
            }
        }
    } catch (e) {
        console.error('[ERROR] switchMode:', e);
        toast('模式切换失败', 'error');
    } finally {
        isSwitchingMode = false;
    }
}

async function switchAgent(newAgentId) {
    if (isSwitchingAgent || currentAgentId === newAgentId) return;
    isSwitchingAgent = true;

    try {
        saveCurrentAgentState();

        const chatBoxEl = chatBox;
        const agentCardSelector = $('agentCardSelector');

        if (chatBoxEl) {
            chatBoxEl.style.opacity = '0';
            chatBoxEl.style.transform = 'translateX(-20px)';
        }

        if (agentCardSelector) {
            agentCardSelector.style.opacity = '0';
        }

        await new Promise(resolve => setTimeout(resolve, 200));

        agentSelect.value = newAgentId;
        document.querySelectorAll('.agent-card').forEach(card => {
            card.classList.remove('active');
            if (card.dataset.agentId === newAgentId) card.classList.add('active');
        });

        currentAgentId = newAgentId;
        updateAgentHint();
        restoreAgentState(newAgentId);

        if (chatBoxEl) {
            chatBoxEl.style.opacity = '1';
            chatBoxEl.style.transform = 'translateX(0)';
        }

        if (agentCardSelector) {
            agentCardSelector.style.opacity = '1';
        }
    } catch (e) {
        console.error('[ERROR] switchAgent:', e);
        toast('智能体切换失败', 'error');
    } finally {
        isSwitchingAgent = false;
    }
}

// ============================================================
// 区块 03 · 认证UI
// ============================================================
async function checkAuth() {
    try {
        const data = await api('/api/auth/me');
        currentUser = data;
        showMainScreen();
    } catch {
        showAuthScreen();
    }
}

async function loadVersion() {
    try {
        const data = await api('/version');
        const verEl = $('versionDisplay');
        if (verEl) verEl.textContent = data.version || 'v1.0.0';
    } catch (e) {
        toast('版本信息加载失败', 'warn');
        console.error('[ERROR] fetchVersion:', e);
    }
}

function showAuthScreen() {
    $('authScreen').style.display = 'flex';
    $('mainScreen').style.display = 'none';
}

function showMainScreen() {
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
    currentMode = 'chat';
    document.getElementById('chatMode').style.display = 'flex';
    document.getElementById('rpgMode').style.display = 'none';
}

function updateUserInfo() {
    if (!currentUser) return;
    $('creditsDisplay').textContent = `💰 ${currentUser.credits}`;
    $('usernameDisplay').textContent = currentUser.username;
    $('adminBtn').style.display = currentUser.role === 'admin' ? 'block' : 'none';
    if ($('dashboardBtn')) $('dashboardBtn').style.display = currentUser.role === 'admin' ? 'block' : 'none';
    updateFreeModeDisplay(currentUser.has_personal_api);
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

        currentUser = data.user;
        if (data.password_reset_required) {
            currentUser = data.user;
            showForcePasswordChange();
            return;
        }
        showMainScreen();
        showAuthError('');
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

    try {
        const data = await api('/api/auth/register', {
            method: 'POST',
            body: JSON.stringify({ username, password })
        });

        if (data.error) {
            showAuthError(data.error);
            return;
        }

        currentUser = data.user;
        showMainScreen();
        showAuthError('');
    } catch (e) {
        showAuthError('注册失败，请重试');
        console.error('[ERROR] register:', e);
    }
}

async function logout() {
    try {
        await api('/api/auth/logout');
    } catch (e) {
        console.error('[ERROR] logout:', e);
        toast('退出登录失败', 'warn');
    }
    currentUser = null;
    rpgState = { sessionId: null, world: null, playerName: '', storyline: [] };
    currentMode = 'chat';
    isShared = false;
    editingAgentId = null;
    editingWorldId = null;
    editingModelId = null;
    if (spectateTimer) { clearInterval(spectateTimer); spectateTimer = null; }
    if (spectateRefreshTimer) { clearInterval(spectateRefreshTimer); spectateRefreshTimer = null; }
    chatBox.innerHTML = '';
    storyText.innerHTML = '';
    choicesArea.innerHTML = '';
    showAuthScreen();
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

// ---- Force password change after admin reset ----
function showForcePasswordChange() {
    const loginPwd = $("loginPassword").value.trim();
    if (!pwd || pwd.length < 8) {
    if (!pwd || pwd.length < 8) {
        logout();
        return;
    }
    toast("正在更新密码...");
    api("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ old_password: loginPassword, new_password: pwd })
    }).then(data => {
        if (data.error) { toast(data.error); logout(); }
        else { toast("密码已更新，欢迎回来！"); showMainScreen(); }
    }).catch(() => { toast("密码更新失败，请重试"); logout(); });
}

function showAuthError(msg) {
    $('authError').textContent = msg || '';
}

// ============================================================
// 区块 04 · 模型与初始化
// ============================================================
async function populateModels() {
    const sel = $('modelSelect');
    if (!sel) return;
    try {
        const models = await api('/api/models');
        const hasPersonal = currentUser && currentUser.has_personal_api;
        
        const systemPaid = models.filter(m => m.source === 'system' && (m.credits_per_1k || 1) > 0);
        const systemFree = models.filter(m => m.source === 'system' && (m.credits_per_1k || 1) === 0);
        const userModels = models.filter(m => m.source === 'personal');
        
        let html = '';
        for (const m of systemPaid) {
            html += `<option value="${escapeHtml(m.model_id)}">${escapeHtml(m.label)} (${m.credits_per_1k}积分/千Token)</option>`;
        }
        if (systemFree.length > 0) {
            html += '<option disabled>──────────</option>';
            for (const m of systemFree) {
                html += `<option value="${escapeHtml(m.model_id)}">${escapeHtml(m.label)} (🆓 免费)</option>`;
            }
        }
        if (userModels.length > 0) {
            html += '<option disabled>──────────</option>';
            html += '<option disabled>🔑 我的自有API模型 (不计费)</option>';
            for (const m of userModels) {
                html += `<option value="${escapeHtml(m.model_id)}">${escapeHtml(m.label)} (🔑 自有API)</option>`;
            }
        }
        sel.innerHTML = html;
        if (models.length) {
            const defaultModel = systemPaid.length > 0 ? systemPaid[0].model_id
                : systemFree.length > 0 ? systemFree[0].model_id
                : userModels.length > 0 ? userModels[0].model_id
                : null;
            if (defaultModel) sel.value = defaultModel;
        }
    } catch {
        sel.innerHTML = '<option value="">📡 模型加载失败，请刷新重试</option>';
    }
}

function getSelectedModel() {
    return $('modelSelect') ? $('modelSelect').value : 'mimo-v2.5-free';
}

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    setupEventListeners();
    loadVersion();
});

function setupEventListeners() {
    // Auth
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

    // Password visibility toggles
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
    
    $('changePwdBtn').addEventListener('click', () => {
        $('changePwdModal').classList.add('show');
        $('changePwdMsg').textContent = '';
    });
    $('changePwdClose').addEventListener('click', () => {
        $('changePwdModal').classList.remove('show');
    });
    $('changePwdModal').addEventListener('click', e => {
        if (e.target === $('changePwdModal')) $('changePwdModal').classList.remove('show');
    });
    $('changePwdSubmit').addEventListener('click', changePassword);

    // Mode Tabs
    document.querySelectorAll('.mode-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            hideLoading();
            switchMode(tab.dataset.mode);
        });
    });

    // Panel Toggle Buttons
    document.querySelectorAll('.panel-toggle').forEach(btn => {
        btn.addEventListener('click', () => {
            const panel = btn.dataset.panel;
            const panelEl = document.getElementById(panel);
            if (panelEl) {
                panelEl.classList.toggle('collapsed');
            }
        });
    });

    // Mobile Tab Bar
    document.querySelectorAll('.mobile-tab-item[data-mode]').forEach(tab => {
        tab.addEventListener('click', () => {
            hideLoading();
            switchMode(tab.dataset.mode);
        });
    });

    // Dashboard Button
    $('dashboardBtn')?.addEventListener('click', () => {
        window.open('/dashboard', '_blank');
    });
}

let csrfToken = '';

async function fetchCsrfToken() {
    try {
        const data = await api('/api/csrf-token');
        csrfToken = data.csrf_token || '';
    } catch (e) {
        toast('安全令牌获取失败，部分功能可能不可用', 'warn');
        console.error('[ERROR] fetchCsrfToken:', e);
    }
}

fetchCsrfToken();

// ============================================================
// 区块 05 · API Helpers
// ============================================================
async function api(url, opts = {}) {
    const headers = { 'Content-Type': 'application/json' };
    if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken;
    }
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
            currentUser = null;
            showAuthScreen();
            throw new Error('未登录');
        }
        return { error: '服务器响应格式错误' };
    }
    if (data.error === '未登录') {
        currentUser = null;
        showAuthScreen();
        throw new Error('未登录');
    }
    return data;
}

async function apiStream(url, opts = {}) {
    const headers = { 'Content-Type': 'application/json' };
    if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken;
    }
    const res = await fetch(url, {
        headers,
        credentials: 'include',
        ...opts
    });
    if (!res.ok) {
        if (res.status === 401) {
            currentUser = null;
            showAuthScreen();
            throw new Error('未登录');
        }
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }
    return res;
}

// ============================================================
// 区块 06 · 聊天UI
// ============================================================
async function loadAgents() {
    try {
        const data = await api('/api/agents');
        const agents = Array.isArray(data) ? data : [];
        agentSelect.innerHTML = agents.map(a =>
            `<option value="${escapeHtml(a.id)}">${escapeHtml(a.avatar || '🧔')} ${escapeHtml(a.name)} ${a.title ? '— ' + escapeHtml(a.title) : ''}</option>`
        ).join('');
        if (agents.length) {
            agentSelect.value = agents[0].id;
            currentAgentId = agents[0].id;
        }
        updateAgentHint();
        renderAgentCards(agents);
    } catch (e) {
        const skel = $('agentSkeleton');
        if (skel) skel.style.display = 'none';
        const cs = $('agentCardSelector');
        if (cs) { cs.style.display = ''; cs.innerHTML = '<div style="padding:14px 18px;color:var(--text-dim);">加载失败</div>'; }
        console.error('[ERROR] loadAgents:', e);
    }
}

function renderAgentCards(agents) {
    const cardSelector = $('agentCardSelector');
    if (!cardSelector) return;
    const skel = $('agentSkeleton');
    if (skel) skel.style.display = 'none';
    cardSelector.style.display = '';
    
    cardSelector.innerHTML = agents.map((a, index) => `
        <div class="agent-card ${index === 0 ? 'active' : ''}" data-agent-id="${escapeHtml(a.id)}">
            <div class="agent-avatar">${escapeHtml(a.avatar || '🧔')}</div>
            <div class="agent-name">${escapeHtml(a.name)}</div>
            ${a.title ? `<div class="agent-title">${escapeHtml(a.title)}</div>` : ''}
        </div>
    `).join('');
    
    document.querySelectorAll('.agent-card').forEach(card => {
        card.addEventListener('click', () => switchAgent(card.dataset.agentId));
    });
    
    const searchInput = $('agentSearchInput');
    if (searchInput) {
        searchInput.value = '';
        searchInput.addEventListener('input', () => {
            const q = searchInput.value.toLowerCase();
            document.querySelectorAll('.agent-card').forEach(card => {
                const name = card.querySelector('.agent-name')?.textContent?.toLowerCase() || '';
                const title = card.querySelector('.agent-title')?.textContent?.toLowerCase() || '';
                card.style.display = name.includes(q) || title.includes(q) ? '' : 'none';
            });
        });
    }
}

window.selectAgent = function(id) {
    switchAgent(id);
}

function updateAgentHint() {
    const sel = agentSelect.selectedOptions[0];
    $('agentHint').textContent = sel ? `当前：${sel.textContent}` : '请选择一位角色聊聊';
}

agentSelect.addEventListener('change', () => {
    switchAgent(agentSelect.value);
});

sendBtn.addEventListener('click', sendMessage);
messageInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});
messageInput.addEventListener('input', () => {
    messageInput.style.height = 'auto';
    messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';
});

let isSending = false;

async function sendMessage() {
    if (isSending) return;
    const msg = messageInput.value.trim();
    if (!msg) return;
    isSending = true;
    const agentId = agentSelect.value;
    messageInput.value = '';
    messageInput.style.height = 'auto';
    appendMessage(msg, 'user');
    sendBtn.disabled = true;
    sendBtn.textContent = '⏳ 思考中...';
    const thinkingEl = appendMessage('', 'agent', agentSelect.selectedOptions[0]?.textContent || '');
    const thinkDots = createThinkingIndicator();
    thinkingEl.querySelector('.md-body').appendChild(thinkDots);
    try {
        const data = await api('/api/chat', {
            method: 'POST',
            body: JSON.stringify({ message: msg, agent_id: agentId, model: getSelectedModel() })
        });
        thinkDots.remove();
        if (data.error) {
            if (data.error === '积分不足') {
                toast('积分不足，请联系管理员充值');
                thinkingEl.remove();
            } else {
                thinkingEl.querySelector('.md-body').innerHTML = '❌ ' + escapeHtml(data.error);
            }
        } else {
            thinkingEl.querySelector('.md-body').innerHTML = renderMarkdown(data.reply || '（没有回应）');
            if (data.credits_left !== undefined) {
                currentUser.credits = data.credits_left;
                updateUserInfo();
            }
        }
    } catch (err) {
        thinkDots.remove();
        thinkingEl.querySelector('.md-body').innerHTML = '❌ 网络错误，请重试';
    } finally {
        isSending = false;
        sendBtn.disabled = false;
        sendBtn.innerHTML = '<span class="btn-icon">🍺</span> 来一杯';
        chatBox.scrollTop = chatBox.scrollHeight;
    }
}

function createThinkingIndicator() {
    const wrap = document.createElement('span');
    wrap.className = 'thinking-dots';
    wrap.innerHTML = '<span></span><span></span><span></span>';
    return wrap;
}

function appendMessage(text, role, name) {
    const div = document.createElement('div');
    div.className = `msg ${role}`;
    const header = document.createElement('div');
    header.className = 'msg-header';
    const avatar = document.createElement('span');
    avatar.className = 'msg-avatar';
    if (role === 'agent') {
        avatar.textContent = name ? name.charAt(0) : '🤖';
        if (name) {
            const nm = document.createElement('span');
            nm.className = 'msg-name';
            nm.textContent = name;
            header.appendChild(nm);
        }
    } else {
        avatar.textContent = '🧑';
    }
    header.insertBefore(avatar, header.firstChild);
    const time = document.createElement('span');
    time.className = 'msg-time';
    time.textContent = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    header.appendChild(time);
    div.appendChild(header);
    const content = document.createElement('div');
    content.className = 'md-body';
    if (role === 'agent') {
        content.innerHTML = renderMarkdown(text);
    } else {
        content.textContent = text;
    }
    div.appendChild(content);
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
    return div;
}

// ============================================================
// 区块 07 · 会话管理
// ============================================================
async function loadSessions() {
    try {
        const [sessions, activeData] = await Promise.all([
            api('/api/rpg/sessions'),
            api('/api/rpg/active-count').catch(() => ({ total: 0 }))
        ]);
        // Show total active count across all users
        $('sessionsCount').textContent = activeData.total;
        if (sessions.length === 0) {
            $('sessionsEmpty').style.display = 'block';
            $('sessionsList').innerHTML = '';
            return;
        }
        $('sessionsEmpty').style.display = 'none';
        $('sessionsList').innerHTML = sessions.map(s => {
            const active = rpgState.sessionId === s.session_id;
            const time = formatTime(s.last_active);
            return `
                <div class="session-card ${active ? 'active current' : ''}" data-sid="${escapeHtml(s.session_id)}">
                    <div class="sc-emoji">${escapeHtml(s.world_emoji)}</div>
                    <div class="sc-info">
                        <div class="sc-name">${escapeHtml(s.world_name)}</div>
                        <div class="sc-meta">🧑 ${escapeHtml(s.player_name)} · ${s.rounds}轮 · ${time}</div>
                    </div>
                    <div class="sc-actions">
                        <button class="sc-delete" data-sid="${escapeHtml(s.session_id)}" title="删除记录">🗑️</button>
                    </div>
                </div>
            `;
        }).join('');
        
        document.querySelectorAll('.session-card').forEach(card => {
            card.addEventListener('click', () => resumeGame(card.dataset.sid));
        });
        document.querySelectorAll('.sc-delete').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                deleteSession(e, btn.dataset.sid);
            });
        });
    } catch (e) {
        $('sessionsCount').textContent = '?';
        $('sessionsList').innerHTML = '<div class="status-empty">加载失败</div>';
        console.error('[ERROR] loadSessions:', e);
    }
}

function formatTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    const now = new Date();
    const diff = now - d;
    if (diff < 60000) return '刚刚';
    if (diff < 3600000) return Math.floor(diff/60000) + '分钟前';
    if (diff < 86400000) return Math.floor(diff/3600000) + '小时前';
    return d.toLocaleDateString('zh-CN');
}

window.deleteSession = async function(e, sid) {
    e.stopPropagation();
    if (!confirm('确定删除这个跑团记录？数据不可恢复。')) return;
    try {
        await api(`/api/rpg/session/${sid}`, { method: 'DELETE' });
        if (rpgState.sessionId === sid) {
            rpgState = { sessionId: null, world: null, playerName: '', storyline: [] };
            gameScreen.style.display = 'none';
            worldSelectScreen.style.display = 'block';
            if (shareBtn) shareBtn.style.display = 'none';
        }
        loadSessions();
    } catch (e) {
        console.error('[ERROR] deleteSession:', e);
        toast('删除失败', 'error');
    }
};

async function resumeGame(sessionId) {
    try {
        const data = await api(`/api/rpg/session/${sessionId}`);
        if (data.error) {
            toast(data.error);
            return;
        }
        showLoading('🔄 恢复游戏中...', data.player_name);
        worldSelectScreen.style.display = 'none';
        gameScreen.style.display = 'flex';
        personalContent.innerHTML = '<div class="status-empty">恢复中...</div>';

        rpgState.sessionId = sessionId;
        rpgState.playerName = data.player_name;
        rpgState.world = { id: data.world_id, emoji: '📖', name: '加载中...' };
        rpgState.sections = data.sections || {};
        try {
            const worlds = await api('/api/rpg/worlds');
            const w = worlds.find(x => x.id === data.world_id);
            if (w) rpgState.world = w;
        } catch(e) { console.error('Load world info failed:', e); }
        gameWorldName.textContent = `${rpgState.world.emoji} ${rpgState.world.name}`;
        gamePlayerName.textContent = `🧑 ${data.player_name}`;
        $('gameRound').textContent = `第${Math.max(1, data.storyline ? data.storyline.length : 0)}轮`;

        hideLoading();
        renderStory(data.last_story || '');
        renderStatus(data.sections || data.last_state || '');
        renderChoices(data.last_story || '');
        rpgState.storyline = data.storyline || [];
        renderStoryline();
        renderRelationships(data.relationships);
        isShared = !!data.share_token;
        if (shareBtn) {
            shareBtn.style.display = 'block';
            shareBtn.textContent = isShared ? '🔓 取消分享' : '🔗 分享';
        }
    } catch (e) {
        console.error('[ERROR] resumeGame:', e);
        hideLoading();
        worldSelectScreen.style.display = 'block';
        gameScreen.style.display = 'none';
        toast('恢复游戏失败，请重试');
    }
}

$('sessionsBarHeader').addEventListener('click', () => {
    $('sessionsBody').classList.toggle('collapsed');
    $('sessionsToggle').classList.toggle('collapsed');
});

// ============================================================
// 区块 08 · 世界与评分
// ============================================================
async function loadWorlds() {
    loadSessions();
    try {
        const worlds = await api('/api/rpg/worlds');
        worldGrid.innerHTML = worlds.map(w => {
            const ratingHtml = renderRatingStars(w.avg_rating || 0);
            return `
            <div class="world-card" data-id="${escapeHtml(w.id)}">
                <div class="wc-emoji">${escapeHtml(w.emoji || '📖')}</div>
                <div class="wc-name">${escapeHtml(w.name)}</div>
                <div class="wc-genre">${escapeHtml(w.genre || '')}</div>
                <div class="wc-desc">${escapeHtml(w.desc || '')}</div>
                <div class="wc-rating">
                    <span class="wc-stars">${ratingHtml}</span>
                    <span class="wc-rating-text">${w.avg_rating || '-'} (${w.rating_count || 0}评)</span>
                    <button class="wc-rate-btn" data-wid="${escapeHtml(w.id)}">⭐ 评价</button>
                </div>
            </div>
            `;
        }).join('');
        document.querySelectorAll('.world-card').forEach(card => {
            card.addEventListener('click', (e) => {
                const rateBtn = e.target.closest('.wc-rate-btn');
                if (rateBtn) { openRateWorld(e, rateBtn.dataset.wid); return; }
                startGame(card.dataset.id);
            });
        });
    } catch (e) {
        worldGrid.innerHTML = '<div class="status-empty" style="grid-column:1/-1;">加载失败，请刷新重试</div>';
        console.error('[ERROR] loadWorlds:', e);
    }
}

function renderRatingStars(avg) {
    const full = Math.round(avg);
    let html = '';
    for (let i = 1; i <= 5; i++) {
        if (i <= full) html += '<span class="rating-star full">★</span>';
        else html += '<span class="rating-star">☆</span>';
    }
    return html;
}

// --- World Rating ---
window.openRateWorld = async function(e, worldId) {
    e.stopPropagation();
    const ratings = await api(`/api/rpg/worlds/${worldId}/ratings`).catch(() => []);
    const myRating = ratings.find(r => r.user_id === (currentUser?.id || 0));
    let existingModal = $('rateWorldModal');
    if (existingModal) existingModal.remove();
    currentPickedRating = 0;

    const modal = document.createElement('div');
    modal.className = 'modal-overlay show';
    modal.id = 'rateWorldModal';
    modal.innerHTML = `
        <div class="modal modal-wide">
            <div class="modal-header">
                <span>⭐ 评价世界书</span>
                <button class="modal-close">&times;</button>
            </div>
            <div class="modal-body">
                <div class="rate-my-section">
                    <div class="form-group"><label>你的评分</label>
                        <div class="rate-star-picker">${[1,2,3,4,5].map(n =>
                            `<span class="rate-pick-star" data-r="${n}">☆</span>`
                        ).join('')}</div>
                    </div>
                    <div class="form-group"><label>你的评价（可选）</label>
                        <textarea id="rateReview" rows="3" placeholder="写下你对这个世界的感受...">${escapeHtml(myRating?.review || '')}</textarea>
                    </div>
                    <button class="btn-add" data-wid="${escapeHtml(worldId)}">提交评价</button>
                </div>
                <div class="rate-history-section">
                    <div class="rate-history-title">📝 玩家评价 (${ratings.length})</div>
                    <div class="rate-history-list">
                        ${ratings.length === 0 ? '<div class="status-empty">暂无评价，来做第一个评价的人吧！</div>' :
                        ratings.slice().reverse().map(r => `
                            <div class="rate-history-item">
                                <div class="rhi-header">
                                    <span class="rhi-user">👤 ${escapeHtml(r.username)}</span>
                                    <span class="rhi-stars">${renderRatingStars(r.rating)}</span>
                                    <span class="rhi-time">${formatTime(r.created_at || r.updated_at)}</span>
                                </div>
                                ${r.review ? `<div class="rhi-review">${escapeHtml(r.review)}</div>` : ''}
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    modal.querySelectorAll('.rate-pick-star').forEach(s => {
        s.addEventListener('click', () => pickRating(parseInt(s.dataset.r)));
    });

    if (myRating) {
        currentPickedRating = myRating.rating;
        updatePickStars(myRating.rating);
    }
    modal.querySelector('.btn-add').addEventListener('click', () => submitRating(modal.querySelector('.btn-add').dataset.wid));
    modal.querySelector('.modal-close').addEventListener('click', closeRateModal);
    modal.addEventListener('click', e => { if (e.target === modal) closeRateModal(); });
};

let currentPickedRating = 0;

window.pickRating = function(r) {
    currentPickedRating = r;
    updatePickStars(r);
};

function updatePickStars(r) {
    document.querySelectorAll('.rate-pick-star').forEach(s => {
        const sr = parseInt(s.dataset.r);
        s.textContent = sr <= r ? '★' : '☆';
        s.classList.toggle('picked', sr <= r);
    });
}

window.closeRateModal = function() {
    const modal = $('rateWorldModal');
    if (modal) modal.remove();
    currentPickedRating = 0;
};

window.submitRating = async function(worldId) {
    if (currentPickedRating < 1 || currentPickedRating > 5) {
        toast('请选择1-5星评分');
        return;
    }
    try {
        const review = ($('rateReview')?.value || '').trim();
        const res = await api(`/api/rpg/worlds/${worldId}/ratings`, {
            method: 'POST',
            body: JSON.stringify({ rating: currentPickedRating, review })
        });
        if (res.error) { toast(res.error); return; }
        closeRateModal();
        loadWorlds();
    } catch (e) {
        console.error('[ERROR] submitRating:', e);
        toast('提交评价失败');
    }
};

// ============================================================
// 区块 09 · RPG游戏核心
// ============================================================
async function startGame(worldId) {
    if (_gameStarting) return;
    _gameStarting = true;
    let name = prompt('请输入你的角色名：', '旅人') || '旅人';
    name = name.trim().replace(/[<>"'&]/g, '');
    if (!name) name = '旅人';
    worldSelectScreen.style.display = 'none';
    gameScreen.style.display = 'flex';
    personalContent.innerHTML = '<div class="status-empty">故事载入中...</div>';
    storyText.textContent = '';
    choicesArea.innerHTML = '';

    showLoading('📖 世界正在苏醒...', 'AI 主持人正在构建初始场景');

    const loadingStates = [
        '正在初始化游戏世界...',
        'AI 主持人正在构思剧情...',
        '正在生成开场场景...',
        '即将进入冒险...'
    ];
    let stateIdx = 0;
    const loadingTimer = setInterval(() => {
        stateIdx = (stateIdx + 1) % loadingStates.length;
        updateLoadingStatus(loadingStates[stateIdx]);
    }, 1500);

    rpgAbortController = new AbortController();

    try {
        const data = await api('/api/rpg/start', {
            method: 'POST',
            body: JSON.stringify({ world_id: worldId, player_name: name, model: getSelectedModel() }),
            signal: rpgAbortController.signal
        });
        clearInterval(loadingTimer);

        if (data.error) {
            hideLoading();
            if (data.error === '积分不足') {
                toast('积分不足，请联系管理员充值');
                worldSelectScreen.style.display = 'block';
                gameScreen.style.display = 'none';
            } else {
                storyText.textContent = '❌ ' + data.error;
            }
            return;
        }

        rpgState.sessionId = data.session_id;
        rpgState.world = data.world;
        rpgState.playerName = data.player_name;
        rpgState.storyline = data.storyline || [];
        rpgState.sections = data.sections || null;
        gameWorldName.textContent = `${data.world.emoji} ${data.world.name}`;
        gamePlayerName.textContent = `🧑 ${data.player_name}`;
        $('gameRound').textContent = `第${Math.max(1, data.storyline ? data.storyline.length : 0)}轮`;

        isShared = !!data.share_token;
        if (shareBtn) {
            shareBtn.style.display = 'block';
            shareBtn.textContent = isShared ? '🔓 取消分享' : '🔗 分享';
        }

        if (data.credits_left !== undefined) {
            currentUser.credits = data.credits_left;
            updateUserInfo();
        }

        hideLoading();
        renderStory(data.story);
        renderStatus(data.sections || data.state || '');
        renderChoices(data.story);
        renderStoryline();
        renderRelationships(data.relationships);
    } catch (e) {
        clearInterval(loadingTimer);
        if (e.name === 'AbortError') {
            console.info('[INFO] startGame aborted by user');
            return;
        }
        console.error('[ERROR] startGame:', e);
        hideLoading();
        storyText.textContent = '❌ 游戏启动失败，请重试';
    } finally {
        clearInterval(loadingTimer);
        rpgAbortController = null;
        _gameStarting = false;
    }
}

async function actGame(choice) {
    if (!rpgState.sessionId) return;
    if (rpgAbortController) return;
    if (_rpgRequestActive) return;
    if (actGameStatusTimeout) { clearTimeout(actGameStatusTimeout); actGameStatusTimeout = null; }
    _rpgRequestActive = true;
    showLoading('🎭 故事继续展开...', '');

    const MAX_RETRIES = 2;
    let retryCount = 0;

    while (retryCount <= MAX_RETRIES) {
        if (retryCount > 0) {
            const delay = Math.pow(2, retryCount) * 1000;
            updateLoadingStatus(`🔄 连接断开，${delay/1000}秒后重试...`);
            await new Promise(r => setTimeout(r, delay));
            if (!rpgState.sessionId) { hideLoading(); _rpgRequestActive = false; return; }
        }

        rpgAbortController = new AbortController();

        try {
            const resp = await apiStream('/api/rpg/act/stream', {
                method: 'POST',
                body: JSON.stringify({ session_id: rpgState.sessionId, choice, model: getSelectedModel() }),
                signal: rpgAbortController.signal
            });
            const reader = resp.body.getReader();
            const dec = new TextDecoder();
            let buffer = '', full = '', startTime = Date.now();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += dec.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    let json;
                    try {
                        json = JSON.parse(line.slice(6));
                    } catch (e) {
                        console.error('[ERROR] Failed to parse SSE chunk:', e);
                        continue;
                    }
                    if (json.type === 'chunk') {
                        full += json.text;
                        storyText.innerHTML = renderMarkdown(full);
                        storyBox.scrollTop = storyBox.scrollHeight;
                        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
                        const estTotal = Math.max(800, full.length * 2);
                        const pct = Math.min(95, full.length / estTotal * 100);
                        const speed = elapsed > 0 ? (full.length / parseFloat(elapsed)).toFixed(0) : 0;
                        updateProgress(pct, Math.round(pct) + '% · ' + full.length + '字');
                        $('loadingSub').textContent = '⏱ ' + elapsed + 's · ' + speed + '字/s';
                        updateLoadingStatus('AI 正在生成故事...');
                    } else if (json.type === 'done') {
                        updateProgress(100, '100%');
                        updateLoadingStatus('✓ 故事生成完成，正在渲染...');
                        actGameStatusTimeout = setTimeout(() => updateLoadingStatus(''), 500);
                        if (json.credits_left !== undefined) {
                            currentUser.credits = json.credits_left;
                            updateUserInfo();
                        }
                        rpgState.storyline = json.storyline || rpgState.storyline || [];
                        rpgState.sections = json.sections || null;
                        storyText.innerHTML = renderMarkdown(json.story || full);
                        renderStatus(json.sections || json.state || '');
                        renderChoices(json.story || full);
                        renderStoryline();
                        renderRelationships(json.relationships);
                        $('gameRound').textContent = `第${Math.max(1, (rpgState.storyline || []).length)}轮`;
                        hideLoading();
                        rpgAbortController = null;
                        _rpgRequestActive = false;
                        return;
                    } else if (json.type === 'error') {
                        storyText.textContent = '❌ ' + json.text;
                        hideLoading();
                        rpgAbortController = null;
                        _rpgRequestActive = false;
                        return;
                    }
                }
            }
            if (full && !storyText.textContent.startsWith('❌')) {
                storyText.innerHTML = renderMarkdown(full);
                renderChoices(full);
                renderStoryline();
            }
            hideLoading();
            rpgAbortController = null;
            _rpgRequestActive = false;
            return;
        }
        } catch (e) {
            if (e.name === 'AbortError') {
                console.info('[INFO] actGame aborted by user');
                hideLoading();
                rpgAbortController = null;
                _rpgRequestActive = false;
                return;
            }
            if (!rpgState.sessionId) { hideLoading(); _rpgRequestActive = false; return; }
            retryCount++;
            console.warn(`[WARN] SSE stream failed, attempt ${retryCount}/${MAX_RETRIES}:`, e);
            rpgAbortController = null;
        }
    }

    try {
        storyText.textContent = '⏳ 流式连接失败，使用普通模式...';
        const data = await api('/api/rpg/act', {
            method: 'POST',
            body: JSON.stringify({ session_id: rpgState.sessionId, choice, model: getSelectedModel() })
        });
        if (data.error) {
            if (data.error === '积分不足') { toast('积分不足'); return; }
            storyText.textContent = '❌ ' + data.error; return;
        }
        if (data.credits_left !== undefined) { currentUser.credits = data.credits_left; updateUserInfo(); }
        rpgState.storyline = data.storyline || [];
        rpgState.sections = data.sections || null;
        storyText.innerHTML = renderMarkdown(data.story || '');
        renderStatus(data.sections || data.state || '');
        renderChoices(data.story || '');
        renderStoryline();
        renderRelationships(data.relationships);
        $('gameRound').textContent = `第${Math.max(1, rpgState.storyline.length)}轮`;
    } catch (fallbackErr) {
        console.error('[ERROR] actGame fallback:', fallbackErr);
        storyText.textContent = '❌ 故事展开失败，请重试';
    } finally {
        hideLoading();
        rpgAbortController = null;
        _rpgRequestActive = false;
    }
}

// ============================================================
// 区块 10 · Markdown渲染
// ============================================================
function renderMarkdown(text) {
    if (!text) return '';
    const raw = String(text);
    try {
        if (typeof marked !== 'undefined') {
            marked.setOptions({ breaks: true, gfm: true });
            const html = marked.parse(raw);
            if (typeof DOMPurify !== 'undefined') {
                return DOMPurify.sanitize(html);
            }
            return escapeHtml(html);
        }
    } catch (e) { 
        console.error('Render markdown failed:', e); 
        toast('内容渲染失败', 'warn');
    }
    // Fallback: basic HTML escape
    return raw.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
}

// Lightweight plain-text cleanup for status values and short snippets (NOT for story text)
function cleanText(t) {
    return String(t || '')
        .replace(/\n{3,}/g, '\n\n')
        .replace(/[ \t]+/g, ' ')
        .trim();
}

function renderStory(text) {
    storyText.innerHTML = renderMarkdown(text);
    storyBox.scrollTop = 0;
}

// --- Personal Panel Rendering ---
// Narrative section keys — these contain long text, NOT shown in sidebar
const NARRATIVE_KEYS = new Set([
    '背景', '简介', '外貌', '外貌描述', '描述', '性格', '性格特点',
    '故事概要', '过往', '回忆', '内心独白', '世界观', '阵营', '信仰',
    '关系', '关系网', '关系_map', '剧情', '剧情摘要', '任务详情', '日志',
    '事件', '事件记录', '备注', '说明', '提示', '介绍', '剧情回顾'
]);

// Data section keys — these contain stats/numbers to show compactly
const DATA_KEYS = new Set([
    '状态', '属性', '技能', '能力', '天赋', '专长', '特质',
    '装备', '背包', '物品', '道具', '武器', '防具', '金钱', '资源',
    '任务', '进度', '成就', '称号', '法术', '招式', '绝技', '判定'
]);

// Split a value into data pairs (key:value) and discard narrative tail
function extractDataPairs(rawValue) {
    const parts = rawValue.split(/\s+/);
    const pairs = [];
    let inData = true;
    for (const part of parts) {
        if (inData && part.includes(':')) {
            const colonIdx = part.indexOf(':');
            const label = part.slice(0, colonIdx);
            const value = part.slice(colonIdx + 1);
            // Stop collecting if label is clearly narrative (long, no shorthand)
            if (label.length > 8) { inData = false; continue; }
            pairs.push({ label: label, value: value });
        } else if (part.length < 3 || part.match(/^[0-9+\-*/%]+$/)) {
            // Short tokens or pure numbers after data pairs — likely still data
            continue;
        } else {
            // Sentence-like text → end of data region
            inData = false;
        }
    }
    return pairs;
}

// Check if a value string contains Markdown formatting
function hasMarkdownFormatting(str) {
    return /[*_`#\[\]~>|]/.test(str) && str.length > 6;
}

function renderKeyDataSection(key, cleanedValue) {
    const pairs = extractDataPairs(cleanedValue);
    if (pairs.length === 0) return '';

    let rowHtml = pairs.map(p => {
        let { label, value } = p;
        let cls = 'status-value';
        const num = parseFloat(value);
        if (!isNaN(num)) {
            cls += num <= 20 ? ' danger' : num >= 80 ? ' success' : ' highlight';
        }
        const renderedValue = hasMarkdownFormatting(value) ? renderMarkdown(value) : escapeHtml(value);
        const hpLabels = ['HP', '生命', '血量', '体力', '精力', '生命值', 'hp', 'Hp'];
        if (!isNaN(num) && hpLabels.includes(label)) {
            const pct = Math.min(100, Math.max(0, num));
            return '<div class="status-item status-bar-row">' +
                '<span class="status-label">'+escapeHtml(label)+'</span>' +
                '<span class="'+cls+'">'+renderedValue+'</span>' +
                '<div class="status-bar-track"><div class="status-bar-fill" style="width:'+pct+'%;background:'+(pct<=30?'var(--accent)':pct<=60?'var(--gold-dim)':'var(--gold)')+'"></div></div>' +
                '</div>';
        }
        return '<div class="status-item"><span class="status-label">'+escapeHtml(label)+'</span><span class="'+cls+' md-inline">'+renderedValue+'</span></div>';
    }).join('');
    return '<div class="status-section"><div class="status-section-title">'+escapeHtml(key)+'</div>'+rowHtml+'</div>';
}

function renderStatus(sectionsOrText) {
    if (!sectionsOrText) { personalContent.innerHTML = '<div class="status-empty">暂无状态数据</div>'; return; }
    if (typeof sectionsOrText === 'object' && !Array.isArray(sectionsOrText)) {
        let html = '';
        for (const [key, val] of Object.entries(sectionsOrText)) {
            if (key === '关系_map' || typeof val === 'object') continue;
            if (NARRATIVE_KEYS.has(key)) continue;
            const cleaned = cleanText(val);
            if (DATA_KEYS.has(key)) {
                html += renderKeyDataSection(escapeHtml(key), cleaned);
            } else if (cleaned.length < 60 && cleaned.includes(':')) {
                html += renderKeyDataSection(escapeHtml(key), cleaned);
            }
        }
        personalContent.innerHTML = html || '<div class="status-empty">暂无关键数据</div>';
        return;
    }
    let clean = String(sectionsOrText).replace(/【[^】]*】/g, '').trim();
    const items = clean.split(/\s+/).filter(s => s.includes(':'));
    if (items.length === 0) { personalContent.innerHTML = '<div class="status-empty">'+escapeHtml(clean)+'</div>'; return; }
    personalContent.innerHTML = items.map(i => {
        let n = i.indexOf(':'), label = i.slice(0,n).trim(), value = i.slice(n+1).trim(), cls = 'status-value';
        const num = parseFloat(value);
        if (!isNaN(num)) cls += num <= 20 ? ' danger' : num >= 80 ? ' success' : ' highlight';
        const rendVal = hasMarkdownFormatting(value) ? renderMarkdown(value) : escapeHtml(value);
        return '<div class="status-item"><span class="status-label">'+escapeHtml(label)+'</span><span class="'+cls+' md-inline">'+rendVal+'</span></div>';
    }).join('');
}

function parseStatusValue(val) {
    if (!val || !val.trim()) return '<div class="status-empty" style="padding:4px 0;">空</div>';
    const cleaned = cleanText(val);
    const items = cleaned.split(/\s+/).filter(s => s.includes(':'));
    if (!items.length) return '<div class="status-item"><span class="status-value md-inline">'+renderMarkdown(cleaned)+'</span></div>';
    return items.map(i => {
        let n = i.indexOf(':'), label = i.slice(0,n).trim(), value = i.slice(n+1).trim(), cls = 'status-value';
        const num = parseFloat(value);
        if (!isNaN(num)) cls += num <= 20 ? ' danger' : num >= 80 ? ' success' : ' highlight';
        const rendVal = hasMarkdownFormatting(value) ? renderMarkdown(value) : escapeHtml(value);
        return '<div class="status-item"><span class="status-label">'+escapeHtml(label)+'</span><span class="'+cls+' md-inline">'+rendVal+'</span></div>';
    }).join('');
}

function renderChoices(storyText) {
    choicesArea.innerHTML = '';
    if (!storyText) return;

    const text = String(storyText);

    // Check for 【判定】 - skill check challenge
    const sections = rpgState.sections || {};
    const judgement = sections['判定'];
    if (judgement) {
        const diffMatch = judgement.match(/难度[：:]\s*(\d+)/);
        const attrMatch = judgement.match(/属性[：:]\s*(\S+)/);
        const difficulty = diffMatch ? parseInt(diffMatch[1]) : 15;
        const attribute = attrMatch ? attrMatch[1] : '未知';
        const attrValue = getAttrValue(attribute);
        const modifier = calculateModifier(attrValue);
        const modStr = modifier >= 0 ? '+' + modifier : String(modifier);
        const realDifficulty = calculateRealDifficulty(difficulty, sections);

        const card = document.createElement('div');
        card.className = 'judgement-card';
        card.innerHTML = '<div class="judge-header">⚔️ 检定挑战</div>' +
            '<div class="judge-info-row">' +
                '<div class="judge-info"><span>属性</span><span>'+escapeHtml(attribute)+(attrValue!==null?' <small style="color:var(--text-dim)">('+escapeHtml(attrValue)+')</small>':'')+'</span></div>' +
                '<div class="judge-info"><span>修正</span><span class="'+(modifier>=0?'judge-mod-pos':'judge-mod-neg')+'">'+modStr+'</span></div>' +
            '</div>' +
            '<div class="judge-info-row">' +
                '<div class="judge-info"><span>基础难度</span><span>'+difficulty+'</span></div>' +
                '<div class="judge-info"><span>实际难度</span><span class="judge-diff">'+realDifficulty+'</span></div>' +
            '</div>' +
            '<div class="judge-desc">'+escapeHtml(judgement.slice(0, 200))+'</div>' +
            '<div class="judge-result" id="judgeResult" style="display:none;"></div>' +
            '<button class="judge-roll-btn">🎲 投掷 d20</button>';
        choicesArea.appendChild(card);
        const rollBtn = card.querySelector('.judge-roll-btn');
        rollBtn.addEventListener('click', () => doSkillCheck(difficulty, realDifficulty, modifier, attribute));
    }

    // Find all 【数字】 patterns, only keep those near end of text
    const allMatches = [];
    const re = /【(\d+)】([^【\n]*)/g;
    let m;
    while ((m = re.exec(text)) !== null) {
        allMatches.push({ num: m[1], text: m[2].trim(), pos: m.index });
    }

    // Keep only choices near the end (within last 300 chars), max 6
    const choices = allMatches.length > 2
        ? allMatches.filter(c => text.length - c.pos < 300).slice(-6)
        : allMatches;

    if (choices.length === 0) {
        const btn = document.createElement('button');
        btn.className = 'choice-btn';
        btn.textContent = '▶ 继续';
        btn.addEventListener('click', () => actGame('继续'));
        choicesArea.appendChild(btn);
        addCustomInput();
        return;
    }

    for (const c of choices) {
        const btn = document.createElement('button');
        btn.className = 'choice-btn';
        btn.textContent = `${c.num}. ${c.text}`;
        btn.addEventListener('click', () => actGame(c.text));
        choicesArea.appendChild(btn);
    }

    addCustomInput();
}

// ============================================================
// 区块 11 · 骰子技能检定
// ============================================================
// Extract attribute value from sections (search 属性, 状态, 技能)
function getAttrValue(attrName) {
    const sections = rpgState.sections || {};
    const candidates = ['属性', '状态', '技能', '能力'];
    for (const key of candidates) {
        const val = sections[key];
        if (!val) continue;
        const re = new RegExp(attrName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '[：:]\\s*(\\d+)', 'i');
        const m = cleanText(val).match(re);
        if (m) return parseInt(m[1]);
    }
    return null;
}

// Calculate modifier: value - 5 (attributes scale 1-10, 5 is average)
function calculateModifier(attrValue) {
    if (attrValue === null) return 0;
    return Math.max(-4, Math.min(5, attrValue - 5));
}

// Calculate real difficulty considering situation
function calculateRealDifficulty(baseDiff, sections) {
    let realDiff = baseDiff;
    const status = cleanText(sections['状态'] || '');
    const events = cleanText(sections['事件'] || '');

    // Injuries reduce effectiveness → raise difficulty
    const injuryMatch = status.match(/受伤|重伤|虚弱|中毒|诅咒|恐惧|混乱/);
    if (injuryMatch) realDiff += 2;

    // Favorable conditions → lower difficulty
    const buffMatch = status.match(/鼓舞|激励|专注|强化|祝福|潜行/);
    if (buffMatch) realDiff -= 2;

    // Environmental factors from events
    const envHard = events.match(/困难|危险|陷阱|伏击|暴风雨|黑暗/);
    if (envHard) realDiff += 2;
    const envEasy = events.match(/轻松|安全|休息|明亮|支援|熟悉/);
    if (envEasy) realDiff -= 2;

    return Math.max(5, Math.min(30, realDiff));
}

let skillCheckTimer = null;
let actGameStatusTimeout = null;

function doSkillCheck(baseDifficulty, realDifficulty, modifier, attribute) {
    const btn = document.querySelector('.judge-roll-btn');
    if (btn) btn.disabled = true;
    const resultEl = document.getElementById('judgeResult');
    if (!resultEl) return;
    resultEl.style.display = 'block';
    resultEl.className = 'judge-result';
    resultEl.innerHTML = '<span class="judge-rolling">🎲 投掷中...</span>';

    if (skillCheckTimer) clearTimeout(skillCheckTimer);
    skillCheckTimer = setTimeout(() => {
        skillCheckTimer = null;
        const roll = Math.floor(Math.random() * 20) + 1;
        const total = roll + modifier;
        const success = total >= realDifficulty;

        let breakdown = '📊 检定明细<br>';
        breakdown += '▸ d20 掷出: ' + roll + '<br>';
        breakdown += '▸ ' + escapeHtml(attribute) + '修正: ' + (modifier >= 0 ? '+' : '') + modifier + '<br>';
        breakdown += '▸ 总结果: ' + total + ' (vs ' + realDifficulty + ')<br>';
        if (baseDifficulty !== realDifficulty) {
            breakdown += '▸ 局势调整: ' + (realDifficulty > baseDifficulty ? '+' : '') + (realDifficulty - baseDifficulty) + '<br>';
        }
        breakdown += '<br>' + (success ? '✅ 检定成功！' : '❌ 检定失败！');

        resultEl.className = 'judge-result ' + (success ? 'judge-success' : 'judge-fail');
        resultEl.innerHTML = breakdown;

        let resultText;
        if (roll === 20) {
            resultText = '大成功！请描述极为顺利的发展。';
        } else if (roll === 1) {
            resultText = '大失败！请描述严重的失败后果，但仍继续推进故事。';
        } else if (success) {
            resultText = '成功。请描述检定通过后的顺利发展。';
        } else {
            resultText = '失败。请描述检定未通过后的发展和后果，故事继续进行。';
        }

        actGame('我进行' + attribute + '检定：掷出d20=' + roll + '（修正' + (modifier >= 0 ? '+' : '') + modifier + '=' + total + '，难度' + realDifficulty + '），' + resultText);
    }, 500);
}

function addCustomInput() {
    const wrap = document.createElement('div');
    wrap.className = 'custom-action-wrap';

    const inp = document.createElement('input');
    inp.type = 'text';
    inp.placeholder = '✏️ 自定义行动...';
    inp.className = 'custom-action-input';

    const btn = document.createElement('button');
    btn.className = 'custom-action-go';
    btn.textContent = '行动';
    btn.disabled = true;

    inp.addEventListener('input', () => { btn.disabled = !inp.value.trim(); });
    inp.addEventListener('keydown', e => {
        if (e.key === 'Enter' && inp.value.trim()) {
            actGame(inp.value.trim());
            inp.value = '';
            btn.disabled = true;
        }
    });
    btn.addEventListener('click', () => {
        if (inp.value.trim()) {
            actGame(inp.value.trim());
            inp.value = '';
            btn.disabled = true;
        }
    });

    wrap.appendChild(inp);
    wrap.appendChild(btn);
    choicesArea.appendChild(wrap);
}

// ============================================================
// 区块 12 · 故事线与关系
// ============================================================
function renderStoryline() {
    const body = $('storylineBody');
    const sl = rpgState.storyline || [];
    if (!body) return;
    if (sl.length === 0) {
        body.innerHTML = '<div class="status-empty" style="padding:12px 0;">尚无历史记录</div>';
        return;
    }
    body.innerHTML = sl.map((entry, i) => {
        const isCurrent = i === sl.length - 1;
        return `
        <div class="sl-entry ${isCurrent ? 'current' : ''}" data-round="${entry.round}">
            <div class="sl-round">#${entry.round}</div>
            <div class="sl-content">
                <div class="sl-choice"><span class="sl-choice-tag">▸</span>${escapeHtml(cleanText(entry.choice))}</div>
                <div class="sl-story">${escapeHtml(cleanText((entry.story || '').slice(0, 50)))}</div>
            </div>
            <div class="sl-actions">
                <button class="sl-review" data-action="review-round" data-round="${entry.round}" title="查看完整故事">📖</button>
                ${!isCurrent ? `<button class="sl-jump" data-action="jump-round" data-round="${entry.round}" title="回退到此轮">↩</button>` : ''}
            </div>
        </div>`;
    }).join('');
    body.querySelectorAll('[data-action="review-round"]').forEach(btn => {
        btn.addEventListener('click', () => reviewRound(parseInt(btn.dataset.round)));
    });
    body.querySelectorAll('[data-action="jump-round"]').forEach(btn => {
        btn.addEventListener('click', () => jumpToRound(parseInt(btn.dataset.round)));
    });
}

window.reviewRound = function(round) {
    const sl = rpgState.storyline || [];
    const entry = sl.find(e => e.round === round);
    if (!entry) return;
    const storyText = entry.story || '（无故事记录）';
    const isCurrent = round === (sl.length > 0 ? sl[sl.length - 1].round : -1);

    $('reviewContent').innerHTML = renderMarkdown(storyText);
    $('reviewTitle').textContent = `第 ${round} 轮 · ${cleanText((entry.choice || '').slice(0, 50))}${isCurrent ? '（当前）' : ''}`;
    $('reviewModal').style.display = 'flex';
};

$('reviewClose').addEventListener('click', () => {
    $('reviewModal').style.display = 'none';
});

$('reviewModal').addEventListener('click', (e) => {
    if (e.target === $('reviewModal')) $('reviewModal').style.display = 'none';
});

window.jumpToRound = async function(round) {
    if (!rpgState.sessionId) return;
    if (!confirm(`确定回到第 ${round} 轮？之后的选择将被清空。`)) return;
    showLoading('⏳ 回溯中...', `回到第 ${round} 轮`);
    try {
        const data = await api(`/api/rpg/session/${rpgState.sessionId}/branch`, {
            method: 'POST',
            body: JSON.stringify({ round })
        });
        if (data.error) { toast(data.error); return; }
        rpgState.storyline = data.storyline || [];
        renderStory(data.last_story || '');
        renderStatus(data.sections || data.last_state || '');
        renderChoices(data.last_story || '');
        renderStoryline();
        renderRelationships(data.relationships);
    } catch (e) {
        console.error('[ERROR] jumpToRound:', e);
        toast('回溯失败');
    } finally {
        hideLoading();
    }
};

$('storylineHeader').addEventListener('click', () => {
    const body = $('storylineBody');
    const toggle = $('storylineToggle');
    body.classList.toggle('collapsed');
    toggle.classList.toggle('collapsed');
});

function renderRelationships(rels) {
    const body = $('relsBody');
    if (!body) return;
    if (!rels || Object.keys(rels).length === 0) {
        body.innerHTML = '<div class="status-empty" style="padding:12px 0;">暂无关系数据</div>';
        return;
    }
    body.innerHTML = Object.entries(rels).map(([k, v]) =>
        `<div class="status-item"><span class="status-label">${escapeHtml(k)}</span><span class="status-value highlight">${escapeHtml(v)}</span></div>`
    ).join('');
}

$('exitGameBtn').addEventListener('click', () => {
    $('exitConfirmModal').classList.add('show');
});

$('exitCancelBtn').addEventListener('click', () => {
    $('exitConfirmModal').classList.remove('show');
});

$('exitConfirmBtn').addEventListener('click', () => {
    $('exitConfirmModal').classList.remove('show');
    hideLoading();
    if (skillCheckTimer) { clearTimeout(skillCheckTimer); skillCheckTimer = null; }
    if (actGameStatusTimeout) { clearTimeout(actGameStatusTimeout); actGameStatusTimeout = null; }
    if (rpgAbortController) {
        rpgAbortController.abort();
        rpgAbortController = null;
    }
    rpgState = { sessionId: null, world: null, playerName: '', storyline: [] };
    gameScreen.style.display = 'none';
    worldSelectScreen.style.display = 'block';
    loadSessions();
    if (shareBtn) shareBtn.style.display = 'none';
});

// ============================================================
// 区块 13 · Agent管理UI
// ============================================================
const manageBtn = $('manageBtn');
const manageModal = $('manageModal');
const modalClose = $('modalClose');

manageBtn.addEventListener('click', () => { manageModal.classList.add('show'); renderAgentList(); });
modalClose.addEventListener('click', () => manageModal.classList.remove('show'));
manageModal.addEventListener('click', e => { if (e.target === manageModal) manageModal.classList.remove('show'); });

async function renderAgentList() {
    try {
        const agents = await api('/api/agents');
        $('agentList').innerHTML = agents.map(a => `
            <div class="agent-list-item">
                <span class="ali-emoji">${escapeHtml(a.avatar || '🧔')}</span>
                <span class="ali-name"><strong>${escapeHtml(a.name)}</strong> ${a.title ? '<small style="color:var(--text-dim)">— ' + escapeHtml(a.title) + '</small>' : ''}</span>
                <span class="ali-actions">
                    <button class="btn-edit" data-aid="${escapeHtml(a.id)}">✏️</button>
                    <button class="btn-del" data-aid="${escapeHtml(a.id)}">🗑️</button>
                </span>
            </div>`).join('');

        document.querySelectorAll('.btn-edit').forEach(btn => {
            btn.addEventListener('click', () => editAgent(btn.dataset.aid));
        });
        document.querySelectorAll('.btn-del').forEach(btn => {
            btn.addEventListener('click', () => deleteAgent(btn.dataset.aid));
        });
    } catch (e) {
        console.error('[ERROR] renderAgentList:', e);
        $('agentList').innerHTML = '<div class="status-empty">加载失败</div>';
    }
}

window.deleteAgent = async function(id) {
    if (!confirm('确定要删除这个智能体吗？')) return;
    try {
        await api('/api/agents/' + id, { method: 'DELETE' });
        renderAgentList();
        loadAgents();
    } catch (e) {
        console.error('[ERROR] deleteAgent:', e);
        toast('删除失败', 'error');
    }
};

const editorModal = $('editorModal');
const editorClose = $('editorClose');
let editingAgentId = null;

window.editAgent = async function(id) {
    editingAgentId = id;
    try {
        const agents = await api('/api/agents');
        const a = agents.find(x => x.id === id);
        if (!a) return;
        $('editorTitle').textContent = '✏️ 编辑智能体';
        $('editId').value = a.id; $('editId').disabled = true;
        $('editName').value = a.name;
        $('editAvatar').value = a.avatar || '🧔';
        $('editTitle').value = a.title || '';
        $('editModel').value = a.model || 'mimo-v2.5-free';
        $('editTemp').value = a.temperature || 0.8;
        $('editGreeting').value = a.greeting || '';
        $('editPrompt').value = a.system_prompt || '';
        editorModal.classList.add('show');
    } catch (e) {
        console.error('[ERROR] editAgent:', e);
        toast('加载智能体信息失败', 'error');
    }
};

$('addAgentBtn').addEventListener('click', () => {
    editingAgentId = null;
    $('editorTitle').textContent = '➕ 新建智能体';
    ['editId','editName','editAvatar','editTitle','editGreeting','editPrompt'].forEach(id => $(id).value = '');
    $('editAvatar').value = '🧔';
    $('editModel').value = 'mimo-v2.5-free';
    $('editTemp').value = 0.85;
    $('editId').disabled = false;
    editorModal.classList.add('show');
});

$('editorClose').addEventListener('click', () => editorModal.classList.remove('show'));
$('editorCancel').addEventListener('click', () => editorModal.classList.remove('show'));
editorModal.addEventListener('click', e => { if (e.target === editorModal) editorModal.classList.remove('show'); });

$('editorSave').addEventListener('click', async () => {
    try {
        const data = {
            id: $('editId').value.trim(),
            name: $('editName').value.trim(),
            avatar: $('editAvatar').value.trim() || '🧔',
            title: $('editTitle').value.trim(),
            model: $('editModel').value.trim() || 'mimo-v2.5-free',
            temperature: parseFloat($('editTemp').value) || 0.85,
            greeting: $('editGreeting').value.trim(),
            system_prompt: $('editPrompt').value.trim()
        };
        if (!data.id || !data.name) { toast('ID和名称不能为空'); return; }
        if (editingAgentId) {
            await api('/api/agents/' + editingAgentId, {
                method: 'PUT',
                body: JSON.stringify(data)
            });
        } else {
            const res = await api('/api/agents', {
                method: 'POST',
                body: JSON.stringify(data)
            });
            if (res.error) { toast(res.error); return; }
        }
        editorModal.classList.remove('show');
        renderAgentList();
        loadAgents();
    } catch (e) {
        console.error('[ERROR] editorSave:', e);
        toast('保存失败');
    }
});

// ============================================================
// 区块 14 · 世界管理UI
// ============================================================
const manageWorldBtn = $('manageWorldBtn');
const worldManageModal = $('worldManageModal');
const worldManageClose = $('worldManageClose');

manageWorldBtn.addEventListener('click', () => {
    worldManageModal.classList.add('show');
    renderWorldList();
    renderMySubmissions();
});
worldManageClose.addEventListener('click', () => worldManageModal.classList.remove('show'));
worldManageModal.addEventListener('click', e => { if (e.target === worldManageModal) worldManageModal.classList.remove('show'); });

async function renderWorldList() {
    try {
        const worlds = await api('/api/rpg/worlds');
        const isAdmin = currentUser && currentUser.role === 'admin';
        $('worldManageGrid').innerHTML = worlds.map((w, i) => `
            <div class="world-list-item" data-wid="${escapeHtml(w.id)}">
                ${isAdmin ? `<span class="wli-order">
                    <button class="btn-order-up" data-wid="${escapeHtml(w.id)}" ${i === 0 ? 'disabled' : ''}>▲</button>
                    <button class="btn-order-down" data-wid="${escapeHtml(w.id)}" ${i === worlds.length - 1 ? 'disabled' : ''}>▼</button>
                </span>` : ''}
                <span style="font-size:22px;">${escapeHtml(w.emoji || '📖')}</span>
                <span style="flex:1;"><strong>${escapeHtml(w.name)}</strong> <small style="color:var(--text-dim)">${escapeHtml(w.genre || '')}</small></span>
                ${isAdmin ? `<span class="ali-actions">
                    <button class="btn-edit-w" data-wid="${escapeHtml(w.id)}">✏️</button>
                    <button class="btn-del-w" data-wid="${escapeHtml(w.id)}">🗑️</button>
                </span>` : ''}
            </div>`).join('');

        if (isAdmin) {
            document.querySelectorAll('.btn-order-up').forEach(btn => {
                btn.addEventListener('click', () => moveWorldUp(btn.dataset.wid));
            });
            document.querySelectorAll('.btn-order-down').forEach(btn => {
                btn.addEventListener('click', () => moveWorldDown(btn.dataset.wid));
            });
            document.querySelectorAll('.btn-edit-w').forEach(btn => {
                btn.addEventListener('click', () => editWorld(btn.dataset.wid));
            });
            document.querySelectorAll('.btn-del-w').forEach(btn => {
                btn.addEventListener('click', () => deleteWorld(btn.dataset.wid));
            });
        }
    } catch (e) {
        console.error('[ERROR] renderWorldList:', e);
        $('worldManageGrid').innerHTML = '<div class="status-empty">加载失败</div>';
    }
}

window.moveWorldUp = async function(worldId) {
    try {
        const worlds = await api('/api/rpg/worlds');
        const idx = worlds.findIndex(w => w.id === worldId);
        if (idx <= 0) return;
        [worlds[idx - 1], worlds[idx]] = [worlds[idx], worlds[idx - 1]];
        const order = worlds.map(w => w.id);
        await api('/api/rpg/worlds/reorder', { method: 'POST', body: JSON.stringify({ order }) });
        renderWorldList();
        loadWorlds();
    } catch (e) {
        console.error('[ERROR] moveWorldUp:', e);
        toast('排序失败', 'error');
    }
};

window.moveWorldDown = async function(worldId) {
    try {
        const worlds = await api('/api/rpg/worlds');
        const idx = worlds.findIndex(w => w.id === worldId);
        if (idx < 0 || idx >= worlds.length - 1) return;
        [worlds[idx], worlds[idx + 1]] = [worlds[idx + 1], worlds[idx]];
        const order = worlds.map(w => w.id);
        await api('/api/rpg/worlds/reorder', { method: 'POST', body: JSON.stringify({ order }) });
        renderWorldList();
        loadWorlds();
    } catch (e) {
        console.error('[ERROR] moveWorldDown:', e);
        toast('排序失败', 'error');
    }
};

window.deleteWorld = async function(id) {
    if (!confirm('确定要删除这个世界书吗？')) return;
    try {
        const data = await api(`/api/rpg/worlds/${id}`, { method: 'DELETE' });
        if (data.error) {
            toast(data.error);
            return;
        }
        renderWorldList();
        loadWorlds();
        if (rpgState.world && rpgState.world.id === id) {
            rpgState = { sessionId: null, world: null, playerName: '', storyline: [] };
            gameScreen.style.display = 'none';
            worldSelectScreen.style.display = 'block';
        }
    } catch (e) {
        console.error('[ERROR] deleteWorld:', e);
        toast('删除失败', 'error');
    }
};

async function renderMySubmissions() {
    try {
        const subs = await api('/api/rpg/worlds/my-submissions');
        $('mySubsCount').textContent = subs.length > 0 ? `(${subs.length}个待审核)` : '(无)';
        if (subs.length === 0) { $('mySubmissionsList').innerHTML = '<div class="status-empty" style="padding:4px 0;">暂无投稿</div>'; return; }
        $('mySubmissionsList').innerHTML = subs.map(s => `
            <div class="world-list-item">
                <span style="font-size:22px;">${escapeHtml(s.emoji || '📖')}</span>
                <span style="flex:1;"><strong>${escapeHtml(s.name)}</strong><br><small style="color:var(--text-dim)">状态：${s.status === 'pending' ? '⏳ 待审核' : '❌ 已拒绝'}</small></span>
                <span class="ali-actions">
                    <button data-action="edit-sub" data-sid="${escapeHtml(s.id)}">✏️</button>
                    <button class="del" data-action="del-sub" data-sid="${escapeHtml(s.id)}">🗑️</button>
                </span>
            </div>
        `).join('');
        $('mySubmissionsList').querySelectorAll('[data-action="edit-sub"]').forEach(btn => {
            btn.addEventListener('click', () => editMySub(btn.dataset.sid));
        });
        $('mySubmissionsList').querySelectorAll('[data-action="del-sub"]').forEach(btn => {
            btn.addEventListener('click', () => delMySub(btn.dataset.sid));
        });
    } catch (e) {
        $('mySubsCount').textContent = '(加载失败)';
        $('mySubmissionsList').innerHTML = '<div class="status-empty">加载失败</div>';
        console.error('[ERROR] renderMySubmissions:', e);
    }
}
window.editMySub = async function(id) {
    try {
        const subs = await api('/api/rpg/worlds/my-submissions');
        const s = subs.find(x => x.id === id); if (!s) return;
        $('sEditId').value = s.id; $('sEditId').disabled = true;
        $('sEditName').value = s.name || ''; $('sEditEmoji').value = s.emoji || '🌟';
        $('sEditGenre').value = s.genre || ''; $('sEditDesc').value = s.desc || '';
        $('sEditPrompt').value = s.system_prompt || ''; $('sEditTemp').value = s.temperature || 0.85;
        $('sEditMaxTokens').value = s.max_tokens || 700;
        window._editingSubId = id;
        submitWorldModal.classList.add('show');
    } catch (e) {
        console.error('[ERROR] editMySub:', e);
        toast('加载投稿信息失败', 'error');
    }
};
window.delMySub = async function(id) {
    if (!confirm('确定删除这个投稿？')) return;
    try {
        await api(`/api/rpg/worlds/submissions/${id}`, { method: 'DELETE' });
        renderMySubmissions();
    } catch (e) {
        console.error('[ERROR] delMySub:', e);
        toast('删除失败', 'error');
    }
};

const worldEditorModal = $('worldEditorModal');
const worldEditorClose = $('worldEditorClose');
let editingWorldId = null;

window.editWorld = async function(id) {
    editingWorldId = id;
    try {
        const worlds = await api('/api/rpg/worlds');
        const w = worlds.find(x => x.id === id);
        if (!w) return;
        $('worldEditorTitle').textContent = '✏️ 编辑世界书';
        $('wEditName').value = w.name || '';
        $('wEditId').value = w.id || '';
        $('wEditEmoji').value = w.emoji || '📖';
        $('wEditGenre').value = w.genre || '';
        $('wEditDesc').value = w.desc || '';
        $('wEditPrompt').value = w.system_prompt || '';
        $('wEditTemp').value = w.temperature || 0.85;
        $('wEditMaxTokens').value = w.max_tokens || 700;
        $('wEditId').disabled = true;
        worldEditorModal.classList.add('show');
    } catch (e) {
        console.error('[ERROR] editWorld:', e);
        toast('加载世界书信息失败', 'error');
    }
};

$('addWorldBtn').addEventListener('click', () => {
    editingWorldId = null;
    $('worldEditorTitle').textContent = '📖 新建世界书';
    ['wEditName','wEditId','wEditDesc','wEditPrompt'].forEach(id => $(id).value = '');
    $('wEditEmoji').value = '🌟';
    $('wEditGenre').value = '';
    $('wEditTemp').value = 0.85;
    $('wEditMaxTokens').value = 700;
    $('wEditId').disabled = false;
    worldEditorModal.classList.add('show');
});

$('worldEditorClose').addEventListener('click', () => worldEditorModal.classList.remove('show'));
$('worldEditorCancel').addEventListener('click', () => worldEditorModal.classList.remove('show'));
worldEditorModal.addEventListener('click', e => { if (e.target === worldEditorModal) worldEditorModal.classList.remove('show'); });

$('worldEditorSave').addEventListener('click', async () => {
    try {
        const id = $('wEditId').value.trim();
        const name = $('wEditName').value.trim();
        if (!id || !name) { toast('ID和名称不能为空'); return; }
        const world = {
            id,
            name,
            emoji: $('wEditEmoji').value.trim() || '📖',
            genre: $('wEditGenre').value.trim(),
            desc: $('wEditDesc').value.trim(),
            system_prompt: $('wEditPrompt').value.trim(),
            temperature: parseFloat($('wEditTemp').value) || 0.85,
            max_tokens: parseInt($('wEditMaxTokens').value) || 700
        };
        let worlds = await api('/api/rpg/worlds');
        if (editingWorldId) {
            const idx = worlds.findIndex(w => w.id === editingWorldId);
            if (idx >= 0) worlds[idx] = world;
        } else {
            if (worlds.some(w => w.id === id)) { toast('该ID已存在'); return; }
            worlds.push(world);
        }
        await api('/api/rpg/worlds', {
            method: 'POST',
            body: JSON.stringify(worlds)
        });
        worldEditorModal.classList.remove('show');
        renderWorldList();
        loadWorlds();
    } catch (e) {
        console.error('[ERROR] worldEditorSave:', e);
        toast('保存失败：' + e.message);
    }
});

// ============================================================
// 区块 15 · 管理员面板
// ============================================================
const adminBtn = $('adminBtn');
const adminModal = $('adminModal');
const adminClose = $('adminClose');
const adminCancel = $('adminCancel');

adminBtn.addEventListener('click', () => {
    adminModal.classList.add('show');
    loadAdminModels();
    loadAdminUsers();
    loadAdminKeys();
});
adminClose.addEventListener('click', () => adminModal.classList.remove('show'));
adminCancel.addEventListener('click', () => adminModal.classList.remove('show'));
adminModal.addEventListener('click', e => { if (e.target === adminModal) adminModal.classList.remove('show'); });

document.querySelectorAll('.admin-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.admin-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const panel = tab.dataset.panel;
        $('adminModelsPanel').style.display = panel === 'models' ? 'block' : 'none';
        $('adminUsersPanel').style.display = panel === 'users' ? 'block' : 'none';
        $('adminCreditKeysPanel').style.display = panel === 'creditkeys' ? 'block' : 'none';
        $('adminStatsPanel').style.display = panel === 'stats' ? 'block' : 'none';
        $('adminSubmissionsPanel').style.display = panel === 'submissions' ? 'block' : 'none';
        if (panel === 'stats') { loadAdminStats(); loadAdminAllSessions(); }
        if (panel === 'submissions') loadAdminSubmissions();
    });
});

// Admin Models
async function loadAdminModels() {
    try {
        const models = await api('/api/admin/models');
        $('adminModelsList').innerHTML = models.map(m => `
            <div class="admin-list-item">
                <div class="ali-main">
                    <div class="ali-name">${escapeHtml(m.label)}</div>
                    <div class="ali-meta">ID: ${escapeHtml(m.model_id)} | ${m.credits_per_1k}积分/千Token | 优先级: ${m.priority} | ${m.enabled ? '✅ 启用' : '❌ 禁用'}${m.api_base ? ' | 🔗 自定义API' : ''}</div>
                </div>
                <div class="ali-actions">
                    <button data-action="edit-admin-model" data-mid="${m.id}">✏️</button>
                    <button class="del" data-action="delete-admin-model" data-mid="${m.id}">🗑️</button>
                </div>
            </div>
        `).join('');
        $('adminModelsList').querySelectorAll('[data-action="edit-admin-model"]').forEach(btn => {
            btn.addEventListener('click', () => editAdminModel(parseInt(btn.dataset.mid)));
        });
        $('adminModelsList').querySelectorAll('[data-action="delete-admin-model"]').forEach(btn => {
            btn.addEventListener('click', () => deleteAdminModel(parseInt(btn.dataset.mid)));
        });
    } catch (e) {
        console.error('[ERROR] loadAdminModels:', e);
        $('adminModelsList').innerHTML = '<div class="status-empty">加载失败</div>';
    }
}

const modelEditorModal = $('modelEditorModal');
const modelEditorClose = $('modelEditorClose');
let editingModelId = null;

$('addModelBtn').addEventListener('click', () => {
    editingModelId = null;
    $('modelEditorTitle').textContent = '➕ 添加模型';
    ['mEditModelId','mEditName','mEditLabel','mEditApiBase','mEditApiKey'].forEach(id => $(id).value = '');
    $('mEditCreditsPer1k').value = '1';
    $('mEditPriority').value = '100';
    $('mEditEnabled').checked = true;
    modelEditorModal.classList.add('show');
});

window.editAdminModel = async function(id) {
    editingModelId = id;
    const models = await api('/api/admin/models');
    const m = models.find(x => x.id === id);
    if (!m) return;
    $('modelEditorTitle').textContent = '✏️ 编辑模型';
    $('mEditModelId').value = m.model_id;
    $('mEditName').value = m.name;
    $('mEditLabel').value = m.label;
    $('mEditCreditsPer1k').value = m.credits_per_1k || m.price_per_call || 1;
    $('mEditPriority').value = m.priority || 100;
    $('mEditApiBase').value = m.api_base || '';
    $('mEditApiKey').value = m.has_api_key ? '********' : '';
    $('mEditApiKey').placeholder = m.has_api_key ? '已保存，留空保持不变' : 'sk-xxxxxxxx';
    $('mEditEnabled').checked = m.enabled;
    modelEditorModal.classList.add('show');
};

$('modelEditorClose').addEventListener('click', () => modelEditorModal.classList.remove('show'));
$('modelEditorCancel').addEventListener('click', () => modelEditorModal.classList.remove('show'));
modelEditorModal.addEventListener('click', e => { if (e.target === modelEditorModal) modelEditorModal.classList.remove('show'); });

$('modelEditorSave').addEventListener('click', async () => {
    const data = {
        model_id: $('mEditModelId').value.trim(),
        name: $('mEditName').value.trim(),
        label: $('mEditLabel').value.trim(),
        credits_per_1k: parseInt($('mEditCreditsPer1k').value) || 1,
        priority: parseInt($('mEditPriority').value) || 100,
        enabled: $('mEditEnabled').checked,
        api_base: $('mEditApiBase').value.trim(),
        api_key: $('mEditApiKey').value.trim()
    };
    if (!data.model_id || !data.name || !data.label) {
        toast('model_id、名称和标签不能为空');
        return;
    }

    if (editingModelId) {
        await api(`/api/admin/models/${editingModelId}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    } else {
        const res = await api('/api/admin/models', {
            method: 'POST',
            body: JSON.stringify(data)
        });
        if (res.error) { toast(res.error); return; }
    }

    modelEditorModal.classList.remove('show');
    loadAdminModels();
    populateModels();
});

window.deleteAdminModel = async function(id) {
    if (!confirm('确定要删除这个模型吗？')) return;
    await api(`/api/admin/models/${id}`, { method: 'DELETE' });
    loadAdminModels();
    populateModels();
};

// Admin Users
async function loadAdminUsers() {
    const users = await api('/api/admin/users');
    $('adminUsersList').innerHTML = users.map(u => `
        <div class="admin-list-item">
            <div class="ali-main">
                <div class="ali-name">${escapeHtml(u.username)} ${u.role === 'admin' ? '(管理员)' : ''}</div>
                <div class="ali-meta">ID: ${u.id} | 积分: ${u.credits} | 注册: ${new Date(u.created_at).toLocaleDateString()}</div>
            </div>
            <div class="ali-actions">
                <button class="btn-edit-u" data-uid="${u.id}">💰</button>
                <button class="btn-del-u" data-uid="${u.id}">🗑️</button>
            </div>
        </div>
    `).join('');
    
    document.querySelectorAll('.btn-edit-u').forEach(btn => {
        btn.addEventListener('click', () => editAdminUser(parseInt(btn.dataset.uid)));
    });
    document.querySelectorAll('.btn-del-u').forEach(btn => {
        btn.addEventListener('click', () => deleteAdminUser(parseInt(btn.dataset.uid)));
    });
}

window.editAdminUser = async function(id) {
    const users = await api('/api/admin/users');
    const u = users.find(x => x.id === id);
    if (!u) return;
    const newCredits = prompt(`为 ${u.username} 设置新积分：`, u.credits);
    if (newCredits === null) return;
    const credits = parseInt(newCredits);
    if (isNaN(credits) || credits < 0) {
        toast('请输入有效的积分数量');
        return;
    }
    await api(`/api/admin/users/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ credits })
    });
    loadAdminUsers();
};

window.deleteAdminUser = async function(id) {
    if (!confirm('确定要删除这个用户吗？')) return;
    await api(`/api/admin/users/${id}`, { method: 'DELETE' });
    loadAdminUsers();
};

// --- Credit Keys (Admin) ---
async function loadAdminKeys() {
    const keys = await api('/api/admin/credit-keys');
    $('adminKeysList').innerHTML = keys.map(k => `
        <div class="key-list-item">
            <span class="key-code">${escapeHtml(k.key)}</span>
            <span class="key-info">
                <div>💰 ${k.credits} 积分</div>
                <div class="key-meta">
                    ${k.used
                        ? `<span class="key-used">✅ 已使用 (用户ID: ${k.used_by})</span>`
                        : `<span class="key-unused">🔓 未使用</span>`}
                    · ${new Date(k.created_at).toLocaleDateString()}
                </div>
            </span>
            ${!k.used ? `<span class="ali-actions"><button class="del" data-action="delete-key" data-kid="${k.id}">🗑️</button></span>` : ''}
        </div>
    `).join('');
    $('adminKeysList').querySelectorAll('[data-action="delete-key"]').forEach(btn => {
        btn.addEventListener('click', () => deleteKey(parseInt(btn.dataset.kid)));
    });
}

$('genKeyBtn').addEventListener('click', async () => {
    try {
        const credits = parseInt($('keyCredits').value) || 100;
        const count = parseInt($('keyCount').value) || 1;
        const data = await api('/api/admin/credit-keys', {
            method: 'POST',
            body: JSON.stringify({ credits, count })
        });
        if (data.error) { toast(data.error); return; }
        const keysText = data.keys.join('\n');
        toast(`已生成 ${data.count} 个 ${data.credits} 积分密钥：\n\n${keysText}\n\n请复制并分发给用户`);
        loadAdminKeys();
    } catch (e) {
        console.error('[ERROR] genKeyBtn:', e);
        toast('生成密钥失败：' + e.message);
    }
});

window.deleteKey = async function(id) {
    if (!confirm('确定要删除这个未使用的密钥吗？')) return;
    await api(`/api/admin/credit-keys/${id}`, { method: 'DELETE' });
    loadAdminKeys();
};

// ============================================================
// 区块 16 · 个人API与用户模型
// ============================================================
const apiSettingsBtn = $('apiSettingBtn');
const apiSettingsModal = $('apiSettingsModal');
const apiSettingsClose = $('apiSettingsClose');

apiSettingsBtn.addEventListener('click', async () => {
    await loadPersonalApiConfig();
    await loadUserModels();
    apiSettingsModal.classList.add('show');
});
apiSettingsClose.addEventListener('click', () => apiSettingsModal.classList.remove('show'));
apiSettingsModal.addEventListener('click', e => { if (e.target === apiSettingsModal) apiSettingsModal.classList.remove('show'); });

async function loadPersonalApiConfig() {
    // 已迁移至模型级别配置，此处保留空函数避免外部调用报错
}

window.fillNewModelApiUrl = function() {
    const provider = $('newModelProvider').value;
    const presets = {
        siliconflow: {
            url: 'https://api.siliconflow.cn/v1/chat/completions',
            placeholder: 'deepseek-ai/DeepSeek-V3'
        },
        deepseek: {
            url: 'https://api.deepseek.com/v1/chat/completions',
            placeholder: 'deepseek-chat'
        },
        qwen: {
            url: 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
            placeholder: 'qwen-plus'
        },
        zhipu: {
            url: 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
            placeholder: 'glm-4-flash'
        },
        moonshot: {
            url: 'https://api.moonshot.cn/v1/chat/completions',
            placeholder: 'moonshot-v1-8k'
        }
    };
    if (presets[provider]) {
        $('newModelApiBase').value = presets[provider].url;
        if (presets[provider].placeholder && !$('newModelId').value) {
            $('newModelId').placeholder = presets[provider].placeholder;
        }
    }
}

// --- User Models Management ---
async function loadUserModels() {
    try {
        const models = await api('/api/auth/models');
        const list = $('userModelsList');
        if (models.length === 0) {
            list.innerHTML = '<div class="status-empty" style="padding:16px;">暂无自定义模型，点击上方"+ 添加模型"添加</div>';
            return;
        }
        list.innerHTML = models.map(m => {
            const apiStatus = m.api_base ? (m.has_api_key ? '🔗 已配置API' : '⚠️ 缺API Key') : '🔑 用默认API';
            return `
            <div class="admin-list-item">
                <div class="ali-main">
                    <div class="ali-name">${escapeHtml(m.label)}</div>
                    <div class="ali-meta">ID: ${escapeHtml(m.model_id)} | 🔑 自有API模型（不计费）| ${apiStatus}</div>
                </div>
                <div class="ali-actions">
                    <button data-action="edit-user-model" data-model-id="${escapeHtml(m.model_id)}" title="编辑">✏️</button>
                    <button class="del" data-action="delete-user-model" data-model-id="${escapeHtml(m.model_id)}" title="删除">🗑️</button>
                </div>
            </div>`;
        }).join('');
        $('userModelsList').querySelectorAll('[data-action="edit-user-model"]').forEach(btn => {
            btn.addEventListener('click', () => editUserModel(btn.dataset.modelId));
        });
        $('userModelsList').querySelectorAll('[data-action="delete-user-model"]').forEach(btn => {
            btn.addEventListener('click', () => deleteUserModel(btn.dataset.modelId));
        });
    } catch (e) {
        console.error('[ERROR] loadUserModels:', e);
        $('userModelsList').innerHTML = '<div class="status-empty" style="padding:16px;color:#ff6b6b;">加载失败</div>';
    }
}

async function deleteUserModel(modelId) {
    if (!confirm(`确定删除模型 "${modelId}" 吗？`)) return;
    try {
        await api(`/api/auth/models/${modelId}`, { method: 'DELETE' });
        toast('模型已删除', 'success');
        loadUserModels();
        populateModels();
    } catch {
        toast('删除失败', 'error');
    }
}

window.editUserModel = async function(modelId) {
    try {
        const models = await api('/api/auth/models');
        const m = models.find(x => x.model_id === modelId);
        if (!m) { toast('模型不存在', 'error'); return; }
        $('umEditId').value = m.model_id;
        $('umEditName').value = m.name || '';
        $('umEditLabel').value = m.label || '';
        $('umEditApiBase').value = m.api_base || '';
        $('umEditApiKey').value = m.has_api_key ? '********' : '';
        $('umEditApiKey').placeholder = m.has_api_key ? '已保存，留空保持不变' : 'sk-xxxxxxxx';
        $('umEditMsg').textContent = '';
        $('userModelEditorModal').classList.add('show');
    } catch (e) {
        console.error('[ERROR] editUserModel:', e);
        toast('加载模型信息失败', 'error');
    }
};

$('userModelEditorClose').addEventListener('click', () => {
    $('userModelEditorModal').classList.remove('show');
});
$('userModelEditorModal').addEventListener('click', e => {
    if (e.target === $('userModelEditorModal')) $('userModelEditorModal').classList.remove('show');
});

$('umEditSaveBtn').addEventListener('click', async () => {
    const modelId = $('umEditId').value.trim();
    const data = {
        name: $('umEditName').value.trim(),
        label: $('umEditLabel').value.trim(),
        api_base: $('umEditApiBase').value.trim(),
        api_key: $('umEditApiKey').value.trim()
    };
    if (!data.name || !data.label) {
        $('umEditMsg').textContent = '❌ 名称和标签不能为空';
        return;
    }
    $('umEditSaveBtn').disabled = true;
    $('umEditMsg').textContent = '⏳ 保存中...';
    try {
        await api(`/api/auth/models/${modelId}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
        toast('模型已更新', 'success');
        $('userModelEditorModal').classList.remove('show');
        loadUserModels();
        populateModels();
    } catch (e) {
        console.error('[ERROR] updateUserModel:', e);
        $('umEditMsg').textContent = '❌ 保存失败';
    }
    $('umEditSaveBtn').disabled = false;
});

$('addUserModelBtn').addEventListener('click', () => {
    $('addUserModelForm').style.display = 'block';
    $('newModelId').value = '';
    $('newModelName').value = '';
    $('newModelLabel').value = '';
    $('newModelProvider').value = '';
    $('newModelApiBase').value = '';
    $('newModelApiKey').value = '';
    $('newModelId').focus();
});

$('cancelNewModelBtn').addEventListener('click', () => {
    $('addUserModelForm').style.display = 'none';
});

$('newModelProvider').addEventListener('change', fillNewModelApiUrl);

$('saveNewModelBtn').addEventListener('click', async () => {
    const modelId = $('newModelId').value.trim();
    const name = $('newModelName').value.trim();
    const label = $('newModelLabel').value.trim();
    const apiBase = $('newModelApiBase').value.trim();
    const apiKey = $('newModelApiKey').value.trim();

    if (!modelId || !name || !label) {
        toast('请填写模型ID、名称和标签', 'error');
        return;
    }
    if ((apiBase && !apiKey) || (!apiBase && apiKey)) {
        toast('API 地址和 Key 必须同时填写，或都留空', 'error');
        return;
    }

    try {
        await api('/api/auth/models', {
            method: 'POST',
            body: JSON.stringify({ model_id: modelId, name, label, api_base: apiBase, api_key: apiKey })
        });
        toast('模型添加成功', 'success');
        $('addUserModelForm').style.display = 'none';
        loadUserModels();
        populateModels();
    } catch (e) {
        console.error('[ERROR] addUserModel:', e);
        toast('添加失败，模型可能已存在', 'error');
    }
});

apiSettingsModal.addEventListener('click', e => {
    if (e.target === apiSettingsModal) apiSettingsModal.classList.remove('show');
});

apiSettingsModal.addEventListener('show', loadUserModels);

function updateFreeModeDisplay(hasApi) {
    const display = $('freeModeDisplay');
    if (display) display.style.display = hasApi ? 'inline' : 'none';
}

// ============================================================
// 区块 17 · 兑换与投稿
// ============================================================
const redeemBtn = $('redeemBtn');
const redeemModal = $('redeemModal');
const redeemClose = $('redeemClose');

redeemBtn.addEventListener('click', () => {
    $('redeemCode').value = '';
    $('redeemMsg').textContent = '';
    redeemModal.classList.add('show');
});
redeemClose.addEventListener('click', () => redeemModal.classList.remove('show'));
redeemModal.addEventListener('click', e => { if (e.target === redeemModal) redeemModal.classList.remove('show'); });

$('redeemSubmitBtn').addEventListener('click', async () => {
    const code = $('redeemCode').value.trim().toUpperCase();
    if (!code) { $('redeemMsg').textContent = '❌ 请输入密钥'; return; }
    $('redeemSubmitBtn').disabled = true;
    $('redeemMsg').textContent = '⏳ 兑换中...';
    try {
        const data = await api('/api/redeem', {
            method: 'POST',
            body: JSON.stringify({ key: code })
        });
        if (data.error) {
            $('redeemMsg').textContent = '❌ ' + data.error;
        } else {
            $('redeemMsg').textContent = '✅ ' + data.message;
            currentUser.credits = data.credits_left;
            updateUserInfo();
        }
    } catch {
        $('redeemMsg').textContent = '❌ 兑换失败';
    }
    $('redeemSubmitBtn').disabled = false;
});

$('redeemCode').addEventListener('keydown', e => {
    if (e.key === 'Enter') $('redeemSubmitBtn').click();
});

// --- World Submission ---
const submitWorldBtn = $('submitWorldBtn');
const submitWorldModal = $('submitWorldModal');
const submitWorldClose = $('submitWorldClose');

submitWorldBtn.addEventListener('click', () => {
    window._editingSubId = null;
    $('sEditId').disabled = false;
    ['sEditId','sEditName','sEditDesc','sEditPrompt'].forEach(id => $(id).value = '');
    $('sEditEmoji').value = '🌟';
    submitWorldModal.classList.add('show');
});
submitWorldClose.addEventListener('click', () => {
    window._editingSubId = null;
    $('sEditId').disabled = false;
    submitWorldModal.classList.remove('show');
});
submitWorldModal.addEventListener('click', e => { if (e.target === submitWorldModal) submitWorldModal.classList.remove('show'); });

$('submitWorldSaveBtn').addEventListener('click', async () => {
    const data = {
        name: $('sEditName').value.trim(),
        emoji: $('sEditEmoji').value.trim() || '📖',
        genre: $('sEditGenre').value.trim(),
        desc: $('sEditDesc').value.trim(),
        system_prompt: $('sEditPrompt').value.trim(),
        temperature: parseFloat($('sEditTemp').value) || 0.85,
        max_tokens: parseInt($('sEditMaxTokens').value) || 700
    };
    const editingId = window._editingSubId;
    if (!editingId && !$('sEditId').value.trim()) { toast('ID不能为空'); return; }
    if (!data.name) { toast('名称不能为空'); return; }
    let res;
    if (editingId) {
        res = await api(`/api/rpg/worlds/submissions/${editingId}`, { method: 'PUT', body: JSON.stringify(data) });
    } else {
        data.id = $('sEditId').value.trim();
        res = await api('/api/rpg/worlds/submit', { method: 'POST', body: JSON.stringify(data) });
    }
    if (res.error) { toast(res.error); return; }
    toast('✅ ' + (res.message || '操作成功'));
    submitWorldModal.classList.remove('show');
    ['sEditId','sEditName','sEditDesc','sEditPrompt'].forEach(id => $(id).value = '');
    $('sEditEmoji').value = '🌟';
    $('sEditId').disabled = false;
    window._editingSubId = null;
    renderMySubmissions();
});

$('addMySubBtn').addEventListener('click', () => {
    worldManageModal.classList.remove('show');
    submitWorldBtn.click();
});

// --- Admin Stats ---
async function loadAdminStats() {
    try {
        const stats = await api('/api/admin/stats');
        let html = `<div class="stats-summary">
            <div class="stat-card"><div class="stat-num">${escapeHtml(stats.total_calls)}</div><div class="stat-label">总调用次数</div></div>
            <div class="stat-card"><div class="stat-num">${escapeHtml(stats.total_tokens)}</div><div class="stat-label">总Token消耗</div></div>
            <div class="stat-card"><div class="stat-num">${escapeHtml(stats.total_cost)}</div><div class="stat-label">总消耗积分</div></div>
            <div class="stat-card"><div class="stat-num">${escapeHtml(stats.active_sessions)}</div><div class="stat-label">当前活跃跑团</div></div>
        </div>`;
        html += '<div class="stats-section"><div class="admin-panel-header">👥 用户消费排行</div>';
        const users = Object.entries(stats.users || {}).sort((a,b) => b[1].cost - a[1].cost);
        html += users.map(u => `<div class="stats-user"><span>${escapeHtml(u[0])}</span><span>${escapeHtml(u[1].calls)}次 · ${escapeHtml(u[1].tokens)}Token · 💰${escapeHtml(u[1].cost)}积分</span></div>`).join('');
        html += '</div>';
        html += '<div class="stats-section"><div class="admin-panel-header">🤖 模型使用排行</div>';
        Object.entries(stats.models || {}).sort((a,b) => b[1].calls - a[1].calls).forEach(m => {
            html += `<div class="stats-user"><span>${escapeHtml(m[0])}</span><span>${escapeHtml(m[1].calls)}次 · ${escapeHtml(m[1].tokens)}Token</span></div>`;
        });
        html += '</div>';
        if (stats.sessions_detail && stats.sessions_detail.length) {
            html += '<div class="stats-section"><div class="admin-panel-header">🏃 当前活跃会话</div>';
            stats.sessions_detail.slice(0,10).forEach(s => {
                html += `<div class="stats-user"><span>${escapeHtml(s.player)} · ${escapeHtml(s.world)}</span><span>${escapeHtml(s.rounds)}轮</span></div>`;
            });
            html += '</div>';
        }
        $('adminStatsContent').innerHTML = html;
    } catch { $('adminStatsContent').innerHTML = '<div class="status-empty">加载失败</div>'; }
}

// --- Admin Submissions ---
async function loadAdminSubmissions() {
    const subs = await api('/api/rpg/worlds/submissions');
    $('adminSubmissionsList').innerHTML = subs.length === 0
        ? '<div class="status-empty">暂无待审核投稿</div>'
        : subs.map(s => `
            <div class="world-list-item">
                <span style="font-size:22px;">${escapeHtml(s.emoji || '📖')}</span>
                <span style="flex:1;"><strong>${escapeHtml(s.name)}</strong><br><small style="color:var(--text-dim)">👤 ${escapeHtml(s.submitter)} · ${escapeHtml(s.genre || '')}</small></span>
                <span class="ali-actions">
                    <button class="btn-approve-s" data-sid="${escapeHtml(s.id)}">✅ 通过</button>
                    <button class="btn-reject-s" data-sid="${escapeHtml(s.id)}">❌ 拒绝</button>
                </span>
            </div>
        `).join('');
    
    document.querySelectorAll('.btn-approve-s').forEach(btn => {
        btn.addEventListener('click', () => approveSub(btn.dataset.sid));
    });
    document.querySelectorAll('.btn-reject-s').forEach(btn => {
        btn.addEventListener('click', () => rejectSub(btn.dataset.sid));
    });
}

window.approveSub = async function(id) {
    if (!confirm('通过后将上架到世界书列表，确认？')) return;
    await api(`/api/rpg/worlds/submissions/${id}`, { method: 'POST', body: JSON.stringify({ action: 'approve' }) });
    loadAdminSubmissions();
};

window.rejectSub = async function(id) {
    if (!confirm('拒绝后将删除此投稿，确认？')) return;
    await api(`/api/rpg/worlds/submissions/${id}`, { method: 'POST', body: JSON.stringify({ action: 'reject' }) });
    loadAdminSubmissions();
};

// --- Admin: All Sessions ---
async function loadAdminAllSessions() {
    try {
        const sessions = await api('/api/admin/all-sessions');
        $('adminAllSessionsList').innerHTML = sessions.length === 0
            ? '<div class="status-empty">暂无跑团数据</div>'
            : sessions.map(s => `
                <div class="admin-list-item">
                    <div class="ali-main">
                        <div class="ali-name">${escapeHtml(s.world_emoji)} ${escapeHtml(s.player_name)} · ${escapeHtml(s.world_name)} <small>#${s.rounds}轮</small></div>
                        <div class="ali-meta" style="font-size:11px;color:var(--text-dim);">用户${s.user_id||'?'}　${escapeHtml(s.state_preview||'无状态数据')} ${!s.shared?'| 🔒 未分享':'| 🔗 已分享'}</div>
                    </div>
                    <div class="ali-actions">
                        <button data-action="admin-watch" data-sid="${escapeHtml(s.session_id)}" title="实时监控">🔍</button>
                    </div>
                </div>
            `).join('');
        $('adminAllSessionsList').querySelectorAll('[data-action="admin-watch"]').forEach(btn => {
            btn.addEventListener('click', () => adminWatchSession(btn.dataset.sid));
        });
    } catch { $('adminAllSessionsList').innerHTML = '<div class="status-empty">加载失败</div>'; }
}

window.adminWatchSession = function(sid) {
    // Admin can spectate ANY session, shared or not
    $('adminModal').classList.remove('show');
    currentMode = 'rpg';
    document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
    document.querySelector('[data-mode="rpg"]').classList.add('active');
    document.getElementById('chatMode').style.display = 'none';
    document.getElementById('rpgMode').style.display = 'block';
    worldSelectScreen.style.display = 'none';
    gameScreen.style.display = 'none';
    $('spectateScreen').style.display = 'block';
    // Set banner for admin monitor
    const banner = $('spectateBanner');
    if (banner) {
        banner.className = 'spectate-banner admin-monitor';
        $('spectateBannerText').textContent = '🔍 管理员实时监控';
    }
    $('spectateBadge').style.display = 'inline-block';
    $('spectateBadge').className = 'spectate-badge admin-badge';
    $('spectateBadge').textContent = '⚡ 监控模式';
    // Start admin spectate polling
    spectateToken = sid;
    spectateMode = 'admin';
    spectatePoll();
    if (spectateTimer) clearInterval(spectateTimer);
    spectateTimer = setInterval(spectatePoll, 2000);
};

// ============================================================
// 区块 18 · 分享与观战
// ============================================================
const shareBtn = $('shareBtn');
shareBtn.addEventListener('click', async () => {
    if (!rpgState.sessionId) return;
    if (isShared) {
        const data = await api(`/api/rpg/session/${rpgState.sessionId}/unshare`, { method: 'POST' });
        if (data.error) { toast(data.error, 'error'); return; }
        isShared = false;
        shareBtn.textContent = '🔗 分享';
        toast('已取消分享，将从围观广场移除', 'info');
    } else {
        const data = await api(`/api/rpg/session/${rpgState.sessionId}/share`, { method: 'POST' });
        if (data.error) { toast(data.error, 'error'); return; }
        isShared = true;
        shareBtn.textContent = '🔓 取消分享';
        const shareUrl = data.share_url || '';
        $('shareUrlInput').value = shareUrl;
        $('shareSuccessModal').classList.add('show');
    }
    const square = $('spectateSquare');
    if (square) loadSpectateSquare();
});

$('shareCloseBtn').addEventListener('click', () => {
    $('shareSuccessModal').classList.remove('show');
});

$('copyShareUrlBtn').addEventListener('click', async () => {
    const url = $('shareUrlInput').value;
    if (!url) return;
    try {
        await navigator.clipboard.writeText(url);
        toast('✅ 链接已复制到剪贴板', 'success');
    } catch (e) {
        const input = $('shareUrlInput');
        input.select();
        document.execCommand('copy');
        toast('✅ 链接已复制到剪贴板', 'success');
    }
});

$('shareSuccessModal').addEventListener('click', e => {
    if (e.target === $('shareSuccessModal')) {
        $('shareSuccessModal').classList.remove('show');
    }
});

$('exitConfirmModal').addEventListener('click', e => {
    if (e.target === $('exitConfirmModal')) {
        $('exitConfirmModal').classList.remove('show');
    }
});

// --- Spectate (Watch others play) ---
let spectateTimer = null, spectateToken = '';
let spectateMode = 'shared'; // 'shared' or 'admin'

let spectateRefreshTimer = null;
$('spectateBtn').addEventListener('click', () => {
    const square = $('spectateSquare');
    if (square.style.display !== 'none') {
        square.style.display = 'none';
        if (spectateRefreshTimer) { clearInterval(spectateRefreshTimer); spectateRefreshTimer = null; }
        return;
    }
    loadSpectateSquare();
    square.style.display = 'block';
    if (!spectateRefreshTimer) spectateRefreshTimer = setInterval(loadSpectateSquare, 5000);
});

async function loadSpectateSquare() {
    const list = $('spectateList');
    try {
        const sessions = await api('/api/rpg/shared-sessions');
        if (!sessions.length) {
            list.innerHTML = '<div class="status-empty">暂无正在分享的跑团</div>';
            return;
        }
        list.innerHTML = sessions.map(s => `
            <div class="spectate-item">
                <span class="si-emoji">${escapeHtml(s.world_emoji)}</span>
                <span class="si-info">
                    <div class="si-name">${escapeHtml(s.player)} · ${escapeHtml(s.world_name)}</div>
                    <div class="si-meta">${s.rounds}轮 · 刚刚</div>
                </span>
                <button class="si-enter" data-action="spectate" data-token="${escapeHtml(s.share_token)}">👀 围观</button>
            </div>
        `).join('');
        list.querySelectorAll('[data-action="spectate"]').forEach(btn => {
            btn.addEventListener('click', () => startSpectate(btn.dataset.token));
        });
    } catch { list.innerHTML = '<div class="status-empty">加载失败</div>'; }
}

async function startSpectate(token) {
    worldSelectScreen.style.display = 'none';
    gameScreen.style.display = 'none';
    $('spectateScreen').style.display = 'block';
    spectateToken = token;
    spectateMode = 'shared';
    // Set banner for regular spectate
    const banner = $('spectateBanner');
    if (banner) {
        banner.className = 'spectate-banner';
        $('spectateBannerText').textContent = '👀 实时围观中';
    }
    $('spectateBadge').style.display = 'inline-block';
    $('spectateBadge').className = 'spectate-badge';
    $('spectateBadge').textContent = '🔒 只读';
    spectatePoll();
    if (spectateTimer) clearInterval(spectateTimer);
    spectateTimer = setInterval(spectatePoll, 2000);
}

async function spectatePoll() {
    try {
        const url = spectateMode === 'admin'
            ? '/api/rpg/admin/spectate/' + spectateToken
            : '/api/rpg/shared/' + spectateToken;
        const d = await api(url);
        if (d.error) {
            $('specStoryText').textContent = spectateMode === 'admin' ? '会话不存在或已结束' : '会话已结束';
            if (spectateTimer) clearInterval(spectateTimer);
            return;
        }
        $('specWorldName').textContent = (d.world.emoji||'') + ' ' + d.world.name;
        $('specPlayerName').textContent = '🧑 ' + d.player_name;
        const rounds = d.storyline ? d.storyline.length : (d.rounds || 0);
        $('specRoundInfo').textContent = '⚡ 第' + (rounds + 1) + '轮 · ' + (spectateMode === 'admin' ? '实时监控' : '实时围观');
        $('specStoryText').innerHTML = renderMarkdown(d.last_story || '');
        $('specStatus').innerHTML = renderSectionsHtml(d.sections);
        if (d.relationship && Object.keys(d.relationship).length) {
            $('specRelsPanel').style.display = '';
            $('specRelsBody').innerHTML = Object.entries(d.relationship).map(([k,v]) =>
                '<div class="status-item"><span class="status-label">'+escapeHtml(k)+'</span><span class="status-value highlight">'+escapeHtml(v)+'</span></div>'
            ).join('');
        }
        if (d.storyline && d.storyline.length) {
            $('specStorylineBody').innerHTML = d.storyline.map((e,i) => {
                let is = i === d.storyline.length - 1;
                return '<div class="sl-entry'+(is?' current':'')+'"><div class="sl-round">#'+e.round+'</div><div class="sl-content"><div class="sl-choice"><span class="sl-choice-tag">▸</span>'+escapeHtml(e.choice)+'</div><div class="sl-story">'+escapeHtml(e.story||'')+'</div></div></div>';
            }).join('');
        }
    } catch(e) {
        $('specStoryText').textContent = '⚠️ 连接中断，正在重试...';
        console.error('Spectate render failed:', e);
    }
}

function renderSectionsHtml(sec) {
    if (!sec || !Object.keys(sec).length) return '<div class="status-empty">暂无</div>';
    let h = '';
    for (const [k, v] of Object.entries(sec)) {
        if (k === '关系_map' || typeof v === 'object') continue;
        h += '<div class="status-section"><div class="status-section-title">'+escapeHtml(k)+'</div>';
        h += parseStatusValue(cleanText(v));
        h += '</div>';
    }
    return h || '<div class="status-empty">暂无</div>';
}

$('specExitBtn').addEventListener('click', () => {
    if (spectateTimer) clearInterval(spectateTimer);
    spectateTimer = null;
    spectateMode = 'shared';
    $('spectateScreen').style.display = 'none';
    worldSelectScreen.style.display = 'block';
});

// Show share button (now handled inside startGame/resumeGame)

document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        if (spectateTimer) { clearInterval(spectateTimer); spectateTimer = null; }
        if (spectateRefreshTimer) { clearInterval(spectateRefreshTimer); spectateRefreshTimer = null; }
    }
});

// ===== END OF FILE =====
