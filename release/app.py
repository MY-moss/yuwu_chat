# ============================================================
# 文件: app.py | 职责: Flask主应用 | 区块数: 22
# ============================================================

# ============================================================
# 区块 01 · 导入与配置
# ============================================================
import os
import sys
import json
import uuid
import collections
import threading
import time
import re
import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse
import ipaddress
import requests
from flask import Flask, render_template, request, jsonify, session, Response, stream_with_context
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.pool import NullPool
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import random
import base64
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


_API_KEY_PATTERN = re.compile(r'(sk-[a-zA-Z0-9]{20,}|api[_-]?key["\']?\s*[:=]\s*["\']?[a-zA-Z0-9]{16,})', re.IGNORECASE)
def sanitize_log(msg):
    if isinstance(msg, str):
        return _API_KEY_PATTERN.sub('***API_KEY_REDACTED***', msg)
    return msg

def get_base_path():
    if hasattr(sys, '_MEIPASS'):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_PATH = get_base_path()

# ============================================================
# 区块 02 · 工具与安全
# ============================================================
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
        # Check for encoded IP addresses (decimal, hex, octal, mixed)
        try:
            decoded_ip = None
            if hostname.isdigit() or (len(hostname) > 2 and hostname.startswith(('0x', '0X'))):
                decoded_ip = str(ipaddress.IPv4Address(int(hostname, 0)))
            elif '.' in hostname:
                parts = hostname.split('.')
                if len(parts) == 4:
                    octets = []
                    for p in parts:
                        if p.startswith(('0x', '0X')):
                            octets.append(int(p, 16))
                        elif p.startswith('0') and len(p) > 1:
                            octets.append(int(p, 8))
                        else:
                            octets.append(int(p))
                    if all(0 <= o <= 255 for o in octets):
                        decoded_ip = '.'.join(str(o) for o in octets)
            if decoded_ip:
                addr = ipaddress.ip_address(decoded_ip)
                if addr.is_private or addr.is_loopback or addr.is_link_local:
                    return False, '不允许访问私有或本地地址'
        except (ValueError, TypeError):
            pass
        return True, ''
    except Exception as e:
        return False, 'URL 解析失败'

load_dotenv(os.path.join(BASE_PATH, '.env'))

app = Flask(__name__, 
            static_folder=os.path.join(BASE_PATH, 'static'),
            template_folder=os.path.join(BASE_PATH, 'templates'))
_secret_key = os.getenv("SECRET_KEY", "")
if not _secret_key or _secret_key == "GENERATE_RANDOM_KEY_IN_PRODUCTION" or _secret_key == "tavern-secret-key-change-in-production":
    _key_file = os.path.join(os.path.dirname(__file__), '.secret_key')
    try:
        with open(_key_file, 'r') as f:
            app.secret_key = f.read().strip()
        if not app.secret_key:
            raise ValueError("empty key file")
    except (FileNotFoundError, ValueError):
        app.secret_key = secrets.token_hex(32)
        with open(_key_file, 'w') as f:
            f.write(app.secret_key)
else:
    app.secret_key = _secret_key
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_PATH, "instance", "tavern.db")}'
# NOTE: SQLite DB is in instance/tavern.db under the web root. In production, move the DB file
# outside the web root (e.g., /var/data/) to prevent direct download via the web server.
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'poolclass': NullPool,
    'connect_args': {'timeout': 30}
}
app.config['TEMPLATES_AUTO_RELOAD'] = app.debug
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(BASE_PATH, 'app.log'), encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)
app.config['JSON_AS_ASCII'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # Set True in production with HTTPS
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

def escape_html(s):
    if s is None:
        return ''
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#39;')


def get_fernet():
    key_material = app.secret_key.encode() if isinstance(app.secret_key, str) else app.secret_key
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b'tavern-encrypt-v1', iterations=100000)
    key = base64.urlsafe_b64encode(kdf.derive(key_material))
    return Fernet(key)


def encrypt_value(plaintext):
    if not plaintext:
        return None
    if not HAS_CRYPTO:
        return plaintext
    try:
        f = get_fernet()
        return f.encrypt(plaintext.encode()).decode()
    except Exception:
        return plaintext


def decrypt_value(ciphertext):
    if not ciphertext:
        return None
    if not HAS_CRYPTO:
        return ciphertext
    try:
        f = get_fernet()
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        return ciphertext

def safe_commit():
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logger.error(f"Database commit failed: {e}")
        return False

def validate_password(password):
    if len(password) < 8:
        return False, "密码长度至少8位"
    if not re.search(r'[a-z]', password):
        return False, "密码必须包含至少一个小写字母"
    if not re.search(r'[A-Z]', password):
        return False, "密码必须包含至少一个大写字母"
    if not re.search(r'[0-9]', password):
        return False, "密码必须包含至少一个数字"
    return True, ""

@app.before_request
def protect_db_and_csrf():
    # SEC-02: Block direct database file access
    if request.path.rstrip("/").endswith(".db"):
        return jsonify({"error": "Access denied"}), 403

    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(16)
    if request.method not in ['POST', 'PUT', 'DELETE']:
        return
    if request.path in ['/api/auth/login', '/api/auth/register']:
        return
    csrf_token = request.headers.get('X-CSRF-Token', '')
    session_token = session.get('_csrf_token', '')
    if csrf_token != session_token:
        return jsonify({"error": "CSRF token invalid"}), 403

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
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' cdn.jsdelivr.net 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "frame-ancestors 'none'"
    )
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

import tempfile
import shutil

# ============================================================
# 区块 03 · JSON 数据层
# ============================================================
def atomic_json_dump(data, file_path, **kwargs):
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(file_path) or None)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, **kwargs)
        shutil.move(tmp_path, file_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise


def atomic_json_load(file_path, default=None):
    if not os.path.exists(file_path):
        return default
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning(f"atomic_json_load: invalid JSON in {file_path}")
        return default

def load_version():
    paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.json"),
        os.path.join(os.getcwd(), "version.json"),
        os.path.join(BASE_PATH, "version.json")
    ]
    for version_file in paths:
        try:
            with open(version_file, "r", encoding="utf-8-sig") as f:
                v = json.load(f)
                build = v.get("build", 0)
                if build > 0:
                    return f"v{v['major']}.{v['minor']}.{v['patch']}.{build}"
                return f"v{v['major']}.{v['minor']}.{v['patch']}"
        except Exception as e:
            logger.error(f"load_version failed: {e}")
            continue
    return "v1.0.0"

def load_changelog():
    paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "CHANGELOG.json"),
        os.path.join(os.getcwd(), "CHANGELOG.json"),
        os.path.join(BASE_PATH, "CHANGELOG.json")
    ]
    for changelog_file in paths:
        try:
            with open(changelog_file, "r", encoding="utf-8") as f:
                return json.load(f).get("history", [])
        except Exception as e:
            logger.error(f"load_changelog failed: {e}")
            continue
    return []

VERSION = load_version()
CHANGELOG = load_changelog()

# 强制所有跑团输出格式 — 内容来自 rpg_format.txt
MANDATORY_RPG_FORMAT = open(os.path.join(BASE_PATH, "rpg_format.txt"), "r", encoding="utf-8").read()

histories = {}
rpg_sessions = {}
_json_cache = {}
_json_cache_mtime = {}

def _cached_json_load(file_path, default=None):
    try:
        if not os.path.exists(file_path):
            return default
        mtime = os.path.getmtime(file_path)
        if file_path in _json_cache and _json_cache_mtime.get(file_path) == mtime:
            return _json_cache[file_path]
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _json_cache[file_path] = data
        _json_cache_mtime[file_path] = mtime
        return data
    except Exception as e:
        logger.error(f"_cached_json_load failed for {file_path}: {e}")
        return default

def _invalidate_json_cache(file_path):
    _json_cache.pop(file_path, None)
    _json_cache_mtime.pop(file_path, None)

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
_register_attempts = {}
_register_lock = threading.Lock()
_REGISTER_RATE_LIMIT = 5
_REGISTER_RATE_WINDOW = 60
_redeem_attempts = {}
_redeem_lock = threading.Lock()
_REDEEM_RATE_LIMIT = 5
_REDEEM_RATE_WINDOW = 60
_SESSION_TTL = 86400


