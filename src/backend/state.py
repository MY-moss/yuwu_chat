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

# ===== 并发锁（9个：7 RLock + 2 Lock，RLock 支持嵌套获取避免 save_* 调用时死锁）=====
_histories_lock = threading.RLock()
_sessions_lock = threading.RLock()
_agents_lock = threading.RLock()
_worlds_lock = threading.RLock()
_ratings_lock = threading.RLock()
_submissions_lock = threading.RLock()
_usage_log_lock = threading.RLock()
_json_cache_lock = threading.Lock()
_rate_limit_lock = threading.Lock()  # H02: check_rate_limit TOCTOU 竞态防护

