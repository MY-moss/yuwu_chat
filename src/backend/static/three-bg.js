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

    // 方案5: 主题过渡更新
    _updateThemeTransition();

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
    _themeTransition = null;
    _currentTheme = null;
    _clearDice();
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

// ============================================================
// 方案5: 世界书主题化 3D 背景
// ============================================================

let _currentTheme = null;
let _themeTransition = null;

function _applyMovementMode(positions, velocities, i3, spread, speed, mode, gravity) {
    switch (mode) {
        case 'up':
            velocities[i3 + 1] += gravity;
            if (positions[i3 + 1] > spread.y) {
                positions[i3 + 1] = -spread.y;
            }
            break;
        case 'down':
            velocities[i3 + 1] -= gravity;
            if (positions[i3 + 1] < -spread.y) {
                positions[i3 + 1] = spread.y;
            }
            break;
        case 'float':
            velocities[i3 + 1] = Math.sin(positions[i3] * 0.01) * speed * 0.3;
            break;
        case 'drift':
            velocities[i3] *= 0.995;
            velocities[i3 + 1] *= 0.995;
            if (Math.random() < 0.001) {
                velocities[i3] += (Math.random() - 0.5) * speed;
                velocities[i3 + 1] += (Math.random() - 0.5) * speed;
            }
            break;
        case 'pulse':
            const pulse = Math.sin(positions[i3 + 2] * 0.02) * speed * 0.5;
            velocities[i3 + 1] = pulse;
            break;
        case 'slow':
            velocities[i3] *= 0.999;
            velocities[i3 + 1] *= 0.999;
            velocities[i3 + 2] *= 0.999;
            break;
        case 'rotate':
            const angle = positions[i3] * 0.001;
            velocities[i3] = -Math.sin(angle) * speed * 0.5;
            velocities[i3 + 2] = Math.cos(angle) * speed * 0.5;
            break;
        default:
            break;
    }
}

/**
 * 切换世界书主题
 * @param {string} themeId - 主题ID，对应 WORLD_THEMES.themes 中的键
 */
export function setWorldTheme(themeId) {
    const cfg = THREE_CONFIG.WORLD_THEMES;
    if (!cfg.enabled || !_particles || !_THREE) return;

    const theme = cfg.themes[themeId] || cfg.default;
    if (_currentTheme && _currentTheme.name === theme.name) return;

    const startColors = _currentTheme ? _currentTheme.colors : cfg.default.colors;
    const startSpeed = _currentTheme ? _currentTheme.speed : cfg.default.speed;
    const startSize = _currentTheme ? _currentTheme.size : cfg.default.size;

    _themeTransition = {
        startTime: performance.now(),
        duration: cfg.transitionDuration,
        startColors: startColors.map(c => new _THREE.Color(c)),
        endColors: theme.colors.map(c => new _THREE.Color(c)),
        startSpeed,
        endSpeed: theme.speed,
        startSize,
        endSize: theme.size,
        theme
    };

    _currentTheme = theme;
}

/**
 * 重置为默认主题
 */
export function resetTheme() {
    setWorldTheme('default');
}

// 在主动画循环中添加主题过渡逻辑
function _updateThemeTransition() {
    if (!_themeTransition || !_particles) return;

    const now = performance.now();
    const elapsed = now - _themeTransition.startTime;
    const t = Math.min(elapsed / _themeTransition.duration, 1);
    const eased = _easeInOutCubic(t);

    const colors = _particles.geometry.attributes.color.array;
    const count = colors.length / 3;

    for (let i = 0; i < count; i++) {
        const i3 = i * 3;
        const startColor = _themeTransition.startColors[Math.floor(Math.random() * _themeTransition.startColors.length)];
        const endColor = _themeTransition.endColors[Math.floor(Math.random() * _themeTransition.endColors.length)];

        colors[i3] = startColor.r + (endColor.r - startColor.r) * eased;
        colors[i3 + 1] = startColor.g + (endColor.g - startColor.g) * eased;
        colors[i3 + 2] = startColor.b + (endColor.b - startColor.b) * eased;
    }
    _particles.geometry.attributes.color.needsUpdate = true;

    const targetSpeed = _themeTransition.startSpeed + (_themeTransition.endSpeed - _themeTransition.startSpeed) * eased;
    const velocities = _particles.userData.velocities;
    for (let i = 0; i < velocities.length; i++) {
        velocities[i] = velocities[i] / (_themeTransition.startSpeed || 0.01) * targetSpeed;
    }

    _particles.material.size = _themeTransition.startSize + (_themeTransition.endSize - _themeTransition.startSize) * eased;

    if (t >= 1) {
        _themeTransition = null;
    }
}

// ============================================================
// 方案1: 3D 骰子动画
// ============================================================

let _diceObject = null;
let _diceResultCallback = null;
let _diceAnimation = null;

function _createDiceGeometry(THREE) {
    const cfg = THREE_CONFIG.DICE_ANIMATION;
    const geometry = new THREE.BoxGeometry(cfg.diceSize, cfg.diceSize, cfg.diceSize);

    const faces = [
        { indices: [0, 1, 2, 3], dots: [3] },
        { indices: [4, 5, 6, 7], dots: [1] },
        { indices: [0, 1, 5, 4], dots: [2, 6] },
        { indices: [2, 3, 7, 6], dots: [4, 5] },
        { indices: [0, 3, 7, 4], dots: [1, 3, 5] },
        { indices: [1, 2, 6, 5], dots: [2, 4, 6] }
    ];

    const uvArray = [];
    const dotPositions = {
        1: [[0.5, 0.5]],
        2: [[0.25, 0.25], [0.75, 0.75]],
        3: [[0.25, 0.25], [0.5, 0.5], [0.75, 0.75]],
        4: [[0.25, 0.25], [0.75, 0.25], [0.25, 0.75], [0.75, 0.75]],
        5: [[0.25, 0.25], [0.75, 0.25], [0.5, 0.5], [0.25, 0.75], [0.75, 0.75]],
        6: [[0.25, 0.2], [0.75, 0.2], [0.25, 0.5], [0.75, 0.5], [0.25, 0.8], [0.75, 0.8]]
    };

    for (const face of faces) {
        const dots = dotPositions[face.dots.length] || [];
        for (let i = 0; i < 4; i++) {
            const corner = i;
            const u = corner % 2;
            const v = Math.floor(corner / 2);
            uvArray.push(u, v);
        }
    }

    geometry.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(uvArray), 2));
    return geometry;
}

