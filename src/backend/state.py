# ============================================================
# 文件: state.py | 职责: 进程级可变状态与并发锁
# ============================================================
import threading

# ===== 运行时数据 =====
histories = {}
rpg_sessions = {}

# ===== JSON 文件缓存 =====
_json_cache = {}
_json_cache_mtime = {}

# ===== 并发锁 =====
_histories_lock = threading.Lock()
_sessions_lock = threading.Lock()
_agents_lock = threading.Lock()
_worlds_lock = threading.Lock()
_ratings_lock = threading.Lock()
_submissions_lock = threading.Lock()
_usage_log_lock = threading.Lock()

# ===== 限流计数（DB 兜底，内存计数为兼容保留）=====
_login_attempts = {}
_login_lock = threading.Lock()
_register_attempts = {}
_register_lock = threading.Lock()
_redeem_attempts = {}
_redeem_lock = threading.Lock()
