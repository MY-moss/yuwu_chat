// ============================================================
// 文件: world-ui.js | 职责: 世界书管理弹窗（CRUD、排序、投稿编辑）
// ============================================================
import { state } from './state.js';
import { $, toast, escapeHtml } from './utils.js';
import { api } from './api.js';
import { loadWorlds } from './rpg.js';

export async function renderWorldList() {
    try {
        const worlds = await api('/api/rpg/worlds');
        const isAdmin = state.currentUser && state.currentUser.role === 'admin';
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

async function moveWorldUp(worldId) {
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
}

async function moveWorldDown(worldId) {
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
}

async function deleteWorld(id) {
    if (!confirm('确定要删除这个世界书吗？')) return;
    try {
        const data = await api(`/api/rpg/worlds/${id}`, { method: 'DELETE' });
        if (data.error) {
            toast(data.error);
            return;
        }
        renderWorldList();
        loadWorlds();
        if (state.rpgState.world && state.rpgState.world.id === id) {
            state.rpgState = { sessionId: null, world: null, playerName: '', storyline: [], sections: null };
            $('gameScreen').style.display = 'none';
            $('worldSelectScreen').style.display = 'block';
        }
    } catch (e) {
        console.error('[ERROR] deleteWorld:', e);
        toast('删除失败', 'error');
    }
}

export async function renderMySubmissions() {
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

async function editMySub(id) {
    try {
        const subs = await api('/api/rpg/worlds/my-submissions');
        const s = subs.find(x => x.id === id); if (!s) return;
        $('sEditId').value = s.id; $('sEditId').disabled = true;
        $('sEditName').value = s.name || ''; $('sEditEmoji').value = s.emoji || '🌟';
        $('sEditGenre').value = s.genre || ''; $('sEditDesc').value = s.desc || '';
        $('sEditPrompt').value = s.system_prompt || ''; $('sEditTemp').value = s.temperature || 0.85;
        $('sEditMaxTokens').value = s.max_tokens || 700;
        state._editingSubId = id;
        $('submitWorldModal').classList.add('show');
    } catch (e) {
        console.error('[ERROR] editMySub:', e);
        toast('加载投稿信息失败', 'error');
    }
}

async function delMySub(id) {
    if (!confirm('确定删除这个投稿？')) return;
    try {
        await api(`/api/rpg/worlds/submissions/${id}`, { method: 'DELETE' });
        renderMySubmissions();
    } catch (e) {
        console.error('[ERROR] delMySub:', e);
        toast('删除失败', 'error');
    }
}

async function editWorld(id) {
    state.editingWorldId = id;
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
        $('worldEditorModal').classList.add('show');
    } catch (e) {
        console.error('[ERROR] editWorld:', e);
        toast('加载世界书信息失败', 'error');
    }
}

export function initWorldUI() {
    const manageWorldBtn = $('manageWorldBtn');
    const worldManageModal = $('worldManageModal');
    const worldManageClose = $('worldManageClose');

    manageWorldBtn?.addEventListener('click', () => {
        worldManageModal.classList.add('show');
        renderWorldList();
        renderMySubmissions();
    });
    worldManageClose?.addEventListener('click', () => worldManageModal.classList.remove('show'));
    worldManageModal?.addEventListener('click', e => { if (e.target === worldManageModal) worldManageModal.classList.remove('show'); });

    const worldEditorModal = $('worldEditorModal');

    $('addWorldBtn')?.addEventListener('click', () => {
        state.editingWorldId = null;
        $('worldEditorTitle').textContent = '📖 新建世界书';
        ['wEditName','wEditId','wEditDesc','wEditPrompt'].forEach(id => $(id).value = '');
        $('wEditEmoji').value = '🌟';
        $('wEditGenre').value = '';
        $('wEditTemp').value = 0.85;
        $('wEditMaxTokens').value = 700;
        $('wEditId').disabled = false;
        worldEditorModal.classList.add('show');
    });

    $('worldEditorClose')?.addEventListener('click', () => worldEditorModal.classList.remove('show'));
    $('worldEditorCancel')?.addEventListener('click', () => worldEditorModal.classList.remove('show'));
    worldEditorModal?.addEventListener('click', e => { if (e.target === worldEditorModal) worldEditorModal.classList.remove('show'); });

    $('worldEditorSave')?.addEventListener('click', async () => {
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
            if (state.editingWorldId) {
                const idx = worlds.findIndex(w => w.id === state.editingWorldId);
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
}

// ===== END OF FILE =====
