# ============================================================
# 文件: blueprints/admin.py | 职责: 管理员后台（模型/用户/统计/API配置/卡密/兑换）
# ============================================================
import uuid
import hashlib
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models import (db, User, ModelConfig, UserModelConfig, ApiConfig,
                    CreditKey, UsageLog, Feedback)
from state import histories, rpg_sessions, _histories_lock, _sessions_lock
from utils.security import admin_required, is_safe_url, encrypt_value
from utils.json_io import save_sessions, check_rate_limit, load_worlds

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__)


# ===== 模型管理 =====
@admin_bp.route("/api/admin/models", methods=["GET"])
@login_required
@admin_required
def admin_list_models():
    models = ModelConfig.query.order_by(ModelConfig.priority).all()
    return jsonify([m.to_dict_admin() for m in models])


@admin_bp.route("/api/admin/models", methods=["POST"])
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
    if len(model_id) > 200 or len(name) > 100 or len(label) > 100:
        return jsonify({"error": "输入长度超限（model_id≤200, name/label≤100）"}), 400
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


@admin_bp.route("/api/admin/models/<int:model_id>", methods=["PUT"])
@login_required
@admin_required
def admin_update_model(model_id):
    model = db.session.get(ModelConfig, model_id)
    if not model:
        return jsonify({"error": "模型不存在"}), 404

    data = request.json
    if "name" in data:
        if len(str(data["name"])) > 100:
            return jsonify({"error": "name长度不能超过100"}), 400
        model.name = data["name"]
    if "label" in data:
        if len(str(data["label"])) > 100:
            return jsonify({"error": "label长度不能超过100"}), 400
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


@admin_bp.route("/api/admin/models/<int:model_id>", methods=["DELETE"])
@login_required
@admin_required
def admin_delete_model(model_id):
    model = db.session.get(ModelConfig, model_id)
    if not model:
        return jsonify({"error": "模型不存在"}), 404

    db.session.delete(model)
    db.session.commit()
    return jsonify({"status": "ok"})


# ===== 用户管理 =====
@admin_bp.route("/api/admin/users", methods=["GET"])
@login_required
@admin_required
def admin_list_users():
    # [AUDIT-H01] 用户列表无分页，大量用户时 OOM 风险
    users = User.query.all()
    return jsonify([u.to_dict() for u in users])


@admin_bp.route("/api/admin/users/<int:user_id>", methods=["PUT"])
@login_required
@admin_required
def admin_update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "用户不存在"}), 404

    data = request.json
    if "username" in data:
        new_username = sanitize_input(data["username"]).strip()
        if not new_username:
            return jsonify({"error": "用户名不能为空"}), 400
        if len(new_username) < 2 or len(new_username) > 32:
            return jsonify({"error": "用户名长度必须在2-32字符之间"}), 400
        if User.query.filter(User.username == new_username, User.id != user_id).first():
            return jsonify({"error": "该用户名已被使用"}), 400
        old_username = user.username
        user.username = new_username
        Feedback.query.filter_by(user_id=user_id).update({"username": new_username})
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


@admin_bp.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
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


# ===== 统计 =====
@admin_bp.route("/api/admin/stats", methods=["GET"])
@login_required
@admin_required
def admin_stats():
    days = request.args.get('days', 30, type=int)
    days = max(1, min(days, 365))
    cutoff_time = datetime.now() - timedelta(days=days)
    from sqlalchemy import func
    base_query = UsageLog.query.filter(UsageLog.created_at >= cutoff_time)
    stats = db.session.query(
        func.count(UsageLog.id).label('total_calls'),
        func.coalesce(func.sum(UsageLog.tokens), 0).label('total_tokens'),
        func.coalesce(func.sum(UsageLog.cost), 0).label('total_cost')
    ).filter(UsageLog.created_at >= cutoff_time).first()
    total_calls = stats.total_calls or 0
    total_tokens = stats.total_tokens or 0
    total_cost = float(stats.total_cost or 0)
    user_stats = db.session.query(
        UsageLog.username, func.count(UsageLog.id).label('calls'),
        func.coalesce(func.sum(UsageLog.tokens), 0).label('tokens'),
        func.coalesce(func.sum(UsageLog.cost), 0).label('cost')
    ).filter(UsageLog.created_at >= cutoff_time).group_by(UsageLog.username).all()
    users = {u.username: {"calls": u.calls, "tokens": u.tokens, "cost": float(u.cost)} for u in user_stats}
    model_stats = db.session.query(
        UsageLog.model, func.count(UsageLog.id).label('calls'),
        func.coalesce(func.sum(UsageLog.tokens), 0).label('tokens')
    ).filter(UsageLog.created_at >= cutoff_time).group_by(UsageLog.model).all()
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


