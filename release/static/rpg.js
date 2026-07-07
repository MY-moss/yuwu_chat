// ============================================================
// 文件: rpg.js | 职责: 跑团系统（世界书/评分/会话/游戏核心/骰子/故事线/分享/观战）
// ============================================================
import { state } from './state.js';
import { $, toast, escapeHtml, showLoading, hideLoading, updateProgress, updateLoadingStatus, updateUserInfo, getSelectedModel, formatTime, setManagedInterval } from './utils.js';
import { api, apiStream } from './api.js';
import { renderMarkdown, highlightCode, cleanText, renderStory, renderStatus, parseStatusValue } from './renderer.js';

// ============================================================
// 区块 07 · 会话管理
// ============================================================
export async function loadSessions() {
    try {
        const [sessions, activeData] = await Promise.all([
            api('/api/rpg/sessions'),
            api('/api/rpg/active-count').catch(() => ({ total: 0 }))
        ]);
        $('sessionsCount').textContent = activeData.total;
        if (sessions.length === 0) {
            $('sessionsEmpty').style.display = 'block';
            $('sessionsList').innerHTML = '';
            return;
        }
        $('sessionsEmpty').style.display = 'none';
        $('sessionsList').innerHTML = sessions.map(s => {
            const active = state.rpgState.sessionId === s.session_id;
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

async function deleteSession(e, sid) {
    e.stopPropagation();
    if (!confirm('确定删除这个跑团记录？数据不可恢复。')) return;
    try {
        await api(`/api/rpg/session/${sid}`, { method: 'DELETE' });
        if (state.rpgState.sessionId === sid) {
            state.rpgState = { sessionId: null, world: null, playerName: '', storyline: [], sections: null };
            $('gameScreen').style.display = 'none';
            $('worldSelectScreen').style.display = 'block';
            const shareBtn = $('shareBtn');
            if (shareBtn) shareBtn.style.display = 'none';
        }
        loadSessions();
    } catch (e) {
        console.error('[ERROR] deleteSession:', e);
        toast('删除失败', 'error');
    }
}

export async function resumeGame(sessionId) {
    try {
        const data = await api(`/api/rpg/session/${sessionId}`);
        if (data.error) {
            toast(data.error);
            return;
        }
        showLoading('🔄 恢复游戏中...', data.player_name);
        const worldSelectScreen = $('worldSelectScreen');
        const gameScreen = $('gameScreen');
        const personalContent = $('personalContent');
        worldSelectScreen.style.display = 'none';
        gameScreen.style.display = 'flex';
        personalContent.innerHTML = '<div class="status-empty">恢复中...</div>';

        state.rpgState.sessionId = sessionId;
        state.rpgState.playerName = data.player_name;
        state.rpgState.world = { id: data.world_id, emoji: '📖', name: '加载中...' };
        state.rpgState.sections = data.sections || {};
        try {
            const worlds = await api('/api/rpg/worlds');
            const w = worlds.find(x => x.id === data.world_id);
            if (w) state.rpgState.world = w;
        } catch(e) { console.error('Load world info failed:', e); }
        $('gameWorldName').textContent = `${state.rpgState.world.emoji} ${state.rpgState.world.name}`;
        $('gamePlayerName').textContent = `🧑 ${data.player_name}`;
        $('gameRound').textContent = `第${Math.max(1, data.storyline ? data.storyline.length : 0)}轮`;

        hideLoading();
        renderStory(data.last_story || '');
        renderStatus(data.sections || data.last_state || '');
        renderChoices(data.last_story || '');
        state.rpgState.storyline = data.storyline || [];
        renderStoryline();
        renderRelationships(data.relationships);
        state.isShared = !!data.share_token;
        const shareBtn = $('shareBtn');
        if (shareBtn) {
            shareBtn.style.display = 'block';
            shareBtn.textContent = state.isShared ? '🔓 取消分享' : '🔗 分享';
        }
    } catch (e) {
        console.error('[ERROR] resumeGame:', e);
        hideLoading();
        $('worldSelectScreen').style.display = 'block';
        $('gameScreen').style.display = 'none';
        toast('恢复游戏失败，请重试');
    }
}

// ============================================================
// 区块 08 · 世界与评分
// ============================================================
export async function loadWorlds() {
    loadSessions();
    try {
        const worlds = await api('/api/rpg/worlds');
        const worldGrid = $('worldGrid');
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
        $('worldGrid').innerHTML = '<div class="status-empty" style="grid-column:1/-1;">加载失败，请刷新重试</div>';
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

async function openRateWorld(e, worldId) {
    e.stopPropagation();
    const ratings = await api(`/api/rpg/worlds/${worldId}/ratings`).catch(() => []);
    const myRating = ratings.find(r => r.user_id === (state.currentUser?.id || 0));
    let existingModal = $('rateWorldModal');
    if (existingModal) existingModal.remove();
    state.currentPickedRating = 0;

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
        state.currentPickedRating = myRating.rating;
        updatePickStars(myRating.rating);
    }
    modal.querySelector('.btn-add').addEventListener('click', () => submitRating(modal.querySelector('.btn-add').dataset.wid));
    modal.querySelector('.modal-close').addEventListener('click', closeRateModal);
    modal.addEventListener('click', e => { if (e.target === modal) closeRateModal(); });
}

function pickRating(r) {
    state.currentPickedRating = r;
    updatePickStars(r);
}

function updatePickStars(r) {
    document.querySelectorAll('.rate-pick-star').forEach(s => {
        const sr = parseInt(s.dataset.r);
        s.textContent = sr <= r ? '★' : '☆';
        s.classList.toggle('picked', sr <= r);
    });
}

function closeRateModal() {
    const modal = $('rateWorldModal');
    if (modal) modal.remove();
    state.currentPickedRating = 0;
}

async function submitRating(worldId) {
    if (state.currentPickedRating < 1 || state.currentPickedRating > 5) {
        toast('请选择1-5星评分');
        return;
    }
    try {
        const review = ($('rateReview')?.value || '').trim();
        const res = await api(`/api/rpg/worlds/${worldId}/ratings`, {
            method: 'POST',
            body: JSON.stringify({ rating: state.currentPickedRating, review })
        });
        if (res.error) { toast(res.error); return; }
        closeRateModal();
        loadWorlds();
    } catch (e) {
        console.error('[ERROR] submitRating:', e);
        toast('提交评价失败');
    }
}

// ============================================================
// 区块 09 · RPG游戏核心
// ============================================================
export async function startGame(worldId) {
    if (state._gameStarting) return;
    state._gameStarting = true;
    let name = prompt('请输入你的角色名：', '旅人') || '旅人';
    name = name.trim().replace(/[<>"'&]/g, '');
    if (!name) name = '旅人';
    const worldSelectScreen = $('worldSelectScreen');
    const gameScreen = $('gameScreen');
    const personalContent = $('personalContent');
    const storyText = $('storyText');
    const choicesArea = $('choicesArea');
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

    state.rpgAbortController = new AbortController();

    try {
        const data = await api('/api/rpg/start', {
            method: 'POST',
            body: JSON.stringify({ world_id: worldId, player_name: name, model: getSelectedModel() }),
            signal: state.rpgAbortController.signal
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

        state.rpgState.sessionId = data.session_id;
        state.rpgState.world = data.world;
        state.rpgState.playerName = data.player_name;
        state.rpgState.storyline = data.storyline || [];
        state.rpgState.sections = data.sections || null;
        $('gameWorldName').textContent = `${data.world.emoji} ${data.world.name}`;
        $('gamePlayerName').textContent = `🧑 ${data.player_name}`;
        $('gameRound').textContent = `第${Math.max(1, data.storyline ? data.storyline.length : 0)}轮`;

        state.isShared = !!data.share_token;
        const shareBtn = $('shareBtn');
        if (shareBtn) {
            shareBtn.style.display = 'block';
            shareBtn.textContent = state.isShared ? '🔓 取消分享' : '🔗 分享';
        }

        if (data.credits_left !== undefined) {
            state.currentUser.credits = data.credits_left;
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
        state.rpgAbortController = null;
        state._gameStarting = false;
    }
}

export async function actGame(choice) {
    if (!state.rpgState.sessionId) return;
    if (state.rpgAbortController) return;
    if (state._rpgRequestActive) return;
    if (state.actGameStatusTimeout) { clearTimeout(state.actGameStatusTimeout); state.actGameStatusTimeout = null; }
    state._rpgRequestActive = true;
    showLoading('🎭 故事继续展开...', '');

    const MAX_RETRIES = 2;
    let retryCount = 0;
    const storyText = $('storyText');
    const storyBox = $('storyBox');

    while (retryCount <= MAX_RETRIES) {
        if (retryCount > 0) {
            const delay = Math.pow(2, retryCount) * 1000;
            updateLoadingStatus(`🔄 连接断开，${delay/1000}秒后重试...`);
            await new Promise(r => setTimeout(r, delay));
            if (!state.rpgState.sessionId) { hideLoading(); state._rpgRequestActive = false; return; }
        }

        state.rpgAbortController = new AbortController();

        try {
            const resp = await apiStream('/api/rpg/act/stream', {
                method: 'POST',
                body: JSON.stringify({ session_id: state.rpgState.sessionId, choice, model: getSelectedModel() }),
                signal: state.rpgAbortController.signal
            });
            const reader = resp.body.getReader();
            const dec = new TextDecoder();
            let buffer = '', full = '', startTime = Date.now();
            let updatePending = false;

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
                    // [AUDIT-P14] full 字符串无界累积（~400KB+ GC 压力）
                    if (json.type === 'chunk') {
                        full += json.text;
                        if (!updatePending) {
                            updatePending = true;
                            // [AUDIT-P15] RAF + innerHTML 每次全量渲染，布局抖动
                            requestAnimationFrame(() => {
                                storyText.innerHTML = renderMarkdown(full);
                                storyBox.scrollTop = storyBox.scrollHeight;
                                const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
                                const estTotal = Math.max(800, full.length * 2);
                                const pct = Math.min(95, full.length / estTotal * 100);
                                const speed = elapsed > 0 ? (full.length / parseFloat(elapsed)).toFixed(0) : 0;
                                updateProgress(pct, Math.round(pct) + '% · ' + full.length + '字');
                                $('loadingSub').textContent = '⏱ ' + elapsed + 's · ' + speed + '字/s';
                                updateLoadingStatus('AI 正在生成故事...');
                                updatePending = false;
                            });
                        }
                    } else if (json.type === 'done') {
                        updateProgress(100, '100%');
                        updateLoadingStatus('✓ 故事生成完成，正在渲染...');
                        state.actGameStatusTimeout = setTimeout(() => updateLoadingStatus(''), 500);
                        if (json.credits_left !== undefined) {
                            state.currentUser.credits = json.credits_left;
                            updateUserInfo();
                        }
                        state.rpgState.storyline = json.storyline || state.rpgState.storyline || [];
                        state.rpgState.sections = json.sections || null;
                        // [AUDIT-X03] innerHTML 渲染 SSE 流数据，DOMPurify 缺失时 XSS 入口
                        storyText.innerHTML = renderMarkdown(json.story || full);
                        renderStatus(json.sections || json.state || '');
                        renderChoices(json.story || full);
                        renderStoryline();
                        renderRelationships(json.relationships);
                        $('gameRound').textContent = `第${Math.max(1, (state.rpgState.storyline || []).length)}轮`;
                        hideLoading();
                        state.rpgAbortController = null;
                        state._rpgRequestActive = false;
                        return;
                    } else if (json.type === 'error') {
                        storyText.textContent = '❌ ' + json.text;
                        hideLoading();
                        state.rpgAbortController = null;
                        state._rpgRequestActive = false;
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
            state.rpgAbortController = null;
            state._rpgRequestActive = false;
            return;

        } catch (e) {
            if (e.name === 'AbortError') {
                console.info('[INFO] actGame aborted by user');
                hideLoading();
                state.rpgAbortController = null;
                state._rpgRequestActive = false;
                return;
            }
            if (!state.rpgState.sessionId) { hideLoading(); state._rpgRequestActive = false; return; }
            retryCount++;
            console.warn(`[WARN] SSE stream failed, attempt ${retryCount}/${MAX_RETRIES}:`, e);
            state.rpgAbortController = null;
        }
    }

    try {
        storyText.textContent = '⏳ 流式连接失败，使用普通模式...';
        const data = await api('/api/rpg/act', {
            method: 'POST',
            body: JSON.stringify({ session_id: state.rpgState.sessionId, choice, model: getSelectedModel() })
        });
        if (data.error) {
            if (data.error === '积分不足') { toast('积分不足'); return; }
            storyText.textContent = '❌ ' + data.error; return;
        }
        if (data.credits_left !== undefined) { state.currentUser.credits = data.credits_left; updateUserInfo(); }
        state.rpgState.storyline = data.storyline || [];
        state.rpgState.sections = data.sections || null;
        storyText.innerHTML = renderMarkdown(data.story || '');
        renderStatus(data.sections || data.state || '');
        renderChoices(data.story || '');
        renderStoryline();
        renderRelationships(data.relationships);
        $('gameRound').textContent = `第${Math.max(1, state.rpgState.storyline.length)}轮`;
    } catch (fallbackErr) {
        console.error('[ERROR] actGame fallback:', fallbackErr);
        storyText.textContent = '❌ 故事展开失败，请重试';
    } finally {
        hideLoading();
        state.rpgAbortController = null;
        state._rpgRequestActive = false;
    }
}

// ============================================================
// 区块 10 (部分) · 渲染选择分支（从renderer.js迁入，因调用actGame/doSkillCheck）
// ============================================================
export function renderChoices(storyTextContent) {
    const choicesArea = $('choicesArea');
    choicesArea.innerHTML = '';
    if (!storyTextContent) return;

    const text = String(storyTextContent);

    const sections = state.rpgState.sections || {};
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

    const allMatches = [];
    const re = /【(\d+)】([^【\n]*)/g;
    let m;
    while ((m = re.exec(text)) !== null) {
        allMatches.push({ num: m[1], text: m[2].trim(), pos: m.index });
    }

    const choices = allMatches.length > 2
        ? allMatches.filter(c => c.text && text.length - c.pos < 300).slice(-6)
        : allMatches.filter(c => c.text);

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
function getAttrValue(attrName) {
    const sections = state.rpgState.sections || {};
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

function calculateModifier(attrValue) {
    if (attrValue === null) return 0;
    return Math.max(-4, Math.min(5, attrValue - 5));
}

function calculateRealDifficulty(baseDiff, sections) {
    let realDiff = baseDiff;
    const status = cleanText(sections['状态'] || '');
    const events = cleanText(sections['事件'] || '');

    const injuryMatch = status.match(/受伤|重伤|虚弱|中毒|诅咒|恐惧|混乱/);
    if (injuryMatch) realDiff += 2;

    const buffMatch = status.match(/鼓舞|激励|专注|强化|祝福|潜行/);
    if (buffMatch) realDiff -= 2;

    const envHard = events.match(/困难|危险|陷阱|伏击|暴风雨|黑暗/);
    if (envHard) realDiff += 2;
    const envEasy = events.match(/轻松|安全|休息|明亮|支援|熟悉/);
    if (envEasy) realDiff -= 2;

    return Math.max(5, Math.min(30, realDiff));
}

async function doSkillCheck(baseDifficulty, realDifficulty, modifier, attribute) {
    const btn = document.querySelector('.judge-roll-btn');
    if (btn) btn.disabled = true;
    const resultEl = document.getElementById('judgeResult');
    if (!resultEl) return;
    resultEl.style.display = 'block';
    resultEl.className = 'judge-result';
    resultEl.innerHTML = '<span class="judge-rolling">🎲 投掷中...</span>';

    if (state.skillCheckTimer) clearTimeout(state.skillCheckTimer);

    try {
        const data = await api('/api/rpg/roll', {
            method: 'POST',
            body: JSON.stringify({
                session_id: state.rpgState.sessionId,
                difficulty: realDifficulty,
                modifier: modifier,
                attribute: attribute
            })
        });

        if (data.error) {
            resultEl.innerHTML = '❌ ' + escapeHtml(data.error);
            if (btn) btn.disabled = false;
            return;
        }

        const roll = data.roll;
        const total = data.total;
        const success = data.success;

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
    }
    catch (e) {
        console.error('[ERROR] doSkillCheck:', e);
        resultEl.innerHTML = '❌ 掷骰失败，请重试';
        if (btn) btn.disabled = false;
    }
}

function addCustomInput() {
    const choicesArea = $('choicesArea');
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
export function renderStoryline() {
    const body = $('storylineBody');
    const sl = state.rpgState.storyline || [];
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

function reviewRound(round) {
    const sl = state.rpgState.storyline || [];
    const entry = sl.find(e => e.round === round);
    if (!entry) return;
    const storyText = entry.story || '（无故事记录）';
    const isCurrent = round === (sl.length > 0 ? sl[sl.length - 1].round : -1);

    $('reviewContent').innerHTML = renderMarkdown(storyText);
    $('reviewTitle').textContent = `第 ${round} 轮 · ${cleanText((entry.choice || '').slice(0, 50))}${isCurrent ? '（当前）' : ''}`;
    $('reviewModal').style.display = 'flex';
}

async function jumpToRound(round) {
    if (!state.rpgState.sessionId) return;
    if (!confirm(`确定回到第 ${round} 轮？之后的选择将被清空。`)) return;
    showLoading('⏳ 回溯中...', `回到第 ${round} 轮`);
    try {
        const data = await api(`/api/rpg/session/${state.rpgState.sessionId}/branch`, {
            method: 'POST',
            body: JSON.stringify({ round })
        });
        if (data.error) { toast(data.error); return; }
        state.rpgState.storyline = data.storyline || [];
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
}

export function renderRelationships(rels) {
    const body = $('relsBody');
    if (!body) return;
    if (!rels || Object.keys(rels).length === 0) {
        body.innerHTML = '<div class="status-empty" style="padding:12px 0;">暂无关系数据</div>';
        return;
    }
    body.innerHTML = Object.entries(rels).map(([k, v]) => {
        const cleanK = cleanText(k);
        const cleanV = cleanText(v);
        return `<div class="status-item"><span class="status-label">${escapeHtml(cleanK)}</span><span class="status-value highlight">${escapeHtml(cleanV)}</span></div>`;
    }).join('');
}

// ============================================================
// 区块 18 · 分享与观战
// ============================================================
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
    $('worldSelectScreen').style.display = 'none';
    $('gameScreen').style.display = 'none';
    $('spectateScreen').style.display = 'block';
    state.spectateToken = token;
    state.spectateMode = 'shared';
    const banner = $('spectateBanner');
    if (banner) {
        banner.className = 'spectate-banner';
        $('spectateBannerText').textContent = '👀 实时围观中';
    }
    $('spectateBadge').style.display = 'inline-block';
    $('spectateBadge').className = 'spectate-badge';
    $('spectateBadge').textContent = '🔒 只读';
    spectatePoll();
    if (state.spectateTimer) clearInterval(state.spectateTimer);
    state.spectateTimer = setInterval(spectatePoll, 2000);
}

export async function spectatePoll() {
    try {
        const url = state.spectateMode === 'admin'
            ? '/api/rpg/admin/spectate/' + state.spectateToken
            : '/api/rpg/shared/' + state.spectateToken;
        const d = await api(url);
        if (d.error) {
            $('specStoryText').textContent = state.spectateMode === 'admin' ? '会话不存在或已结束' : '会话已结束';
            if (state.spectateTimer) clearInterval(state.spectateTimer);
            return;
        }
        $('specWorldName').textContent = (d.world.emoji||'') + ' ' + d.world.name;
        $('specPlayerName').textContent = '🧑 ' + d.player_name;
        const rounds = d.storyline ? d.storyline.length : (d.rounds || 0);
        $('specRoundInfo').textContent = '⚡ 第' + (rounds + 1) + '轮 · ' + (state.spectateMode === 'admin' ? '实时监控' : '实时围观');
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

export function initRpg() {
    $('sessionsBarHeader')?.addEventListener('click', () => {
        $('sessionsBody').classList.toggle('collapsed');
        $('sessionsToggle').classList.toggle('collapsed');
    });

    $('reviewClose')?.addEventListener('click', () => {
        $('reviewModal').style.display = 'none';
    });
    $('reviewModal')?.addEventListener('click', (e) => {
        if (e.target === $('reviewModal')) $('reviewModal').style.display = 'none';
    });

    $('storylineHeader')?.addEventListener('click', () => {
        const body = $('storylineBody');
        const toggle = $('storylineToggle');
        body.classList.toggle('collapsed');
        toggle.classList.toggle('collapsed');
    });

    $('exitGameBtn')?.addEventListener('click', () => {
        $('exitConfirmModal').classList.add('show');
    });
    $('exitCancelBtn')?.addEventListener('click', () => {
        $('exitConfirmModal').classList.remove('show');
    });
    $('exitConfirmBtn')?.addEventListener('click', () => {
        $('exitConfirmModal').classList.remove('show');
        hideLoading();
        if (state.skillCheckTimer) { clearTimeout(state.skillCheckTimer); state.skillCheckTimer = null; }
        if (state.actGameStatusTimeout) { clearTimeout(state.actGameStatusTimeout); state.actGameStatusTimeout = null; }
        if (state.rpgAbortController) {
            state.rpgAbortController.abort();
            state.rpgAbortController = null;
        }
        state.rpgState = { sessionId: null, world: null, playerName: '', storyline: [], sections: null };
        $('gameScreen').style.display = 'none';
        $('worldSelectScreen').style.display = 'block';
        loadSessions();
        const shareBtn = $('shareBtn');
        if (shareBtn) shareBtn.style.display = 'none';
    });

    // 分享按钮
    const shareBtn = $('shareBtn');
    shareBtn?.addEventListener('click', async () => {
        if (!state.rpgState.sessionId) return;
        if (state.isShared) {
            const data = await api(`/api/rpg/session/${state.rpgState.sessionId}/unshare`, { method: 'POST' });
            if (data.error) { toast(data.error, 'error'); return; }
            state.isShared = false;
            shareBtn.textContent = '🔗 分享';
            toast('已取消分享，将从围观广场移除', 'info');
        } else {
            const data = await api(`/api/rpg/session/${state.rpgState.sessionId}/share`, { method: 'POST' });
            if (data.error) { toast(data.error, 'error'); return; }
            state.isShared = true;
            shareBtn.textContent = '🔓 取消分享';
            const shareUrl = data.share_url || '';
            $('shareUrlInput').value = shareUrl;
            $('shareSuccessModal').classList.add('show');
        }
        const square = $('spectateSquare');
        if (square) loadSpectateSquare();
    });

    $('shareCloseBtn')?.addEventListener('click', () => {
        $('shareSuccessModal').classList.remove('show');
    });

    $('copyShareUrlBtn')?.addEventListener('click', async () => {
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

    $('shareSuccessModal')?.addEventListener('click', e => {
        if (e.target === $('shareSuccessModal')) {
            $('shareSuccessModal').classList.remove('show');
        }
    });

    $('exitConfirmModal')?.addEventListener('click', e => {
        if (e.target === $('exitConfirmModal')) {
            $('exitConfirmModal').classList.remove('show');
        }
    });

    // 围观按钮
    $('spectateBtn')?.addEventListener('click', () => {
        const square = $('spectateSquare');
        if (square.style.display !== 'none') {
            square.style.display = 'none';
            if (state.spectateRefreshTimer) { clearInterval(state.spectateRefreshTimer); state.spectateRefreshTimer = null; }
            return;
        }
        loadSpectateSquare();
        square.style.display = 'block';
        if (!state.spectateRefreshTimer) state.spectateRefreshTimer = setManagedInterval(loadSpectateSquare, 5000);
    });

    $('specExitBtn')?.addEventListener('click', () => {
        if (state.spectateTimer) clearInterval(state.spectateTimer);
        state.spectateTimer = null;
        state.spectateMode = 'shared';
        $('spectateScreen').style.display = 'none';
        $('worldSelectScreen').style.display = 'block';
    });
}

// ===== END OF FILE =====
