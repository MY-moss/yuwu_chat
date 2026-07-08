# ============================================================
# 文件: utils/json_io.py | 职责: JSON文件原子读写、缓存、版本/格式加载、用量记录、限流
# ============================================================
import os
import json
import uuid
import time
import logging
import tempfile
from datetime import datetime, timedelta
from models import (db, Agent, WorldRating, WorldBook, WorldSubmission,
                    UsageLog, RateLimitEntry)
from state import (rpg_sessions, _json_cache, _json_cache_mtime,
                   _sessions_lock, _ratings_lock, _worlds_lock,
                   _submissions_lock, _usage_log_lock)
from config import (BASE_PATH, AGENTS_FILE, WORLDS_FILE, RATINGS_FILE,
                    SUBMISSIONS_FILE, USAGE_LOG_FILE, SESSIONS_FILE,
                    VERSION_FILE, CHANGELOG_FILE, RPG_FORMAT_FILE)
from utils.security import safe_commit

logger = logging.getLogger(__name__)


def atomic_json_dump(data, file_path, **kwargs):
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(file_path) or None)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, **kwargs)
        os.replace(tmp_path, file_path)
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
        VERSION_FILE,
        os.path.join(os.getcwd(), "version.json"),
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
        CHANGELOG_FILE,
        os.path.join(os.getcwd(), "CHANGELOG.json"),
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

try:
    with open(RPG_FORMAT_FILE, "r", encoding="utf-8") as _f:
        MANDATORY_RPG_FORMAT = _f.read()
except Exception as e:
    logger.error(f"Failed to load rpg_format.txt: {e}")
    MANDATORY_RPG_FORMAT = ""


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


def save_sessions():
    with _sessions_lock:
        keep = {}
        now = time.time()
        for sid, s in list(rpg_sessions.items()):
            last_active = s.get("last_active", "")
            try:
                if last_active:
                    last_active_ts = datetime.fromisoformat(last_active.replace('Z', '+00:00')).timestamp()
                    if now - last_active_ts > 86400:
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
        if len(rpg_sessions) > 500:
            oldest = sorted(rpg_sessions.keys(), key=lambda x: rpg_sessions[x].get("created_at", ""))[:len(rpg_sessions)-500]
            for k in oldest:
                rpg_sessions.pop(k, None)
            logger.warning(f"load_sessions capped at 500, evicted {len(oldest)} oldest")


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
        if not safe_commit():
            logger.error("save_ratings: delete failed, abort")
            return
        for wid, rating_list in ratings_dict.items():
            for r in rating_list:
                wr = WorldRating(
                    world_id=wid, user_id=r.get('user_id', 0),
                    username=r.get('username', ''),
                    rating=r.get('rating', 3), review=r.get('review', '')
                )
                db.session.add(wr)
        safe_commit()


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
        if not safe_commit():
            logger.error("save_worlds_data: delete failed, abort")
            return
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
        safe_commit()


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
        if not safe_commit():
            logger.error("save_submissions: delete failed, abort")
            return
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
        safe_commit()


def log_usage(user_id, username, model, tokens, cost, endpoint):
    try:
        log = UsageLog(
            user_id=user_id, username=username,
            model=model, tokens=tokens, cost=cost,
            endpoint=endpoint
        )
        db.session.add(log)
        db.session.commit()
        count = UsageLog.query.count()
        if count > 10000:
            oldest = UsageLog.query.order_by(UsageLog.id).limit(count - 10000).all()
            for o in oldest:
                db.session.delete(o)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"log_usage failed: {e}")


def check_rate_limit(action, key, max_attempts=5, window=60):
    cutoff = datetime.now() - timedelta(seconds=window)
    RateLimitEntry.query.filter(RateLimitEntry.created_at < cutoff).filter_by(action=action).delete()
    recent = RateLimitEntry.query.filter(
        RateLimitEntry.action == action,
        RateLimitEntry.key == key,
        RateLimitEntry.created_at >= cutoff
    ).count()
    if recent >= max_attempts:
        return False
    db.session.add(RateLimitEntry(action=action, key=key))
    db.session.commit()
    return True
