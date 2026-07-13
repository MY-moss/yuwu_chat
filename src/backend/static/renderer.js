// ============================================================
// 文件: renderer.js | 职责: Markdown渲染、代码高亮、文本清理、状态面板渲染
// UI 增强：renderEmptyChat() — 聊天空状态打字机提示（源自方案五）
// ============================================================
import { $, toast, escapeHtml, typewriter } from './utils.js';

const mdCache = new Map();

export function renderMarkdown(text) {
    if (!text) return '';
    let raw = String(text);
    raw = raw.replace(/\\n/g, '\n')
             .replace(/\\r/g, '\r')
             .replace(/\\t/g, '\t')
             .replace(/\\"/g, '"')
             .replace(/\\'/g, "'")
             .replace(/\\\\/g, '\\');

    if (mdCache.size >= 100) {
        const firstKey = mdCache.keys().next().value;
        mdCache.delete(firstKey);
    }

    let result;
    try {
        if (typeof marked !== 'undefined') {
            marked.setOptions({ breaks: true, gfm: true });
            const html = marked.parse(raw);
            if (typeof DOMPurify !== 'undefined' && DOMPurify.sanitize) {
                result = DOMPurify.sanitize(html, { ADD_TAGS: ['pre', 'code'], ADD_ATTR: ['class'] });
            } else {
                result = html.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            }
        } else {
            result = raw.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
        }
    } catch (e) {
        console.error('Render markdown failed:', e);
        toast('内容渲染失败', 'warn');
        result = raw.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
    }
    mdCache.set(raw, result);
    return result;
}

let highlightScheduled = false;

export function highlightCode(container) {
    if (highlightScheduled) return;
    highlightScheduled = true;
    setTimeout(() => {
        if (typeof hljs !== 'undefined') {
            if (container) {
                container.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
            } else {
                hljs.highlightAll();
            }
        }
        highlightScheduled = false;
    }, 100);
}

export function cleanText(t) {
    if (!t) return '';
    let text = String(t);
    text = text.replace(/\\n/g, '\n')
               .replace(/\\r/g, '\r')
               .replace(/\\t/g, '\t')
               .replace(/\\"/g, '"')
               .replace(/\\'/g, "'")
               .replace(/\\\\/g, '\\')
               .replace(/\n{3,}/g, '\n\n')
               .replace(/[ \t]+/g, ' ')
               .trim();
    return text;
}

export function renderStoryMarkdown(text) {
    return '<div class="md-body">' + renderMarkdown(text) + '</div>';
}

export function renderStory(text) {
    const storyText = $('storyText');
    const storyBox = $('storyBox');
    if (!storyText) return;
    storyText.innerHTML = renderStoryMarkdown(text);
    if (storyBox) storyBox.scrollTop = 0;
    setTimeout(() => highlightCode(storyText), 0);
}

// --- Personal Panel Rendering ---
const NARRATIVE_KEYS = new Set([
    '背景', '简介', '外貌', '外貌描述', '描述', '性格', '性格特点',
    '故事概要', '过往', '回忆', '内心独白', '世界观', '阵营', '信仰',
    '关系', '关系网', '关系_map', '剧情', '剧情摘要', '任务详情', '日志',
    '事件', '事件记录', '备注', '说明', '提示', '介绍', '剧情回顾'
]);

const DATA_KEYS = new Set([
    '状态', '属性', '技能', '能力', '天赋', '专长', '特质',
    '装备', '背包', '物品', '道具', '武器', '防具', '金钱', '资源',
    '任务', '进度', '成就', '称号', '法术', '招式', '绝技', '判定'
]);

export function extractDataPairs(rawValue) {
    const parts = rawValue.split(/\s+/);
    const pairs = [];
    let inData = true;
    for (const part of parts) {
        if (inData && part.includes(':')) {
            const colonIdx = part.indexOf(':');
            const label = part.slice(0, colonIdx);
            const value = part.slice(colonIdx + 1);
            if (label.length > 8) { inData = false; continue; }
            pairs.push({ label: label, value: value });
        } else if (part.length < 3 || part.match(/^[0-9+\-*/%]+$/)) {
            continue;
        } else {
            inData = false;
        }
    }
    return pairs;
}

export function hasMarkdownFormatting(str) {
    return /[*_`#\[\]~>|]/.test(str) && str.length > 6;
}

export function renderKeyDataSection(key, cleanedValue) {
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

export function renderStatus(sectionsOrText) {
    const personalContent = $('personalContent');
    if (!personalContent) return;
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
    let clean = cleanText(String(sectionsOrText).replace(/【[^】]*】/g, ''));
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

export function parseStatusValue(val) {
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

/**
 * 聊天空状态打字机提示（源自方案五）
 * 在聊天框空置时显示逐字浮现的欢迎/引导文字
 * @param {HTMLElement} container - 聊天框容器
 * @param {string} text - 提示文本，默认诗意引导语
 */
export function renderEmptyChat(container, text) {
    if (!container) return () => {};
    const existing = container.querySelector('.empty-typewriter');
    if (existing) existing.remove();

    const el = document.createElement('div');
    el.className = 'empty-typewriter';
    el.style.cssText = 'text-align:center;padding:60px 20px;color:var(--text-dim);font-size:15px;letter-spacing:1px;line-height:1.8;';
    container.appendChild(el);

    const msg = text || '夜色渐浓，酒馆的灯笼已经点亮……\n选一位旅伴，聊聊你的故事吧。';
    return typewriter(el, msg, { speed: 60, delay: 300 });
}

// ===== END OF FILE =====
