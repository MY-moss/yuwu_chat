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

# ===== 并发锁（使用 RLock 支持嵌套获取，避免 save_* 调用时死锁）=====
_histories_lock = threading.RLock()
_sessions_lock = threading.RLock()
_agents_lock = threading.RLock()
_worlds_lock = threading.RLock()
_ratings_lock = threading.RLock()
_submissions_lock = threading.RLock()
_usage_log_lock = threading.RLock()
_json_cache_lock = threading.Lock()

