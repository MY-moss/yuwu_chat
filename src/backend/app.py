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
    tables = [row[0] for row in db.session.execute(db.text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()]
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
                    for rating in ratings:
                        db.session.add(WorldRating(
                            world_id=wid, user_id=rating.get('user_id'),
                            username=rating.get('username', ''),
                            rating=rating.get('rating', 3),
                            review=rating.get('review', ''),
                            created_at=datetime.fromisoformat(rating.get('created_at', datetime.now().isoformat()))
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
                failed_count = 0
                for log_entry in logs[-5000:]:
                    try:
                        ts = log_entry.get('time', log_entry.get('created_at', datetime.now().isoformat()))
                        created_at = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        db.session.add(UsageLog(
                            user_id=log_entry.get('user_id', 0),
                            username=log_entry.get('username', ''),
                            model=log_entry.get('model', ''),
                            tokens=log_entry.get('tokens', 0),
                            cost=log_entry.get('cost', 0),
                            endpoint=log_entry.get('endpoint', 'chat'),
                            created_at=created_at
                        ))
                    except Exception as row_e:
                        failed_count += 1
                        logger.warning(f"UsageLog row migration failed: {row_e}")
                db.session.commit()
                logger.info(f"Migrated usage logs from JSON to SQLite (failed rows: {failed_count})")
                if failed_count > 0:
                    logger.warning(f"UsageLog migration: {failed_count} rows failed to migrate")
            except Exception as e:
                db.session.rollback()
                logger.warning(f"UsageLog migration skipped: {e}")


def _migrate_foreign_keys():
    """N09+N08: 重建表以添加外键约束，同时将CreditKey.key转为sha256哈希"""
    import hashlib as _hl
    try:
        cols = [col[1] for col in db.session.execute(db.text("PRAGMA table_info(credit_key)")).fetchall()]
        if 'key_preview' in cols:
            try:
                row = db.session.execute(db.text("SELECT value FROM api_config WHERE key_name = 'schema_version'")).scalar()
                if not row:
                    db.session.execute(db.text("INSERT OR IGNORE INTO api_config (key_name, value, priority) VALUES ('schema_version', '2', 0)"))
                elif int(row) < 2:
                    db.session.execute(db.text("UPDATE api_config SET value = '2' WHERE key_name = 'schema_version'"))
                db.session.commit()
            except Exception:
                pass
            return
    except Exception:
        return

    try:
        db.session.execute(db.text("PRAGMA foreign_keys=OFF"))

        db.session.execute(db.text("""
            CREATE TABLE _umc_new (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
                model_id VARCHAR(100) NOT NULL,
                name VARCHAR(100) NOT NULL,
                label VARCHAR(100) NOT NULL,
                api_base VARCHAR(500),
                api_key VARCHAR(500),
                priority INTEGER DEFAULT 100,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, model_id)
            )
        """))
        db.session.execute(db.text("INSERT INTO _umc_new (id, user_id, model_id, name, label, api_base, api_key, priority, created_at) SELECT id, user_id, model_id, name, label, api_base, api_key, priority, created_at FROM user_model_config"))
        db.session.execute(db.text("DROP TABLE user_model_config"))
        db.session.execute(db.text("ALTER TABLE _umc_new RENAME TO user_model_config"))

        db.session.execute(db.text("""
            CREATE TABLE _ck_new (
                id INTEGER PRIMARY KEY,
                key VARCHAR(64) NOT NULL UNIQUE,
                key_preview VARCHAR(12) NOT NULL DEFAULT '',
                credits INTEGER NOT NULL,
                used BOOLEAN DEFAULT 0,
                used_by INTEGER REFERENCES user(id) ON DELETE SET NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        rows = db.session.execute(db.text("SELECT id, key, credits, used, used_by, created_at FROM credit_key")).fetchall()
        for row in rows:
            key_plain = row[1] or ""
            key_hash = _hl.sha256(key_plain.encode()).hexdigest()
            key_preview = key_plain[-4:]
            db.session.execute(db.text(
                "INSERT INTO _ck_new (id, key, key_preview, credits, used, used_by, created_at) "
                "VALUES (:id, :kh, :kp, :c, :u, :ub, :ca)"
            ), {"id": row[0], "kh": key_hash, "kp": key_preview, "c": row[2], "u": row[3], "ub": row[4], "ca": row[5]})
        db.session.execute(db.text("DROP TABLE credit_key"))
        db.session.execute(db.text("ALTER TABLE _ck_new RENAME TO credit_key"))
        db.session.execute(db.text("CREATE INDEX IF NOT EXISTS ix_credit_key_key ON credit_key(key)"))

        db.session.execute(db.text("""
            CREATE TABLE _wr_new (
                id INTEGER PRIMARY KEY,
                world_id VARCHAR(100) NOT NULL REFERENCES world_book(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
                username VARCHAR(80) NOT NULL,
                rating INTEGER NOT NULL,
                review TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (world_id, user_id)
            )
        """))
        db.session.execute(db.text("INSERT INTO _wr_new (id, world_id, user_id, username, rating, review, created_at, updated_at) SELECT id, world_id, user_id, username, rating, review, created_at, updated_at FROM world_rating"))
        db.session.execute(db.text("DROP TABLE world_rating"))
        db.session.execute(db.text("ALTER TABLE _wr_new RENAME TO world_rating"))

        db.session.execute(db.text("""
            CREATE TABLE _ws_new (
                id VARCHAR(100) PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                emoji VARCHAR(20) DEFAULT '📖',
                genre VARCHAR(100) DEFAULT '',
                desc TEXT DEFAULT '',
                system_prompt TEXT DEFAULT '',
                temperature FLOAT DEFAULT 0.85,
                max_tokens INTEGER DEFAULT 700,
                submitted_by INTEGER REFERENCES user(id) ON DELETE SET NULL,
                submitter VARCHAR(80) DEFAULT '',
                status VARCHAR(20) DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.session.execute(db.text("INSERT INTO _ws_new (id, name, emoji, genre, desc, system_prompt, temperature, max_tokens, submitted_by, submitter, status, created_at) SELECT id, name, emoji, genre, desc, system_prompt, temperature, max_tokens, submitted_by, submitter, status, created_at FROM world_submission"))
        db.session.execute(db.text("DROP TABLE world_submission"))
        db.session.execute(db.text("ALTER TABLE _ws_new RENAME TO world_submission"))
        db.session.execute(db.text("CREATE INDEX IF NOT EXISTS ix_world_submission_status ON world_submission(status)"))

        db.session.execute(db.text("""
            CREATE TABLE _ul_new (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
                username VARCHAR(80) NOT NULL,
                model VARCHAR(100) NOT NULL,
                tokens INTEGER DEFAULT 0,
                cost FLOAT DEFAULT 0.0,
                endpoint VARCHAR(50) DEFAULT 'chat',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.session.execute(db.text("INSERT INTO _ul_new (id, user_id, username, model, tokens, cost, endpoint, created_at) SELECT id, user_id, username, model, tokens, cost, endpoint, created_at FROM usage_log"))
        db.session.execute(db.text("DROP TABLE usage_log"))
        db.session.execute(db.text("ALTER TABLE _ul_new RENAME TO usage_log"))
        db.session.execute(db.text("CREATE INDEX IF NOT EXISTS ix_usage_log_user_id ON usage_log(user_id)"))
        db.session.execute(db.text("CREATE INDEX IF NOT EXISTS ix_usage_log_created_at ON usage_log(created_at)"))
        db.session.execute(db.text("CREATE INDEX IF NOT EXISTS idx_usage_user_created ON usage_log(user_id, created_at)"))

        db.session.execute(db.text("PRAGMA foreign_keys=ON"))

        try:
            row = db.session.execute(db.text("SELECT value FROM api_config WHERE key_name = 'schema_version'")).scalar()
            if not row:
                db.session.execute(db.text("INSERT OR IGNORE INTO api_config (key_name, value, priority) VALUES ('schema_version', '2', 0)"))
            else:
                db.session.execute(db.text("UPDATE api_config SET value = '2' WHERE key_name = 'schema_version'"))
        except Exception:
            pass
        db.session.commit()
        logger.info("N09+N08: 外键约束和卡密哈希迁移完成")
    except Exception as e:
        db.session.rollback()
        logger.warning(f"N09+N08迁移失败（可能已迁移）: {e}")


def init_db():
    db.create_all()
    migrate_json_to_sqlite()
    _migrate_foreign_keys()
    try:
        cols = [col[1] for col in db.session.execute(db.text("PRAGMA table_info(user_model_config)")).fetchall()]
        if 'api_base' not in cols:
            db.session.execute(db.text("ALTER TABLE user_model_config ADD COLUMN api_base VARCHAR(500)"))
        if 'api_key' not in cols:
            db.session.execute(db.text("ALTER TABLE user_model_config ADD COLUMN api_key VARCHAR(500)"))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning(f"user_model_config migration: {e}")
    try:
        user_cols = [col[1] for col in db.session.execute(db.text("PRAGMA table_info(user)")).fetchall()]
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
        db.session.execute(db.text("CREATE INDEX IF NOT EXISTS idx_usage_user_created ON usage_log(user_id, created_at)"))
        db.session.execute(db.text("CREATE INDEX IF NOT EXISTS ix_world_submission_status ON world_submission(status)"))
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
            try:
                os.chmod(_key_file, 0o600)
            except OSError:
                pass
    else:
        app.secret_key = _secret_key

    # ===== 日志配置 =====
    log_level = getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(os.path.join(BASE_PATH, 'app.log'), maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
        ]
    )

    # ===== 初始化扩展 =====
    db.init_app(app)
    login_manager.init_app(app)

    # N09: 启用SQLite外键约束
    from sqlalchemy import event
    with app.app_context():
        @event.listens_for(db.engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

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
        if not secrets.compare_digest(csrf_token, session_token):
            return jsonify({"error": "CSRF token invalid"}), 403

    @app.route('/api/csrf-token')
    def get_csrf_token():
        return jsonify({"csrf_token": session.get('_csrf_token', '')})

    @app.after_request
    def add_security_and_cache_headers(response):
        if request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'public, max-age=3600, must-revalidate'
            response.headers.pop('Pragma', None)
            response.headers.pop('Expires', None)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' cdn.jsdelivr.net cdnjs.cloudflare.com 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline' cdnjs.cloudflare.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
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
        import traceback
        app.logger.error(f"500 error: {e}\n{traceback.format_exc()}")
        if request.path.startswith('/api/'):
            return jsonify({"error": "服务器内部错误"}), 500
        return render_template('error.html', code=500, message="服务器内部错误"), 500

    # ===== 启动自检 =====
    rules = [rule.rule for rule in app.url_map.iter_rules() if 'csrf' in rule.rule]
    if not rules:
        logger.error("ROUTE MISSING: /api/csrf-token 未注册！")
    else:
        logger.info(f"路由自检通过: {rules[0]} 已注册")

    return app


# ============================================================
# 区块 22 · 启动入口
# ============================================================
# [AUDIT-P12] 使用 Flask 内置 dev server 生产部署，建议 gunicorn/waitress
def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    app = create_app()
    with app.app_context():
        init_db()
        # Schema version check — bump SCHEMA_VERSION when making backwards-incompatible DB changes
        SCHEMA_VERSION = 2
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
        world_count = WorldBook.query.count()
    print(f"[TAVERN] 酒馆已开门 | 版本: {VERSION}")
    print(f"[MODE]  聊天: {len(agents)} 位智能体 | 跑团: {world_count} 本世界书 | 反馈: /feedback | 已恢复 {len(rpg_sessions)} 个跑团会话")
    if api_key:
        print(f"[AI]   状态: 已连接")
    else:
        print(f"[AI]   未配置! 请在 .env 填写 AI_API_KEY 或管理员在面板中配置")
    host = os.getenv("HOST", "127.0.0.1")
    print(f"[URL]  http://{host}:9000")
    port = int(os.getenv("PORT", "9000"))
    app.run(debug=False, host=host, port=port)


if __name__ == "__main__":
    main()