def save_sessions():
    with _sessions_lock:
        keep = {}
        now = time.time()
        for sid, s in list(rpg_sessions.items()):
            last_active = s.get("last_active", "")
            try:
                if last_active:
                    last_active_ts = datetime.fromisoformat(last_active.replace('Z', '+00:00')).timestamp()
                    if now - last_active_ts > _SESSION_TTL:
                        logger.info(f"save_sessions: removing expired session {sid}")
                        continue
            except Exception:
                pass
            k = {k: v for k, v in s.items()}
            hist = k.get("history", [])
            if hist:
                k["history"] = [hist[0]] + hist[-10:]
            else:
                k["history"] = hist
            keep[sid] = k
        max_sessions = 500
        if len(keep) > max_sessions:
            logger.warning(f"save_sessions: truncating {len(keep)} sessions to {max_sessions}")
            oldest_keys = sorted(keep.keys(), key=lambda x: keep[x].get("created_at", ""))[:-max_sessions]
            for old_key in oldest_keys:
                logger.warning(f"save_sessions: removing old session {old_key}")
                keep.pop(old_key)
        atomic_json_dump(keep, SESSIONS_FILE)


def load_sessions():
    global rpg_sessions
    with _sessions_lock:
        loaded = atomic_json_load(SESSIONS_FILE)
        if loaded is None:
            return
        sessions_data = loaded.get('sessions', loaded)
        if isinstance(sessions_data, dict):
            for sid, s in sessions_data.items():
                rpg_sessions[sid] = s
        elif isinstance(sessions_data, list):
            for s in sessions_data:
                try:
                    if isinstance(s, dict):
                        sid = s.get('session_id', str(uuid.uuid4()))
                        rpg_sessions[sid] = s
                    else:
                        logger.warning(f"skipping invalid session entry: {type(s)}")
                except Exception as ex:
                    logger.error(f"loading session: {ex}")

def load_ratings():
    try:
        with _ratings_lock:
            ratings = WorldRating.query.all()
            result = {}
            for r in ratings:
                if r.world_id not in result:
                    result[r.world_id] = []
                result[r.world_id].append(r.to_dict())
            return result
    except Exception as e:
        logger.error(f"load_ratings failed: {e}")
        return {}

def save_ratings(ratings_dict):
    with _ratings_lock:
        WorldRating.query.delete()
        for wid, rating_list in ratings_dict.items():
            for r in rating_list:
                wr = WorldRating(
                    world_id=wid, user_id=r.get('user_id', 0),
                    username=r.get('username', ''),
                    rating=r.get('rating', 3), review=r.get('review', '')
                )
                db.session.add(wr)
        db.session.commit()

def load_worlds():
    try:
        with _worlds_lock:
            worlds = WorldBook.query.order_by(WorldBook.order).all()
            return [w.to_dict() for w in worlds]
    except Exception as e:
        logger.error(f"load_worlds failed: {e}")
        return []

def save_worlds_data(worlds_list):
    with _worlds_lock:
        WorldBook.query.delete()
        for w_data in worlds_list:
            wb = WorldBook(
                id=w_data.get('id'), name=w_data.get('name', ''),
                emoji=w_data.get('emoji', '📖'), genre=w_data.get('genre', ''),
                desc=w_data.get('desc', ''),
                system_prompt=w_data.get('system_prompt', ''),
                temperature=w_data.get('temperature', 0.85),
                max_tokens=w_data.get('max_tokens', 700),
                order=w_data.get('order', 0)
            )
            db.session.add(wb)
        db.session.commit()


def load_submissions():
    try:
        with _submissions_lock:
            subs = WorldSubmission.query.order_by(WorldSubmission.created_at.desc()).all()
            return [s.to_dict() for s in subs]
    except Exception as e:
        logger.error(f"load_submissions failed: {e}")
        return []


def save_submissions(subs_list):
    with _submissions_lock:
        WorldSubmission.query.delete()
        for s_data in subs_list:
            ws = WorldSubmission(
                id=s_data.get('id'), name=s_data.get('name', ''),
                emoji=s_data.get('emoji', '📖'), genre=s_data.get('genre', ''),
                desc=s_data.get('desc', ''),
                system_prompt=s_data.get('system_prompt', ''),
                temperature=s_data.get('temperature', 0.85),
                max_tokens=s_data.get('max_tokens', 700),
                submitted_by=s_data.get('submitted_by', 0),
                submitter=s_data.get('submitter', ''),
                status=s_data.get('status', 'pending')
            )
            db.session.add(ws)
        db.session.commit()


_usage_log_lock = threading.Lock()

def log_usage(user_id, username, model, tokens, cost, endpoint):
    try:
        log = UsageLog(
            user_id=user_id, username=username,
            model=model, tokens=tokens, cost=cost,
            endpoint=endpoint
        )
        db.session.add(log)
        db.session.commit()
        # Keep last 10000 entries
        count = UsageLog.query.count()
        if count > 10000:
            oldest = UsageLog.query.order_by(UsageLog.id).limit(count - 10000).all()
            for o in oldest:
                db.session.delete(o)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"log_usage failed: {e}")


# ===== 反馈系统（已迁移至 Feedback 模型，文件读写已废弃）=====


# ============================================================
# 区块 04 · 数据库模型
# ============================================================
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
    last_active = db.Column(db.DateTime, default=datetime.now, index=True)
    token_version = db.Column(db.Integer, default=1)
    password_reset_required = db.Column(db.Boolean, default=False)

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
            'last_active': self.last_active.isoformat() if self.last_active else None,
            'password_reset_required': self.password_reset_required or False
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
            'created_at': self.created_at.isoformat(),
            'source': 'system'
        }

    def to_dict_admin(self):
        data = self.to_dict()
        data['api_base'] = self.api_base
        data['has_api_key'] = bool(self.api_key)
        return data


class UserModelConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    model_id = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    label = db.Column(db.String(100), nullable=False)
    api_base = db.Column(db.String(500), nullable=True)
    api_key = db.Column(db.String(500), nullable=True)
    priority = db.Column(db.Integer, default=100)
    created_at = db.Column(db.DateTime, default=datetime.now)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'model_id', name='uq_user_model'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'model_id': self.model_id,
            'name': self.name,
            'label': self.label,
            'credits_per_1k': 0,
            'enabled': True,
            'priority': self.priority,
            'created_at': self.created_at.isoformat(),
            'source': 'personal',
            'api_base': self.api_base,
            'has_api_key': bool(self.api_key)
        }


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
    user_id = db.Column(db.Integer, nullable=False, index=True)
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


class Agent(db.Model):
    __tablename__ = 'agent'
    id = db.Column(db.String(100), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    avatar = db.Column(db.String(500), nullable=False, default='🤖')
    model = db.Column(db.String(100), nullable=False)
    system_prompt = db.Column(db.Text, nullable=False)
    temperature = db.Column(db.Float, default=0.8)
    max_tokens = db.Column(db.Integer, default=1024)
    greeting = db.Column(db.String(500), nullable=True)
    mock_replies = db.Column(db.Text, nullable=True)
    mock_default = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        d = {
            'id': self.id, 'name': self.name, 'avatar': self.avatar,
            'model': self.model, 'system_prompt': self.system_prompt,
            'temperature': self.temperature, 'max_tokens': self.max_tokens
        }
        if self.greeting:
            d['greeting'] = self.greeting
        if self.mock_replies:
            try: d['mock_replies'] = json.loads(self.mock_replies)
            except: d['mock_replies'] = {}
        if self.mock_default:
            d['mock_default'] = self.mock_default
        return d

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data.get('id'), name=data.get('name', ''),
            avatar=data.get('avatar', '🤖'), model=data.get('model', ''),
            system_prompt=data.get('system_prompt', ''),
            temperature=data.get('temperature', 0.8),
            max_tokens=data.get('max_tokens', 1024),
            greeting=data.get('greeting'),
            mock_replies=json.dumps(data.get('mock_replies', {}), ensure_ascii=False) if data.get('mock_replies') else None,
            mock_default=data.get('mock_default')
        )


