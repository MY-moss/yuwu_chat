// ============================================================
// 文件: three-bg.js | 职责: Three.js 3D效果（粒子背景+登录装饰环）
// ============================================================
import { THREE_CONFIG, getAdaptiveParticleCount, isWebGLSupported } from './three-config.js';

let _scene = null;
let _camera = null;
let _renderer = null;
let _particles = null;
let _rings = [];
let _animationId = null;
let _lastFrameTime = 0;
let _isActive = false;

/**
 * 动态导入 Three.js（通过 CDN URL，CSP 兼容）
 */
async function loadThree() {
    const module = await import(/* @vite-ignore */ THREE_CONFIG.CDN.THREE_URL);
    return module.default || module;
}

/**
 * 初始化粒子背景系统
 */
function initParticles(THREE) {
    const cfg = THREE_CONFIG.PARTICLE_BG;
    const count = getAdaptiveParticleCount();

    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);
    const velocities = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    const opacities = new Float32Array(count);
    const opacityDeltas = new Float32Array(count);

    const palette = cfg.colors.map(c => new THREE.Color(c));

    for (let i = 0; i < count; i++) {
        const i3 = i * 3;
        positions[i3] = (Math.random() - 0.5) * cfg.spread.x * 2;
        positions[i3 + 1] = (Math.random() - 0.5) * cfg.spread.y * 2;
        positions[i3 + 2] = (Math.random() - 0.5) * cfg.spread.z * 2;

        velocities[i3] = (Math.random() - 0.5) * cfg.speed;
        velocities[i3 + 1] = (Math.random() - 0.5) * cfg.speed;
        velocities[i3 + 2] = (Math.random() - 0.5) * cfg.speed;

        const color = palette[Math.floor(Math.random() * palette.length)];
        colors[i3] = color.r;
        colors[i3 + 1] = color.g;
        colors[i3 + 2] = color.b;

        opacities[i] = cfg.opacity.min + Math.random() * (cfg.opacity.max - cfg.opacity.min);
        opacityDeltas[i] = (Math.random() - 0.5) * cfg.opacitySpeed;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const material = new THREE.PointsMaterial({
        size: cfg.particleSize,
        sizeAttenuation: cfg.particleSizeAttenuation,
        vertexColors: true,
        transparent: true,
        opacity: 0.8,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        fog: true
    });

    _particles = new THREE.Points(geometry, material);
    _particles.userData = { velocities, opacities, opacityDeltas };
    _scene.add(_particles);

    _scene.fog = new THREE.FogExp2(0x1a1410, 0.008);
}

/**
 * 初始化登录界面装饰环
 */
function initAuthRings(THREE) {
    const cfg = THREE_CONFIG.AUTH_RINGS;
    if (!cfg.enabled) return;

    _rings = cfg.rings.map(ringCfg => {
        const geometry = new THREE.TorusGeometry(ringCfg.radius, ringCfg.tube, 16, 100);
        const material = new THREE.MeshBasicMaterial({
            color: ringCfg.color,
            transparent: true,
            opacity: ringCfg.opacity,
            blending: THREE.AdditiveBlending,
            depthWrite: false
        });
        const ring = new THREE.Mesh(geometry, material);
        ring.userData = { rotSpeed: ringCfg.rotSpeed };
        _scene.add(ring);
        return ring;
    });
}

/**
 * 动画循环
 */
