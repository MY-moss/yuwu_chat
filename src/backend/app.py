# ============================================================
# 文件: app.py | 职责: Flask 应用工厂、数据库初始化、迁移、启动入口
# ============================================================
import os
import sys
import json
import secrets
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session
from logging.handlers import RotatingFileHandler
from flask_login import LoginManager
from dotenv import load_dotenv

from config import (Config, BASE_PATH, WORLDS_FILE, AGENTS_FILE, RATINGS_FILE,
                    SUBMISSIONS_FILE, USAGE_LOG_FILE, _ADMIN_CREDITS)
from models import (db, User, ModelConfig, UserModelConfig, ApiConfig,
                    Agent, WorldBook, WorldRating, WorldSubmission, UsageLog)
from state import histories, rpg_sessions
# [AUDIT-S11] 未添加 CORS 配置，跨站请求不受限制
from utils.security import safe_commit, encrypt_value, HAS_CRYPTO
from utils.json_io import (load_sessions, load_version, load_changelog,
                           VERSION, CHANGELOG, _cached_json_load)
from utils.ai_service import load_agents, get_effective_api

load_dotenv(os.path.join(BASE_PATH, '.env'))

logger = logging.getLogger(__name__)

login_manager = LoginManager()
login_manager.login_view = None  # API only, no redirect — use unauthorized_handler instead


@login_manager.user_loader
def load_user(user_id):
    user = db.session.get(User, int(user_id))
    if user and '_user_token_version' in session and session['_user_token_version'] != (user.token_version or 1):
        return None
    return user


@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({"error": "未登录"}), 401


def migrate_json_to_sqlite():
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
                            # [AUDIT-N10] ts.replace('Z','+00:00').split('+')[0] 截断时区信息导致日期错误
                        created_at=datetime.fromisoformat(ts.replace('Z', '+00:00').split('+')[0])
                        ))
                    # [AUDIT-E01] except pass 静默吞掉所有行错误，迁移数据损坏不可见
                    except Exception: pass
                db.session.commit()
                logger.info(f"Migrated usage logs from JSON to SQLite")
            except Exception as e:
                db.session.rollback()
                logger.warning(f"UsageLog migration skipped: {e}")


def init_db():
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
        db.session.execute(db.text("CREATE INDEX IF NOT EXISTS ix_credit_key_key ON credit_key(key)"))
        db.session.execute(db.text("CREATE INDEX IF NOT EXISTS ix_model_config_model_id ON model_config(model_id)"))
        db.session.execute(db.text("CREATE INDEX IF NOT EXISTS ix_usage_log_created_at ON usage_log(created_at)"))
        db.session.execute(db.text("CREATE INDEX IF NOT EXISTS ix_rate_limit_entry_action ON rate_limit_entry(action, key)"))
        try:
            db.session.execute(db.text("ALTER TABLE user ADD COLUMN password_reset_required BOOLEAN DEFAULT 0"))
            db.session.commit()
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
        admin = User(username='admin', role='admin', credits=_ADMIN_CREDITS)
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
        db.session.add(ApiConfig(key_name='API_KEY', value=encrypt_value(os.getenv('AI_API_KEY', '')), priority=10))
        db.session.add(ApiConfig(key_name='API_URL', value=os.getenv('AI_API_URL', ''), priority=5))
        safe_commit()


def create_app():
    app = Flask(__name__,
                static_folder=os.path.join(BASE_PATH, 'static'),
                template_folder=os.path.join(BASE_PATH, 'templates'))
    app.config.from_object(Config)

    # ===== Secret key 处理（保持与原逻辑一致）=====
    _secret_key = os.getenv("SECRET_KEY", "")
    if not _secret_key or _secret_key == "GENERATE_RANDOM_KEY_IN_PRODUCTION" or _secret_key == "tavern-secret-key-change-in-production":
        _key_file = os.path.join(BASE_PATH, '.secret_key')
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

    # ===== 日志配置 =====
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(os.path.join(BASE_PATH, 'app.log'), maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
        ]
    )

    # ===== 初始化扩展 =====
    db.init_app(app)
    login_manager.init_app(app)

    if not HAS_CRYPTO:
        logger.critical("CRITICAL: cryptography library not installed! API key encryption will fail.")
        logger.critical("Please install cryptography: pip install cryptography")
        raise RuntimeError("加密依赖未安装，请安装 cryptography 库")

    # ===== 注册蓝图 =====
    from blueprints.auth import auth_bp
    from blueprints.chat import chat_bp
    from blueprints.rpg import rpg_bp
    from blueprints.admin import admin_bp
    from blueprints.feedback import feedback_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(rpg_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(feedback_bp)

    # ===== 全局钩子 =====
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
    def add_security_and_cache_headers(response):
        if request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'public, max-age=3600, must-revalidate'
            response.headers.pop('Pragma', None)
            response.headers.pop('Expires', None)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        # response.headers['Content-Security-Policy'] = (
        #     "default-src 'self'; "
        #     "script-src 'self' cdn.jsdelivr.net cdnjs.cloudflare.com 'unsafe-inline' 'unsafe-eval'; "
        #     "style-src 'self' 'unsafe-inline' cdnjs.cloudflare.com; "
        #     "img-src 'self' data:; "
        #     "connect-src 'self'; "
        #     "font-src 'self'; "
        #     "frame-ancestors 'none'; "
        #     "base-uri 'self'; "
        #     "form-action 'self'"
        # )
        return response

    # ===== 应用级路由 =====
    @app.route("/version")
    def get_version():
        return jsonify({"version": VERSION})

    @app.route("/version/changelog")
    def get_changelog():
        return jsonify({"changelog": CHANGELOG})

    # ===== 错误处理器 =====
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api/'):
            return jsonify({"error": "资源不存在"}), 404
        return render_template('error.html', code=404, message="页面未找到"), 404

    @app.errorhandler(500)
    def server_error(e):
        # [AUDIT-E02] 无 traceback 日志，无法定位 500 错误根因
        app.logger.error(f"500 error: {e}")
        if request.path.startswith('/api/'):
            return jsonify({"error": "服务器内部错误"}), 500
        return render_template('error.html', code=500, message="服务器内部错误"), 500

    # ===== 启动自检 =====
    rules = [r.rule for r in app.url_map.iter_rules() if 'csrf' in r.rule]
    if not rules:
        logger.error("ROUTE MISSING: /api/csrf-token 未注册！")
    else:
        logger.info(f"路由自检通过: {rules[0]} 已注册")

    return app


# ============================================================
# 区块 22 · 启动入口
# ============================================================
# [AUDIT-P12] 使用 Flask 内置 dev server 生产部署，建议 gunicorn/waitress
# [AUDIT-Q12] 无 main() 函数，启动逻辑在 if __name__ 顶层级
if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    app = create_app()
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
    with app.app_context():
        agents = load_agents()
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
    port = int(os.getenv("PORT", "9000"))
    app.run(debug=False, host=host, port=port)
