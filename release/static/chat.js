// ============================================================
// 文件: chat.js | 职责: 聊天UI、模型列表、智能体切换、消息发送、聊天搜索
// ============================================================
import { state } from './state.js';
import { $, toast, escapeHtml, updateUserInfo, getSelectedModel } from './utils.js';
import { api } from './api.js';
import { renderMarkdown, highlightCode } from './renderer.js';
import { applyChatBubble3D } from './three-card.js';

export async function populateModels() {
    const sel = $('modelSelect');
    if (!sel) return;
    try {
        const models = await api('/api/models');
        const hasPersonal = state.currentUser && state.currentUser.has_personal_api;

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

export async function loadAgents() {
    try {
        const data = await api('/api/agents');
        const agents = Array.isArray(data) ? data : [];
        const agentSelect = $('agentSelect');
        agentSelect.innerHTML = agents.map(a =>
            `<option value="${escapeHtml(a.id)}">${escapeHtml(a.avatar || '🧔')} ${escapeHtml(a.name)} ${a.title ? '— ' + escapeHtml(a.title) : ''}</option>`
        ).join('');
        if (agents.length) {
            agentSelect.value = agents[0].id;
            state.currentAgentId = agents[0].id;
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
        searchInput.oninput = () => {
            const q = searchInput.value.toLowerCase();
            document.querySelectorAll('.agent-card').forEach(card => {
                const name = card.querySelector('.agent-name')?.textContent?.toLowerCase() || '';
                const title = card.querySelector('.agent-title')?.textContent?.toLowerCase() || '';
                card.style.display = name.includes(q) || title.includes(q) ? '' : 'none';
            });
        };
    }
}

function updateAgentHint() {
    const sel = $('agentSelect');
    const hint = $('agentHint');
    if (!hint) return;
    const opt = sel?.selectedOptions[0];
    hint.textContent = opt ? `当前：${opt.textContent}` : '请选择一位角色聊聊';
}

function saveCurrentAgentState() {
    if (!state.currentAgentId) return;
    const chatBox = $('chatBox');
    if (!chatBox) return;
    const keys = Object.keys(state.agentState);
    if (keys.length > 50) {
        const sorted = keys.sort((a, b) => (state.agentState[a].timestamp || 0) - (state.agentState[b].timestamp || 0));
        sorted.slice(0, sorted.length - 50).forEach(k => delete state.agentState[k]);
    }
    state.agentState[state.currentAgentId] = {
        scrollTop: chatBox.scrollTop,
        scrollHeight: chatBox.scrollHeight,
        messages: chatBox.innerHTML,
        timestamp: Date.now()
    };
}

function restoreAgentState(agentId) {
    if (!state.agentState[agentId]) return;
    const chatBox = $('chatBox');
    if (!chatBox) return;
    const saved = state.agentState[agentId];
    if (typeof DOMPurify !== 'undefined' && DOMPurify.sanitize) {
        chatBox.innerHTML = DOMPurify.sanitize(saved.messages, { ADD_TAGS: ['pre','code'], ADD_ATTR: ['class'] });
    } else {
        chatBox.textContent = saved.messages;  // M10: DOMPurify 未加载时安全降级为 textContent
    }
    chatBox.scrollTop = saved.scrollTop;
}

export async function switchAgent(newAgentId) {
    if (state.isSwitchingAgent || state.currentAgentId === newAgentId) return;
    state.isSwitchingAgent = true;

    try {
        saveCurrentAgentState();

        const chatBox = $('chatBox');
        const agentCardSelector = $('agentCardSelector');
        const agentSelect = $('agentSelect');

        if (chatBox) {
            chatBox.style.opacity = '0';
            chatBox.style.transform = 'translateX(-20px)';
        }

        if (agentCardSelector) {
            agentCardSelector.style.opacity = '0';
        }

        await new Promise(resolve => setTimeout(resolve, 200));

        if (agentSelect) agentSelect.value = newAgentId;
        document.querySelectorAll('.agent-card').forEach(card => {
            card.classList.remove('active');
            if (card.dataset.agentId === newAgentId) card.classList.add('active');
        });

        state.currentAgentId = newAgentId;
        updateAgentHint();
        restoreAgentState(newAgentId);

        if (chatBox) {
            chatBox.style.opacity = '1';
            chatBox.style.transform = 'translateX(0)';
        }

        if (agentCardSelector) {
            agentCardSelector.style.opacity = '1';
        }
    } catch (e) {
        console.error('[ERROR] switchAgent:', e);
        toast('智能体切换失败', 'error');
    } finally {
        state.isSwitchingAgent = false;
    }
}

async function sendMessage() {
    if (state.isSending) return;
    const messageInput = $('messageInput');
    const msg = messageInput.value.trim();
    if (!msg) return;
    state.isSending = true;
    const agentSelect = $('agentSelect');
    const agentId = agentSelect.value;
    messageInput.value = '';
    messageInput.style.height = 'auto';
    const panel = $('previewPanel');
    if (panel) panel.style.display = 'none';
    appendMessage(msg, 'user');
    const sendBtn = $('sendBtn');
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
                state.currentUser.credits = data.credits_left;
                updateUserInfo();
            }
        }
    } catch (err) {
        thinkDots.remove();
        thinkingEl.querySelector('.md-body').innerHTML = '❌ 网络错误，请重试';
    } finally {
        state.isSending = false;
        sendBtn.disabled = false;
        sendBtn.innerHTML = '<span class="btn-icon">🍺</span> 来一杯';
        const chatBox = $('chatBox');
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
    const chatBox = $('chatBox');
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
    setTimeout(() => { highlightCode(content); applyChatBubble3D(); }, 0);
    return div;
}

function initChatSearch() {
    const searchInput = $('chatSearchInput');
    const filterRole = $('chatFilterRole');
    const clearBtn = $('chatSearchClear');
    if (!searchInput || !filterRole || !clearBtn) return;

    function applySearch() {
        const keyword = searchInput.value.trim().toLowerCase();
        const role = filterRole.value;
        const messages = document.querySelectorAll('.msg');

        clearBtn.style.display = keyword || role ? 'block' : 'none';

        let matchCount = 0;
        messages.forEach((msg) => {
            const isUser = msg.classList.contains('user');
            const isAgent = msg.classList.contains('agent');
            const content = msg.textContent.toLowerCase();

            let roleMatch = true;
            if (role === 'user' && !isUser) roleMatch = false;
            if (role === 'agent' && !isAgent) roleMatch = false;

            let textMatch = true;
            if (keyword && !content.includes(keyword)) textMatch = false;

            if (roleMatch && textMatch) {
                msg.style.display = '';
                if (keyword) {
                    msg.classList.add('highlight');
                } else {
                    msg.classList.remove('highlight');
                }
                matchCount++;
            } else {
                msg.style.display = 'none';
                msg.classList.remove('highlight');
            }
        });

        if (keyword && matchCount === 0) {
            const chatBox = $('chatBox');
            if (chatBox && chatBox.querySelectorAll('.msg[style="display: none;"]').length === messages.length) {
                toast(`未找到包含 "${searchInput.value}" 的消息`, 'info');
            }
        }
    }

    searchInput.addEventListener('input', applySearch);
    filterRole.addEventListener('change', applySearch);

    clearBtn.addEventListener('click', () => {
        searchInput.value = '';
        filterRole.value = '';
        applySearch();
    });
}

export function initChat() {
    const agentSelect = $('agentSelect');
    agentSelect?.addEventListener('change', () => switchAgent(agentSelect.value));

    const sendBtn = $('sendBtn');
    sendBtn?.addEventListener('click', sendMessage);

    const messageInput = $('messageInput');
    messageInput?.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    messageInput?.addEventListener('input', () => {
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';
    });

    initChatSearch();
}

// ===== END OF FILE =====