class WorldBook(db.Model):
    __tablename__ = 'world_book'
    id = db.Column(db.String(100), primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    emoji = db.Column(db.String(20), default='📖')
    genre = db.Column(db.String(100), default='')
    desc = db.Column(db.Text, default='')
    system_prompt = db.Column(db.Text, default='')
    temperature = db.Column(db.Float, default=0.85)
    max_tokens = db.Column(db.Integer, default=700)
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'emoji': self.emoji,
            'genre': self.genre, 'desc': self.desc,
            'system_prompt': self.system_prompt,
            'temperature': self.temperature, 'max_tokens': self.max_tokens,
            'order': self.order
        }


class WorldRating(db.Model):
    __tablename__ = 'world_rating'
    id = db.Column(db.Integer, primary_key=True)
    world_id = db.Column(db.String(100), db.ForeignKey('world_book.id'), nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    username = db.Column(db.String(80), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    review = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, onupdate=datetime.now)

    __table_args__ = (
        db.UniqueConstraint('world_id', 'user_id', name='uq_world_user_rating'),
    )

    def to_dict(self):
        return {
            'user_id': self.user_id, 'username': self.username,
            'rating': self.rating, 'review': self.review,
            'created_at': self.created_at.isoformat()
        }


class WorldSubmission(db.Model):
    __tablename__ = 'world_submission'
    id = db.Column(db.String(100), primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    emoji = db.Column(db.String(20), default='📖')
    genre = db.Column(db.String(100), default='')
    desc = db.Column(db.Text, default='')
    system_prompt = db.Column(db.Text, default='')
    temperature = db.Column(db.Float, default=0.85)
    max_tokens = db.Column(db.Integer, default=700)
    submitted_by = db.Column(db.Integer, nullable=False)
    submitter = db.Column(db.String(80), default='')
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'emoji': self.emoji,
            'genre': self.genre, 'desc': self.desc,
            'system_prompt': self.system_prompt,
            'temperature': self.temperature, 'max_tokens': self.max_tokens,
            'submitted_by': self.submitted_by, 'submitter': self.submitter,
            'status': self.status, 'created_at': self.created_at.isoformat()
        }


class UsageLog(db.Model):
    __tablename__ = 'usage_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    username = db.Column(db.String(80), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    tokens = db.Column(db.Integer, default=0)
    cost = db.Column(db.Float, default=0.0)
    endpoint = db.Column(db.String(50), default='chat')
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)

    def to_dict(self):
        return {
            'id': self.id, 'user_id': self.user_id,
            'username': self.username, 'model': self.model,
            'tokens': self.tokens, 'cost': self.cost,
            'endpoint': self.endpoint,
            'time': self.created_at.isoformat()
        }


# ============================================================
# 区块 05 · 认证辅助
# ============================================================
@login_manager.user_loader
def load_user(user_id):
    user = db.session.get(User, int(user_id))
    if user and '_user_token_version' in session and session['_user_token_version'] != (user.token_version or 1):
        return None
    return user


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