# ===== 全部会话 =====
@admin_bp.route("/api/admin/all-sessions", methods=["GET"])
@login_required
@admin_required
def admin_all_sessions():
    worlds = load_worlds()
    wmap = {w["id"]: w for w in worlds}
    items = []
    with _sessions_lock:
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


# ===== API 配置 =====
@admin_bp.route("/api/admin/api-config", methods=["GET"])
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


@admin_bp.route("/api/admin/api-config", methods=["PUT"])
@login_required
@admin_required
def update_api_config_route():
    data = request.json
    if "api_key" in data and data["api_key"].strip() and data["api_key"].strip() != '********':
        cfg = ApiConfig.query.filter_by(key_name="API_KEY").first()
        if cfg:
            cfg.value = encrypt_value(data["api_key"].strip())
        else:
            db.session.add(ApiConfig(key_name="API_KEY", value=encrypt_value(data["api_key"].strip())))
    if "api_url" in data and data["api_url"].strip():
        api_url = data["api_url"].strip()
        safe, msg = is_safe_url(api_url)
        if not safe:
            return jsonify({"error": "API地址不安全: " + msg}), 400
        cfg = ApiConfig.query.filter_by(key_name="API_URL").first()
        if cfg:
            cfg.value = api_url
        else:
            db.session.add(ApiConfig(key_name="API_URL", value=api_url))
    db.session.commit()
    return jsonify({"status": "ok"})


@admin_bp.route("/api/admin/api-config/priority", methods=["PUT"])
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


# ===== 卡密管理 =====
@admin_bp.route("/api/admin/credit-keys", methods=["GET"])
@login_required
@admin_required
def list_credit_keys():
    keys = CreditKey.query.order_by(CreditKey.created_at.desc()).all()
    return jsonify([k.to_dict() for k in keys])


@admin_bp.route("/api/admin/credit-keys", methods=["POST"])
@login_required
@admin_required
def generate_credit_key():
    data = request.json
    credits = int(data.get("credits", 100))
    count = int(data.get("count", 1))
    if credits < 1 or credits > 999999 or count < 1 or count > 100:
        return jsonify({"error": "参数无效（credits: 1-999999, count: 1-100）"}), 400

    generated = []
    for _ in range(count):
        plaintext = "TAVERN-" + uuid.uuid4().hex[:12].upper()
        key_hash, key_preview = CreditKey.hash_key(plaintext)
        db.session.add(CreditKey(key=key_hash, key_preview=key_preview, credits=credits))
        generated.append(plaintext)

    db.session.commit()
    return jsonify({
        "status": "ok",
        "keys": generated,
        "credits": credits,
        "count": count
    })


@admin_bp.route("/api/admin/credit-keys/<int:key_id>", methods=["DELETE"])
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


# ===== 兑换（用户）=====
@admin_bp.route("/api/redeem", methods=["POST"])
@login_required
def redeem_key():
    client_ip = request.remote_addr
    if not check_rate_limit('redeem', client_ip, max_attempts=5, window=60):
        return jsonify({"error": "兑换过于频繁，请稍后再试"}), 429

    data = request.json
    code = data.get("key", "").strip().upper()
    if not code:
        return jsonify({"error": "请输入充值密钥"}), 400

    code_hash, _ = CreditKey.hash_key(code)
    key = CreditKey.query.filter_by(key=code_hash, used=False).first()
    if not key:
        return jsonify({"error": "无效的充值密钥或已被使用"}), 404

    updated = CreditKey.query.filter_by(id=key.id, used=False).update({
        'used': True,
        'used_by': current_user.id
    })
    if updated == 0:
        return jsonify({"error": "该密钥已被使用"}), 400

    db.session.execute(
        db.text("UPDATE user SET credits = credits + :amt WHERE id = :uid"),
        {"amt": key.credits, "uid": current_user.id}
    )
    db.session.commit()

    return jsonify({
        "message": f"充值成功，获得 {key.credits} 积分",
        "credits_left": current_user.credits
    })
