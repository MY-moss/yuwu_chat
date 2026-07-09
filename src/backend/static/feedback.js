// ============================================================
// 文件: feedback.js | 职责: 反馈页面逻辑 | 区块数: 9
// ============================================================
import { $, escapeHtml, formatDate, toast } from './utils.js';
import { api, fetchCsrfToken } from './api.js';

// ============================================================
// 区块 01 · 全局状态
// ============================================================
let currentPage = 1;
let currentUser = null;
let isAdmin = false;
let currentRating = 3;

// ============================================================
// 区块 02 · 初始化
// ============================================================
async function init() {
    try {
        await fetchCsrfToken();
        const meRes = await api('/api/auth/me');
        if (meRes.error || !meRes.username) {
            window.location.href = '/';
            return;
        }
        currentUser = meRes;
        isAdmin = currentUser.role === 'admin';
        $('usernameDisplay').textContent = currentUser.username;

        if (isAdmin) {
            $('statsBar').style.display = 'flex';
            loadStats();
        }

        loadFeedbackList();
        setupRating();
        setupFormSubmit();
        setupFilters();
    } catch (e) {
        console.error('[ERROR] feedback init:', e);
        toast('页面初始化失败，请刷新重试', 'error');
    }
    $('backToTavernBtn').addEventListener('click', () => window.location.href = '/');
    $('fbDetailClose').addEventListener('click', closeFbDetail);
    $('fbList').addEventListener('click', e => {
        const card = e.target.closest('.fb-card');
        if (card && card.dataset.fbId) openFbDetail(parseInt(card.dataset.fbId));
    });
    $('fbPagination').addEventListener('click', e => {
        const btn = e.target.closest('.fb-page-btn');
        if (btn && !btn.disabled && btn.dataset.page) goPage(parseInt(btn.dataset.page));
    });
    $('fbDetailModal').addEventListener('click', e => {
        const btn = e.target.closest('button[data-action]');
        if (!btn) return;
        const id = parseInt(btn.dataset.fbId);
        if (btn.dataset.action === 'save') saveFbDetail(id);
        if (btn.dataset.action === 'delete') deleteFb(id);
    });
}

// ============================================================
// 区块 04 · 评分星星
// ============================================================
function setupRating() {
    const stars = document.querySelectorAll('.fb-star');
    stars.forEach(star => {
        star.addEventListener('click', () => {
            currentRating = parseInt(star.dataset.value);
            stars.forEach(s => {
                s.classList.toggle('active', parseInt(s.dataset.value) <= currentRating);
            });
        });
        star.addEventListener('mouseenter', () => {
            const val = parseInt(star.dataset.value);
            stars.forEach(s => {
                s.classList.toggle('active', parseInt(s.dataset.value) <= val);
            });
        });
    });
    document.getElementById('fbRating').addEventListener('mouseleave', () => {
        stars.forEach(s => {
            s.classList.toggle('active', parseInt(s.dataset.value) <= currentRating);
        });
    });
    stars.forEach(s => {
        s.classList.toggle('active', parseInt(s.dataset.value) <= currentRating);
    });
}

function getRating() {
    const activeStars = document.querySelectorAll('.fb-star.active');
    if (activeStars.length === 0) return 3;
    let r = 0;
    activeStars.forEach(s => {
        const v = parseInt(s.dataset.value);
        if (v > r) r = v;
    });
    return r || 3;
}