def migrate_json_to_sqlite():
    with app.app_context():
        tables = [r[0] for r in db.session.execute(db.text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()]
        migrated = {}
        for t in ['agent', 'world_book', 'world_rating', 'world_submission', 'usage_log']:
            migrated[t] = t in tables

        if not migrated['agent']:
            db.create_all()

        if migrated['agent'] and Agent.query.first() is None:
            if os.path.exists(AGENTS_FILE):
                try:
                    data = _cached_json_load(AGENTS_FILE, {"agents": []})
                    agents = data.get("agents", [])
                    for a in agents:
                        existing = Agent.query.get(a.get('id'))
                        if not existing:
                            db.session.add(Agent.from_dict(a))
                    db.session.commit()
                    logger.info(f"Migrated {len(agents)} agents from JSON to SQLite")
                except Exception as e:
                    db.session.rollback()
                    logger.warning(f"Agent migration skipped: {e}")

        if migrated['world_book'] and WorldBook.query.first() is None:
            if os.path.exists(WORLDS_FILE):
                try:
                    data = _cached_json_load(WORLDS_FILE, {"worlds": []})
                    worlds = data.get("worlds", [])
                    for w in worlds:
                        existing = WorldBook.query.get(w.get('id'))
                        if not existing:
                            db.session.add(WorldBook(
                                id=w.get('id'), name=w.get('name', ''),
                                emoji=w.get('emoji', '📖'), genre=w.get('genre', ''),
                                desc=w.get('desc', ''),
                                system_prompt=w.get('system_prompt', ''),
                                temperature=w.get('temperature', 0.85),
                                max_tokens=w.get('max_tokens', 700),
                                order=w.get('order', 0)
                            ))
                    db.session.commit()
                    logger.info(f"Migrated {len(worlds)} worlds from JSON to SQLite")
                except Exception as e:
                    db.session.rollback()
                    logger.warning(f"World migration skipped: {e}")

        if migrated['world_rating'] and WorldRating.query.first() is None:
            if os.path.exists(RATINGS_FILE):
                try:
                    data = _cached_json_load(RATINGS_FILE, {})
                    for wid, ratings in data.items():
                        for r in ratings:
                            db.session.add(WorldRating(
                                world_id=wid, user_id=r.get('user_id'),
                                username=r.get('username', ''),
                                rating=r.get('rating', 3),
                                review=r.get('review', ''),
                                created_at=datetime.fromisoformat(r.get('created_at', datetime.now().isoformat()))
                            ))
                    db.session.commit()
                    logger.info("Migrated ratings from JSON to SQLite")
                except Exception as e:
                    db.session.rollback()
                    logger.warning(f"Rating migration skipped: {e}")

        if migrated['world_submission'] and WorldSubmission.query.first() is None:
            if os.path.exists(SUBMISSIONS_FILE):
                try:
                    data = _cached_json_load(SUBMISSIONS_FILE, [])
                    for s in data:
                        db.session.add(WorldSubmission(
                            id=s.get('id'), name=s.get('name', ''),
                            emoji=s.get('emoji', '📖'), genre=s.get('genre', ''),
                            desc=s.get('desc', ''),
                            system_prompt=s.get('system_prompt', ''),
                            temperature=s.get('temperature', 0.85),
                            max_tokens=s.get('max_tokens', 700),
                            submitted_by=s.get('submitted_by', 0),
                            submitter=s.get('submitter', ''),
                            status=s.get('status', 'pending')
                        ))
                    db.session.commit()
                    logger.info("Migrated submissions from JSON to SQLite")
                except Exception as e:
                    db.session.rollback()
                    logger.warning(f"Submission migration skipped: {e}")

        if migrated['usage_log'] and UsageLog.query.first() is None:
            if os.path.exists(USAGE_LOG_FILE):
                try:
                    data = _cached_json_load(USAGE_LOG_FILE, [])
                    logs = data if isinstance(data, list) else data.get('logs', [])
                    for l in logs[-5000:]:
                        try:
                            ts = l.get('time', l.get('created_at', datetime.now().isoformat()))
                            db.session.add(UsageLog(
                                user_id=l.get('user_id', 0),
                                username=l.get('username', ''),
                                model=l.get('model', ''),
                                tokens=l.get('tokens', 0),
                                cost=l.get('cost', 0),
                                endpoint=l.get('endpoint', 'chat'),
                                created_at=datetime.fromisoformat(ts.replace('Z', '+00:00').split('+')[0])
                            ))
                        except: pass
                    db.session.commit()
                    logger.info(f"Migrated usage logs from JSON to SQLite")
                except Exception as e:
                    db.session.rollback()
                    logger.warning(f"UsageLog migration skipped: {e}")


def init_db():
    with app.app_context():
        db.create_all()
        migrate_json_to_sqlite()
        try:
            cols = [r[1] for r in db.session.execute(db.text("PRAGMA table_info(user_model_config)")).fetchall()]
            if 'api_base' not in cols:
                db.session.execute(db.text("ALTER TABLE user_model_config ADD COLUMN api_base VARCHAR(500)"))
            if 'api_key' not in cols:
                db.session.execute(db.text("ALTER TABLE user_model_config ADD COLUMN api_key VARCHAR(500)"))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.warning(f"user_model_config migration: {e}")
        try:
            user_cols = [r[1] for r in db.session.execute(db.text("PRAGMA table_info(user)")).fetchall()]
            if 'token_version' not in user_cols:
                db.session.execute(db.text("ALTER TABLE user ADD COLUMN token_version INTEGER DEFAULT 1"))
                db.session.execute(db.text("UPDATE user SET token_version = 1 WHERE token_version IS NULL"))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.warning(f"token_version migration: {e}")
        try:
            db.session.execute(db.text("CREATE INDEX IF NOT EXISTS ix_user_last_active ON user(last_active)"))
            db.session.execute(db.text("CREATE INDEX IF NOT EXISTS ix_feedback_user_id ON feedback(user_id)"))
            try: db.session.execute(db.text("ALTER TABLE user ADD COLUMN password_reset_required BOOLEAN DEFAULT 0")); db.session.commit()
            except Exception: pass
        except Exception as e:
            db.session.rollback()
            logger.warning(f"index migration: {e}")
        admin_exists = db.session.execute(db.text('SELECT COUNT(*) FROM user WHERE username = "admin"')).scalar()
        admin_pwd = os.getenv("ADMIN_PASSWORD")
        if not admin_exists:
            if not admin_pwd:
                admin_pwd = secrets.token_urlsafe(16)
                logger.info("Admin password auto-generated (set ADMIN_PASSWORD env var to customize)")
            admin = User(username='admin', role='admin', credits=99999)
            admin.set_password(admin_pwd)
            db.session.add(admin)
            safe_commit()
        else:
            if admin_pwd:
                admin = User.query.filter_by(username='admin').first()
                admin.set_password(admin_pwd)
                safe_commit()
                logger.info("Admin password updated from environment variable.")
        safe_commit()
        zero_credit_models = ['deepseek-ai/DeepSeek-V3', 'deepseek-ai/DeepSeek-V4-Flash', 'deepseek-ai/DeepSeek-V4-Pro']
        for model_id in zero_credit_models:
            ModelConfig.query.filter_by(model_id=model_id).delete()
            UserModelConfig.query.filter_by(model_id=model_id).delete()
        safe_commit()
        api_key_exists = db.session.execute(db.text('SELECT COUNT(*) FROM api_config WHERE key_name = "API_KEY"')).scalar()
        if not api_key_exists:
            db.session.add(ApiConfig(key_name='API_KEY', value=os.getenv('AI_API_KEY', ''), priority=10))
            db.session.add(ApiConfig(key_name='API_URL', value=os.getenv('AI_API_URL', ''), priority=5))
            safe_commit()


# ============================================================
# 区块 06 · Agent 与 AI 工具
# ============================================================
def load_agents():
    try:
        with _agents_lock:
            agents = Agent.query.all()
            return [a.to_dict() for a in agents]
    except Exception as e:
        logger.error(f"load_agents failed: {e}")
        return []


def save_agents(agents_list):
    with _agents_lock:
        Agent.query.delete()
        for a_data in agents_list:
            db.session.add(Agent.from_dict(a_data))
        db.session.commit()


def get_agent(agent_id):
    agent = Agent.query.get(agent_id)
    return agent.to_dict() if agent else None


def mock_reply(message, agent):
    replies = agent.get("mock_replies", {})
    default = agent.get("mock_default", "嗯，我在听，你继续说。")
    for kw, resp in replies.items():
        if kw in message:
            return f"【AI暂未配置】{resp}"
    return f"【AI暂未配置】{default}"


def get_model_price(model_id):
    user_model = UserModelConfig.query.filter_by(user_id=current_user.id, model_id=model_id).first()
    if user_model:
        return 0
    model = ModelConfig.query.filter_by(model_id=model_id, enabled=True).first()
    if model:
        return model.credits_per_1k
    return 1


def deduct_credits(user, amount, max_retries=3):
    """Deduct credits with optimistic locking via token_version."""
    for attempt in range(max_retries):
        current_ver = user.token_version or 1
        result = db.session.execute(
            db.text(
                "UPDATE user SET credits = credits - :amt "
                "WHERE id = :uid AND credits >= :amt AND token_version = :ver"
            ),
            {"amt": amount, "uid": user.id, "ver": current_ver}
        )
        db.session.commit()
        if result.rowcount > 0:
            db.session.refresh(user)
            return True
        db.session.refresh(user)
        if user.credits < amount:
            return False
    return False


def using_personal_api():
    return bool(current_user.personal_api_base and current_user.personal_api_key)


def parse_usage(resp_json):
    try:
        usage = resp_json.get("usage", {})
        return usage.get("total_tokens", 0), usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    except Exception as e:
        logger.error(f"parse_usage failed: {e}")
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
    """返回 (api_key, api_url) — 优先用户模型 API → 系统模型 API → 用户个人 API → 全局配置 → .env"""
    if user is None:
        try:
            from flask_login import current_user
            if current_user and current_user.is_authenticated:
                user = current_user
        except Exception:
            pass
    if model_id and user:
        user_model = UserModelConfig.query.filter_by(user_id=user.id, model_id=model_id).first()
        if user_model and user_model.api_base and user_model.api_key:
            return decrypt_value(user_model.api_key), user_model.api_base
    if model_id:
        model = ModelConfig.query.filter_by(model_id=model_id).first()
        if model and model.api_base and model.api_key:
            return decrypt_value(model.api_key), model.api_base
    if user and user.personal_api_base and user.personal_api_key:
        return decrypt_value(user.personal_api_key), user.personal_api_base
    key = get_api_config("API_KEY", os.getenv("AI_API_KEY", ""))
    url = get_api_config("API_URL", os.getenv("AI_API_URL", ""))
    return decrypt_value(key) if key else key, url


# ============================================================
# 区块 07 · 页面路由
# ============================================================
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


# ============================================================
# 区块 08 · 用户认证路由
# ============================================================
@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    if len(username) < 2 or len(username) > 32:
        return jsonify({"error": "用户名长度必须在2-32位之间"}), 400
    if not re.match(r'^[a-zA-Z0-9\u4e00-\u9fa5_]+$', username):
        return jsonify({"error": "用户名只能包含字母、数字、中文和下划线"}), 400
    if len(password) > 128:
        return jsonify({"error": "密码长度不能超过128位"}), 400
    valid_pwd, pwd_msg = validate_password(password)
    if not valid_pwd:
        return jsonify({"error": pwd_msg}), 400

    client_ip = request.remote_addr
    with _register_lock:
        now = time.time()
        reg_attempts = _register_attempts.get(client_ip, [])
        reg_attempts = [t for t in reg_attempts if now - t < _REGISTER_RATE_WINDOW]
        if len(reg_attempts) >= _REGISTER_RATE_LIMIT:
            return jsonify({"error": "注册过于频繁，请稍后再试"}), 429
        reg_attempts.append(now)
        _register_attempts[client_ip] = reg_attempts

    user = User(username=username, credits=100)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        if 'UNIQUE constraint failed' in str(e) or 'duplicate key' in str(e).lower():
            return jsonify({"error": "用户名已存在"}), 400
        logger.error(f"Registration failed for username: {username}")
        return jsonify({"error": "注册失败，请重试"}), 500

    login_user(user)
    session.permanent = True
    session['_user_token_version'] = user.token_version or 1
    return jsonify({"message": "注册成功", "user": user.to_dict()}), 201


@app.route("/api/user/usage", methods=["GET"])
@login_required
def user_usage():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    per_page = min(per_page, 100)
    query = UsageLog.query.filter_by(user_id=current_user.id).order_by(UsageLog.created_at.desc())
    total = query.count()
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    start = (page - 1) * per_page
    logs = query.offset(start).limit(per_page).all()
    return jsonify({
        "logs": [l.to_dict() for l in logs],
        "total": total,
        "page": page,
        "pages": pages
    })


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    client_ip = request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or request.remote_addr

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
    session.permanent = True
    session['_user_token_version'] = user.token_version or 1
    session['_csrf_token'] = secrets.token_hex(16)

    with _login_lock:
        _login_attempts.pop(client_ip, None)

    return jsonify({"message": "登录成功", "user": user.to_dict(), "password_reset_required": user.password_reset_required or False, "csrf_token": session['_csrf_token']})


@app.route("/api/auth/reset-admin-password", methods=["POST"])
@login_required
@admin_required
def reset_admin_password():
    admin = User.query.filter_by(username='admin').first()
    if admin:
        new_pwd = secrets.token_urlsafe(12)
        admin.set_password(new_pwd)
        admin.password_reset_required = True
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error("Admin password reset failed")
            return jsonify({"error": "密码重置失败"}), 500
        logger.info("Admin password reset completed")
        return jsonify({"message": "管理员密码已重置", "new_password": new_pwd})
    return jsonify({"error": "管理员用户不存在"}), 404


@app.route("/api/auth/logout")
@login_required
def logout():
    logout_user()
    session['_csrf_token'] = secrets.token_hex(16)
    return jsonify({"message": "退出成功", "csrf_token": session['_csrf_token']})


@app.route("/api/auth/change-password", methods=["POST"])
@login_required
def change_password():
    data = request.json
    old_password = data.get("old_password")
    new_password = data.get("new_password")
    
    if not old_password or not new_password:
        return jsonify({"error": "请输入原密码和新密码"}), 400
    
    if len(new_password) > 128:
        return jsonify({"error": "新密码长度不能超过128位"}), 400
    valid_pwd, pwd_msg = validate_password(new_password)
    if not valid_pwd:
        return jsonify({"error": "新" + pwd_msg}), 400

    if not current_user.check_password(old_password):
        return jsonify({"error": "原密码不正确"}), 401
    
    current_user.set_password(new_password)
    current_user.password_reset_required = False
    current_user.token_version = (current_user.token_version or 1) + 1
    db.session.commit()
    
    logout_user()
    session['_csrf_token'] = secrets.token_hex(16)
    
    return jsonify({"message": "密码修改成功，请重新登录", "csrf_token": session['_csrf_token']})


@app.route("/api/auth/me")
def get_current_user():
    if current_user.is_authenticated:
        now = datetime.now()
        if not current_user.last_active or (now - current_user.last_active).total_seconds() > 60:
            current_user.last_active = now
            db.session.commit()
        return jsonify(current_user.to_dict())
    return jsonify({"error": "未登录"}), 401


@app.route("/api/auth/ping", methods=["POST"])
@login_required
def ping_active():
    current_user.last_active = datetime.now()
    db.session.commit()
    return jsonify({"status": "ok"})


# ============================================================
# 区块 09 · 版本路由
# ============================================================
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
        current_user.personal_api_key = encrypt_value(v.strip()) if v else None
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(sanitize_log(f"Save API config failed: {e}"))
        return jsonify({"error": "保存失败"}), 500
    return jsonify({"status": "ok", "has_personal_api": bool(current_user.personal_api_base and current_user.personal_api_key)})


@app.route("/api/models", methods=["GET"])
@login_required
def list_models():
    system_models = ModelConfig.query.filter_by(enabled=True).order_by(ModelConfig.priority).all()
    user_models = UserModelConfig.query.filter_by(user_id=current_user.id).order_by(UserModelConfig.priority).all()
    
    all_models = []
    system_model_ids = set()
    
    for m in system_models:
        all_models.append(m.to_dict())
        system_model_ids.add(m.model_id)
    
    for m in user_models:
        if m.model_id not in system_model_ids:
            all_models.append(m.to_dict())
    
    all_models.sort(key=lambda x: x['priority'])
    return jsonify(all_models)


# ============================================================
# 区块 10 · 模型管理路由
# ============================================================
@app.route("/api/auth/models", methods=["GET"])
@login_required
def list_user_models():
    models = UserModelConfig.query.filter_by(user_id=current_user.id).order_by(UserModelConfig.priority).all()
    return jsonify([m.to_dict() for m in models])


@app.route("/api/auth/models", methods=["POST"])
@login_required
def add_user_model():
    data = request.json
    model_id = data.get("model_id", "").strip()
    name = data.get("name", "").strip()
    label = data.get("label", "").strip()

    if not model_id or not name or not label:
        return jsonify({"error": "模型ID、名称和标签不能为空"}), 400

    existing = UserModelConfig.query.filter_by(user_id=current_user.id, model_id=model_id).first()
    if existing:
        return jsonify({"error": "该模型已存在"}), 400

    model = UserModelConfig(
        user_id=current_user.id,
        model_id=model_id,
        name=name,
        label=label,
        priority=data.get("priority", 100),
        api_base=None,
        api_key=None
    )
    if "api_base" in data:
        v = data.get("api_base", "").strip()
        if v:
            safe, msg = is_safe_url(v)
            if not safe:
                return jsonify({"error": "API地址不安全: " + msg}), 400
            model.api_base = v
    if "api_key" in data:
        v = data.get("api_key", "").strip() or None
        model.api_key = encrypt_value(v) if v else None
    db.session.add(model)
    db.session.commit()
    return jsonify(model.to_dict()), 201


@app.route("/api/auth/models/<model_id>", methods=["PUT"])
@login_required
def update_user_model(model_id):
    model = UserModelConfig.query.filter_by(user_id=current_user.id, model_id=model_id).first()
    if not model:
        return jsonify({"error": "模型不存在"}), 404

    data = request.json
    if "name" in data:
        model.name = data["name"].strip()
    if "label" in data:
        model.label = data["label"].strip()
    if "priority" in data:
        model.priority = data["priority"]
    if "api_base" in data:
        v = data["api_base"]
        if v:
            safe, msg = is_safe_url(v)
            if not safe:
                return jsonify({"error": "API地址不安全: " + msg}), 400
            model.api_base = v.strip()
        else:
            model.api_base = None
    if "api_key" in data:
        v = data["api_key"]
        if v and v.strip() != '********':
            model.api_key = encrypt_value(v.strip())
        elif not v:
            model.api_key = None

    db.session.commit()
    return jsonify(model.to_dict())


@app.route("/api/auth/models/<model_id>", methods=["DELETE"])
@login_required
def delete_user_model(model_id):
    model = UserModelConfig.query.filter_by(user_id=current_user.id, model_id=model_id).first()
    if not model:
        return jsonify({"error": "模型不存在"}), 404
    
    db.session.delete(model)
    db.session.commit()
    return jsonify({"status": "ok"})


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
    try:
        credits_per_1k = int(credits_per_1k)
        if credits_per_1k < 0 or credits_per_1k > 1000:
            return jsonify({"error": "credits_per_1k必须在0到1000之间"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "credits_per_1k必须是整数"}), 400

    model = ModelConfig(
        model_id=model_id,
        name=name,
        label=label,
        credits_per_1k=credits_per_1k,
        priority=data.get("priority", 100),
        api_base=None,
        api_key=None
    )
    if "api_base" in data:
        v = data.get("api_base", "").strip()
        if v:
            safe, msg = is_safe_url(v)
            if not safe:
                return jsonify({"error": "API地址不安全: " + msg}), 400
            model.api_base = v
    if "api_key" in data:
        v = data.get("api_key", "").strip() or None
        model.api_key = encrypt_value(v) if v else None
    db.session.add(model)
    db.session.commit()
    return jsonify(model.to_dict()), 201


@app.route("/api/admin/models/<int:model_id>", methods=["PUT"])
@login_required
@admin_required
def admin_update_model(model_id):
    model = db.session.get(ModelConfig, model_id)
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
        if v:
            safe, msg = is_safe_url(v)
            if not safe:
                return jsonify({"error": "API地址不安全: " + msg}), 400
            model.api_base = v.strip()
        else:
            model.api_base = None
    if "api_key" in data:
        v = data["api_key"]
        if v and v.strip() != '********':
            model.api_key = encrypt_value(v.strip())
    if "priority" in data:
        model.priority = int(data["priority"])

    db.session.commit()
    return jsonify(model.to_dict())


@app.route("/api/admin/models/<int:model_id>", methods=["DELETE"])
@login_required
@admin_required
def admin_delete_model(model_id):
    model = db.session.get(ModelConfig, model_id)
    if not model:
        return jsonify({"error": "模型不存在"}), 404

    db.session.delete(model)
    db.session.commit()
    return jsonify({"status": "ok"})


# ============================================================
# 区块 11 · 管理员用户管理
# ============================================================
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
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "用户不存在"}), 404

    data = request.json
    if "credits" in data:
        try:
            credits = int(data["credits"])
            if credits < 0 or credits > 999999:
                return jsonify({"error": "积分值无效（0-999999）"}), 400
            user.credits = credits
        except (ValueError, TypeError):
            return jsonify({"error": "积分值必须为整数"}), 400
    if "role" in data:
        role = data["role"]
        if role not in ["user", "admin"]:
            return jsonify({"error": "无效的角色值"}), 400
        if role == "admin":
            admin_count = User.query.filter_by(role="admin").count()
            if user.role != "admin" and admin_count >= 3:
                return jsonify({"error": "管理员数量已达上限（3人）"}), 400
        if role == "user" and user.role == "admin":
            admin_count = User.query.filter_by(role="admin").count()
            if admin_count <= 1:
                return jsonify({"error": "必须至少保留一名管理员"}), 400
        user.role = role

    db.session.commit()
    return jsonify(user.to_dict())


