import os
import sys
import json
import uuid
import threading
from datetime import datetime, timedelta
from urllib.parse import urlparse
import requests
from flask import Flask, render_template, request, jsonify, session, Response, stream_with_context
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
import secrets

def get_base_path():
    if hasattr(sys, '_MEIPASS'):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_PATH = get_base_path()

def is_safe_url(url):
    try:
        p = urlparse(url)
        if p.scheme not in ('http', 'https'):
            return False, '仅支持 http/https 协议'
        hostname = p.hostname
        if not hostname:
            return False, '无效的主机名'
        if hostname in ('localhost', '127.0.0.1', '0.0.0.0', '::1'):
            return False, '不允许访问本地地址'
        if hostname.startswith('169.254.'):
            return False, '不允许访问链路本地地址'
        if hostname.startswith('10.') or hostname.startswith('192.168.') or hostname.startswith('172.'):
            if hostname.startswith('172.'):
                parts = hostname.split('.')
                if len(parts) >= 2 and 16 <= int(parts[1]) <= 31:
                    return False, '不允许访问私有网络地址'
            else:
                return False, '不允许访问私有网络地址'
        return True, ''
    except Exception as e:
        return False, 'URL 解析失败'

load_dotenv(os.path.join(BASE_PATH, '.env'))

app = Flask(__name__, 
            static_folder=os.path.join(BASE_PATH, 'static'),
            template_folder=os.path.join(BASE_PATH, 'templates'))
_secret_key = os.getenv("SECRET_KEY", "")
if not _secret_key or _secret_key == "GENERATE_RANDOM_KEY_IN_PRODUCTION" or _secret_key == "tavern-secret-key-change-in-production":
    app.secret_key = secrets.token_hex(32)
else:
    app.secret_key = _secret_key
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_PATH, "instance", "tavern.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['TEMPLATES_AUTO_RELOAD'] = app.debug
app.config['JSON_AS_ASCII'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

def escape_html(s):
    if s is None:
        return ''
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#39;')

@app.before_request
def csrf_protect():
    if request.method in ['POST', 'PUT', 'DELETE']:
        csrf_token = request.headers.get('X-CSRF-Token', '')
        session_token = session.get('_csrf_token', '')
        if csrf_token != session_token:
            return jsonify({"error": "CSRF token invalid"}), 403
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(16)

@app.route('/api/csrf-token')
def get_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(16)
    return jsonify({"csrf_token": session['_csrf_token']})

@app.after_request
def add_no_cache_header(response):
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = None  # API only, no redirect — use unauthorized_handler instead

AGENTS_FILE = os.path.join(BASE_PATH, "agents.json")
WORLDS_FILE = os.path.join(BASE_PATH, "worldbooks.json")
RATINGS_FILE = os.path.join(BASE_PATH, "world_ratings.json")
SUBMISSIONS_FILE = os.path.join(BASE_PATH, "world_submissions.json")
USAGE_LOG_FILE = os.path.join(BASE_PATH, "usage_log.json")
SESSIONS_FILE = os.path.join(BASE_PATH, "rpg_sessions.json")

def load_version():
    paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "version.json"),
        os.path.join(os.getcwd(), "version.json"),
        os.path.join(BASE_PATH, "version.json")
    ]
    for version_file in paths:
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                v = json.load(f)
                return f"v{v['major']}.{v['minor']}.{v['patch']}"
        except Exception as e:
            print(f"[ERROR]: {e}", flush=True)
            continue
    return "v1.0.0"

def load_changelog():
    paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "CHANGELOG.json"),
        os.path.join(os.getcwd(), "CHANGELOG.json"),
        os.path.join(BASE_PATH, "CHANGELOG.json")
    ]
    for changelog_file in paths:
        try:
            with open(changelog_file, "r", encoding="utf-8") as f:
                return json.load(f).get("history", [])
        except Exception as e:
            print(f"[ERROR]: {e}", flush=True)
            continue
    return []

VERSION = load_version()
CHANGELOG = load_changelog()

# 强制所有跑团输出格式 — 无论世界书提示词是否包含
MANDATORY_RPG_FORMAT = """
【强制格式】
1. 先输出故事段落，再输出数据段
2. 数据段如下（每次必须包含【状态】和【事件】，其他可选）：
【状态】HP 精力 金钱等
【属性】力量 敏捷 智力 魅力 体质
【背包】物品清单
【技能】技能与等级
【情绪】当前情绪
【关系】NPC/势力:好感度
【事件】当前关键事件
3. 数据段完毕后，在末尾提供3-5个选项：
【1】选项文字
【2】选项文字
【3】选项文字
【4】选项文字
4. 有挑战时额外输出【判定】难度:X 属性:X 说明:X
5. 数值随故事合理变化
"""

histories = {}
rpg_sessions = {}

_histories_lock = threading.Lock()
_sessions_lock = threading.Lock()
_agents_lock = threading.Lock()
_worlds_lock = threading.Lock()
_ratings_lock = threading.Lock()
_submissions_lock = threading.Lock()
_login_attempts = {}
_login_lock = threading.Lock()
_LOGIN_RATE_LIMIT = 5
_LOGIN_RATE_WINDOW = 60


def save_sessions():
    with _sessions_lock:
        keep = {}
        for sid, s in list(rpg_sessions.items()):
            k = {k: v for k, v in s.items()}
            hist = k.get("history", [])
            if hist:
                k["history"] = [hist[0]] + hist[-10:]  # keep system prompt + last 10
            else:
                k["history"] = hist
            keep[sid] = k
        keys = list(keep.keys())[-100:]
        keep = {k: keep[k] for k in keys}
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(keep, f, ensure_ascii=False, indent=2, default=str)


def load_sessions():
    global rpg_sessions
    if not os.path.exists(SESSIONS_FILE):
        return
    with _sessions_lock:
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            try:
                loaded = json.load(f)
                sessions_data = loaded.get('sessions', loaded)
                if isinstance(sessions_data, dict):
                    for sid, s in sessions_data.items():
                        rpg_sessions[sid] = s
                elif isinstance(sessions_data, list):
                    for s in sessions_data:
                        rpg_sessions[s.get('session_id', str(id(s)))] = s
            except Exception as e:
                print(f"[ERROR]: {e}", flush=True)

def load_ratings():
    if not os.path.exists(RATINGS_FILE):
        return {}
    with _ratings_lock:
        with open(RATINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

def save_ratings(ratings):
    with _ratings_lock:
        with open(RATINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(ratings, f, ensure_ascii=False, indent=2)

def load_worlds():
    try:
        if not os.path.exists(WORLDS_FILE):
            return []
        with _worlds_lock:
            with open(WORLDS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            worlds = data.get("worlds", [])
            for i, w in enumerate(worlds):
                if "order" not in w:
                    w["order"] = i
            return worlds
    except Exception as e:
        print(f"[ERROR] load_worlds failed: {e}", flush=True)
        return []

def save_worlds_data(worlds):
    with _worlds_lock:
        with open(WORLDS_FILE, "w", encoding="utf-8") as f:
            json.dump({"worlds": worlds}, f, ensure_ascii=False, indent=2)


def load_submissions():
    if not os.path.exists(SUBMISSIONS_FILE):
        return []
    with _submissions_lock:
        with open(SUBMISSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_submissions(subs):
    with _submissions_lock:
        with open(SUBMISSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(subs, f, ensure_ascii=False, indent=2)


_usage_log_lock = threading.Lock()

def log_usage(user_id, username, model, tokens, cost, endpoint):
    entry = {
        "time": datetime.now().isoformat(),
        "user_id": user_id,
        "username": username,
        "model": model,
        "tokens": tokens,
        "cost": cost,
        "endpoint": endpoint
    }
    with _usage_log_lock:
        logs = []
        if os.path.exists(USAGE_LOG_FILE):
            with open(USAGE_LOG_FILE, "r", encoding="utf-8") as f:
                try: logs = json.load(f)
                except Exception as e: logs = []
        logs.append(entry)
        # Keep last 10000 entries
        if len(logs) > 10000:
            logs = logs[-10000:]
        with open(USAGE_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)


# ===== 反馈系统（已迁移至 Feedback 模型，文件读写已废弃）=====


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='user')
    credits = db.Column(db.Integer, default=100)
    total_tokens = db.Column(db.Integer, default=0)
    personal_api_base = db.Column(db.String(500), nullable=True)
    personal_api_key = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_active = db.Column(db.DateTime, default=datetime.now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'credits': self.credits,
            'total_tokens': self.total_tokens,
            'has_personal_api': bool(self.personal_api_base and self.personal_api_key),
            'created_at': self.created_at.isoformat(),
            'last_active': self.last_active.isoformat() if self.last_active else None
        }


class ModelConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    model_id = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    label = db.Column(db.String(100), nullable=False)
    credits_per_1k = db.Column(db.Integer, default=1)
    enabled = db.Column(db.Boolean, default=True)
    api_base = db.Column(db.String(500), nullable=True)
    api_key = db.Column(db.String(500), nullable=True)
    priority = db.Column(db.Integer, default=100)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'model_id': self.model_id,
            'name': self.name,
            'label': self.label,
            'credits_per_1k': self.credits_per_1k,
            'enabled': self.enabled,
            'priority': self.priority,
            'created_at': self.created_at.isoformat()
        }

    def to_dict_admin(self):
        data = self.to_dict()
        data['api_base'] = self.api_base
        data['has_api_key'] = bool(self.api_key)
        return data


class ApiConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key_name = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(500), nullable=False)
    priority = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {'key_name': self.key_name, 'value': self.value, 'priority': self.priority}


class CreditKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(32), unique=True, nullable=False)
    credits = db.Column(db.Integer, nullable=False)
    used = db.Column(db.Boolean, default=False)
    used_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'key': self.key,
            'credits': self.credits,
            'used': self.used,
            'used_by': self.used_by,
            'created_at': self.created_at.isoformat()
        }