function animate(timestamp) {
    if (!_isActive) return;

    const interval = THREE_CONFIG.PERFORMANCE.FRAME_INTERVAL;
    if (timestamp - _lastFrameTime < interval) {
        _animationId = requestAnimationFrame(animate);
        return;
    }
    _lastFrameTime = timestamp;

    if (_particles) {
        const positions = _particles.geometry.attributes.position.array;
        const { velocities, opacities, opacityDeltas } = _particles.userData;
        const cfg = THREE_CONFIG.PARTICLE_BG;
        const count = positions.length / 3;

        for (let i = 0; i < count; i++) {
            const i3 = i * 3;
            positions[i3] += velocities[i3];
            positions[i3 + 1] += velocities[i3 + 1];
            positions[i3 + 2] += velocities[i3 + 2];

            if (Math.abs(positions[i3]) > cfg.spread.x) velocities[i3] *= -1;
            if (Math.abs(positions[i3 + 1]) > cfg.spread.y) velocities[i3 + 1] *= -1;
            if (Math.abs(positions[i3 + 2]) > cfg.spread.z) velocities[i3 + 2] *= -1;

            opacities[i] += opacityDeltas[i];
            if (opacities[i] < cfg.opacity.min || opacities[i] > cfg.opacity.max) {
                opacityDeltas[i] *= -1;
                opacities[i] = Math.max(cfg.opacity.min, Math.min(cfg.opacity.max, opacities[i]));
            }
        }

        _particles.geometry.attributes.position.needsUpdate = true;
        _particles.rotation.y += cfg.rotationSpeed;
    }

    _rings.forEach(ring => {
        const { rotSpeed } = ring.userData;
        ring.rotation.x += rotSpeed.x;
        ring.rotation.y += rotSpeed.y;
        ring.rotation.z += rotSpeed.z;
    });

    _renderer.render(_scene, _camera);
    _animationId = requestAnimationFrame(animate);
}

/**
 * 处理窗口大小变化
 */
function onResize() {
    if (!_camera || !_renderer) return;
    _camera.aspect = window.innerWidth / window.innerHeight;
    _camera.updateProjectionMatrix();
    _renderer.setSize(window.innerWidth, window.innerHeight);
    _renderer.setPixelRatio(Math.min(window.devicePixelRatio, THREE_CONFIG.PERFORMANCE.DPR_MAX));
}

/**
 * 初始化 Three.js 背景
 * @returns {Promise<boolean>} 是否成功初始化
 */
export async function initThreeBg() {
    if (!isWebGLSupported()) {
        console.info('[three-bg] WebGL 不支持，降级为 CSS 背景效果');
        return false;
    }
    if (!THREE_CONFIG.PARTICLE_BG.enabled && !THREE_CONFIG.AUTH_RINGS.enabled) {
        return false;
    }

    try {
        const THREE = await loadThree();

        const canvas = document.getElementById(THREE_CONFIG.PARTICLE_BG.canvasId);
        if (!canvas) {
            console.warn('[three-bg] 未找到 canvas 元素 #threeCanvas');
            return false;
        }

        _scene = new THREE.Scene();
        _camera = new THREE.PerspectiveCamera(
            60, window.innerWidth / window.innerHeight, 0.1, 1000
        );
        _camera.position.z = THREE_CONFIG.PARTICLE_BG.cameraZ;

        _renderer = new THREE.WebGLRenderer({
            canvas,
            alpha: true,
            antialias: true,
            powerPreference: 'high-performance'
        });
        _renderer.setSize(window.innerWidth, window.innerHeight);
        _renderer.setPixelRatio(Math.min(window.devicePixelRatio, THREE_CONFIG.PERFORMANCE.DPR_MAX));
        _renderer.setClearColor(0x000000, 0);

        initParticles(THREE);
        initAuthRings(THREE);

        window.addEventListener('resize', onResize);
        _isActive = true;
        _animationId = requestAnimationFrame(animate);

        console.info('[three-bg] Three.js 背景初始化成功');
        return true;
    } catch (e) {
        console.error('[three-bg] 初始化失败，降级为 CSS 背景效果', e);
        return false;
    }
}

/**
 * 销毁 Three.js 背景，释放资源
 */
export function destroyThreeBg() {
    _isActive = false;
    if (_animationId) {
        cancelAnimationFrame(_animationId);
        _animationId = null;
    }
    window.removeEventListener('resize', onResize);

    if (_particles) {
        _particles.geometry.dispose();
        _particles.material.dispose();
        _particles = null;
    }

    _rings.forEach(ring => {
        ring.geometry.dispose();
        ring.material.dispose();
    });
    _rings = [];

    if (_renderer) {
        _renderer.dispose();
        _renderer = null;
    }
    _scene = null;
    _camera = null;
}

/**
 * 显示/隐藏装饰环（登录界面切换时调用）
 * @param {boolean} visible
 */
export function setRingsVisible(visible) {
    _rings.forEach(ring => {
        ring.visible = visible;
    });
}

// ===== END OF FILE =====
