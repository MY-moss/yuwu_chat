# ============================================================
# 文件: config.py | 职责: 应用配置、路径解析、常量
# ============================================================
import os
import sys
from datetime import timedelta
from sqlalchemy.pool import QueuePool


def get_base_path():
    """返回应用根目录。PyInstaller 打包后资源在 sys._MEIPASS，但可写数据应放在 sys.executable 同级。"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_PATH = get_base_path()


class Config:
    """Flask 配置对象，通过 app.config.from_object 加载。"""
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(BASE_PATH, "instance", "tavern.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'poolclass': QueuePool,
        'pool_size': 10,
        'max_overflow': 20,
        'pool_pre_ping': True,
        'pool_recycle': 3600,
        'connect_args': {'timeout': 30}
    }
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    JSON_AS_ASCII = False
    TEMPLATES_AUTO_RELOAD = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # [AUDIT-N53] SESSION_COOKIE_SECURE = False 未通过环境变量控制，生产部署可能遗漏 HTTPS-only
    SESSION_COOKIE_SECURE = False  # 生产环境 HTTPS 下置 True
    # [AUDIT-N03] SECRET_KEY 占位符是确定性字符串，启动时需 assert 检测覆盖
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SECRET_KEY = 'GENERATE_RANDOM_KEY_IN_PRODUCTION'  # 运行时由 create_app 替换


# ===== JSON 数据文件路径 =====
AGENTS_FILE = os.path.join(BASE_PATH, "agents.json")
WORLDS_FILE = os.path.join(BASE_PATH, "worldbooks.json")
RATINGS_FILE = os.path.join(BASE_PATH, "world_ratings.json")
SUBMISSIONS_FILE = os.path.join(BASE_PATH, "world_submissions.json")
USAGE_LOG_FILE = os.path.join(BASE_PATH, "usage_log.json")
SESSIONS_FILE = os.path.join(BASE_PATH, "rpg_sessions.json")
RPG_FORMAT_FILE = os.path.join(BASE_PATH, "rpg_format.txt")
VERSION_FILE = os.path.join(BASE_PATH, "version.json")
CHANGELOG_FILE = os.path.join(BASE_PATH, "CHANGELOG.json")

# ===== 应用常量 =====
_SESSION_TTL = 86400
_INITIAL_CREDITS = 100
_ADMIN_CREDITS = 99999
_MAX_SESSIONS = 500
_MAX_HISTORIES = 500
_MAX_HISTORY_MSGS = 100
_MAX_TOTAL_MSGS = 10000
_MAX_CHAT_TOKENS = 1024
_MAX_RPG_TOKENS = 1500
_MAX_USAGE_LOG = 10000
_DEDUCT_RETRIES = 3

# ===== 登录/注册/兑换 限流参数 =====
_LOGIN_RATE_LIMIT = 5
_LOGIN_RATE_WINDOW = 60
_REGISTER_RATE_LIMIT = 5
_REGISTER_RATE_WINDOW = 60
_REDEEM_RATE_LIMIT = 5
_REDEEM_RATE_WINDOW = 60
