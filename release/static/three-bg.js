// ============================================================
// 文件: three-bg.js | 职责: Three.js 3D效果（粒子背景+登录装饰环+模式过渡+消息粒子）
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
let _THREE = null;

// 模式过渡状态
let _modeTransition = null;

// 消息粒子爆发系统
let _burstSystems = [];

// 移动端检测
const _isMobile = window.matchMedia('(max-width: 768px)').matches;

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

    // 方案4: 模式切换过渡 — 相机穿越粒子层
    if (_modeTransition && _camera) {
        const elapsed = timestamp - _modeTransition.startTime;
        const t = Math.min(elapsed / _modeTransition.duration, 1);
        const { startZ, peakZ } = _modeTransition;

        if (t < 0.5) {
            const p = _easeInOutCubic(t * 2);
            _camera.position.z = startZ + (peakZ - startZ) * p;
        } else {
            const p = _easeInOutCubic((t - 0.5) * 2);
            _camera.position.z = peakZ + (startZ - peakZ) * p;
        }

        if (t >= 1) {
            const velocities = _particles?.userData?.velocities;
            if (velocities && _modeTransition.origSpeeds) {
                for (let i = 0; i < velocities.length; i++) {
                    velocities[i] = _modeTransition.origSpeeds[i];
                }
            }
            _camera.position.z = startZ;
            _modeTransition = null;
        }
    }

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

    // 方案6: 消息粒子特效更新
    _updateBurstSystems(timestamp);

    _renderer.render(_scene, _camera);
    _animationId = requestAnimationFrame(animate);
}

