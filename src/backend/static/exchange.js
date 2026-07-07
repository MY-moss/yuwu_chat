// ============================================================
// 文件: exchange.js | 职责: 兑换码、世界书投稿
// ============================================================
import { state } from './state.js';
import { $, toast, updateUserInfo } from './utils.js';
import { api } from './api.js';
import { renderMySubmissions } from './world-ui.js';

export function initExchange() {
    const redeemBtn = $('redeemBtn');
    const redeemModal = $('redeemModal');
    const redeemClose = $('redeemClose');

    redeemBtn?.addEventListener('click', () => {
        $('redeemCode').value = '';
        $('redeemMsg').textContent = '';
        redeemModal.classList.add('show');
    });
    redeemClose?.addEventListener('click', () => redeemModal.classList.remove('show'));
    redeemModal?.addEventListener('click', e => { if (e.target === redeemModal) redeemModal.classList.remove('show'); });

    $('redeemSubmitBtn')?.addEventListener('click', async () => {
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
                state.currentUser.credits = data.credits_left;
                updateUserInfo();
            }
        } catch {
            $('redeemMsg').textContent = '❌ 兑换失败';
        }
        $('redeemSubmitBtn').disabled = false;
    });

    $('redeemCode')?.addEventListener('keydown', e => {
        if (e.key === 'Enter') $('redeemSubmitBtn').click();
    });

    // --- World Submission ---
    const submitWorldBtn = $('submitWorldBtn');
    const submitWorldModal = $('submitWorldModal');
    const submitWorldClose = $('submitWorldClose');
    const worldManageModal = $('worldManageModal');

    submitWorldBtn?.addEventListener('click', () => {
        state._editingSubId = null;
        $('sEditId').disabled = false;
        ['sEditId','sEditName','sEditDesc','sEditPrompt'].forEach(id => $(id).value = '');
        $('sEditEmoji').value = '🌟';
        submitWorldModal.classList.add('show');
    });
    submitWorldClose?.addEventListener('click', () => {
        state._editingSubId = null;
        $('sEditId').disabled = false;
        submitWorldModal.classList.remove('show');
    });
    submitWorldModal?.addEventListener('click', e => { if (e.target === submitWorldModal) submitWorldModal.classList.remove('show'); });

    $('submitWorldSaveBtn')?.addEventListener('click', async () => {
        const data = {
            name: $('sEditName').value.trim(),
            emoji: $('sEditEmoji').value.trim() || '📖',
            genre: $('sEditGenre').value.trim(),
            desc: $('sEditDesc').value.trim(),
            system_prompt: $('sEditPrompt').value.trim(),
            temperature: parseFloat($('sEditTemp').value) || 0.85,
            max_tokens: parseInt($('sEditMaxTokens').value) || 700
        };
        const editingId = state._editingSubId;
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
        state._editingSubId = null;
        renderMySubmissions();
    });

    $('addMySubBtn')?.addEventListener('click', () => {
        worldManageModal.classList.remove('show');
        submitWorldBtn.click();
    });
}

// ===== END OF FILE =====