function _createDiceMaterial(THREE) {
    const cfg = THREE_CONFIG.DICE_ANIMATION;
    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 256;
    const ctx = canvas.getContext('2d');

    ctx.fillStyle = '#' + cfg.colors.face.toString(16).padStart(6, '0');
    ctx.fillRect(0, 0, 256, 256);

    ctx.strokeStyle = '#' + cfg.colors.border.toString(16).padStart(6, '0');
    ctx.lineWidth = 4;
    ctx.strokeRect(2, 2, 252, 252);

    ctx.fillStyle = '#' + cfg.colors.number.toString(16).padStart(6, '0');
    const dotSize = 20;
    const dotPositions = [
        [],
        [[0.5, 0.5]],
        [[0.25, 0.25], [0.75, 0.75]],
        [[0.25, 0.25], [0.5, 0.5], [0.75, 0.75]],
        [[0.25, 0.25], [0.75, 0.25], [0.25, 0.75], [0.75, 0.75]],
        [[0.25, 0.25], [0.75, 0.25], [0.5, 0.5], [0.25, 0.75], [0.75, 0.75]],
        [[0.25, 0.2], [0.75, 0.2], [0.25, 0.5], [0.75, 0.5], [0.25, 0.8], [0.75, 0.8]]
    ];

    for (let i = 1; i <= 6; i++) {
        const row = Math.floor((i - 1) / 2);
        const col = (i - 1) % 2;
        ctx.save();
        ctx.translate(col * 128 + 64, row * 128 + 64);
        for (const [dx, dy] of dotPositions[i]) {
            ctx.beginPath();
            ctx.arc((dx - 0.5) * 100, (dy - 0.5) * 100, dotSize / 2, 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.restore();
    }

    const texture = new THREE.CanvasTexture(canvas);
    return new THREE.MeshStandardMaterial({
        map: texture,
        roughness: 0.3,
        metalness: 0.1
    });
}

/**
 * 滚动 3D 骰子
 * @param {number} sides - 骰子面数（默认20面）
 * @param {function} callback - 动画结束回调，参数为骰子结果
 */
export function rollDice(sides = 20, callback = null) {
    const cfg = THREE_CONFIG.DICE_ANIMATION;
    if (!cfg.enabled || !_scene || !_THREE || !_camera) return;
    if (_isMobile) {
        const result = Math.floor(Math.random() * sides) + 1;
        if (callback) setTimeout(() => callback(result), 500);
        return;
    }

    if (_diceObject) {
        _scene.remove(_diceObject);
        _diceObject.geometry.dispose();
        _diceObject.material.dispose();
        _diceObject = null;
    }

    _diceResultCallback = callback;
    const THREE = _THREE;

    const geometry = _createDiceGeometry(THREE);
    const material = _createDiceMaterial(THREE);
    _diceObject = new THREE.Mesh(geometry, material);

    _diceObject.position.set(0, 15, 0);
    _diceObject.castShadow = true;
    _scene.add(_diceObject);

    const result = Math.floor(Math.random() * sides) + 1;
    const rotations = {
        x: (Math.random() * 4 + result * 0.5) * Math.PI,
        y: (Math.random() * 4 + result * 0.7) * Math.PI,
        z: (Math.random() * 4 + result * 0.3) * Math.PI
    };

    const startPos = { y: 15 };
    const startRot = { x: 0, y: 0, z: 0 };
    const startTime = performance.now();

    _diceAnimation = { startTime, rotations, startPos, startRot, result };

    function animateDice(timestamp) {
        if (!_diceAnimation || !_diceObject) return;

        const elapsed = timestamp - _diceAnimation.startTime;
        const t = Math.min(elapsed / cfg.duration, 1);

        const bounce = Math.sin(t * Math.PI * cfg.bounceCount) * (1 - t) * 10;
        const eased = _easeInOutCubic(t);

        _diceObject.position.y = startPos.y * (1 - eased) + bounce + 2;
        _diceObject.rotation.x = startRot.x + _diceAnimation.rotations.x * eased;
        _diceObject.rotation.y = startRot.y + _diceAnimation.rotations.y * eased;
        _diceObject.rotation.z = startRot.z + _diceAnimation.rotations.z * eased;

        if (t >= 1) {
            setTimeout(() => {
                if (_diceResultCallback) {
                    _diceResultCallback(_diceAnimation.result);
                }
                _diceResultCallback = null;
                _diceAnimation = null;
            }, cfg.resultDelay);
        } else {
            requestAnimationFrame(animateDice);
        }
    }

    requestAnimationFrame(animateDice);
}

/**
 * 清理骰子对象
 */
function _clearDice() {
    if (_diceObject) {
        _scene.remove(_diceObject);
        _diceObject.geometry.dispose();
        _diceObject.material.dispose();
        _diceObject = null;
    }
    _diceAnimation = null;
    _diceResultCallback = null;
}

// ===== END OF FILE =====