function _easeInOutCubic(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
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
        _THREE = THREE;

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

    _clearBurstSystems();

    if (_renderer) {
        _renderer.dispose();
        _renderer = null;
    }
    _scene = null;
    _camera = null;
    _THREE = null;
    _modeTransition = null;
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

// ============================================================
// 方案4: 模式切换 3D 过渡动画（相机穿越粒子层）
// ============================================================

/**
 * 触发模式切换 3D 过渡动画
 * 相机沿 Z 轴推进穿过粒子层，再回退到原位，配合粒子加速产生穿越感
 * @param {string} _toMode - 目标模式（'chat' | 'rpg'），预留用于差异化效果
 */
export function transitionMode(_toMode) {
    const cfg = THREE_CONFIG.MODE_TRANSITION;
    if (!cfg.enabled || !_camera || !_particles || !_THREE) return;
    if (_isMobile) return;

    if (_modeTransition) {
        const vels = _particles.userData.velocities;
        for (let i = 0; i < vels.length; i++) {
            vels[i] = _modeTransition.origSpeeds[i];
        }
    }

    const startZ = THREE_CONFIG.PARTICLE_BG.cameraZ;
    const peakZ = startZ + cfg.cameraPushZ;

    const velocities = _particles.userData.velocities;
    const origSpeeds = new Float32Array(velocities.length);
    for (let i = 0; i < velocities.length; i++) {
        origSpeeds[i] = velocities[i];
        velocities[i] *= cfg.particleSpeedBoost;
    }

    _modeTransition = {
        startTime: performance.now(),
        duration: cfg.duration,
        startZ,
        peakZ,
        origSpeeds
    };
}

// ============================================================
// 方案6: 发送/接收消息粒子特效
// ============================================================

/**
 * 将屏幕坐标转换为 3D 世界坐标
 */
function _screenToWorld(screenX, screenY) {
    if (!_camera || !_THREE) return null;
    const ndcX = (screenX / window.innerWidth) * 2 - 1;
    const ndcY = -(screenY / window.innerHeight) * 2 + 1;
    const vec = new _THREE.Vector3(ndcX, ndcY, 0.5);
    vec.unproject(_camera);
    return vec;
}

/**
 * 触发消息粒子特效
 * @param {number} screenX - 屏幕X坐标（像素）
 * @param {number} screenY - 屏幕Y坐标（像素）
 * @param {'send'|'receive'} type - 发送或接收
 */
export function emitMessageParticles(screenX, screenY, type = 'send') {
    const cfg = THREE_CONFIG.MESSAGE_PARTICLES;
    if (!cfg.enabled || !_scene || !_camera || !_THREE || !_renderer) return;

    const worldPos = _screenToWorld(screenX, screenY);
    if (!worldPos) return;

    const THREE = _THREE;
    const count = type === 'send' ? cfg.sendCount : cfg.receiveCount;
    const color = type === 'send' ? cfg.sendColor : cfg.receiveColor;

    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);
    const velocities = new Float32Array(count * 3);

    for (let i = 0; i < count; i++) {
        const i3 = i * 3;
        if (type === 'send') {
            positions[i3] = worldPos.x;
            positions[i3 + 1] = worldPos.y;
            positions[i3 + 2] = worldPos.z;
            const angle = Math.random() * Math.PI * 2;
            const elevation = (Math.random() - 0.5) * Math.PI;
            const speed = 0.1 + Math.random() * 0.2;
            velocities[i3] = Math.cos(angle) * Math.cos(elevation) * speed;
            velocities[i3 + 1] = Math.sin(elevation) * speed + 0.05;
            velocities[i3 + 2] = Math.sin(angle) * Math.cos(elevation) * speed;
        } else {
            const angle = Math.random() * Math.PI * 2;
            const radius = cfg.spreadRadius * (0.5 + Math.random() * 0.5);
            positions[i3] = worldPos.x + Math.cos(angle) * radius;
            positions[i3 + 1] = worldPos.y + Math.sin(angle) * radius;
            positions[i3 + 2] = worldPos.z + (Math.random() - 0.5) * radius;
            const frames = cfg.duration / 16;
            velocities[i3] = (worldPos.x - positions[i3]) / frames;
            velocities[i3 + 1] = (worldPos.y - positions[i3 + 1]) / frames;
            velocities[i3 + 2] = (worldPos.z - positions[i3 + 2]) / frames;
        }
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const material = new THREE.PointsMaterial({
        size: cfg.particleSize,
        sizeAttenuation: true,
        color: color,
        transparent: true,
        opacity: 1,
        blending: THREE.AdditiveBlending,
        depthWrite: false
    });

    const points = new THREE.Points(geometry, material);
    _scene.add(points);

    _burstSystems.push({
        points,
        geometry,
        material,
        velocities,
        startTime: performance.now(),
        duration: cfg.duration,
        type
    });
}

/**
 * 在主动画循环中更新所有爆发粒子系统
 */
function _updateBurstSystems(now) {
    if (_burstSystems.length === 0) return;

    for (let i = _burstSystems.length - 1; i >= 0; i--) {
        const burst = _burstSystems[i];
        const elapsed = now - burst.startTime;
        const t = elapsed / burst.duration;

        if (t >= 1) {
            _scene.remove(burst.points);
            burst.geometry.dispose();
            burst.material.dispose();
            _burstSystems.splice(i, 1);
            continue;
        }

        const positions = burst.geometry.attributes.position.array;
        const vels = burst.velocities;
        const count = positions.length / 3;

        for (let j = 0; j < count; j++) {
            const j3 = j * 3;
            positions[j3] += vels[j3];
            positions[j3 + 1] += vels[j3 + 1];
            positions[j3 + 2] += vels[j3 + 2];

            if (burst.type === 'send') {
                vels[j3] *= 0.97;
                vels[j3 + 1] *= 0.97;
                vels[j3 + 2] *= 0.97;
            } else if (t > 0.8) {
                vels[j3] *= 0.85;
                vels[j3 + 1] *= 0.85;
                vels[j3 + 2] *= 0.85;
            }
        }
        burst.geometry.attributes.position.needsUpdate = true;

        if (burst.type === 'send') {
            burst.material.opacity = 1 - t * t;
        } else {
            burst.material.opacity = t < 0.3 ? t / 0.3 : 1 - (t - 0.3) / 0.7;
        }
    }
}

/**
 * 清理所有爆发粒子系统
 */
function _clearBurstSystems() {
    _burstSystems.forEach(burst => {
        if (_scene) _scene.remove(burst.points);
        burst.geometry.dispose();
        burst.material.dispose();
    });
    _burstSystems = [];
}

// ===== END OF FILE =====
