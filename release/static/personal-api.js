// ============================================================
// 文件: personal-api.js | 职责: 个人API设置、用户自定义模型管理
// ============================================================
import { state } from './state.js';
import { $, toast, escapeHtml } from './utils.js';
import { api } from './api.js';
import { populateModels } from './chat.js';

export async function loadPersonalApiConfig() {
    // 已迁移至模型级别配置，此处保留空函数避免外部调用报错
}

export function fillNewModelApiUrl() {
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

export async function loadUserModels() {
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

async function editUserModel(modelId) {
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
}

export function initPersonalApi() {
    const apiSettingsBtn = $('apiSettingBtn');
    const apiSettingsModal = $('apiSettingsModal');
    const apiSettingsClose = $('apiSettingsClose');

    apiSettingsBtn?.addEventListener('click', async () => {
        await loadPersonalApiConfig();
        await loadUserModels();
        apiSettingsModal.classList.add('show');
    });
    apiSettingsClose?.addEventListener('click', () => apiSettingsModal.classList.remove('show'));
    apiSettingsModal?.addEventListener('click', e => { if (e.target === apiSettingsModal) apiSettingsModal.classList.remove('show'); });

    $('userModelEditorClose')?.addEventListener('click', () => {
        $('userModelEditorModal').classList.remove('show');
    });
    $('userModelEditorModal')?.addEventListener('click', e => {
        if (e.target === $('userModelEditorModal')) $('userModelEditorModal').classList.remove('show');
    });

    $('umEditSaveBtn')?.addEventListener('click', async () => {
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

    $('addUserModelBtn')?.addEventListener('click', () => {
        $('addUserModelForm').style.display = 'block';
        $('newModelId').value = '';
        $('newModelName').value = '';
        $('newModelLabel').value = '';
        $('newModelProvider').value = '';
        $('newModelApiBase').value = '';
        $('newModelApiKey').value = '';
        $('newModelId').focus();
    });

    $('cancelNewModelBtn')?.addEventListener('click', () => {
        $('addUserModelForm').style.display = 'none';
    });

    $('newModelProvider')?.addEventListener('change', fillNewModelApiUrl);

    $('saveNewModelBtn')?.addEventListener('click', async () => {
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

    apiSettingsModal?.addEventListener('click', e => {
        if (e.target === apiSettingsModal) apiSettingsModal.classList.remove('show');
    });
}

// ===== END OF FILE =====