class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    username = db.Column(db.String(80), nullable=False)
    category = db.Column(db.String(32), nullable=False, default='suggestion')
    rating = db.Column(db.Integer, nullable=False, default=3)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='open')
    admin_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.username,
            'category': self.category,
            'rating': self.rating,
            'title': self.title,
            'content': self.content,
            'status': self.status,
            'admin_note': self.admin_note or '',
            'created_at': self.created_at.isoformat()
        }


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def admin_required(f):
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            return jsonify({"error": "管理员权限不足"}), 403
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function


@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({"error": "未登录"}), 401


def init_db():
    with app.app_context():
        db.create_all()
        admin_exists = db.session.execute(db.text('SELECT COUNT(*) FROM user WHERE username = "admin"')).scalar()
        if not admin_exists:
            admin_pwd = os.getenv("ADMIN_PASSWORD")
            if not admin_pwd:
                print("[ERROR] ADMIN_PASSWORD environment variable not set. Cannot create admin user.", flush=True)
                return
            admin = User(username='admin', role='admin', credits=99999)
            admin.set_password(admin_pwd)
            db.session.add(admin)
            db.session.commit()
        # Seed models that don't exist yet
        default_models = [
            {'model_id': 'deepseek-ai/DeepSeek-V3', 'name': 'DeepSeek V3', 'label': '🧠 DeepSeek-V3', 'credits_per_1k': 0},
            {'model_id': 'deepseek-ai/DeepSeek-V4-Flash', 'name': 'DeepSeek V4 Flash', 'label': '⚡ DeepSeek-V4-Flash', 'credits_per_1k': 0},
            {'model_id': 'deepseek-ai/DeepSeek-V4-Pro', 'name': 'DeepSeek V4 Pro', 'label': '🔮 DeepSeek-V4-Pro', 'credits_per_1k': 0},
        ]
        for m in default_models:
            exists = db.session.execute(db.text('SELECT COUNT(*) FROM model_config WHERE model_id = :mid'), {'mid': m['model_id']}).scalar()
            if not exists:
                model = ModelConfig(**m)
                db.session.add(model)
        db.session.commit()
        api_key_exists = db.session.execute(db.text('SELECT COUNT(*) FROM api_config WHERE key_name = "API_KEY"')).scalar()
        if not api_key_exists:
            db.session.add(ApiConfig(key_name='API_KEY', value=os.getenv('AI_API_KEY', ''), priority=10))
            db.session.add(ApiConfig(key_name='API_URL', value=os.getenv('AI_API_URL', ''), priority=5))
            db.session.commit()


def load_agents():
    try:
        with _agents_lock:
            with open(AGENTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("agents", [])
    except Exception as e:
        print(f"[ERROR] load_agents failed: {e}", flush=True)
        return []


def save_agents(agents):
    with _agents_lock:
        with open(AGENTS_FILE, "w", encoding="utf-8") as f:
            json.dump({"agents": agents}, f, ensure_ascii=False, indent=2)


def get_agent(agent_id):
    for a in load_agents():
        if a["id"] == agent_id:
            return a
    return None


def mock_reply(message, agent):
    replies = agent.get("mock_replies", {})
    default = agent.get("mock_default", "嗯，我在听，你继续说。")
    for kw, resp in replies.items():
        if kw in message:
            return resp
    return default


def get_model_price(model_id):
    model = ModelConfig.query.filter_by(model_id=model_id, enabled=True).first()
    if model:
        return model.credits_per_1k
    return 1


def deduct_credits(user, amount):
    if user.credits >= amount:
        user.credits -= amount
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"deduct_credits commit failed: {e}")
            return False
        return True
    return False


def using_personal_api():
    return bool(current_user.personal_api_base and current_user.personal_api_key)


def parse_usage(resp_json):
    try:
        usage = resp_json.get("usage", {})
        return usage.get("total_tokens", 0), usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    except Exception as e:
        print(f"[ERROR]: {e}", flush=True)
        return 0, 0, 0


def estimate_tokens(text):
    if not text:
        return 0
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return chinese_chars + (other_chars // 4) * 3 + (other_chars % 4 > 0) * 1


def calc_token_cost(tokens, credits_per_1k):
    if credits_per_1k <= 0:
        return 0
    return max(1, (tokens * credits_per_1k + 999) // 1000)  # ceil division, min 1 credit


def get_api_config(key_name, default=""):
    cfg = ApiConfig.query.filter_by(key_name=key_name).first()
    if cfg:
        return cfg.value
    return default


def get_effective_api(model_id=None, user=None):
    """返回 (api_key, api_url) — 优先用户的个人 API → 模型自定义 API → 全局配置 → .env"""
    if user is None:
        try:
            from flask_login import current_user
            if current_user and current_user.is_authenticated:
                user = current_user
        except Exception as e:
            print(f"[ERROR]: {e}", flush=True)
    if user and user.personal_api_base and user.personal_api_key:
        return user.personal_api_key, user.personal_api_base
    if model_id:
        model = ModelConfig.query.filter_by(model_id=model_id).first()
        if model and model.api_base and model.api_key:
            return model.api_key, model.api_base
    key = get_api_config("API_KEY", os.getenv("AI_API_KEY", ""))
    url = get_api_config("API_URL", os.getenv("AI_API_URL", ""))
    return key, url


@app.route("/")
def index():
    agents = load_agents()
    default = agents[0] if agents else {"id": "none", "name": "无", "avatar": "🧔"}
    return render_template("index.html", agents=agents, default_agent=default)


@app.route("/dashboard")
@login_required
@admin_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    if len(password) < 6:
        return jsonify({"error": "密码长度至少6位"}), 400
    if len(password) > 128:
        return jsonify({"error": "密码长度不能超过128位"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "用户名已存在"}), 400

    user = User(username=username, credits=100)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    login_user(user)
    return jsonify({"message": "注册成功", "user": user.to_dict()}), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    client_ip = request.remote_addr

    with _login_lock:
        now = time.time()
        attempts = _login_attempts.get(client_ip, [])
        attempts = [t for t in attempts if now - t < _LOGIN_RATE_WINDOW]
        if len(attempts) >= _LOGIN_RATE_LIMIT:
            return jsonify({"error": f"登录尝试过于频繁，请 {_LOGIN_RATE_WINDOW} 秒后再试"}), 429
        attempts.append(now)
        _login_attempts[client_ip] = attempts

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "用户名或密码错误"}), 401

    login_user(user)

    with _login_lock:
        _login_attempts.pop(client_ip, None)

    return jsonify({"message": "登录成功", "user": user.to_dict()})


@app.route("/api/auth/reset-admin-password", methods=["POST"])
@login_required
@admin_required
def reset_admin_password():
    admin = User.query.filter_by(username='admin').first()
    if admin:
        new_pwd = secrets.token_urlsafe(12)
        admin.set_password(new_pwd)
        db.session.commit()
        print(f"[SECURITY] Admin password reset: {new_pwd}", flush=True)
        return jsonify({"message": "管理员密码已重置，请查看服务器日志获取新密码"})
    return jsonify({"error": "管理员用户不存在"}), 404


@app.route("/api/auth/logout")
@login_required
def logout():
    logout_user()
    return jsonify({"message": "退出成功"})


@app.route("/api/auth/change-password", methods=["POST"])
@login_required
def change_password():
    data = request.json
    old_password = data.get("old_password")
    new_password = data.get("new_password")
    
    if not old_password or not new_password:
        return jsonify({"error": "请输入原密码和新密码"}), 400
    
    if len(new_password) < 6:
        return jsonify({"error": "新密码长度至少6位"}), 400
    if len(new_password) > 128:
        return jsonify({"error": "新密码长度不能超过128位"}), 400
    
    if not current_user.check_password(old_password):
        return jsonify({"error": "原密码不正确"}), 401
    
    current_user.set_password(new_password)
    db.session.commit()
    
    return jsonify({"message": "密码修改成功"})


