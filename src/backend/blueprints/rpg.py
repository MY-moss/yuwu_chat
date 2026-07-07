# ============================================================
# 文件: blueprints/rpg.py | 职责: 跑团系统（世界书/评分/投稿/会话/分享/观战/流式）
# ============================================================
import uuid
import secrets
import logging
import requests
from datetime import datetime
from flask import (Blueprint, render_template, request, jsonify,
                   Response, stream_with_context)
from flask_login import login_required, current_user
from models import db, User
from state import rpg_sessions, _sessions_lock, _ratings_lock
from utils.security import admin_required, sanitize_log, is_safe_url
from utils.json_io import (load_worlds, save_worlds_data, load_ratings, save_ratings,
                           load_submissions, save_submissions, save_sessions,
                           log_usage, MANDATORY_RPG_FORMAT)
from utils.ai_service import (call_ai, get_model_price, get_effective_api,
                              using_personal_api, calc_token_cost, deduct_credits,
                              estimate_tokens, parse_rpg_reply, _resolve_judgment,
                              _parse_relationships)

logger = logging.getLogger(__name__)

rpg_bp = Blueprint('rpg', __name__)


# ===== 世界书 =====
@rpg_bp.route("/api/rpg/worlds", methods=["GET"])
@login_required
def list_worlds():
    worlds = load_worlds()
    worlds.sort(key=lambda w: w.get("order", 0))
    ratings = load_ratings()
    for w in worlds:
        w_ratings = ratings.get(w["id"], [])
        w["rating_count"] = len(w_ratings)
        if w_ratings:
            w["avg_rating"] = round(sum(r["rating"] for r in w_ratings) / len(w_ratings), 1)
        else:
            w["avg_rating"] = 0
    return jsonify(worlds)


@rpg_bp.route("/api/rpg/worlds", methods=["POST"])
@login_required
@admin_required
def save_world():
    worlds = request.json
    save_worlds_data(worlds)
    return jsonify({"status": "ok"})


@rpg_bp.route("/api/rpg/worlds/reorder", methods=["POST"])
@login_required
@admin_required
def reorder_worlds():
    """管理员调整世界书排列顺序"""
    data = request.json
    world_ids = data.get("order", [])
    worlds = load_worlds()
    for i, wid in enumerate(world_ids):
        for w in worlds:
            if w["id"] == wid:
                w["order"] = i
                break
    save_worlds_data(worlds)
    return jsonify({"status": "ok"})


@rpg_bp.route("/api/rpg/worlds/<world_id>", methods=["DELETE"])
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


@rpg_bp.route("/api/rpg/active-count", methods=["GET"])
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


# ===== 世界书评分 =====
@rpg_bp.route("/api/rpg/worlds/<world_id>/ratings", methods=["GET"])
@login_required
def get_world_ratings(world_id):
    """获取世界书的评分和评价"""
    ratings = load_ratings()
    world_ratings = ratings.get(world_id, [])
    return jsonify(world_ratings)


@rpg_bp.route("/api/rpg/worlds/<world_id>/ratings", methods=["POST"])
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

    world_ratings = ratings.get(world_id, [])
    avg = round(sum(r["rating"] for r in world_ratings) / len(world_ratings), 1) if world_ratings else 0
    return jsonify({
        "status": "ok",
        "avg_rating": avg,
        "rating_count": len(world_ratings),
        "my_rating": rating,
        "my_review": review
    })


# ===== 世界书投稿 =====
@rpg_bp.route("/api/rpg/worlds/submit", methods=["POST"])
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


@rpg_bp.route("/api/rpg/worlds/submissions", methods=["GET"])
@login_required
@admin_required
def list_submissions():
    subs = load_submissions()
    return jsonify(subs)


@rpg_bp.route("/api/rpg/worlds/submissions/<sub_id>", methods=["POST"])
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


@rpg_bp.route("/api/rpg/worlds/my-submissions", methods=["GET"])
@login_required
def my_submissions():
    subs = load_submissions()
    mine = [s for s in subs if s.get("submitted_by") == current_user.id]
    return jsonify(mine)