@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@login_required
@admin_required
def admin_delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "用户不存在"}), 404
    if user.id == current_user.id:
        return jsonify({"error": "不能删除自己"}), 400

    admin_count = User.query.filter_by(role="admin").count()
    if user.role == "admin" and admin_count <= 1:
        return jsonify({"error": "必须至少保留一名管理员"}), 400

    UserModelConfig.query.filter_by(user_id=user_id).delete()
    Feedback.query.filter_by(user_id=user_id).delete()

    with _histories_lock:
        for key in list(histories.keys()):
            if key.startswith(f"{user_id}_"):
                histories.pop(key, None)

    with _sessions_lock:
        for sid in list(rpg_sessions.keys()):
            if rpg_sessions[sid].get("user_id") == user_id:
                rpg_sessions.pop(sid, None)
        save_sessions()

    db.session.delete(user)
    db.session.commit()
    return jsonify({"status": "ok"})


# ============================================================
# 区块 12 · Agents CRUD
# ============================================================
@app.route("/api/agents", methods=["GET"])
@login_required
def list_agents():
    return jsonify(load_agents())


@app.route("/api/agents", methods=["POST"])
@login_required
@admin_required
def add_agent():
    data = request.json
    if not data:
        return jsonify({"error": "请求数据不能为空"}), 400
    required_fields = ["id", "name", "avatar", "model", "system_prompt"]
    missing = [f for f in required_fields if not data.get(f)]
    if missing:
        return jsonify({"error": f"缺少必填字段: {', '.join(missing)}"}), 400
    agents = load_agents()
    if any(a["id"] == data["id"] for a in agents):
        return jsonify({"error": "智能体ID已存在"}), 400
    if len(data["id"]) > 100:
        return jsonify({"error": "智能体ID长度不能超过100"}), 400
    if len(data["name"]) > 100:
        return jsonify({"error": "智能体名称长度不能超过100"}), 400
    if "temperature" in data and (not isinstance(data["temperature"], (int, float)) or data["temperature"] < 0 or data["temperature"] > 2):
        return jsonify({"error": "temperature必须在0到2之间"}), 400
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
    with _histories_lock:
        for key in list(histories.keys()):
            if key.endswith(f"_{agent_id}"):
                histories.pop(key, None)
    return jsonify({"status": "ok"})