@app.route("/api/auth/me")
def get_current_user():
    if current_user.is_authenticated:
        current_user.last_active = datetime.now()
        db.session.commit()
        return jsonify(current_user.to_dict())
    return jsonify({"error": "未登录"}), 401


@app.route("/api/auth/ping", methods=["POST"])
@login_required
def ping_active():
    current_user.last_active = datetime.now()
    db.session.commit()
    return jsonify({"status": "ok"})


@app.route("/version")
def get_version():
    return jsonify({"version": VERSION})


@app.route("/version/changelog")
def get_changelog():
    return jsonify({"changelog": CHANGELOG})


@app.route("/api/auth/api-config", methods=["GET", "PUT"])
@login_required
def user_api_config():
    if request.method == "GET":
        return jsonify({
            "api_base": current_user.personal_api_base or "",
            "has_personal_api": bool(current_user.personal_api_base and current_user.personal_api_key)
        })
    data = request.json
    if "api_base" in data:
        v = data.get("api_base", "")
        if v:
            safe, msg = is_safe_url(v)
            if not safe:
                return jsonify({"error": "API地址不安全: " + msg}), 400
            current_user.personal_api_base = v.strip()
        else:
            current_user.personal_api_base = None
    if "api_key" in data:
        v = data.get("api_key", "")
        current_user.personal_api_key = v.strip() if v else None
    db.session.commit()
    return jsonify({"status": "ok", "has_personal_api": bool(current_user.personal_api_base and current_user.personal_api_key)})


@app.route("/api/models", methods=["GET"])
@login_required
def list_models():
    models = ModelConfig.query.filter_by(enabled=True).order_by(ModelConfig.priority).all()
    return jsonify([m.to_dict() for m in models])


@app.route("/api/admin/models", methods=["GET"])
@login_required
@admin_required
def admin_list_models():
    models = ModelConfig.query.order_by(ModelConfig.priority).all()
    return jsonify([m.to_dict_admin() for m in models])


@app.route("/api/admin/models", methods=["POST"])
@login_required
@admin_required
def admin_add_model():
    data = request.json
    model_id = data.get("model_id", "").strip()
    name = data.get("name", "").strip()
    label = data.get("label", "").strip()
    credits_per_1k = data.get("credits_per_1k", 1)

    if not model_id or not name or not label:
        return jsonify({"error": "model_id、name和label不能为空"}), 400
    if ModelConfig.query.filter_by(model_id=model_id).first():
        return jsonify({"error": "该模型已存在"}), 400

    model = ModelConfig(
        model_id=model_id,
        name=name,
        label=label,
        credits_per_1k=int(credits_per_1k),
        priority=data.get("priority", 100),
        api_base=data.get("api_base", "").strip() or None,
        api_key=data.get("api_key", "").strip() or None
    )
    db.session.add(model)
    db.session.commit()
    return jsonify(model.to_dict()), 201


@app.route("/api/admin/models/<int:model_id>", methods=["PUT"])
@login_required
@admin_required
def admin_update_model(model_id):
    model = ModelConfig.query.get(model_id)
    if not model:
        return jsonify({"error": "模型不存在"}), 404

    data = request.json
    if "name" in data:
        model.name = data["name"]
    if "label" in data:
        model.label = data["label"]
    if "credits_per_1k" in data:
        model.credits_per_1k = int(data["credits_per_1k"])
    if "enabled" in data:
        model.enabled = bool(data["enabled"])
    if "api_base" in data:
        v = data["api_base"]
        model.api_base = v.strip() if v else None
    if "api_key" in data:
        v = data["api_key"]
        model.api_key = v.strip() if v else None
    if "priority" in data:
        model.priority = int(data["priority"])

    db.session.commit()
    return jsonify(model.to_dict())


@app.route("/api/admin/models/<int:model_id>", methods=["DELETE"])
@login_required
@admin_required
def admin_delete_model(model_id):
    model = ModelConfig.query.get(model_id)
    if not model:
        return jsonify({"error": "模型不存在"}), 404

    db.session.delete(model)
    db.session.commit()
    return jsonify({"status": "ok"})


@app.route("/api/admin/users", methods=["GET"])
@login_required
@admin_required
def admin_list_users():
    users = User.query.all()
    return jsonify([u.to_dict() for u in users])


@app.route("/api/admin/users/<int:user_id>", methods=["PUT"])
@login_required
@admin_required
def admin_update_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "用户不存在"}), 404

    data = request.json
    if "credits" in data:
        user.credits = int(data["credits"])
    if "role" in data:
        user.role = data["role"]

    db.session.commit()
    return jsonify(user.to_dict())


@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@login_required
@admin_required
def admin_delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "用户不存在"}), 404
    if user.id == current_user.id:
        return jsonify({"error": "不能删除自己"}), 400

    db.session.delete(user)
    db.session.commit()
    return jsonify({"status": "ok"})


@app.route("/api/agents", methods=["GET"])
@login_required
def list_agents():
    return jsonify(load_agents())


@app.route("/api/agents", methods=["POST"])
@login_required
@admin_required
def add_agent():
    data = request.json
    agents = load_agents()
    if any(a["id"] == data.get("id") for a in agents):
        return jsonify({"error": "智能体ID已存在"}), 400
    agents.append(data)
    save_agents(agents)
    return jsonify(data), 201


@app.route("/api/agents/<agent_id>", methods=["PUT"])
@login_required
@admin_required
def update_agent(agent_id):
    data = request.json
    agents = load_agents()
    for i, a in enumerate(agents):
        if a["id"] == agent_id:
            agents[i] = {**a, **data}
            agents[i]["id"] = agent_id
            save_agents(agents)
            return jsonify(agents[i])
    return jsonify({"error": "未找到智能体"}), 404


