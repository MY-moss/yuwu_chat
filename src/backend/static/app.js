// ============================================================
// 文件: app.js | 职责: 入口模块 — 初始化、模式切换、全局事件
// ============================================================
import { state } from './state.js';
import { $, toast, hideLoading } from './utils.js';
import { fetchCsrfToken } from './api.js';
import { checkAuth, loadVersion, initAuth } from './auth.js';
import { initChat } from './chat.js';
import { initRpg, loadWorlds, resumeGame } from './rpg.js';
import { initAgentUI } from './agent-ui.js';
import { initWorldUI } from './world-ui.js';
import { initAdmin } from './admin.js';
import { initPersonalApi } from './personal-api.js';
import { initExchange } from './exchange.js';

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

        document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));  // [AUDIT-Q31] querySelectorAll('.mode-tab') 多次重复查询
        document.querySelector(`.mode-tab[data-mode="${newMode}"]`)?.classList.add('active');

        document.querySelectorAll('.mobile-tab-item[data-mode]').forEach(t => t.classList.remove('active'));
        document.querySelector(`.mobile-tab-item[data-mode="${newMode}"]`)?.classList.add('active');

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

document.addEventListener('DOMContentLoaded', () => {
    fetchCsrfToken();
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
});

// ===== END OF FILE =====