# ============================================================
# 区块 13 · 聊天核心
# ============================================================
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
            
            with requests.post(api_url, headers=headers, json=body, timeout=30) as resp:
                if resp.status_code != 200:
                    logger.error(sanitize_log(f"chat API failed: {resp.status_code}"))
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
            if history_length > 100:
                histories[history_key] = histories[history_key][-100:]
            if len(histories) > 500:
                oldest_keys = sorted(histories.keys())[:len(histories)-500]
                for k in oldest_keys:
                    histories.pop(k, None)
        
        return jsonify({
            "reply": reply,
            "history_length": history_length,
            "credits_left": current_user.credits,
            "tokens_used": total_tokens,
            "cost": cost,
            "free": personal
        })

    except Exception as e:
        logger.error(sanitize_log(f"chat failed: {e}"))
        return jsonify({"reply": f"（{agent['name']}擦了擦额头的汗）抱歉，刚才出了点问题……请稍后重试"}), 500


@app.route("/api/history/<agent_id>", methods=["DELETE"])
@login_required
def clear_history(agent_id):
    history_key = f"{current_user.id}_{agent_id}"
    histories.pop(history_key, None)
    return jsonify({"status": "ok"})


def call_ai(messages, model="mimo-v2.5-free", temperature=0.85, max_tokens=1200):
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
        with requests.post(api_url, headers=headers, json=body, timeout=120) as resp:
            if resp.status_code != 200:
                logger.error(sanitize_log(f"call_ai API failed: {resp.status_code}"))
                raise Exception(f"API调用失败")
            data = resp.json()
            full = data["choices"][0]["message"]["content"]
            total_tokens, _, _ = parse_usage(data)
            story, sections = parse_rpg_reply(full)
            if "判定" in sections:
                judgment_text = sections["判定"]
                judge_result = _resolve_judgment(judgment_text, sections)
                if judge_result:
                    story = (story + "\n" + judge_result) if story else judge_result
                    sections.pop("判定", None)
            return story, sections, total_tokens
    except Exception as e:
        logger.error(f"call_ai failed: {e}")
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


def roll_d20(modifier=0):
    """Roll a d20 with modifier, return (roll, total)"""
    roll = random.randint(1, 20)
    total = roll + modifier
    return roll, total


def _resolve_judgment(judgment_text, sections=None):
    """Parse a 【判定】 section from AI output, roll dice server-side, return formatted result string.
    
    Expected format: 属性名 难度:XX 说明:XXXX
    Returns formatted Markdown string with clear success/failure.
    Returns None if no valid judgment found.
    """
    import re
    text = judgment_text.strip()

    JUDGE_ATTRS = r'(力量|敏捷|智力|魅力|体质|感知|意志|幸运|洞察|潜行|说服|威吓|表演|巧手|运动|察觉|调查|生存|自然|宗教|历史|医疗|洞悉|欺瞒|威逼|表演|手上功夫)'
    attr_match = re.search(JUDGE_ATTRS, text)

    dc_match = re.search(r'难度[：:]\s*(\d+)', text)
    desc_match = re.search(r'说明[：:](.*?)$', text, re.DOTALL)

    if not attr_match and not dc_match:
        return None

    attr_name = attr_match.group(1) if attr_match else "通用"
    dc = int(dc_match.group(1)) if dc_match else 15
    desc = desc_match.group(1).strip() if desc_match else ""

    attr_value = None
    if sections and attr_name != "通用":
        for key in ['属性', '状态', '技能', '能力']:
            val = sections.get(key, "")
            pattern = re.compile(re.escape(attr_name) + r'[：:]\s*(\d+)', re.IGNORECASE)
            m = pattern.search(val)
            if m:
                attr_value = int(m.group(1))
                break

    if attr_value is not None:
        modifier = max(-4, min(5, attr_value - 5))
    else:
        modifier = 0

    roll, total = roll_d20(modifier)
    natural_20 = (roll == 20)
    natural_1 = (roll == 1)
    success = total >= dc or natural_20

    if natural_20:
        result_label = "🎉 **大成功！**"
        impact = "天时地利人和齐聚，你的行动获得了超乎预期的完美效果！"
    elif natural_1:
        result_label = "💥 **大失败！**"
        impact = "命运开了个残酷的玩笑，事情朝着最坏的方向发展了……"
    elif success:
        result_label = "✅ **检定成功！**"
        impact = "你的行动取得了理想的效果，局势正向有利的方向发展。"
    else:
        result_label = "❌ **检定失败！**"
        impact = "事情并没有按照预想的方向发展，你需要重新调整策略……"

    desc_line = "**检定说明**: " + desc + "\n" if desc else ""
    nat_line = "(自然20！)" if natural_20 else "(自然1……)" if natural_1 else ""
    nat_line_full = nat_line + "\n" if nat_line else "\n"
    attr_val_str = " (" + str(attr_value) + ")" if attr_value is not None else ""

    result = (
        "\n\n━━━━━ 【🎲 技能检定】 ━━━━━\n"
        "**检定类型**: " + attr_name + "\n"
        "**难度等级**: DC " + str(dc) + "\n"
        + desc_line
        + "━━━━━━━━━━━━━━━━━━━━━\n"
        + "🎯 **d20 掷出**: **" + str(roll) + "**\n"
        + nat_line_full
        + "➕ **属性修正**: " + attr_name + attr_val_str + " = " + ("%+d" % modifier) + "\n"
        + "📊 **最终结果**: " + str(roll) + " " + ("%+d" % modifier) + " = **" + str(total) + "** (目标: **" + str(dc) + "**)\n"
        + "━━━━━━━━━━━━━━━━━━━━━\n"
        + result_label + "\n"
        + impact + "\n"
        + "━━━━━━━━━━━━━━━━━━━━━"
    )

    return result


