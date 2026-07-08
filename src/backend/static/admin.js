// ============================================================
// 文件: admin.js | 职责: 管理员面板（模型/用户/卡密/统计/投稿审核/全量会话）
// ============================================================
import { state } from './state.js';
import { $, toast, escapeHtml, setManagedInterval } from './utils.js';
import { api } from './api.js';
import { populateModels } from './chat.js';
import { spectatePoll } from './rpg.js';

// --- Admin Models ---
export async function loadAdminModels() {
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

async function editAdminModel(id) {
    if (!Number.isInteger(id) || id <= 0) { toast('无效的模型ID'); return; }
    state.editingModelId = id;
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
    $('modelEditorModal').classList.add('show');
}

async function deleteAdminModel(id) {
    if (!Number.isInteger(id) || id <= 0) { toast('无效的模型ID'); return; }
    if (!confirm('确定要删除这个模型吗？')) return;
    await api(`/api/admin/models/${id}`, { method: 'DELETE' });
    loadAdminModels();
    populateModels();
}

// --- Admin Users ---
export async function loadAdminUsers() {
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

async function editAdminUser(id) {
    if (!Number.isInteger(id) || id <= 0) { toast('无效的用户ID'); return; }
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
}

async function deleteAdminUser(id) {
    if (!Number.isInteger(id) || id <= 0) { toast('无效的用户ID'); return; }
    if (!confirm('确定要删除这个用户吗？')) return;
    await api(`/api/admin/users/${id}`, { method: 'DELETE' });
    loadAdminUsers();
}

// --- Credit Keys ---
export async function loadAdminKeys() {
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

async function deleteKey(id) {
    if (!Number.isInteger(id) || id <= 0) { toast('无效的密钥ID'); return; }
    if (!confirm('确定要删除这个未使用的密钥吗？')) return;
    await api(`/api/admin/credit-keys/${id}`, { method: 'DELETE' });
    loadAdminKeys();
}

// --- Admin Stats ---
export async function loadAdminStats() {
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
export async function loadAdminSubmissions() {
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

async function approveSub(id) {
    if (!confirm('通过后将上架到世界书列表，确认？')) return;
    await api(`/api/rpg/worlds/submissions/${id}`, { method: 'POST', body: JSON.stringify({ action: 'approve' }) });
    loadAdminSubmissions();
}

async function rejectSub(id) {
    if (!confirm('拒绝后将删除此投稿，确认？')) return;
    await api(`/api/rpg/worlds/submissions/${id}`, { method: 'POST', body: JSON.stringify({ action: 'reject' }) });
    loadAdminSubmissions();
}

// --- Admin: All Sessions ---
export async function loadAdminAllSessions() {
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

function adminWatchSession(sid) {
    $('adminModal').classList.remove('show');
    state.currentMode = 'rpg';
    document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
    document.querySelector('[data-mode="rpg"]').classList.add('active');
    document.getElementById('chatMode').style.display = 'none';
    document.getElementById('rpgMode').style.display = 'block';
    $('worldSelectScreen').style.display = 'none';
    $('gameScreen').style.display = 'none';
    $('spectateScreen').style.display = 'block';
    const banner = $('spectateBanner');
    if (banner) {
        banner.className = 'spectate-banner admin-monitor';
        $('spectateBannerText').textContent = '🔍 管理员实时监控';
    }
    $('spectateBadge').style.display = 'inline-block';
    $('spectateBadge').className = 'spectate-badge admin-badge';
    $('spectateBadge').textContent = '⚡ 监控模式';
    state.spectateToken = sid;
    state.spectateMode = 'admin';
    spectatePoll();
    if (state.spectateTimer) clearInterval(state.spectateTimer);
    state.spectateTimer = setManagedInterval(spectatePoll, 2000);
}

export function initAdmin() {
    const adminBtn = $('adminBtn');
    const adminModal = $('adminModal');
    const adminClose = $('adminClose');
    const adminCancel = $('adminCancel');
    const modelEditorModal = $('modelEditorModal');

    adminBtn?.addEventListener('click', () => {
        adminModal.classList.add('show');
        loadAdminModels();
        loadAdminUsers();
        loadAdminKeys();
    });
    adminClose?.addEventListener('click', () => adminModal.classList.remove('show'));
    adminCancel?.addEventListener('click', () => adminModal.classList.remove('show'));
    adminModal?.addEventListener('click', e => { if (e.target === adminModal) adminModal.classList.remove('show'); });

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

    $('addModelBtn')?.addEventListener('click', () => {
        state.editingModelId = null;
        $('modelEditorTitle').textContent = '➕ 添加模型';
        ['mEditModelId','mEditName','mEditLabel','mEditApiBase','mEditApiKey'].forEach(id => $(id).value = '');
        $('mEditCreditsPer1k').value = '1';
        $('mEditPriority').value = '100';
        $('mEditEnabled').checked = true;
        modelEditorModal.classList.add('show');
    });

    $('modelEditorClose')?.addEventListener('click', () => modelEditorModal.classList.remove('show'));
    $('modelEditorCancel')?.addEventListener('click', () => modelEditorModal.classList.remove('show'));
    modelEditorModal?.addEventListener('click', e => { if (e.target === modelEditorModal) modelEditorModal.classList.remove('show'); });

    $('modelEditorSave')?.addEventListener('click', async () => {
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

        if (state.editingModelId) {
            await api(`/api/admin/models/${state.editingModelId}`, {
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

    $('genKeyBtn')?.addEventListener('click', async () => {
        try {
            const credits = parseInt($('keyCredits').value) || 100;
            const count = parseInt($('keyCount').value) || 1;
            const data = await api('/api/admin/credit-keys', {
                method: 'POST',
                body: JSON.stringify({ credits, count })
            });
            if (data.error) { toast(data.error); return; }
            const keysText = data.keys.join('\n');
            // [AUDIT-X05] 卡密以 Toast 直接展现，可被页面上其他脚本读取
            toast(`已生成 ${data.count} 个 ${data.credits} 积分密钥：\n\n${keysText}\n\n请复制并分发给用户`);
            loadAdminKeys();
        } catch (e) {
            console.error('[ERROR] genKeyBtn:', e);
            toast('生成密钥失败：' + e.message);
        }
    });
}

// ===== END OF FILE =====
