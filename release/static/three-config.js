// ============================================================
// 文件: three-config.js | 职责: Three.js 效果统一配置入口
// ============================================================
// 所有 Three.js 效果的配置参数集中在此管理，避免碎片化修改。
// 切换策略只需改配置，不需改业务逻辑。

export const THREE_CONFIG = {
    // --- CDN 资源配置 ---
    CDN: {
        THREE_URL: 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js'
    },

    // --- 性能配置 ---
    PERFORMANCE: {
        MAX_FPS: 60,
        PARTICLE_COUNT_DESKTOP: 3000,
        PARTICLE_COUNT_MOBILE: 1200,
        PARTICLE_COUNT_LOW_END: 600,
        DPR_MAX: 2,
        FRAME_INTERVAL: 1000 / 60
    },

    // --- 方案1: 3D 粒子背景系统 ---
    PARTICLE_BG: {
        enabled: true,
        canvasId: 'threeCanvas',
        colors: [0xc8a84e, 0xf0c060, 0xa08030, 0xe8c878],
        particleSize: 2.5,
        particleSizeAttenuation: true,
        spread: { x: 120, y: 80, z: 60 },
        speed: 0.015,
        rotationSpeed: 0.0005,
        opacity: { min: 0.15, max: 0.65 },
        opacitySpeed: 0.008,
        cameraZ: 50,
        fogNear: 40,
        fogFar: 120
    },

    // --- 方案2: 登录界面 3D 装饰环 ---
    AUTH_RINGS: {
        enabled: true,
        ringCount: 3,
        rings: [
            { radius: 8, tube: 0.12, color: 0xc8a84e, opacity: 0.4, rotSpeed: { x: 0.003, y: 0.005, z: 0 } },
            { radius: 10, tube: 0.08, color: 0xf0c060, opacity: 0.25, rotSpeed: { x: 0, y: -0.004, z: 0.002 } },
            { radius: 12, tube: 0.06, color: 0xa08030, opacity: 0.15, rotSpeed: { x: 0.002, y: 0.003, z: -0.001 } }
        ],
        glowIntensity: 0.6,
        cameraZ: 20
    },

    // --- 方案3: 世界书卡片 3D 效果 ---
    WORLD_CARD_3D: {
        enabled: true,
        maxTilt: 12,
        perspective: 1000,
        scale: 1.04,
        transitionSpeed: 0.3,
        shadowStrength: 0.4,
        glareOpacity: 0.15
    },

    // --- 方案4: 聊天消息 3D 阴影 ---
    CHAT_BUBBLE_3D: {
        enabled: true,
        shadowDepth: 8,
        shadowBlur: 16,
        shadowColor: 'rgba(0, 0, 0, 0.4)',
        tiltOnHover: 1.5,
        perspective: 800
    },

    // --- 方案5: 模式切换 3D 过渡动画（相机穿越粒子层）---
    MODE_TRANSITION: {
        enabled: true,
        duration: 800,
        cameraPushZ: 80,
        particleSpeedBoost: 3,
        fogDensity: 0.015
    },

    // --- 方案6: 发送/接收消息粒子特效 ---
    MESSAGE_PARTICLES: {
        enabled: true,
        sendCount: 80,
        receiveCount: 60,
        duration: 1000,
        sendColor: 0xc8a84e,
        receiveColor: 0xf0c060,
        particleSize: 4,
        spreadRadius: 15
    }
};

/**
 * 根据设备性能自动选择粒子数量
 */
export function getAdaptiveParticleCount() {
    const perf = THREE_CONFIG.PERFORMANCE;
    const isMobile = window.matchMedia('(max-width: 768px)').matches;
    const cores = navigator.hardwareConcurrency || 4;
    const memory = navigator.deviceMemory || 4;

    if (isMobile || cores <= 2 || memory <= 2) {
        return perf.PARTICLE_COUNT_LOW_END;
    }
    if (cores <= 4 || memory <= 4) {
        return perf.PARTICLE_COUNT_MOBILE;
    }
    return perf.PARTICLE_COUNT_DESKTOP;
}

/**
 * 检测 WebGL 支持情况
 */
export function isWebGLSupported() {
    try {
        const canvas = document.createElement('canvas');
        return !!(window.WebGLRenderingContext &&
            (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')));
    } catch (e) {
        return false;
    }
}

// ===== END OF FILE =====
