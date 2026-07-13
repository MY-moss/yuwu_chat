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
    },

    // --- 方案5: 世界书主题化 3D 背景 ---
    WORLD_THEMES: {
        enabled: true,
        transitionDuration: 2000,
        default: {
            name: 'default',
            colors: [0xc8a84e, 0xf0c060, 0xa08030, 0xe8c878],
            speed: 0.015,
            size: 2.5,
            opacity: { min: 0.15, max: 0.65 },
            movement: 'random',
            gravity: 0
        },
        themes: {
            'xiyou': { name: '西游', colors: [0xe6c84e, 0xf4d060, 0xc8a030, 0x8b7355], speed: 0.012, size: 3, opacity: { min: 0.2, max: 0.7 }, movement: 'up', gravity: 0.0002 },
            'wuxia': { name: '武侠', colors: [0x8b4513, 0xa0522d, 0xd2691e, 0xcd853f], speed: 0.01, size: 2.5, opacity: { min: 0.25, max: 0.8 }, movement: 'drift', gravity: 0 },
            'shenhua': { name: '神话', colors: [0x9370db, 0xda70d6, 0x87ceeb, 0xdda0dd], speed: 0.008, size: 4, opacity: { min: 0.1, max: 0.5 }, movement: 'float', gravity: -0.0001 },
            'dongman': { name: '动漫', colors: [0xff6b6b, 0x4ecdc4, 0xffe66d, 0x95e1d3], speed: 0.02, size: 2, opacity: { min: 0.3, max: 0.8 }, movement: 'random', gravity: 0 },
            'kongbu': { name: '恐怖', colors: [0x2d5a27, 0x1a3d16, 0x3d7a35, 0x0d1a0b], speed: 0.006, size: 3, opacity: { min: 0.1, max: 0.4 }, movement: 'down', gravity: 0.0003 },
            'zongjiao': { name: '宗教', colors: [0xffd700, 0xffec8b, 0xffeb3b, 0xe6b800], speed: 0.005, size: 5, opacity: { min: 0.15, max: 0.5 }, movement: 'float', gravity: -0.0002 },
            'sci-fi': { name: '科幻', colors: [0x4169e1, 0x00ced1, 0x87ceeb, 0x00bfff], speed: 0.015, size: 2, opacity: { min: 0.2, max: 0.6 }, movement: 'pulse', gravity: 0 },
            'feizhou': { name: '非洲', colors: [0xd2b48c, 0xcd853f, 0xdaa520, 0x8b7355], speed: 0.01, size: 3, opacity: { min: 0.2, max: 0.6 }, movement: 'drift', gravity: 0 },
            'dongwu': { name: '动物', colors: [0x228b22, 0x32cd32, 0x90ee90, 0x006400], speed: 0.012, size: 2.5, opacity: { min: 0.25, max: 0.7 }, movement: 'random', gravity: 0 },
            'steam': { name: '蒸汽朋克', colors: [0xcd853f, 0xdaa520, 0xb8860b, 0x8b6914], speed: 0.008, size: 3.5, opacity: { min: 0.3, max: 0.8 }, movement: 'rotate', gravity: 0 },
            'mohei': { name: '墨黑', colors: [0x303030, 0x404040, 0x505050, 0x606060], speed: 0.005, size: 4, opacity: { min: 0.1, max: 0.35 }, movement: 'slow', gravity: 0 },
            'meilong': { name: '美龙', colors: [0xff4500, 0xff6347, 0xff7f50, 0xffa500], speed: 0.01, size: 3, opacity: { min: 0.2, max: 0.6 }, movement: 'float', gravity: -0.0001 },
            'shenxiao': { name: '神霄', colors: [0x00ced1, 0x20b2aa, 0x48d1cc, 0x7fffd4], speed: 0.006, size: 4, opacity: { min: 0.1, max: 0.5 }, movement: 'float', gravity: -0.0003 },
            'xianxia': { name: '仙侠', colors: [0x87ceeb, 0xadd8e6, 0xb0e0e6, 0xafeeee], speed: 0.007, size: 3.5, opacity: { min: 0.15, max: 0.55 }, movement: 'float', gravity: -0.00015 },
            'mohuan': { name: '魔幻', colors: [0x9932cc, 0xba55d3, 0xee82ee, 0xda70d6], speed: 0.009, size: 3, opacity: { min: 0.2, max: 0.6 }, movement: 'pulse', gravity: 0 },
            'mori': { name: '末世废土', colors: [0x696969, 0x808080, 0xa9a9a9, 0x778899], speed: 0.008, size: 3.5, opacity: { min: 0.25, max: 0.65 }, movement: 'down', gravity: 0.0002 },
            'dalu': { name: '大陆', colors: [0x2e8b57, 0x3cb371, 0x228b22, 0x006400], speed: 0.01, size: 2.5, opacity: { min: 0.2, max: 0.6 }, movement: 'drift', gravity: 0 },
            'default': { name: '默认', colors: [0xc8a84e, 0xf0c060, 0xa08030, 0xe8c878], speed: 0.015, size: 2.5, opacity: { min: 0.15, max: 0.65 }, movement: 'random', gravity: 0 }
        }
    },

    // --- 方案1: 3D 骰子动画 ---
    DICE_ANIMATION: {
        enabled: true,
        duration: 2000,
        diceSize: 8,
        bounceCount: 4,
        gravity: 0.05,
        friction: 0.85,
        rotationSpeed: 0.3,
        colors: {
            face: 0xfafafa,
            border: 0x888888,
            number: 0x222222,
            shadow: 0x000000
        },
        soundEnabled: false,
        resultDelay: 300
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
