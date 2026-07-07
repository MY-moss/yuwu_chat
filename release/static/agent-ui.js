// ============================================================
// 文件: agent-ui.js | 职责: 智能体管理弹窗（CRUD）
// ============================================================
import { state } from './state.js';
import { $, toast, escapeHtml } from './utils.js';
import { api } from './api.js';
import { loadAgents } from './chat.js';

export async function renderAgentList() {
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

async function deleteAgent(id) {
    if (!confirm('确定要删除这个智能体吗？')) return;
    try {
        await api('/api/agents/' + id, { method: 'DELETE' });
        renderAgentList();
        loadAgents();
    } catch (e) {
        console.error('[ERROR] deleteAgent:', e);
        toast('删除失败', 'error');
    }
}

async function editAgent(id) {
    state.editingAgentId = id;
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
        $('editorModal').classList.add('show');
    } catch (e) {
        console.error('[ERROR] editAgent:', e);
        toast('加载智能体信息失败', 'error');
    }
}

export function initAgentUI() {
    const manageBtn = $('manageBtn');
    const manageModal = $('manageModal');
    const modalClose = $('modalClose');

    manageBtn?.addEventListener('click', () => { manageModal.classList.add('show'); renderAgentList(); });
    modalClose?.addEventListener('click', () => manageModal.classList.remove('show'));
    manageModal?.addEventListener('click', e => { if (e.target === manageModal) manageModal.classList.remove('show'); });

    const editorModal = $('editorModal');

    $('addAgentBtn')?.addEventListener('click', () => {
        state.editingAgentId = null;
        $('editorTitle').textContent = '➕ 新建智能体';
        ['editId','editName','editAvatar','editTitle','editGreeting','editPrompt'].forEach(id => $(id).value = '');
        $('editAvatar').value = '🧔';
        $('editModel').value = 'mimo-v2.5-free';
        $('editTemp').value = 0.85;
        $('editId').disabled = false;
        editorModal.classList.add('show');
    });

    $('editorClose')?.addEventListener('click', () => editorModal.classList.remove('show'));
    $('editorCancel')?.addEventListener('click', () => editorModal.classList.remove('show'));
    editorModal?.addEventListener('click', e => { if (e.target === editorModal) editorModal.classList.remove('show'); });

    $('editorSave')?.addEventListener('click', async () => {
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
            if (state.editingAgentId) {
                await api('/api/agents/' + state.editingAgentId, {
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
}

// ===== END OF FILE =====