@app.route("/api/agents/<agent_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_agent(agent_id):
    agents = load_agents()
    new_agents = [a for a in agents if a["id"] != agent_id]
    if len(new_agents) == len(agents):
        return jsonify({"error": "未找到智能体"}), 404
    save_agents(new_agents)
    histories.pop(f"{current_user.id}_{agent_id}", None)
    return jsonify({"status": "ok"})


@app.route("/api/chat", methods=["POST"])
@login_required
def chat():
    data = request.json
    user_message = data.get("message", "").strip()
    agent_id = data.get("agent_id", "")
    model_id = data.get("model", "")

    if not user_message:
        return jsonify({"error": "消息不能为空"}), 400
    if not agent_id:
        return jsonify({"error": "请指定智能体"}), 400

    agent = get_agent(agent_id)
    if not agent:
        return jsonify({"error": "未找到智能体"}), 404

    model = model_id or agent.get("model", "mimo-v2.5-free")
    credits_per_1k = get_model_price(model)

    history_key = f"{current_user.id}_{agent_id}"

    try:
        api_key, api_url = get_effective_api(model)
        if api_key:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            body = {
                "model": model,
                "messages": [{"role": "system", "content": agent["system_prompt"]}],
                "temperature": agent.get("temperature", 0.8),
                "max_tokens": 1024
            }
            
            with _histories_lock:
                if history_key not in histories:
                    histories[history_key] = []
                body["messages"].extend([{"role": "user", "content": user_message}])
                body["messages"].extend(histories[history_key][-19:])
            
            resp = requests.post(api_url, headers=headers, json=body, timeout=30)
            if resp.status_code != 200:
                print(f"[ERROR] chat API failed: {resp.status_code}", flush=True)
                raise Exception(f"API调用失败")
            result = resp.json()
            reply = result["choices"][0]["message"]["content"]
            total_tokens, _, _ = parse_usage(result)
        else:
            with _histories_lock:
                if history_key not in histories:
                    histories[history_key] = []
                messages = [{"role": "system", "content": agent["system_prompt"]}]
                messages.extend([{"role": "user", "content": user_message}])
                messages.extend(histories[history_key][-19:])
            reply = mock_reply(user_message, agent)
            total_tokens = 0

        personal = using_personal_api()
        cost = calc_token_cost(total_tokens, credits_per_1k) if not personal else 0
        if not personal and not deduct_credits(current_user, cost):
            return jsonify({"error": f"积分不足（需要 {cost} 积分）"}), 402

        if not personal:
            current_user.total_tokens = (current_user.total_tokens or 0) + total_tokens
            db.session.commit()

        log_usage(current_user.id, current_user.username, model, total_tokens, cost, "chat")
        
        with _histories_lock:
            histories[history_key].append({"role": "user", "content": user_message})
            histories[history_key].append({"role": "assistant", "content": reply})
            history_length = len(histories[history_key])
        
        return jsonify({
            "reply": reply,
            "history_length": history_length,
            "credits_left": current_user.credits,
            "tokens_used": total_tokens,
            "cost": cost,
            "free": personal
        })

    except Exception as e:
        print(f"[ERROR] chat failed: {e}", flush=True)
        return jsonify({"reply": f"（{agent['name']}擦了擦额头的汗）抱歉，刚才出了点问题……请稍后重试"}), 500


@app.route("/api/history/<agent_id>", methods=["DELETE"])
@login_required
def clear_history(agent_id):
    history_key = f"{current_user.id}_{agent_id}"
    histories.pop(history_key, None)
    return jsonify({"status": "ok"})


def call_ai(messages, model="mimo-v2.5-free", temperature=0.85, max_tokens=400):
    try:
        api_key, api_url = get_effective_api(model)
        if not api_key:
            return None, {}, 0
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        resp = requests.post(api_url, headers=headers, json=body, timeout=60)
        if resp.status_code != 200:
            print(f"[ERROR] call_ai API failed: {resp.status_code}", flush=True)
            raise Exception(f"API调用失败")
        data = resp.json()
        full = data["choices"][0]["message"]["content"]
        total_tokens, _, _ = parse_usage(data)
        story, sections = parse_rpg_reply(full)
        return story, sections, total_tokens
    except Exception as e:
        print(f"[ERROR] call_ai failed: {e}", flush=True)
        return None, {}, 0


def parse_rpg_reply(text):
    import re
    text = text.strip()
    marker_re = r'【([^】]+)】'
    matches = list(re.finditer(marker_re, text))
    if not matches:
        return text, {}

    story = text[:matches[0].start()].strip()
    sections = {}
    for i, m in enumerate(matches):
        key = m.group(1).strip()
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        val = text[start:end].strip().rstrip(',')

        if re.match(r'^\d+$', key):
            story += f"\n【{key}】{val}"
        else:
            sections[key] = val
    return story.strip(), sections


@app.route("/api/rpg/worlds", methods=["GET"])
@login_required
def list_worlds():
    worlds = load_worlds()
    worlds.sort(key=lambda w: w.get("order", 0))
    ratings = load_ratings()
    # Attach ratings info to each world
    for w in worlds:
        w_ratings = ratings.get(w["id"], [])
        w["rating_count"] = len(w_ratings)
        if w_ratings:
            w["avg_rating"] = round(sum(r["rating"] for r in w_ratings) / len(w_ratings), 1)
        else:
            w["avg_rating"] = 0
    return jsonify(worlds)


@app.route("/api/rpg/worlds", methods=["POST"])
@login_required
@admin_required
def save_world():
    worlds = request.json
    save_worlds_data(worlds)
    return jsonify({"status": "ok"})


@app.route("/api/rpg/worlds/reorder", methods=["POST"])
@login_required
@admin_required
def reorder_worlds():
    """管理员调整世界书排列顺序"""
    data = request.json
    world_ids = data.get("order", [])  # list of world ids in desired order
    worlds = load_worlds()
    for i, wid in enumerate(world_ids):
        for w in worlds:
            if w["id"] == wid:
                w["order"] = i
                break
    save_worlds_data(worlds)
    return jsonify({"status": "ok"})


@app.route("/api/rpg/active-count", methods=["GET"])
@login_required
def active_count():
    """返回所有用户活跃跑团总数及按世界书统计"""
    with _sessions_lock:
        by_world = {}
        for sid, s in rpg_sessions.items():
            wid = s.get("world_id", "unknown")
            if wid not in by_world:
                by_world[wid] = 0
            by_world[wid] += 1
        return jsonify({
            "total": len(rpg_sessions),
            "by_world": by_world
        })


@app.route("/api/rpg/worlds/<world_id>/ratings", methods=["GET"])
@login_required
def get_world_ratings(world_id):
    """获取世界书的评分和评价"""
    ratings = load_ratings()
    world_ratings = ratings.get(world_id, [])
    return jsonify(world_ratings)


@app.route("/api/rpg/worlds/<world_id>/ratings", methods=["POST"])
@login_required
def rate_world(world_id):
    """玩家对世界书打分和评价"""
    data = request.json
    rating = int(data.get("rating", 0))
    review = data.get("review", "").strip()
    if rating < 1 or rating > 5:
        return jsonify({"error": "评分需在1-5之间"}), 400
    
    ratings = load_ratings()
    if world_id not in ratings:
        ratings[world_id] = []
    
    # Check if user already rated (update or add)
    user_rating = None
    for r in ratings[world_id]:
        if r["user_id"] == current_user.id:
            user_rating = r
            break
    
    if user_rating:
        user_rating["rating"] = rating
        user_rating["review"] = review
        user_rating["updated_at"] = datetime.now().isoformat()
    else:
        ratings[world_id].append({
            "user_id": current_user.id,
            "username": current_user.username,
            "rating": rating,
            "review": review,
            "created_at": datetime.now().isoformat()
        })
    
    save_ratings(ratings)
    
    # Return updated stats
    world_ratings = ratings.get(world_id, [])
    avg = round(sum(r["rating"] for r in world_ratings) / len(world_ratings), 1) if world_ratings else 0
    return jsonify({
        "status": "ok",
        "avg_rating": avg,
        "rating_count": len(world_ratings),
        "my_rating": rating,
        "my_review": review
    })
    
    
# ===== World Submission (User → Admin Review) =====
@app.route("/api/rpg/worlds/submit", methods=["POST"])
@login_required
def submit_world():
    data = request.json
    wid = data.get("id", "").strip()
    name = data.get("name", "").strip()
    if not wid or not name:
        return jsonify({"error": "ID和名称不能为空"}), 400
    subs = load_submissions()
    if any(s["id"] == wid for s in subs):
        return jsonify({"error": "该ID已被使用"}), 400
    worlds = load_worlds()
    if any(w["id"] == wid for w in worlds):
        return jsonify({"error": "该ID已存在于正式世界书"}), 400
    sub = {
        "id": wid, "name": name,
        "emoji": data.get("emoji", "📖"), "genre": data.get("genre", ""),
        "desc": data.get("desc", ""),
        "system_prompt": data.get("system_prompt", ""),
        "submitted_by": current_user.id,
        "submitter": current_user.username,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    try:
        sub["temperature"] = float(data.get("temperature", 0.85))
        sub["max_tokens"] = int(data.get("max_tokens", 700))
    except (ValueError, TypeError):
        return jsonify({"error": "temperature/max_tokens 必须为数字"}), 400
    subs.append(sub)
    save_submissions(subs)
    return jsonify({"status": "ok", "message": "投稿成功，等待管理员审核"}), 201


@app.route("/api/rpg/worlds/submissions", methods=["GET"])
@login_required
@admin_required
def list_submissions():
    subs = load_submissions()
    return jsonify(subs)


@app.route("/api/rpg/worlds/submissions/<sub_id>", methods=["POST"])
@login_required
@admin_required
def review_submission(sub_id):
    data = request.json
    action = data.get("action", "")
    subs = load_submissions()
    sub = next((s for s in subs if s["id"] == sub_id), None)
    if not sub:
        return jsonify({"error": "投稿不存在"}), 404
    if action == "approve":
        worlds = load_worlds()
        order = max((w.get("order", 0) for w in worlds), default=-1) + 1
        worlds.append({
            "id": sub["id"], "name": sub["name"],
            "emoji": sub.get("emoji", "📖"), "genre": sub.get("genre", ""),
            "desc": sub.get("desc", ""), "system_prompt": sub.get("system_prompt", ""),
            "temperature": sub.get("temperature", 0.85),
            "max_tokens": sub.get("max_tokens", 700), "order": order
        })
        save_worlds_data(worlds)
        subs = [s for s in subs if s["id"] != sub_id]
        save_submissions(subs)
        return jsonify({"status": "ok", "message": "已通过并上架"})
    elif action == "reject":
        subs = [s for s in subs if s["id"] != sub_id]
        save_submissions(subs)
        return jsonify({"status": "ok", "message": "已拒绝并删除"})
    return jsonify({"error": "未知操作"}), 400


@app.route("/api/rpg/worlds/my-submissions", methods=["GET"])
@login_required
def my_submissions():
    subs = load_submissions()
    mine = [s for s in subs if s.get("submitted_by") == current_user.id]
    return jsonify(mine)


# ===== Admin Stats =====
@app.route("/api/admin/stats", methods=["GET"])
@login_required
@admin_required
def admin_stats():
    if not os.path.exists(USAGE_LOG_FILE):
        return jsonify({"total_calls": 0, "total_tokens": 0, "total_cost": 0, "users": {}, "models": {}})
    with _usage_log_lock:
        with open(USAGE_LOG_FILE, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
                if isinstance(logs, dict):
                    logs = list(logs.values())
                elif not isinstance(logs, list):
                    logs = []
            except Exception as e: logs = []
    total_calls = len(logs)
    total_tokens = 0
    total_cost = 0
    users = {}
    models = {}
    for l in logs:
        if not isinstance(l, dict):
            continue
        total_tokens += l.get("tokens", 0)
        total_cost += l.get("cost", 0)
        u = l.get("username", "?")
        users[u] = users.get(u, {"calls":0, "tokens":0, "cost":0})
        users[u]["calls"] += 1
        users[u]["tokens"] += l.get("tokens", 0)
        users[u]["cost"] += l.get("cost", 0)
        m = l.get("model", "?")
        models[m] = models.get(m, {"calls":0, "tokens":0})
        models[m]["calls"] += 1
        models[m]["tokens"] += l.get("tokens", 0)
    with _sessions_lock:
        active_sessions = len(rpg_sessions)
        sessions_detail = []
        worlds = load_worlds()
        wmap = {w["id"]: w["name"] for w in worlds}
        for sid, s in list(rpg_sessions.items())[:50]:
            sessions_detail.append({
                "session_id": sid,
                "player": s.get("player_name", "?"),
                "world": wmap.get(s.get("world_id", ""), "?"),
                "rounds": len(s.get("storyline", [])),
                "last_active": s.get("last_active", "")
            })
    online_users_detail = User.query.filter(
        User.last_active >= datetime.now() - timedelta(minutes=20)
    ).order_by(User.last_active.desc()).all()
    online_users = len(online_users_detail)
    online_users_list = [
        {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "last_active": u.last_active.isoformat() if u.last_active else None
        }
        for u in online_users_detail
    ]
    return jsonify({
        "total_calls": total_calls, "total_tokens": total_tokens, "total_cost": total_cost,
        "users": users, "models": models,
        "active_sessions": active_sessions, "sessions_detail": sessions_detail,
        "online_users": online_users, "online_users_list": online_users_list
    })


# ===== Share & Spectate =====
@app.route("/api/rpg/session/<session_id>/share", methods=["POST"])
@login_required
def share_session(session_id):
    with _sessions_lock:
        sess = rpg_sessions.get(session_id)
        if not sess:
            return jsonify({"error": "会话不存在"}), 404
        if sess.get("user_id") != current_user.id:
            return jsonify({"error": "无权操作"}), 403
        if not sess.get("share_token"):
            sess["share_token"] = secrets.token_hex(8)
            save_sessions()
        return jsonify({
            "share_token": sess["share_token"],
            "share_url": f"/shared/session/{sess['share_token']}"
        })


@app.route("/api/rpg/session/<session_id>/unshare", methods=["POST"])
@login_required
def unshare_session(session_id):
    with _sessions_lock:
        sess = rpg_sessions.get(session_id)
        if not sess:
            return jsonify({"error": "会话不存在"}), 404
        if sess.get("user_id") != current_user.id:
            return jsonify({"error": "无权操作"}), 403
        sess.pop("share_token", None)
        save_sessions()
        return jsonify({"status": "ok"})


@app.route("/api/rpg/shared/<share_token>")
def view_shared_session(share_token):
    with _sessions_lock:
        for sid, sess in rpg_sessions.items():
            if sess.get("share_token") == share_token:
                worlds = load_worlds()
                w = next((w for w in worlds if w["id"] == sess.get("world_id", "")), {})
                sections = sess.get("sections", {})
                return jsonify({
                    "player_name": sess.get("player_name", "?"),
                    "world": {"name": w.get("name", "?"), "emoji": w.get("emoji", "📖")},
                    "last_story": sess.get("last_story", ""),
                    "last_state": sess.get("last_state", sections.get("状态", "")),
                    "relationship": sections.get("关系_map", {}),
                    "sections": sections,
                    "storyline": sess.get("storyline", [])
                })
    return jsonify({"error": "分享链接无效或已过期"}), 404


@app.route("/api/rpg/shared-sessions")
@login_required
def list_shared_sessions():
    with _sessions_lock:
        worlds = load_worlds()
        wmap = {w["id"]: w for w in worlds}
        items = []
        for sid, sess in rpg_sessions.items():
            token = sess.get("share_token")
            if not token:
                continue
            w = wmap.get(sess.get("world_id", ""), {})
            items.append({
                "share_token": token,
                "player": sess.get("player_name", "?"),
                "world_name": w.get("name", "?"),
                "world_emoji": w.get("emoji", "📖"),
                "rounds": len(sess.get("storyline", [])),
                "last_active": sess.get("last_active", "")
            })
        items.sort(key=lambda x: x.get("last_active", "") or "", reverse=True)
        return jsonify(items)


@app.route("/shared/session/<share_token>")
def spectate_page(share_token):
    return render_template("spectate.html", token=share_token)


@app.route("/api/rpg/admin/spectate/<session_id>")
@login_required
@admin_required
def admin_spectate_session(session_id):
    """Admin real-time spectate — no share_token needed"""
    sess = rpg_sessions.get(session_id)
    if not sess:
        return jsonify({"error": "会话不存在"}), 404
    worlds = load_worlds()
    w = next((w for w in worlds if w["id"] == sess.get("world_id", "")), {})
    sections = sess.get("sections", {})
    return jsonify({
        "player_name": sess.get("player_name", "?"),
        "world": {"name": w.get("name", "?"), "emoji": w.get("emoji", "📖")},
        "last_story": sess.get("last_story", ""),
        "last_state": sess.get("last_state", sections.get("状态", "")),
        "relationship": sections.get("关系_map", {}),
        "sections": sections,
        "storyline": sess.get("storyline", []),
        "user_id": sess.get("user_id"),
        "share_token": sess.get("share_token"),
        "rounds": len(sess.get("storyline", []))
    })


@app.route("/api/rpg/start", methods=["POST"])
@login_required
def start_rpg():
    data = request.json
    world_id = data.get("world_id", "")
    player_name = data.get("player_name", "旅人")
    model = data.get("model", "mimo-v2.5-free")

    credits_per_1k = get_model_price(model)

    worlds = load_worlds()
    world = next((w for w in worlds if w["id"] == world_id), None)
    if not world:
        return jsonify({"error": "未找到世界"}), 404

    session_id = str(uuid.uuid4())[:8]
    messages = [
        {"role": "system", "content": world["system_prompt"] + MANDATORY_RPG_FORMAT},
        {"role": "user", "content": f"玩家名称为「{player_name}」。游戏开始，请描述开场场景并输出所有强制段。"}
    ]

    try:
        story, sections, tokens = call_ai(messages,
                        model=model,
                        temperature=world.get("temperature", 0.85),
                        max_tokens=world.get("max_tokens", 600))
    except Exception as e:
        print(f"[ERROR] start_rpg AI call failed: {e}", flush=True)
        story = None
        sections = None
        tokens = 0

    if not story:
        story = f"{world['emoji']} {world['desc']}\n\n【1】推开大门\n【2】侧耳倾听\n【3】转身离开"
        sections = {"状态": "（AI服务暂时不可用）"}
        tokens = 0

    state_str = sections.get("状态", "")
    rels_str = sections.get("关系", "")

    personal = using_personal_api()
    cost = calc_token_cost(tokens, credits_per_1k) if not personal else 0
    if not personal and not deduct_credits(current_user, cost):
        return jsonify({"error": f"积分不足（需要 {cost} 积分）"}), 402
    if not personal:
        current_user.total_tokens = (current_user.total_tokens or 0) + tokens
        db.session.commit()

    log_usage(current_user.id, current_user.username, model, tokens, cost, "rpg_start")

    now = datetime.now().isoformat()
    rpg_sessions[session_id] = {
        "world_id": world_id, "player_name": player_name,
        "user_id": current_user.id, "history": messages,
        "last_story": story, "sections": sections,
        "last_state": state_str, "model": model,
        "storyline": [{"round": 0, "choice": "游戏开始", "story": story[:150], "sections": dict(sections)}],
        "state_log": [{"round": 0, "sections": dict(sections)}],
        "share_token": None, "created_at": now, "last_active": now, "priority": 3
    }
    save_sessions()

    rmap = {}
    if rels_str:
        for part in rels_str.replace("【", "").replace("】", "").split():
            if ":" in part:
                k, v = part.split(":", 1)
                rmap[k.strip()] = v.strip()
    rpg_sessions[session_id]["sections"]["关系_map"] = rmap

    return jsonify({
        "session_id": session_id, "world": world,
        "story": story, "state": state_str,
        "relationships": rmap, "sections": sections,
        "player_name": player_name,
        "storyline": rpg_sessions[session_id]["storyline"],
        "credits_left": current_user.credits,
        "tokens_used": tokens, "cost": cost, "free": personal
    })


@app.route("/api/rpg/act", methods=["POST"])
@login_required
def rpg_act():
    data = request.json
    session_id = data.get("session_id", "")
    choice = data.get("choice", "")

    session = rpg_sessions.get(session_id)
    if not session:
        return jsonify({"error": "会话已过期或不存在"}), 404
    if session["user_id"] != current_user.id:
        return jsonify({"error": "无权访问此会话"}), 403

    model = data.get("model") or session.get("model", "mimo-v2.5-free")
    credits_per_1k = get_model_price(model)

    worlds = load_worlds()
    world = next((w for w in worlds if w["id"] == session["world_id"]), None)
    if not world:
        return jsonify({"error": "世界数据已丢失"}), 404

    session["history"].append({"role": "assistant", "content": session["last_story"]})

    # Force state persistence: inject previous sections into user message
    ctx = f"我选择：{choice}"
    prev_sections = session.get("sections", {})
    if prev_sections:
        ctx += "\n\n当前角色数据：" + "; ".join(f"【{k}】{prev_sections[k]}" for k in prev_sections if not isinstance(prev_sections[k],dict))
    ctx += "\n\n请继续故事，并在末尾输出更新后的所有数据段：【状态】【属性】【关系】【背包】【技能】等"
    session["history"].append({"role": "user", "content": ctx})

    if len(session["history"]) > 30:
        session["history"] = [session["history"][0]] + session["history"][-28:]

    session["model"] = model

    try:
        story, sections, tokens = call_ai(session["history"],
                        model=model,
                        temperature=world.get("temperature", 0.85),
                        max_tokens=world.get("max_tokens", 600))
    except Exception as e:
        print(f"[ERROR] rpg_act AI call failed: {e}", flush=True)
        story = None
        sections = None
        tokens = 0

    if not story:
        story = f"（你选择了：{choice}）\n\n故事继续……\n\n【1】继续前进\n【2】仔细观察四周\n【3】回头"
        sections = session.get("sections", {"状态": "【AI服务暂时不可用】"})
        tokens = 0

    # Merge: keep previous sections that AI didn't update
    prev = session.get("sections", {})
    for k, v in prev.items():
        if k not in sections and k != '关系_map':
            sections[k] = v
    state_str = sections.get("状态", "")

    personal = using_personal_api()
    cost = calc_token_cost(tokens, credits_per_1k) if not personal else 0
    if not personal and not deduct_credits(current_user, cost):
        return jsonify({"error": f"积分不足（需要 {cost} 积分）"}), 402

    if not personal:
        current_user.total_tokens = (current_user.total_tokens or 0) + tokens
        db.session.commit()

    log_usage(current_user.id, current_user.username, model, tokens, cost, "rpg_act")

    session["last_story"] = story
    session["sections"] = sections
    session["last_state"] = state_str
    session["last_active"] = datetime.now().isoformat()
    session.setdefault("state_log", []).append({"round": len(session.get("storyline", [])), "sections": dict(sections)})
    session["storyline"].append({
        "round": len(session["storyline"]), "choice": choice,
        "story": story[:150], "sections": dict(sections)
    })

    # Parse relationships
    rels_str = sections.get("关系", "")
    rmap = {}
    if rels_str:
        for part in rels_str.replace("【", "").replace("】", "").split():
            if ":" in part:
                k, v = part.split(":", 1)
                rmap[k.strip()] = v.strip()
    sections["关系_map"] = rmap

    save_sessions()

    return jsonify({
        "story": story, "state": state_str,
        "storyline": session["storyline"],
        "relationships": rmap, "sections": sections,
        "credits_left": current_user.credits,
        "tokens_used": tokens, "cost": cost, "free": personal
    })


@app.route("/api/rpg/act/stream", methods=["POST"])
@login_required
def rpg_act_stream():
    data = request.json
    session_id = data.get("session_id", "")
    choice = data.get("choice", "")
    sess = rpg_sessions.get(session_id)
    if not sess:
        return jsonify({"error": "会话不存在"}), 404
    if sess["user_id"] != current_user.id:
        return jsonify({"error": "无权访问"}), 403

    model = data.get("model") or sess.get("model", "mimo-v2.5-free")
    worlds = load_worlds()
    world = next((w for w in worlds if w["id"] == sess.get("world_id", "")), None)
    if not world:
        return jsonify({"error": "世界数据已丢失"}), 404

    sess["history"].append({"role": "assistant", "content": sess.get("last_story", "")})
    prev = sess.get("sections", {})
    ctx = f"我选择：{choice}"
    if prev:
        ctx += "\n\n当前数据：" + "; ".join(f"【{k}】{v}" for k, v in prev.items() if not isinstance(v, dict))
    ctx += "\n\n请继续故事并输出更新后的所有数据段"
    sess["history"].append({"role": "user", "content": ctx})
    if len(sess["history"]) > 30:
        sess["history"] = [sess["history"][0]] + sess["history"][-28:]
    sess["model"] = model

    api_key, api_url = get_effective_api(model)
    credits_per_1k = get_model_price(model)

    def generate():
        if not api_key:
            mock_text = "【状态】\n生命值:100/100\n法力值:50/50\n\n（AI 暂未配置，请管理员在面板中配置 API 密钥）"
            for ch in mock_text:
                yield f"data: {_json.dumps({'type':'chunk','text':ch})}\n\n"
            yield f"data: {_json.dumps({'type':'done'})}\n\n"
            return
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = {"model": model, "messages": sess["history"],
                "temperature": world.get("temperature", 0.85),
                "max_tokens": world.get("max_tokens", 400)}
        full_text = ""
        import json as _json
        try:
            # First try with streaming
            body["stream"] = True
            resp = requests.post(api_url, headers=headers, json=body, timeout=60, stream=True)
            # If streaming fails with 400/422/415/etc, retry without streaming
            if resp.status_code in (400, 415, 422, 500):
                body["stream"] = False
                resp = requests.post(api_url, headers=headers, json=body, timeout=60)
                if resp.status_code == 200:
                    data = resp.json()
                    full_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    for ch in full_text:
                        yield f"data: {_json.dumps({'type':'chunk','text':ch})}\n\n"
                    import time; time.sleep(0.02)
            elif resp.status_code != 200:
                try:
                    err_body = resp.text[:500]
                except Exception as e:
                    err_body = ""
                yield f"data: {_json.dumps({'type':'error','text':f'API {resp.status_code}: {err_body}'})}\n\n"
                return
            else:
                # Normal SSE streaming
                it = resp.iter_lines()
                first = next(it, None)
                if first and not first.startswith(b"data: "):
                    raw = first + b"".join(list(it))
                    try:
                        data = _json.loads(raw.decode("utf-8"))
                        full_text = data.get("choices", [{}])[0].get("message", {}).get("content", full_text)
                    except Exception as e:
                        full_text = raw.decode("utf-8", errors="replace")
                else:
                    for line in [first] + list(it) if first else list(it):
                        if not line: continue
                        decoded = line.decode("utf-8")
                        if decoded.startswith("data: "):
                            chunk = decoded[6:]
                            if chunk.strip() == "[DONE]": break
                            try:
                                d = _json.loads(chunk)
                                delta = d.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta:
                                    full_text += delta
                                    yield f"data: {_json.dumps({'type':'chunk','text':delta})}\n\n"
                            except Exception as e:
                                print(f"[ERROR]: {e}", flush=True)
        except Exception as e:
            print(f"[ERROR] rpg_act_stream: {e}", flush=True)
            yield f"data: {_json.dumps({'type':'error','text':str(e)})}\n\n"
            return

        story, sections = parse_rpg_reply(full_text)
        for k, v in prev.items():
            if k not in sections and k != "关系_map":
                sections[k] = v
        state_str = sections.get("状态", "")
        personal = using_personal_api()
        total_tokens = estimate_tokens(full_text)
        cost = max(0, total_tokens * credits_per_1k // 1000) if (not personal and credits_per_1k > 0) else 0
        if not personal and credits_per_1k > 0 and not deduct_credits(current_user, cost):
            yield f"data: {_json.dumps({'type':'error','text':f'积分不足（需要 {cost} 积分）'})}\n\n"
            return
        if not personal:
            current_user.total_tokens = (current_user.total_tokens or 0) + total_tokens
            db.session.commit()

        rmap = {}
        rels_str = sections.get("关系", "")
        if rels_str:
            for part in rels_str.replace("【", "").replace("】", "").split():
                if ":" in part:
                    k, v = part.split(":", 1)
                    rmap[k.strip()] = v.strip()
        sections["关系_map"] = rmap

        sess["last_story"] = story
        sess["sections"] = sections
        sess["last_state"] = state_str
        sess["last_active"] = datetime.now().isoformat()
        rnd = len(sess.get("storyline", []))
        sess.setdefault("state_log", []).append({"round": rnd, "sections": dict(sections)})
        sess["storyline"].append({"round": rnd, "choice": choice, "story": story[:150], "sections": dict(sections)})
        save_sessions()
        log_usage(current_user.id, current_user.username, model, total_tokens, cost, "rpg_act_stream")
        yield f"data: {_json.dumps({'type':'done','story':story,'state':state_str,'relationships':rmap,'sections':sections,'tokens_used':total_tokens,'cost':cost,'credits_left':current_user.credits,'free':personal})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/api/rpg/sessions", methods=["GET"])
@login_required
def list_sessions():
    worlds = load_worlds()
    world_map = {w["id"]: w for w in worlds}

    sessions = []
    for sid, s in rpg_sessions.items():
        if s.get("user_id") != current_user.id:
            continue
        w = world_map.get(s["world_id"], {})
        sessions.append({
            "session_id": sid,
            "world_id": s["world_id"],
            "world_name": w.get("name", "未知"),
            "world_emoji": w.get("emoji", "📖"),
            "player_name": s["player_name"],
            "rounds": len(s.get("storyline", [])),
            "priority": s.get("priority", 3),
            "created_at": s.get("created_at", ""),
            "last_active": s.get("last_active", "")
        })

    sessions.sort(key=lambda x: (-x["priority"], x.get("last_active", "") or ""))
    return jsonify(sessions)


@app.route("/api/admin/all-sessions", methods=["GET"])
@login_required
@admin_required
def admin_all_sessions():
    worlds = load_worlds()
    wmap = {w["id"]: w for w in worlds}
    items = []
    for sid, s in rpg_sessions.items():
        w = wmap.get(s.get("world_id", ""), {})
        sections = s.get("sections", {})
        items.append({
            "session_id": sid,
            "user_id": s.get("user_id"),
            "player_name": s.get("player_name", "?"),
            "world_name": w.get("name", "?"),
            "world_emoji": w.get("emoji", "📖"),
            "rounds": len(s.get("storyline", [])),
            "last_story": (s.get("last_story", "") or "")[:100],
            "state_preview": sections.get("状态", "")[:80],
            "shared": bool(s.get("share_token")),
            "share_token": s.get("share_token"),
            "last_active": s.get("last_active", ""),
            "created_at": s.get("created_at", "")
        })
    items.sort(key=lambda x: x.get("last_active", "") or "", reverse=True)
    return jsonify(items)


@app.route("/api/rpg/session/<session_id>", methods=["PUT"])
@login_required
def update_session(session_id):
    session = rpg_sessions.get(session_id)
    if not session:
        return jsonify({"error": "会话不存在"}), 404
    if session.get("user_id") != current_user.id:
        return jsonify({"error": "无权访问此会话"}), 403

    data = request.json
    if "priority" in data:
        try:
            p = int(data["priority"])
            session["priority"] = max(1, min(5, p))
            save_sessions()
        except (ValueError, TypeError):
            return jsonify({"error": "priority 必须为数字"}), 400
    return jsonify({"status": "ok", "priority": session["priority"]})


@app.route("/api/rpg/session/<session_id>", methods=["GET"])
@login_required
def get_session(session_id):
    session = rpg_sessions.get(session_id)
    if not session:
        return jsonify({"error": "会话不存在"}), 404
    if session.get("user_id") != current_user.id and current_user.role != 'admin':
        return jsonify({"error": "无权访问此会话"}), 403

    sections = session.get("sections", {})
    if not sections and session.get("last_state"):
        sections = {"状态": session["last_state"]}
    return jsonify({
        "player_name": session["player_name"],
        "world_id": session["world_id"],
        "last_story": session["last_story"],
        "last_state": session.get("last_state", ""),
        "sections": sections,
        "storyline": session.get("storyline", []),
        "relationships": sections.get("关系_map", session.get("relationships", {})),
        "state_log": session.get("state_log", []),
        "share_token": session.get("share_token"),
        "priority": session.get("priority", 3),
        "last_active": session.get("last_active", "")
    })


# ===== Branch: Go back to a previous round =====
@app.route("/api/rpg/session/<session_id>/branch", methods=["POST"])
@login_required
def branch_session(session_id):
    sess = rpg_sessions.get(session_id)
    if not sess:
        return jsonify({"error": "会话不存在"}), 404
    if sess.get("user_id") != current_user.id:
        return jsonify({"error": "无权操作"}), 403

    data = request.json
    target = int(data.get("round", 0))
    storyline = sess.get("storyline", [])
    if target < 0 or target >= len(storyline):
        return jsonify({"error": "无效的回溯轮次"}), 400

    # Truncate storyline, state_log, history to target round
    sess["storyline"] = storyline[:target + 1]
    state_log = sess.get("state_log", [])
    sess["state_log"] = state_log[:target + 1] if state_log else []
    last_entry = sess["storyline"][-1] if sess["storyline"] else {}
    sess["last_story"] = last_entry.get("story", "")
    last_sections = last_entry.get("sections", {})
    sess["last_state"] = last_sections.get("状态", "") if isinstance(last_sections, dict) else str(last_sections)
    sess["sections"] = last_sections

    # Truncate message history: keep system prompt + user/assistant pairs up to target
    history = sess.get("history", [])
    # history[0] = system prompt, then pairs of (assistant, user)
    # target=0 means keep system + 1st round (assistant+user), total 3 messages
    kept = [history[0]] if history else []
    pair_count = 0
    for msg in history[1:]:
        if pair_count >= (target + 1) * 2:
            break
        kept.append(msg)
        pair_count += 1
    sess["history"] = kept
    sess["last_active"] = datetime.now().isoformat()
    save_sessions()

    return jsonify({
        "status": "ok",
        "last_story": sess["last_story"],
        "last_state": sess["last_state"],
        "storyline": sess["storyline"],
        "relationships": sess.get("sections", {}).get("关系_map", {})
    })


# ===== Delete Session =====
@app.route("/api/rpg/session/<session_id>", methods=["DELETE"])
@login_required
def delete_session(session_id):
    sess = rpg_sessions.get(session_id)
    if not sess:
        return jsonify({"error": "会话不存在"}), 404
    if sess.get("user_id") != current_user.id:
        return jsonify({"error": "无权操作"}), 403
    rpg_sessions.pop(session_id, None)
    save_sessions()
    return jsonify({"status": "ok"})


# ===== Edit & Resubmit Submission =====
@app.route("/api/rpg/worlds/submissions/<sub_id>", methods=["PUT"])
@login_required
def edit_submission(sub_id):
    subs = load_submissions()
    sub = next((s for s in subs if s["id"] == sub_id), None)
    if not sub:
        return jsonify({"error": "投稿不存在"}), 404
    if sub.get("submitted_by") != current_user.id:
        return jsonify({"error": "你只能编辑自己的投稿"}), 403
    if sub.get("status") != "pending":
        return jsonify({"error": "只能编辑待审核的投稿"}), 400
    data = request.json
    if "name" in data: sub["name"] = data["name"]
    if "emoji" in data: sub["emoji"] = data["emoji"]
    if "genre" in data: sub["genre"] = data["genre"]
    if "desc" in data: sub["desc"] = data["desc"]
    if "system_prompt" in data: sub["system_prompt"] = data["system_prompt"]
    if "temperature" in data: sub["temperature"] = float(data["temperature"])
    if "max_tokens" in data: sub["max_tokens"] = int(data["max_tokens"])
    sub["status"] = "pending"
    save_submissions(subs)
    return jsonify({"status": "ok", "message": "已重新提交审核"})


@app.route("/api/rpg/worlds/submissions/<sub_id>", methods=["DELETE"])
@login_required
def delete_my_submission(sub_id):
    subs = load_submissions()
    sub = next((s for s in subs if s["id"] == sub_id), None)
    if not sub:
        return jsonify({"error": "投稿不存在"}), 404
    if sub.get("submitted_by") != current_user.id:
        return jsonify({"error": "你只能删除自己的投稿"}), 403
    subs = [s for s in subs if s["id"] != sub_id]
    save_submissions(subs)
    return jsonify({"status": "ok"})


# ===== API Config (Admin) =====
@app.route("/api/admin/api-config", methods=["GET"])
@login_required
@admin_required
def get_api_config_route():
    configs = ApiConfig.query.order_by(ApiConfig.priority.desc()).all()
    result = {}
    for cfg in configs:
        if cfg.key_name == "API_KEY":
            result[cfg.key_name] = {
                "value": "***",
                "priority": cfg.priority
            }
        else:
            result[cfg.key_name] = {
                "value": cfg.value,
                "priority": cfg.priority
            }
    api_key_cfg = ApiConfig.query.filter_by(key_name="API_KEY").first()
    return jsonify({
        "configs": result,
        "has_key": bool(api_key_cfg and api_key_cfg.value)
    })


@app.route("/api/admin/api-config", methods=["PUT"])
@login_required
@admin_required
def update_api_config_route():
    data = request.json
    if "api_key" in data and data["api_key"].strip() and "***" not in data["api_key"]:
        cfg = ApiConfig.query.filter_by(key_name="API_KEY").first()
        if cfg:
            cfg.value = data["api_key"].strip()
        else:
            db.session.add(ApiConfig(key_name="API_KEY", value=data["api_key"].strip()))
    if "api_url" in data and data["api_url"].strip():
        cfg = ApiConfig.query.filter_by(key_name="API_URL").first()
        if cfg:
            cfg.value = data["api_url"].strip()
        else:
            db.session.add(ApiConfig(key_name="API_URL", value=data["api_url"].strip()))
    db.session.commit()
    return jsonify({"status": "ok"})


@app.route("/api/admin/api-config/priority", methods=["PUT"])
@login_required
@admin_required
def update_api_priority():
    data = request.json
    key_name = data.get("key_name")
    priority = data.get("priority")
    
    if not key_name:
        return jsonify({"error": "请提供 key_name"}), 400
    
    cfg = ApiConfig.query.filter_by(key_name=key_name).first()
    if not cfg:
        return jsonify({"error": "配置项不存在"}), 404
    
    cfg.priority = int(priority) if priority is not None else 0
    db.session.commit()
    
    return jsonify({"status": "ok", "key_name": key_name, "priority": cfg.priority})


# ===== Credit Keys (Admin) =====
@app.route("/api/admin/credit-keys", methods=["GET"])
@login_required
@admin_required
def list_credit_keys():
    keys = CreditKey.query.order_by(CreditKey.created_at.desc()).all()
    return jsonify([k.to_dict() for k in keys])


@app.route("/api/admin/credit-keys", methods=["POST"])
@login_required
@admin_required
def generate_credit_key():
    data = request.json
    credits = int(data.get("credits", 100))
    count = int(data.get("count", 1))
    if credits < 1 or count < 1 or count > 100:
        return jsonify({"error": "参数无效"}), 400

    generated = []
    for _ in range(count):
        key_str = "TAVERN-" + uuid.uuid4().hex[:12].upper()
        ck = CreditKey(key=key_str, credits=credits)
        db.session.add(ck)
        generated.append(key_str)

    db.session.commit()
    return jsonify({
        "status": "ok",
        "keys": generated,
        "credits": credits,
        "count": count
    })


@app.route("/api/admin/credit-keys/<int:key_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_credit_key(key_id):
    key = CreditKey.query.get(key_id)
    if not key:
        return jsonify({"error": "密钥不存在"}), 404
    if key.used:
        return jsonify({"error": "无法删除已使用的密钥"}), 400
    db.session.delete(key)
    db.session.commit()
    return jsonify({"status": "ok"})


# ===== Redeem (User) =====
@app.route("/api/redeem", methods=["POST"])
@login_required
def redeem_key():
    data = request.json
    code = data.get("key", "").strip().upper()
    if not code:
        return jsonify({"error": "请输入充值密钥"}), 400

    key = CreditKey.query.filter_by(key=code, used=False).first()
    if not key:
        return jsonify({"error": "无效的充值密钥或已被使用"}), 404

    updated = CreditKey.query.filter_by(id=key.id, used=False).update({
        'used': True,
        'used_by': current_user.id
    })
    if updated == 0:
        return jsonify({"error": "该密钥已被使用"}), 400

    current_user.credits += key.credits
    db.session.commit()

    return jsonify({
        "message": f"充值成功，获得 {key.credits} 积分",
        "credits_left": current_user.credits
    })


# ===== 反馈系统路由 =====

@app.route("/feedback")
@login_required
def feedback_page():
    return render_template("feedback.html")


@app.route("/api/feedback", methods=["POST"])
@login_required
def submit_feedback():
    data = request.json
    title = (data.get("title", "") or "").strip()
    content = (data.get("content", "") or "").strip()
    if not title or not content:
        return jsonify({"error": "标题和内容不能为空"}), 400
    if len(title) > 200:
        return jsonify({"error": "标题不能超过200字"}), 400
    if len(content) > 5000:
        return jsonify({"error": "内容不能超过5000字"}), 400

    fb = Feedback(
        user_id=current_user.id,
        username=current_user.username,
        category=data.get("category", "suggestion"),
        rating=int(data.get("rating", 3)),
        title=title,
        content=content,
        status="open"
    )
    db.session.add(fb)
    db.session.commit()
    return jsonify({"message": "反馈已提交，感谢您的宝贵意见！", "feedback": fb.to_dict()})


@app.route("/api/feedback", methods=["GET"])
@login_required
def list_feedback():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    category = request.args.get("category", "")
    status = request.args.get("status", "")
    search = request.args.get("search", "")

    query = Feedback.query
    if current_user.role != "admin":
        query = query.filter_by(user_id=current_user.id)
    if category:
        query = query.filter_by(category=category)
    if status:
        query = query.filter_by(status=status)
    if search:
        query = query.filter(
            (Feedback.title.ilike(f'%{search}%')) | 
            (Feedback.content.ilike(f'%{search}%')) |
            (Feedback.username.ilike(f'%{search}%'))
        )

    total = query.count()
    items = query.order_by(Feedback.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        "items": [fb.to_dict() for fb in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page)
    })


@app.route("/api/feedback/stats", methods=["GET"])
@login_required
def feedback_stats():
    if current_user.role != "admin":
        return jsonify({"error": "无权限"}), 403

    all_fb = Feedback.query.all()
    stats = {"total": len(all_fb), "open": 0, "in_progress": 0, "resolved": 0, "closed": 0,
             "bug": 0, "feature": 0, "suggestion": 0, "praise": 0, "other": 0}
    ratings = []
    for fb in all_fb:
        stats[fb.status] = stats.get(fb.status, 0) + 1
        stats[fb.category] = stats.get(fb.category, 0) + 1
        ratings.append(fb.rating)
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0
    stats["avg_rating"] = avg_rating
    stats["rating_dist"] = {str(i): ratings.count(i) for i in range(1, 6)}
    return jsonify(stats)


@app.route("/api/feedback/<int:feedback_id>", methods=["GET"])
@login_required
def get_feedback(feedback_id):
    fb = Feedback.query.get_or_404(feedback_id)
    if current_user.role != "admin" and fb.user_id != current_user.id:
        return jsonify({"error": "无权限"}), 403
    return jsonify(fb.to_dict())


@app.route("/api/feedback/<int:feedback_id>", methods=["PUT"])
@login_required
def update_feedback(feedback_id):
    fb = Feedback.query.get_or_404(feedback_id)
    if current_user.role != "admin":
        return jsonify({"error": "无权限"}), 403

    data = request.json
    new_status = data.get("status")
    admin_note = data.get("admin_note")

    valid_statuses = ["open", "in_progress", "resolved", "closed"]
    if new_status and new_status in valid_statuses:
        fb.status = new_status
    if admin_note is not None:
        fb.admin_note = admin_note

    db.session.commit()
    return jsonify({"message": "更新成功", "feedback": fb.to_dict()})


@app.route("/api/feedback/<int:feedback_id>", methods=["DELETE"])
@login_required
def delete_feedback(feedback_id):
    fb = Feedback.query.get_or_404(feedback_id)
    if current_user.role != "admin" and fb.user_id != current_user.id:
        return jsonify({"error": "无权限"}), 403
    db.session.delete(fb)
    db.session.commit()
    return jsonify({"message": "已删除"})


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    with app.app_context():
        init_db()
    load_sessions()
    agents = load_agents()
    with app.app_context():
        api_key, api_url = get_effective_api()
    print(f"[TAVERN] 酒馆已开门 | 版本: {VERSION}")
    with open(WORLDS_FILE, "r", encoding="utf-8") as f:
        world_data = json.load(f)
        world_count = len(world_data.get("worlds", []))
    print(f"[MODE]  聊天: {len(agents)} 位智能体 | 跑团: {world_count} 本世界书 | 反馈: /feedback | 已恢复 {len(rpg_sessions)} 个跑团会话")
    if api_key:
        print(f"[AI]   状态: 已连接 | URL: {api_url}")
    else:
        print(f"[AI]   未配置! 请在 .env 填写 AI_API_KEY 或管理员在面板中配置")
    host = os.getenv("HOST", "127.0.0.1")
    print(f"[URL]  http://{host}:9000")

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api/'):
            return jsonify({"error": "资源不存在"}), 404
        return render_template('index.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        app.logger.error(f"500 error: {e}")
        if request.path.startswith('/api/'):
            return jsonify({"error": "服务器内部错误"}), 500
        return render_template('index.html'), 500

    app.run(debug=False, host=host, port=9000)