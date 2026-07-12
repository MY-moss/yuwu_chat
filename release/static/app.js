// ============================================================
// 文件: app.js | 职责: 入口模块 — 初始化、模式切换、全局事件
// ============================================================
import { state } from './state.js';
import { $, toast, hideLoading, typewriter, initCounters } from './utils.js';
import { fetchCsrfToken } from './api.js';
import { checkAuth, loadVersion, initAuth } from './auth.js';
import { initChat } from './chat.js';
import { initRpg, loadWorlds, resumeGame } from './rpg.js';
import { initAgentUI } from './agent-ui.js';
import { initWorldUI } from './world-ui.js';
import { initAdmin } from './admin.js';
import { initPersonalApi } from './personal-api.js';
import { initExchange } from './exchange.js';
import { initThreeBg, setRingsVisible } from './three-bg.js';
import { applyWorldCard3D, applyChatBubble3D } from './three-card.js';

async function switchMode(newMode) {
    if (state.isSwitchingMode || state.currentMode === newMode) return;
    state.isSwitchingMode = true;

    if (state.currentMode === 'rpg' && newMode !== 'rpg') {
        if (state.rpgAbortController) {
            state.rpgAbortController.abort();
            state.rpgAbortController = null;
        }
        state._rpgRequestActive = false;
        hideLoading();
    }

    try {
        const chatModeEl = document.getElementById('chatMode');
        const rpgModeEl = document.getElementById('rpgMode');

        chatModeEl.style.opacity = '0';
        rpgModeEl.style.opacity = '0';

        await new Promise(resolve => setTimeout(resolve, 300));

        state.currentMode = newMode;

        document.querySelectorAll('.mode-tab').forEach(t => t.classList.toggle('active', t.dataset.mode === newMode));
        document.querySelectorAll('.mobile-tab-item[data-mode]').forEach(t => t.classList.toggle('active', t.dataset.mode === newMode));

        const worldSelectScreen = $('worldSelectScreen');
        const gameScreen = $('gameScreen');
        const storyText = $('storyText');

        if (state.currentMode === 'chat') {
            chatModeEl.style.display = 'flex';
            rpgModeEl.style.display = 'none';
            setTimeout(() => { chatModeEl.style.opacity = '1'; }, 50);
        } else if (state.currentMode === 'rpg') {
            chatModeEl.style.display = 'none';
            rpgModeEl.style.display = 'flex';
            setTimeout(() => { rpgModeEl.style.opacity = '1'; }, 50);
            loadWorlds();
            if (state.rpgState.sessionId) {
                gameScreen.style.display = 'flex';
                worldSelectScreen.style.display = 'none';
                if (!storyText.textContent || storyText.textContent.includes('服务器内部错误')) {
                    resumeGame(state.rpgState.sessionId).catch(e => {
                        console.error('[ERROR] resumeGame on tab switch:', e);
                        state.rpgState.sessionId = null;
                        gameScreen.style.display = 'none';
                        worldSelectScreen.style.display = 'block';
                    });
                }
            } else {
                gameScreen.style.display = 'none';
                worldSelectScreen.style.display = 'block';
            }
        }
    } catch (e) {
        console.error('[ERROR] switchMode:', e);
        toast('模式切换失败', 'error');
    } finally {
        state.isSwitchingMode = false;
    }
}

