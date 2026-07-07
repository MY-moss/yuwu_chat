// ============================================================
// 文件: renderer.js | 职责: Markdown渲染、代码高亮、文本清理、状态面板渲染
// ============================================================
import { $, toast, escapeHtml } from './utils.js';

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

    if (mdCache.size > 100) mdCache.clear();  // [AUDIT-Q19] 超过100条时全清，应 LRU 逐出

    // [AUDIT-X02] 自定义 safeHtml 正则解析器可被绕过（先 strip 引号再解析属性），建议替换为 DOMPurify.sanitize()
    function safeHtml(html) {
        const tags = ['b','i','em','strong','a','pre','code','ul','ol','li','p','br','h1','h2','h3','h4','h5','h6','blockquote','hr','table','thead','tbody','tr','th','td','span','div','img'];
        const allowed = new RegExp('^(' + tags.join('|') + ')$', 'i');
        const attrAllow = new Set(['href','src','alt','title','class','target','rel']);
        return html.replace(/<[^>]*>/g, function(m) {
            if (m.startsWith('</')) {
                const tag = m.slice(2, -1).trim();
                return allowed.test(tag) ? m : '';
            }
            const m2 = m.match(/^\s*<(\/?)([\w-]+)(.*?)\/?\s*>$/);
            if (!m2) return '';
            const tag = m2[2], rest = m2[3];
            if (!allowed.test(tag)) return '';
            const attrs = rest.replace(/['"]/g, '').match(/([\w-]+)(?:=['"][^'"]*['"])?/g) || [];
            const safe = attrs.filter(a => {
                const eq = a.indexOf('=');
                const name = eq === -1 ? a : a.slice(0, eq);
                const value = eq === -1 ? '' : a.slice(eq + 1);
                if (!attrAllow.has(name) || name.startsWith('on')) return false;
                if ((name === 'href' || name === 'src') && /^\s*(javascript|data|vbscript):/i.test(value)) return false;
                return true;
            }).join(' ');
            return safe ? '<' + tag + ' ' + safe + '>' : '<' + tag + '>';
        });
    }
    let result;
    try {
        if (typeof marked !== 'undefined') {
            marked.setOptions({ breaks: true, gfm: true });
            const html = marked.parse(raw);
            if (typeof DOMPurify !== 'undefined' && DOMPurify.sanitize) {
                result = DOMPurify.sanitize(html, { ADD_TAGS: ['pre', 'code'], ADD_ATTR: ['class'] });
            } else {
                result = safeHtml(html);
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

export function renderStory(text) {
    const storyText = $('storyText');
    const storyBox = $('storyBox');
    if (!storyText) return;
    storyText.innerHTML = renderMarkdown(text);
    if (storyBox) storyBox.scrollTop = 0;
    setTimeout(() => highlightCode(), 0);
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

// ===== END OF FILE =====