def _parse_relationships(rels_str):
    rmap = {}
    if rels_str:
        for part in rels_str.replace("【", "").replace("】", "").split():
            if ":" in part:
                k, v = part.split(":", 1)
                rmap[k.strip()] = v.strip()
    if not rmap and rels_str:
        for line in rels_str.replace("\r", "").split("\n"):
            line = line.strip()
            if ":" in line and not line.startswith("http"):
                k, v = line.split(":", 1)
                rmap[k.strip()] = v.strip()
    return rmap


# ============================================================
# 区块 14 · RPG 世界
# ============================================================
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


@app.route("/api/rpg/worlds/<world_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_world(world_id):
    """删除单个世界书"""
    worlds = load_worlds()
    original_count = len(worlds)
    worlds = [w for w in worlds if w["id"] != world_id]
    if len(worlds) == original_count:
        return jsonify({"error": "世界书不存在"}), 404
    worlds.sort(key=lambda w: w.get("order", 0))
    for i, w in enumerate(worlds):
        w["order"] = i
    save_worlds_data(worlds)
    return jsonify({"status": "ok"})


@app.route("/api/rpg/active-count", methods=["GET"])
@login_required
def active_count():
    """返回所有用户活跃跑团总数"""
    with _sessions_lock:
        result = {"total": len(rpg_sessions)}
        if getattr(current_user, 'is_admin', current_user.role == 'admin'):
            by_world = {}
            for sid, s in rpg_sessions.items():
                wid = s.get("world_id", "unknown")
                if wid not in by_world:
                    by_world[wid] = 0
                by_world[wid] += 1
            result["by_world"] = by_world
        return jsonify(result)


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
    try:
        rating = int(data.get("rating", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "评分必须为整数"}), 400
    review = data.get("review", "").strip()
    if rating < 1 or rating > 5:
        return jsonify({"error": "评分需在1-5之间"}), 400

    worlds = load_worlds()
    if not any(w["id"] == world_id for w in worlds):
        return jsonify({"error": "世界书不存在"}), 404
    
    with _ratings_lock:
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
        if not (0 <= sub["temperature"] <= 2):
            return jsonify({"error": "temperature 必须在 0-2 之间"}), 400
        if not (100 <= sub["max_tokens"] <= 4096):
            return jsonify({"error": "max_tokens 必须在 100-4096 之间"}), 400
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
# ============================================================
# 区块 15 · 管理员统计
# ============================================================
@app.route("/api/admin/stats", methods=["GET"])
@login_required
@admin_required
def admin_stats():
    from sqlalchemy import func
    stats = db.session.query(
        func.count(UsageLog.id).label('total_calls'),
        func.coalesce(func.sum(UsageLog.tokens), 0).label('total_tokens'),
        func.coalesce(func.sum(UsageLog.cost), 0).label('total_cost')
    ).first()
    total_calls = stats.total_calls or 0
    total_tokens = stats.total_tokens or 0
    total_cost = float(stats.total_cost or 0)
    user_stats = db.session.query(
        UsageLog.username, func.count(UsageLog.id).label('calls'),
        func.coalesce(func.sum(UsageLog.tokens), 0).label('tokens'),
        func.coalesce(func.sum(UsageLog.cost), 0).label('cost')
    ).group_by(UsageLog.username).all()
    users = {u.username: {"calls": u.calls, "tokens": u.tokens, "cost": float(u.cost)} for u in user_stats}
    model_stats = db.session.query(
        UsageLog.model, func.count(UsageLog.id).label('calls'),
        func.coalesce(func.sum(UsageLog.tokens), 0).label('tokens')
    ).group_by(UsageLog.model).all()
    models = {m.model: {"calls": m.calls, "tokens": m.tokens} for m in model_stats}
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
        base_url = request.host_url.rstrip('/')
        return jsonify({
            "share_token": sess["share_token"],
            "share_url": f"{base_url}/shared/session/{sess['share_token']}"
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


# ============================================================
# 区块 16 · 分享与观战
# ============================================================
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


# ============================================================
# 区块 17 · RPG 会话
# ============================================================
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

    session_id = str(uuid.uuid4())[:12]
    messages = [
        {"role": "system", "content": world["system_prompt"] + MANDATORY_RPG_FORMAT},
        {"role": "user", "content": f"玩家名称为「{player_name}」。游戏开始，请描述开场场景并输出所有强制段。"}
    ]

    try:
        story, sections, tokens = call_ai(messages,
                        model=model,
                        temperature=world.get("temperature", 0.85),
                        max_tokens=world.get("max_tokens", 1500))
    except Exception as e:
        logger.error(f"start_rpg AI call failed: {e}")
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

    rmap = _parse_relationships(rels_str)
    rpg_sessions[session_id]["sections"]["关系_map"] = rmap

    return jsonify({
        "session_id": session_id, "world": world,
        "story": story, "state": state_str,
        "relationships": rmap, "sections": sections,
        "player_name": player_name,
        "storyline": rpg_sessions[session_id]["storyline"],
        "share_token": None,
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
        session["history"] = [session["history"][0]] + session["history"][-29:]

    session["model"] = model

    try:
        story, sections, tokens = call_ai(session["history"],
                        model=model,
                        temperature=world.get("temperature", 0.85),
                        max_tokens=world.get("max_tokens", 1500))
    except Exception as e:
        logger.error(f"rpg_act AI call failed: {e}")
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

    rmap = _parse_relationships(sections.get("关系", ""))
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

    prev = sess.get("sections", {})
    ctx = f"我选择：{choice}"
    if prev:
        ctx += "\n\n当前数据：" + "; ".join(f"【{k}】{v}" for k, v in prev.items() if not isinstance(v, dict))
    ctx += "\n\n请继续故事，并在末尾输出更新后的所有数据段：【状态】【属性】【关系】【背包】【技能】等"
    sess["model"] = model

    api_key, api_url = get_effective_api(model)
    credits_per_1k = get_model_price(model)

    user_id = current_user.id
    username = current_user.username
    user_credits = current_user.credits

    def generate():
        import json as _json
        if not api_key:
            mock_text = "【状态】\n生命值:100/100\n法力值:50/50\n\n（AI 暂未配置，请管理员在面板中配置 API 密钥）"
            for ch in mock_text:
                yield f"data: {_json.dumps({'type':'chunk','text':ch})}\n\n"
            yield f"data: {_json.dumps({'type':'done'})}\n\n"
            return
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        temp_history = sess["history"].copy()
        temp_history.append({"role": "assistant", "content": sess.get("last_story", "")})
        temp_history.append({"role": "user", "content": ctx})
        if len(temp_history) > 30:
            temp_history = [temp_history[0]] + temp_history[-29:]
        body = {"model": model, "messages": temp_history,
                "temperature": world.get("temperature", 0.85),
                "max_tokens": world.get("max_tokens", 1500)}
        full_text = ""
        import json as _json
        try:
            body["stream"] = True
            with requests.post(api_url, headers=headers, json=body, timeout=60, stream=True) as resp:
                if resp.status_code in (400, 415, 422, 500):
                    body["stream"] = False
                    with requests.post(api_url, headers=headers, json=body, timeout=60) as resp_retry:
                        if resp_retry.status_code == 200:
                            data = resp_retry.json()
                            choices = data.get("choices", [])
                            full_text = choices[0].get("message", {}).get("content", "") if choices else ""
                            for ch in full_text:
                                yield f"data: {_json.dumps({'type':'chunk','text':ch})}\n\n"
                            import time; time.sleep(0.02)
                elif resp.status_code != 200:
                    try:
                        err_body = resp.text[:500]
                        logger.error(sanitize_log(f"rpg_act_stream API {resp.status_code}: {err_body}"))
                    except Exception as e:
                        err_body = ""
                        logger.error(sanitize_log(f"rpg_act_stream API {resp.status_code}: {e}"))
                    yield f"data: {_json.dumps({'type':'error','text':'AI服务暂时不可用，请稍后重试'})}\n\n"
                    return
                else:
                    it = resp.iter_lines()
                    first = next(it, None)
                    if first and not first.startswith(b"data: "):
                        raw = first + b"".join(list(it))
                        try:
                            data = _json.loads(raw.decode("utf-8"))
                            choices = data.get("choices", [])
                            full_text = choices[0].get("message", {}).get("content", full_text) if choices else full_text
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
                                    choices = d.get("choices", [])
                                    delta = choices[0].get("delta", {}).get("content", "") if choices else ""
                                    if delta:
                                        full_text += delta
                                        yield f"data: {_json.dumps({'type':'chunk','text':delta})}\n\n"
                                except Exception:
                                    pass
        except Exception as e:
            logger.error(f"rpg_act_stream: {e}")
            yield f"data: {_json.dumps({'type':'error','text':'AI服务暂时不可用，请稍后重试'})}\n\n"
            return

        story, sections = parse_rpg_reply(full_text)
        if "判定" in sections:
            judgment_text = sections["判定"]
            judge_result = _resolve_judgment(judgment_text, sections)
            if judge_result:
                story = (story + "\n" + judge_result) if story else judge_result
                sections.pop("判定", None)
        for k, v in prev.items():
            if k not in sections and k != "关系_map":
                sections[k] = v
        state_str = sections.get("状态", "")
        personal = using_personal_api()
        total_tokens = estimate_tokens(full_text)
        cost = calc_token_cost(total_tokens, credits_per_1k) if (not personal and credits_per_1k > 0) else 0

        db_user = User.query.get(user_id)
        if not db_user:
            yield f"data: {_json.dumps({'type':'error','text':'用户不存在'})}\n\n"
            return

        if not personal and credits_per_1k > 0 and not deduct_credits(db_user, cost):
            yield f"data: {_json.dumps({'type':'error','text':f'积分不足（需要 {cost} 积分）'})}\n\n"
            return

        rmap = _parse_relationships(sections.get("关系", ""))
        sections["关系_map"] = rmap

        sess["last_story"] = story
        sess["sections"] = sections
        sess["last_state"] = state_str
        sess["last_active"] = datetime.now().isoformat()
        sess["history"] = temp_history
        rnd = len(sess.get("storyline", []))
        sess.setdefault("state_log", []).append({"round": rnd, "sections": dict(sections)})
        sess["storyline"].append({"round": rnd, "choice": choice, "story": story[:150], "sections": dict(sections)})
        save_sessions()
        log_usage(user_id, username, model, total_tokens, cost, "rpg_act_stream")

        db_user = User.query.get(user_id)
        final_credits = db_user.credits if db_user else user_credits

        yield f"data: {_json.dumps({'type':'done','story':story,'state':state_str,'relationships':rmap,'sections':sections,'tokens_used':total_tokens,'cost':cost,'credits_left':final_credits,'free':personal})}\n\n"

    response = Response(stream_with_context(generate()), mimetype="text/event-stream")
    return response


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
    if not history:
        sess["history"] = []
    else:
        kept = [history[0]]
        pair_count = 0
        for msg in history[1:]:
            if pair_count >= (target + 1) * 2:
                break
            kept.append(msg)
            pair_count += 1
        if len(kept) > 1 and kept[-1].get("role") == "assistant":
            kept.pop()
        sess["history"] = kept
    sess["last_active"] = datetime.now().isoformat()

    sess["sections"]["关系_map"] = _parse_relationships(last_sections.get("关系", ""))

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


@app.route("/api/rpg/roll", methods=["POST"])
@login_required
def roll_dice():
    data = request.json
    session_id = data.get("session_id")
    difficulty = data.get("difficulty", 10)
    modifier = data.get("modifier", 0)
    attribute = data.get("attribute", "")

    if not session_id:
        return jsonify({"error": "缺少会话ID"}), 400

    sess = rpg_sessions.get(session_id)
    if not sess:
        return jsonify({"error": "会话不存在"}), 404
    if sess.get("user_id") != current_user.id:
        return jsonify({"error": "无权操作"}), 403

    import random
    roll = random.randint(1, 20)
    total = roll + modifier
    success = total >= difficulty

    return jsonify({
        "roll": roll,
        "total": total,
        "difficulty": difficulty,
        "modifier": modifier,
        "attribute": attribute,
        "success": success
    })


# ===== Edit & Resubmit Submission =====
# ============================================================
# 区块 18 · 投稿编辑
# ============================================================
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
# ============================================================
# 区块 19 · API 配置/卡密
# ============================================================
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
    if "api_key" in data and data["api_key"].strip() and data["api_key"].strip() != '********':
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
    if credits < 1 or credits > 999999 or count < 1 or count > 100:
        return jsonify({"error": "参数无效（credits: 1-999999, count: 1-100）"}), 400

    keys = [CreditKey(key="TAVERN-" + uuid.uuid4().hex[:12].upper(), credits=credits) for _ in range(count)]
    db.session.add_all(keys)
    generated = [k.key for k in keys]

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
    key = db.session.get(CreditKey, key_id)
    if not key:
        return jsonify({"error": "密钥不存在"}), 404
    if key.used:
        return jsonify({"error": "无法删除已使用的密钥"}), 400
    db.session.delete(key)
    db.session.commit()
    return jsonify({"status": "ok"})


# ===== Redeem (User) =====
# ============================================================
# 区块 20 · 兑换
# ============================================================
@app.route("/api/redeem", methods=["POST"])
@login_required
def redeem_key():
    client_ip = request.remote_addr
    with _redeem_lock:
        now = time.time()
        attempts = _redeem_attempts.get(client_ip, [])
        attempts = [t for t in attempts if now - t < _REDEEM_RATE_WINDOW]
        if len(attempts) >= _REDEEM_RATE_LIMIT:
            return jsonify({"error": "兑换过于频繁，请稍后再试"}), 429
        attempts.append(now)
        _redeem_attempts[client_ip] = attempts

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

# ============================================================
# 区块 21 · 反馈系统
# ============================================================
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

    category = data.get("category", "suggestion")
    if category not in ["bug", "feature", "suggestion", "praise", "other"]:
        return jsonify({"error": "无效的分类"}), 400

    try:
        rating = int(data.get("rating", 3))
        if not (1 <= rating <= 5):
            return jsonify({"error": "评分必须在1-5之间"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "评分必须为整数"}), 400

    fb = Feedback(
        user_id=current_user.id,
        username=current_user.username,
        category=category,
        rating=rating,
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
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = max(1, min(100, request.args.get("per_page", 20, type=int) or 20))
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
        escaped_search = search.replace("%", "\\%").replace("_", "\\_")
        search_pattern = f'%{escaped_search}%'
        query = query.filter(
            (Feedback.title.ilike(search_pattern, escape='\\')) | 
            (Feedback.content.ilike(search_pattern, escape='\\')) |
            (Feedback.username.ilike(search_pattern, escape='\\'))
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
    counter = collections.Counter(ratings)
    stats["rating_dist"] = {str(i): counter.get(i, 0) for i in range(1, 6)}
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


# ============================================================
# 区块 22 · 启动入口
# ============================================================
if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    with app.app_context():
        init_db()
        # Schema version check — bump SCHEMA_VERSION when making backwards-incompatible DB changes
        SCHEMA_VERSION = 1
        try:
            row = db.session.execute(db.text("SELECT value FROM api_config WHERE key_name = 'schema_version'")).scalar()
            if not row:
                db.session.execute(db.text("INSERT OR IGNORE INTO api_config (key_name, value, priority) VALUES ('schema_version', :v, 0)"), {"v": str(SCHEMA_VERSION)})
                db.session.commit()
        except Exception:
            pass
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
        print(f"[AI]   状态: 已连接")
    else:
        print(f"[AI]   未配置! 请在 .env 填写 AI_API_KEY 或管理员在面板中配置")
    host = os.getenv("HOST", "127.0.0.1")
    print(f"[URL]  http://{host}:9000")

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api/'):
            return jsonify({"error": "资源不存在"}), 404
        return render_template('error.html', code=404, message="页面未找到"), 404

    @app.errorhandler(500)
    def server_error(e):
        app.logger.error(f"500 error: {e}")
        if request.path.startswith('/api/'):
            return jsonify({"error": "服务器内部错误"}), 500
        return render_template('error.html', code=500, message="服务器内部错误"), 500

    port = int(os.getenv("PORT", "9000"))
    app.run(debug=False, host=host, port=port)

# ===== END OF FILE =====