function initGlobalEvents() {
    document.querySelectorAll('.mode-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            hideLoading();
            switchMode(tab.dataset.mode);
        });
    });

    document.querySelectorAll('.panel-toggle').forEach(btn => {
        btn.addEventListener('click', () => {
            const panel = btn.dataset.panel;
            const panelEl = document.getElementById(panel);
            if (panelEl) {
                panelEl.classList.toggle('collapsed');
            }
        });
    });

    document.querySelectorAll('.mobile-tab-item[data-mode]').forEach(tab => {
        tab.addEventListener('click', () => {
            hideLoading();
            switchMode(tab.dataset.mode);
        });
    });

    $('dashboardBtn')?.addEventListener('click', () => {
        window.open('/dashboard', '_blank');
    });

    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            state._timers.forEach(id => { clearInterval(id); });
            state._timers.clear();
            state.spectateTimer = null;
            state.spectateRefreshTimer = null;
        }
    });

    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/sw.js').then((registration) => {
            registration.addEventListener('updatefound', () => {
                const newWorker = registration.installing;
                newWorker.addEventListener('statechange', () => {
                    if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                        toast('发现新版本，刷新页面以更新', 'info');
                    }
                });
            });
        }).catch((error) => {
            console.error('Service Worker registration failed:', error);
        });
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    await fetchCsrfToken();
    checkAuth();
    loadVersion();

    initAuth();
    initChat();
    initRpg();
    initAgentUI();
    initWorldUI();
    initAdmin();
    initPersonalApi();
    initExchange();
    initGlobalEvents();
    initCounters();

    // Three.js 3D 粒子背景初始化（WebGL 不支持时降级为 CSS 背景）
    initThreeBg().then(ok => {
        if (ok) console.info('[app] Three.js 背景已启用');
    });

    // 认证屏副标题打字机效果
    const authSub = $('authSub');
    if (authSub) {
        typewriter(authSub, '欢迎回来，旅人', { speed: 80, delay: 400, cursor: true });
    }

    // 认证屏光标聚光灯效果（源自方案一）
    const cleanupSpotlight = initSpotlight();
    window.addEventListener('beforeunload', cleanupSpotlight);

    // M11: 页面卸载时清理所有定时器，防止内存泄漏
    window.addEventListener('beforeunload', () => {
        if (state._timers && state._timers.size > 0) {
            state._timers.forEach(id => clearInterval(id));
            state._timers.clear();
        }
        if (state._heartbeatInterval) clearInterval(state._heartbeatInterval);
        if (state.spectateTimer) clearInterval(state.spectateTimer);
        if (state.spectateRefreshTimer) clearInterval(state.spectateRefreshTimer);
        if (state.actGameStatusTimeout) clearTimeout(state.actGameStatusTimeout);
    });

    // 跑马灯无缝循环（源自方案六）
    initMarquee();
});

/**
 * 光标聚光灯：鼠标在认证屏移动时，光标周围柔和揭示暖色纹理层
 * 使用 CSS mask-image + 变量驱动，RAF 平滑跟随
 * 实现方式：CSS 变量驱动（优于原始 Canvas toDataURL 方案，性能更好）
 * 触屏设备通过 (hover: none) 媒体查询检测，直接降级为静态背景
 */
function initSpotlight() {
    const reveal = $('spotlightReveal');
    const authScreen = $('authScreen');
    if (!reveal || !authScreen) return () => {};

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return () => {};
    if (window.matchMedia('(hover: none)').matches) return () => {}; // 触屏设备无 mousemove

    const SMOOTH = 0.12;
    const mouse = { x: -999, y: -999 };
    const smooth = { x: -999, y: -999 };
    let rafId = null;
    let active = false;

    const onMove = (e) => {
        const rect = authScreen.getBoundingClientRect();
        mouse.x = e.clientX - rect.left;
        mouse.y = e.clientY - rect.top;
        if (!active) {
            active = true;
            reveal.classList.add('active');
        }
        if (!rafId) rafId = requestAnimationFrame(loop);
    };

    const onLeave = () => {
        active = false;
        reveal.classList.remove('active');
        mouse.x = -999;
        mouse.y = -999;
        smooth.x = -999;
        smooth.y = -999;
        if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
    };

    const loop = () => {
        smooth.x += (mouse.x - smooth.x) * SMOOTH;
        smooth.y += (mouse.y - smooth.y) * SMOOTH;
        reveal.style.setProperty('--mx', smooth.x + 'px');
        reveal.style.setProperty('--my', smooth.y + 'px');
        if (Math.abs(mouse.x - smooth.x) > 0.5 || Math.abs(mouse.y - smooth.y) > 0.5) {
            rafId = requestAnimationFrame(loop);
        } else {
            rafId = null;
        }
    };

    authScreen.addEventListener('mousemove', onMove);
    authScreen.addEventListener('mouseleave', onLeave);

    return () => {
        authScreen.removeEventListener('mousemove', onMove);
        authScreen.removeEventListener('mouseleave', onLeave);
        if (rafId) cancelAnimationFrame(rafId);
    };
}

/**
 * 跑马灯无缝循环：复制 .marquee-track 内容，实现无缝滚动
 * 配合 .animate-marquee-left / .animate-marquee-right 使用
 * 克隆内容设置 aria-hidden="true" 避免屏幕阅读器重复朗读
 * dataset.marqueeInited 防止重复初始化（模式切换等场景）
 */
function initMarquee() {
    document.querySelectorAll('.marquee-track').forEach(track => {
        if (track.dataset.marqueeInited) return;
        track.dataset.marqueeInited = '1';
        const clone = track.cloneNode(true);
        clone.setAttribute('aria-hidden', 'true');
        track.parentNode.appendChild(clone);
    });
}

// ===== END OF FILE =====
