// ===== Feedback Page Logic =====
let currentPage = 1;
let currentUser = null;
let isAdmin = false;
let csrfToken = '';

const $ = id => document.getElementById(id);
const toastContainer = $('toastContainer');

function toast(msg, type) {
    const d = document.createElement('div');
    d.className = 'toast ' + (type || 'info');
    d.textContent = msg;
    toastContainer.appendChild(d);
    setTimeout(() => d.classList.add('show'), 10);
    setTimeout(() => { d.classList.remove('show'); setTimeout(() => d.remove(), 300); }, 2500);
}

async function fetchCsrfToken() {
    try {
        const res = await fetch('/api/csrf-token', { credentials: 'include' });
        const data = await res.json();
        csrfToken = data.csrf_token || '';
    } catch {}
}

fetchCsrfToken();

// ===== API Helpers =====
async function api(url, options = {}) {
    const headers = { 'Content-Type': 'application/json' };
    if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken;
    }
    const res = await fetch(url, {
        headers: { ...headers, ...options.headers },
        credentials: 'include',
        ...options
    });
    return res.json();
}

function authApi(url, options = {}) {
    return api(url, options);
}

// ===== Init =====
async function init() {
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
}

// ===== Rating Stars =====
function setupRating() {
    const stars = document.querySelectorAll('.fb-star');
    let currentRating = 3;
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
}

function getRating() {
    let r = 3;
    document.querySelectorAll('.fb-star.active').forEach(s => {
        const v = parseInt(s.dataset.value);
        if (v > r) r = v;
    });
    return r;
}

// ===== Submit =====
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

        const res = await authApi('/api/feedback', {
            method: 'POST',
            body: JSON.stringify({
                category: $('fbCategory').value,
                rating: getRating(),
                title: title,
                content: content
            })
        });

        btn.disabled = false;
        btn.textContent = '✉️ 提交反馈';

        if (res.error) {
            toast(res.error, 'error');
        } else {
            toast(res.message || '提交成功！', 'success');
            $('fbTitle').value = '';
            $('fbContent').value = '';
            currentPage = 1;
            loadFeedbackList();
            if (isAdmin) loadStats();
        }
    });
}

// ===== Filters =====
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

// ===== Load List =====
async function loadFeedbackList() {
    const category = $('fbFilterCategory').value;
    const status = $('fbFilterStatus').value;
    const search = $('fbSearchInput').value.trim();

    let url = `/api/feedback?page=${currentPage}&per_page=15`;
    if (category) url += `&category=${encodeURIComponent(category)}`;
    if (status) url += `&status=${encodeURIComponent(status)}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;

    const data = await authApi(url);

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
        <div class="fb-card" onclick="openFbDetail(${fb.id})">
            <div class="fb-card-header">
                <div class="fb-card-title">${escapeHtml(fb.title)}</div>
                <div class="fb-card-meta">
                    <span class="fb-card-rating">${ratingStars}</span>
                </div>
            </div>
            <div class="fb-card-content">${escapeHtml(fb.content)}</div>
            <div class="fb-card-footer">
                <div style="display:flex;gap:6px;align-items:center;">
                    <span class="fb-tag fb-tag-${fb.category}">${categoryNames[fb.category] || fb.category}</span>
                    <span class="fb-status fb-status-${fb.status}">${statusNames[fb.status] || fb.status}</span>
                </div>
                <span>${escapeHtml(fb.username)} · ${formatDate(fb.created_at)}</span>
            </div>
        </div>`;
    }).join('');

    if (data.pages > 1) {
        $('fbPagination').style.display = 'flex';
        let pagesHtml = `<button class="fb-page-btn" onclick="goPage(${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''}>◀</button>`;
        for (let i = 1; i <= data.pages; i++) {
            pagesHtml += `<button class="fb-page-btn ${i === currentPage ? 'active' : ''}" onclick="goPage(${i})">${i}</button>`;
        }
        pagesHtml += `<button class="fb-page-btn" onclick="goPage(${currentPage + 1})" ${currentPage === data.pages ? 'disabled' : ''}>▶</button>`;
        $('fbPagination').innerHTML = pagesHtml;
    } else {
        $('fbPagination').style.display = 'none';
    }
}

function goPage(page) {
    currentPage = page;
    loadFeedbackList();
}

function formatDate(dateStr) {
    try {
        return new Date(dateStr).toLocaleString('zh-CN');
    } catch {
        return dateStr;
    }
}

// ===== Stats (Admin) =====
async function loadStats() {
    const data = await authApi('/api/feedback/stats');
    if (data.error) return;
    $('statTotal').textContent = data.total;
    $('statOpen').textContent = data.open;
    $('statProgress').textContent = data.in_progress;
    $('statResolved').textContent = data.resolved;
    $('statRating').textContent = data.avg_rating;
}

// ===== Detail Modal =====
async function openFbDetail(id) {
    const data = await authApi(`/api/feedback/${id}`);
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
            <span class="fb-tag fb-tag-${fb.category}">${categoryNames[fb.category]}</span>
            <span class="fb-status fb-status-${fb.status}" style="margin-left:6px;">${statusNames[fb.status]}</span>
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
            <button class="fb-admin-save" onclick="saveFbDetail(${fb.id})">💾 保存</button>
            <button class="fb-admin-delete" onclick="deleteFb(${fb.id})">🗑 删除</button>
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
    const res = await authApi(`/api/feedback/${id}`, {
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
    if (!confirm('确定要删除这条反馈吗？')) return;
    const res = await authApi(`/api/feedback/${id}`, { method: 'DELETE' });
    if (res.error) {
        toast(res.error, 'error');
    } else {
        toast('已删除', 'success');
        closeFbDetail();
        loadFeedbackList();
        if (isAdmin) loadStats();
    }
}

function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
}

init();