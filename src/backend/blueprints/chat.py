# ============================================================
# 文件: blueprints/chat.py | 职责: 页面路由、聊天、智能体CRUD、模型列表、用量
# ============================================================
import logging
import requests
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from models import db, UsageLog, ModelConfig, UserModelConfig
from config import _MAX_HISTORY_MSGS, _MAX_HISTORIES
from state import histories, _histories_lock
from utils.security import admin_required, validate_id_param, sanitize_log, is_safe_url
from utils.json_io import log_usage
from utils.ai_service import (load_agents, save_agents, get_agent, get_model_price,
                              get_effective_api, mock_reply, using_personal_api,
                              calc_token_cost, deduct_credits, parse_usage)

logger = logging.getLogger(__name__)

chat_bp = Blueprint('chat', __name__)


@chat_bp.route("/")
def index():
    agents = load_agents()
    default = agents[0] if agents else {"id": "none", "name": "无", "avatar": "🧔"}
    return render_template("index.html", agents=agents, default_agent=default)


@chat_bp.route("/dashboard")
@login_required
@admin_required
def dashboard():
    return render_template("dashboard.html")


@chat_bp.route("/api/user/usage", methods=["GET"])
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


@chat_bp.route("/api/models", methods=["GET"])
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


@chat_bp.route("/api/agents", methods=["GET"])
@login_required
def list_agents():
    return jsonify(load_agents())


@chat_bp.route("/api/agents", methods=["POST"])
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


@chat_bp.route("/api/agents/<agent_id>", methods=["PUT"])
@login_required
@admin_required
def update_agent(agent_id):
    if not validate_id_param(agent_id):
        return jsonify({"error": "无效的智能体ID"}), 400
    data = request.json
    agents = load_agents()
    for i, a in enumerate(agents):
        if a["id"] == agent_id:
            agents[i] = {**a, **data}
            agents[i]["id"] = agent_id
            save_agents(agents)
            return jsonify(agents[i])
    return jsonify({"error": "未找到智能体"}), 404


@chat_bp.route("/api/agents/<agent_id>", methods=["DELETE"])
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


# [AUDIT-S12] 聊天端点无速率限制，可快速消耗积分
@chat_bp.route("/api/chat", methods=["POST"])
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

    # [AUDIT-E10] 用户消息在 line 188 附加到 body["messages"]，但 histories[-19:] 在 line 189，导致当前消息先于历史
    try:
        api_key, api_url = get_effective_api(model)
        if api_key:
            if not api_url:
                logger.error("chat API URL is empty")
                return jsonify({"error": "API地址配置不完整"}), 400
            safe, reason = is_safe_url(api_url)
            if not safe:
                logger.error(sanitize_log(f"chat API URL unsafe: {reason}"))
                return jsonify({"error": "API地址配置不安全"}), 400
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
                body["messages"].extend(histories[history_key][-19:])
                body["messages"].extend([{"role": "user", "content": user_message}])

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

        # [AUDIT-S16] 非原子扣除：先用户获取历史，后调用 API，再扣费（竞态窗口大）
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
            if history_length > _MAX_HISTORY_MSGS:
                histories[history_key] = histories[history_key][:-_MAX_HISTORY_MSGS]
            if len(histories) > _MAX_HISTORIES:
                oldest_keys = sorted(histories.keys())[:len(histories)-_MAX_HISTORIES]
                for k in oldest_keys:
                    histories.pop(k, None)
            total_msgs = sum(len(v) for v in histories.values())
            if total_msgs > 10000:
                for k in list(histories.keys())[:50]:
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


@chat_bp.route("/api/history/<agent_id>", methods=["DELETE"])
@login_required
def clear_history(agent_id):
    history_key = f"{current_user.id}_{agent_id}"
    histories.pop(history_key, None)
    return jsonify({"status": "ok"})