// ============================================================
// 区块 05 · 提交反馈
// ============================================================
function setupFormSubmit() {
    $('fbSubmitBtn').addEventListener('click', async () => {
        const title = $('fbTitle').value.trim();
        const content = $('fbContent').value.trim();
        if (!title || !content) {
            toast('请填写标题和内容', 'warn');
            return;
        }

        const btn = $('fbSubmitBtn');
        btn.disabled = true;
        btn.textContent = '提交中...';

        try {
            const res = await api('/api/feedback', {
                method: 'POST',
                body: JSON.stringify({
                    category: $('fbCategory').value,
                    rating: getRating(),
                    title: title,
                    content: content
                })
            });

            if (res.error) {
                toast(res.error, 'error');
            } else {
                toast(res.message || '提交成功！', 'success');
                $('fbTitle').value = '';
                $('fbContent').value = '';
                $('fbCategory').value = 'suggestion';
                currentRating = 3;
                document.querySelectorAll('.fb-star').forEach(s => {
                    s.classList.toggle('active', parseInt(s.dataset.value) <= 3);
                });
                currentPage = 1;
                loadFeedbackList();
                if (isAdmin) loadStats();
            }
        } catch (e) {
            console.error('[ERROR] submit feedback:', e);
            toast('提交失败，请检查网络连接', 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = '✉️ 提交反馈';
        }
    });
}

// ============================================================
// 区块 06 · 筛选器
// ============================================================
function setupFilters() {
    $('fbFilterCategory').addEventListener('change', () => { currentPage = 1; loadFeedbackList(); });
    $('fbFilterStatus').addEventListener('change', () => { currentPage = 1; loadFeedbackList(); });
    $('fbSearchInput').addEventListener('input', debounce(() => { currentPage = 1; loadFeedbackList(); }, 300));
}

function debounce(fn, delay) {
    let timer = null;
    return function () {
        clearTimeout(timer);
        timer = setTimeout(fn, delay);
    };
}

// ============================================================
// 区块 07 · 加载列表
// ============================================================
async function loadFeedbackList() {
    const category = $('fbFilterCategory').value;
    const status = $('fbFilterStatus').value;
    const search = $('fbSearchInput').value.trim();

    let url = `/api/feedback?page=${currentPage}&per_page=15`;
    if (category) url += `&category=${encodeURIComponent(category)}`;
    if (status) url += `&status=${encodeURIComponent(status)}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;

    showFeedbackSkeleton();

    const data = await api(url);

    if (data.error) {
        $('fbList').innerHTML = `<div class="fb-empty">加载失败: ${escapeHtml(data.error)}</div>`;
        return;
    }

    if (!data.items || data.items.length === 0) {
        $('fbList').innerHTML = '<div class="fb-empty">暂无反馈数据</div>';
        $('fbPagination').style.display = 'none';
        return;
    }

    const categoryNames = { bug: 'Bug', feature: '功能建议', suggestion: '改进建议', praise: '好评', other: '其他' };
    const statusNames = { open: '待处理', in_progress: '处理中', resolved: '已解决', closed: '已关闭' };

    $('fbList').innerHTML = data.items.map(fb => {
        const ratingStars = Array.from({ length: 5 }, (_, i) =>
            i < fb.rating ? '<span class="star-on">★</span>' : '<span class="star-off">☆</span>'
        ).join('');

        return `
        <div class="fb-card" data-fb-id="${fb.id}">
            <div class="fb-card-header">
                <div class="fb-card-title">${escapeHtml(fb.title)}</div>
                <div class="fb-card-meta">
                    <span class="fb-card-rating">${ratingStars}</span>
                </div>
            </div>
            <div class="fb-card-content">${escapeHtml(fb.content)}</div>
            <div class="fb-card-footer">
                <div style="display:flex;gap:6px;align-items:center;">
                    <span class="fb-tag fb-tag-${escapeHtml(fb.category)}">${categoryNames[fb.category] || fb.category}</span>
                    <span class="fb-status fb-status-${escapeHtml(fb.status)}">${statusNames[fb.status] || fb.status}</span>
                </div>
                <span>${escapeHtml(fb.username)} · ${formatDate(fb.created_at)}</span>
            </div>
        </div>`;
    }).join('');

    if (data.pages > 1) {
        $('fbPagination').style.display = 'flex';
        let pagesHtml = `<button class="fb-page-btn" data-page="${currentPage - 1}" ${currentPage === 1 ? 'disabled' : ''}>◀</button>`;
        for (let i = 1; i <= data.pages; i++) {
            pagesHtml += `<button class="fb-page-btn ${i === currentPage ? 'active' : ''}" data-page="${i}">${i}</button>`;
        }
        pagesHtml += `<button class="fb-page-btn" data-page="${currentPage + 1}" ${currentPage === data.pages ? 'disabled' : ''}>▶</button>`;
        $('fbPagination').innerHTML = pagesHtml;
    } else {
        $('fbPagination').style.display = 'none';
    }
}

function goPage(page) {
    currentPage = page;
    loadFeedbackList();
}

function showFeedbackSkeleton() {
    const skeleton = Array.from({ length: 5 }, () => `
        <div class="fb-skeleton-card">
            <div class="fb-skeleton-title"></div>
            <div class="fb-skeleton-content"></div>
            <div class="fb-skeleton-content"></div>
            <div class="fb-skeleton-footer">
                <div class="fb-skeleton-tag"></div>
                <div class="fb-skeleton-time"></div>
            </div>
        </div>
    `).join('');
    $('fbList').innerHTML = skeleton;
    $('fbPagination').style.display = 'none';
}

// ============================================================
// 区块 08 · 统计（管理员）
// ============================================================
async function loadStats() {
    const data = await api('/api/feedback/stats');
    if (data.error) return;
    $('statTotal').textContent = data.total;
    $('statOpen').textContent = data.open;
    $('statProgress').textContent = data.in_progress;
    $('statResolved').textContent = data.resolved;
    $('statRating').textContent = data.avg_rating;
}

// ============================================================
// 区块 09 · 详情弹窗
// ============================================================
async function openFbDetail(id) {
    const data = await api(`/api/feedback/${id}`);
    if (data.error) {
        toast(data.error, 'error');
        return;
    }
    const fb = data;

    const categoryNames = { bug: 'Bug', feature: '功能建议', suggestion: '改进建议', praise: '好评', other: '其他' };
    const statusNames = { open: '待处理', in_progress: '处理中', resolved: '已解决', closed: '已关闭' };
    const statusOptions = Object.entries(statusNames).map(([k, v]) =>
        `<option value="${k}" ${fb.status === k ? 'selected' : ''}>${v}</option>`
    ).join('');

    const ratingStars = Array.from({ length: 5 }, (_, i) =>
        i < fb.rating ? '<span class="star-on">★</span>' : '<span class="star-off">☆</span>'
    ).join('');

    $('fbDetailTitle').textContent = '反馈详情 #' + fb.id;
    $('fbDetailBody').innerHTML = `
        <div class="fb-detail-title">${escapeHtml(fb.title)}</div>
        <div class="fb-detail-section">
            <div class="fb-detail-label">分类</div>
            <span class="fb-tag fb-tag-${escapeHtml(fb.category)}">${categoryNames[fb.category] || fb.category}</span>
            <span class="fb-status fb-status-${escapeHtml(fb.status)}" style="margin-left:6px;">${statusNames[fb.status] || fb.status}</span>
            <span class="fb-card-rating" style="margin-left:8px;">${ratingStars}</span>
        </div>
        <div class="fb-detail-section">
            <div class="fb-detail-label">内容</div>
            <div class="fb-detail-value">${escapeHtml(fb.content)}</div>
        </div>
        <div class="fb-detail-section">
            <div class="fb-detail-label">提交者</div>
            <div class="fb-detail-value">${escapeHtml(fb.username)} · ${formatDate(fb.created_at)}</div>
        </div>
        ${fb.admin_note ? `
        <div class="fb-detail-section">
            <div class="fb-detail-label">管理员备注</div>
            <div class="fb-detail-value" style="color:var(--gold-dim);">${escapeHtml(fb.admin_note)}</div>
        </div>` : ''}
        ${isAdmin ? `
        <div class="fb-admin-actions">
            <select class="fb-admin-status-select" id="adminStatus">
                ${statusOptions}
            </select>
            <input type="text" class="fb-admin-note" id="adminNote" placeholder="管理员备注..." value="${escapeHtml(fb.admin_note || '')}">
            <button class="fb-admin-save" data-action="save" data-fb-id="${fb.id}">💾 保存</button>
            <button class="fb-admin-delete" data-action="delete" data-fb-id="${fb.id}">🗑 删除</button>
        </div>` : ''}
    `;
    $('fbDetailModal').style.display = 'flex';
}

function closeFbDetail() {
    $('fbDetailModal').style.display = 'none';
}

async function saveFbDetail(id) {
    const status = $('adminStatus').value;
    const adminNote = $('adminNote').value.trim();
    const res = await api(`/api/feedback/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ status, admin_note: adminNote })
    });
    if (res.error) {
        toast(res.error, 'error');
    } else {
        toast('已更新', 'success');
        closeFbDetail();
        loadFeedbackList();
        if (isAdmin) loadStats();
    }
}

async function deleteFb(id) {
    if (!await showConfirmModal('确定要删除这条反馈吗？')) return;
    const res = await api(`/api/feedback/${id}`, { method: 'DELETE' });
    if (res.error) {
        toast(res.error, 'error');
    } else {
        toast('已删除', 'success');
        closeFbDetail();
        loadFeedbackList();
        if (isAdmin) loadStats();
    }
}

function showConfirmModal(msg) {
    const overlay = $('fbConfirmModal');
    const msgEl = $('fbConfirmMsg');
    if (!overlay || !msgEl) return Promise.resolve(false);
    msgEl.textContent = msg;
    overlay.style.display = 'flex';
    overlay.classList.add('show');
    return new Promise(resolve => {
        const cleanup = () => {
            overlay.style.display = 'none';
            overlay.classList.remove('show');
            $('fbConfirmOk').onclick = null;
            $('fbConfirmCancel').onclick = null;
        };
        $('fbConfirmOk').onclick = () => { cleanup(); resolve(true); };
        $('fbConfirmCancel').onclick = () => { cleanup(); resolve(false); };
    });
}

// ES Module defer: DOM已就绪，直接初始化
init();

// ===== END OF FILE =====