@rpg_bp.route("/api/rpg/worlds/submissions/<sub_id>", methods=["PUT"])
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


@rpg_bp.route("/api/rpg/worlds/submissions/<sub_id>", methods=["DELETE"])
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


# ===== 分享与观战 =====
@rpg_bp.route("/api/rpg/session/<session_id>/share", methods=["POST"])
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


@rpg_bp.route("/api/rpg/session/<session_id>/unshare", methods=["POST"])
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


@rpg_bp.route("/api/rpg/shared/<share_token>")
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


@rpg_bp.route("/api/rpg/shared-sessions")
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


@rpg_bp.route("/shared/session/<share_token>")
def spectate_page(share_token):
    return render_template("spectate.html", token=share_token)


@rpg_bp.route("/api/rpg/admin/spectate/<session_id>")
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


# ===== 跑团会话 =====
@rpg_bp.route("/api/rpg/start", methods=["POST"])
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

    # [AUDIT-S19] start_rpg 先调用 AI API (line 424) 后扣费
    personal = using_personal_api()
    cost = calc_token_cost(tokens, credits_per_1k) if not personal else 0
    if not personal and not deduct_credits(current_user, cost):
        return jsonify({"error": f"积分不足（需要 {cost} 积分）"}), 402
    if not personal:
        current_user.total_tokens = (current_user.total_tokens or 0) + tokens
        db.session.commit()

    log_usage(current_user.id, current_user.username, model, tokens, cost, "rpg_start")

    if len(rpg_sessions) >= 500:
        oldest = sorted(rpg_sessions.keys(), key=lambda x: rpg_sessions[x].get("created_at", ""))[:50]
        for k in oldest:
            rpg_sessions.pop(k, None)
        logger.warning(f"rpg_sessions capped at 500, evicted {len(oldest)} oldest")

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


@rpg_bp.route("/api/rpg/act", methods=["POST"])
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

    prev = session.get("sections", {})
    for k, v in prev.items():
        if k not in sections and k != '关系_map':
            sections[k] = v
    state_str = sections.get("状态", "")

    # [AUDIT-S17] rpg_act 先调用 AI API (line 521) 后扣费，竞态条件
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


@rpg_bp.route("/api/rpg/act/stream", methods=["POST"])
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
        total_tokens = 0
        if not api_key:
            mock_text = "【状态】\n生命值:100/100\n法力值:50/50\n\n（AI 暂未配置，请管理员在面板中配置 API 密钥）"
            for ch in mock_text:
                yield f"data: {_json.dumps({'type':'chunk','text':ch})}\n\n"
            yield f"data: {_json.dumps({'type':'done'})}\n\n"
            return
        if not api_url:
            logger.error("rpg_act_stream API URL is empty")
            yield f"data: {_json.dumps({'type':'error','text':'API地址配置不完整'})}\n\n"
            return
        safe, reason = is_safe_url(api_url)
        if not safe:
            logger.error(sanitize_log(f"rpg_act_stream API URL unsafe: {reason}"))
            yield f"data: {_json.dumps({'type':'error','text':'API地址配置不安全'})}\n\n"
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


@rpg_bp.route("/api/rpg/sessions", methods=["GET"])
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


@rpg_bp.route("/api/rpg/session/<session_id>", methods=["PUT"])
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


@rpg_bp.route("/api/rpg/session/<session_id>", methods=["GET"])
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


@rpg_bp.route("/api/rpg/session/<session_id>/branch", methods=["POST"])
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

    sess["storyline"] = storyline[:target + 1]
    state_log = sess.get("state_log", [])
    sess["state_log"] = state_log[:target + 1] if state_log else []
    last_entry = sess["storyline"][-1] if sess["storyline"] else {}
    sess["last_story"] = last_entry.get("story", "")
    last_sections = last_entry.get("sections", {})
    sess["last_state"] = last_sections.get("状态", "") if isinstance(last_sections, dict) else str(last_sections)
    sess["sections"] = last_sections

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


@rpg_bp.route("/api/rpg/session/<session_id>", methods=["DELETE"])
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


@rpg_bp.route("/api/rpg/roll", methods=["POST"])
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
