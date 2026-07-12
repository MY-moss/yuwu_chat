// ============================================================
// 文件: three-card.js | 职责: CSS 3D 卡片效果（世界书卡片+聊天气泡）
// ============================================================
import { THREE_CONFIG } from './three-config.js';

/**
 * 为世界书卡片添加 3D 倾斜效果
 * 在卡片渲染后调用 applyWorldCard3D() 绑定事件
 */
export function applyWorldCard3D() {
    const cfg = THREE_CONFIG.WORLD_CARD_3D;
    if (!cfg.enabled) return;

    document.querySelectorAll('.world-card').forEach(card => {
        if (card.dataset.card3dInit) return;
        card.dataset.card3dInit = '1';

        card.style.transformStyle = 'preserve-3d';
        card.style.transition = `transform ${cfg.transitionSpeed}s ease-out, box-shadow ${cfg.transitionSpeed}s ease-out`;
        card.style.willChange = 'transform';

        const glare = document.createElement('div');
        glare.className = 'wc-glare';
        glare.style.cssText = `
            position: absolute; inset: 0; border-radius: inherit;
            background: linear-gradient(135deg, rgba(255,255,255,${cfg.glareOpacity}) 0%, transparent 50%);
            opacity: 0; pointer-events: none; transition: opacity ${cfg.transitionSpeed}s;
            z-index: 1;
        `;
        card.style.position = 'relative';
        card.appendChild(glare);

        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const cx = rect.width / 2;
            const cy = rect.height / 2;
            const rotateX = ((y - cy) / cy) * -cfg.maxTilt;
            const rotateY = ((x - cx) / cx) * cfg.maxTilt;

            card.style.transform = `perspective(${cfg.perspective}px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale(${cfg.scale})`;
            card.style.boxShadow = `${(x - cx) / cx * cfg.shadowStrength * 10}px ${(y - cy) / cy * cfg.shadowStrength * 10}px ${cfg.shadowStrength * 30}px rgba(0,0,0,0.5)`;

            glare.style.opacity = '1';
            glare.style.background = `radial-gradient(circle at ${x}px ${y}px, rgba(255,215,0,${cfg.glareOpacity}) 0%, transparent 60%)`;
        });

        card.addEventListener('mouseleave', () => {
            card.style.transform = `perspective(${cfg.perspective}px) rotateX(0) rotateY(0) scale(1)`;
            card.style.boxShadow = '';
            glare.style.opacity = '0';
        });
    });
}

/**
 * 为聊天消息气泡添加 3D 阴影和悬停倾斜效果
 * 在消息渲染后调用 applyChatBubble3D() 绑定事件
 */
export function applyChatBubble3D() {
    const cfg = THREE_CONFIG.CHAT_BUBBLE_3D;
    if (!cfg.enabled) return;

    const bubbles = document.querySelectorAll('.message, .msg, [class*="message-"]');
    bubbles.forEach(bubble => {
        if (bubble.dataset.bubble3dInit) return;
        bubble.dataset.bubble3dInit = '1';

        bubble.style.transition = `transform 0.2s ease-out, box-shadow 0.2s ease-out`;

        bubble.addEventListener('mouseenter', () => {
            const isUser = bubble.classList.contains('user');
            const tiltDir = isUser ? 1 : -1;
            bubble.style.transform = `perspective(${cfg.perspective}px) rotateY(${tiltDir * cfg.tiltOnHover}deg) translateY(-${cfg.shadowDepth * 0.3}px)`;
            bubble.style.boxShadow = `0 ${cfg.shadowDepth}px ${cfg.shadowBlur}px ${cfg.shadowColor}`;
        });

        bubble.addEventListener('mouseleave', () => {
            bubble.style.transform = '';
            bubble.style.boxShadow = '';
        });
    });
}

// ===== END OF FILE =====
