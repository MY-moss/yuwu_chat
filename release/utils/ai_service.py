# ============================================================
# 文件: utils/ai_service.py | 职责: 智能体管理、AI调用、用量计算、API配置
# ============================================================
import os
import re
import secrets
import logging
import requests
from flask_login import current_user
from models import db, Agent, UserModelConfig, ModelConfig, ApiConfig
from state import _agents_lock
from utils.security import decrypt_value, sanitize_log, is_safe_url

logger = logging.getLogger(__name__)


def load_agents():
    try:
        agents = Agent.query.all()
        return [a.to_dict() for a in agents]
    except Exception as e:
        logger.error(f"load_agents failed: {e}")
        return []


def save_agents(agents_list):
    with _agents_lock:
        try:
            Agent.query.delete()
            for a_data in agents_list:
                db.session.add(Agent.from_dict(a_data))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"save_agents failed: {e}")


def get_agent(agent_id):
    agent = Agent.query.get(agent_id)
    return agent.to_dict() if agent else None


def mock_reply(message, agent):
    replies = agent.get("mock_replies", {})
    default = agent.get("mock_default", "嗯，我在听，你继续说。")
    for kw, resp in replies.items():
        if kw in message:
            return f"【AI暂未配置】{resp}"
    return f"【AI暂未配置】{default}"


def get_model_price(model_id):
    user_model = UserModelConfig.query.filter_by(user_id=current_user.id, model_id=model_id).first()
    if user_model:
        return 0
    model = ModelConfig.query.filter_by(model_id=model_id, enabled=True).first()
    if model:
        return model.credits_per_1k
    return 1


def deduct_credits(user, amount, max_retries=3):
    """Deduct credits with optimistic locking."""
    for attempt in range(max_retries):
        result = db.session.execute(
            db.text(
                "UPDATE user SET credits = credits - :amt "
                "WHERE id = :uid AND credits >= :amt"
            ),
            {"amt": amount, "uid": user.id}
        )
        db.session.commit()
        if result.rowcount > 0:
            db.session.refresh(user)
            return True
        db.session.refresh(user)
        if user.credits < amount:
            return False
    return False


def using_personal_api():
    return bool(current_user.personal_api_base and current_user.personal_api_key)


def parse_usage(resp_json):
    try:
        usage = resp_json.get("usage", {})
        return usage.get("total_tokens", 0), usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    except Exception as e:
        logger.error(f"parse_usage failed: {e}")
        return 0, 0, 0


def estimate_tokens(text):
    if not text:
        return 0
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return chinese_chars + (other_chars // 4) * 3 + (other_chars % 4 > 0) * 1


def calc_token_cost(tokens, credits_per_1k):
    if credits_per_1k <= 0:
        return 0
    return max(1, (tokens * credits_per_1k + 999) // 1000)


def get_api_config(key_name, default=""):
    cfg = ApiConfig.query.filter_by(key_name=key_name).first()
    if cfg:
        return cfg.value
    return default


def get_effective_api(model_id=None, user=None):
    """返回 (api_key, api_url) — 优先用户模型 API → 系统模型 API → 用户个人 API → 全局配置 → .env"""
    if user is None:
        try:
            if current_user and current_user.is_authenticated:
                user = current_user
        except Exception:
            pass
    if model_id and user:
        user_model = UserModelConfig.query.filter_by(user_id=user.id, model_id=model_id).first()
        if user_model and user_model.api_base and user_model.api_key:
            return decrypt_value(user_model.api_key), user_model.api_base
    if model_id:
        model = ModelConfig.query.filter_by(model_id=model_id).first()
        if model and model.api_base and model.api_key:
            return decrypt_value(model.api_key), model.api_base
    if user and user.personal_api_base and user.personal_api_key:
        return decrypt_value(user.personal_api_key), user.personal_api_base
    key = get_api_config("API_KEY", os.getenv("AI_API_KEY", ""))
    url = get_api_config("API_URL", os.getenv("AI_API_URL", ""))
    return decrypt_value(key) if key else key, url


def call_ai(messages, model="mimo-v2.5-free", temperature=0.85, max_tokens=1200):
    try:
        api_key, api_url = get_effective_api(model)
        if not api_key:
            return None, {}, 0
        if not api_url:
            logger.error("call_ai API URL is empty")
            return None, {}, 0
        safe, reason = is_safe_url(api_url)
        if not safe:
            logger.error(sanitize_log(f"call_ai API URL unsafe: {reason}"))
            return None, {}, 0
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        with requests.post(api_url, headers=headers, json=body, timeout=(10, 120), allow_redirects=False) as resp:
            if resp.status_code != 200:
                logger.error(sanitize_log(f"call_ai API failed: {resp.status_code}"))
                raise Exception(f"API调用失败: HTTP {resp.status_code}")
            data = resp.json()
            full = data["choices"][0]["message"]["content"]
            total_tokens, _, _ = parse_usage(data)
            story, sections = parse_rpg_reply(full)
            if "判定" in sections:
                judgment_text = sections["判定"]
                judge_result = _resolve_judgment(judgment_text, sections)
                if judge_result:
                    story = (story + "\n" + judge_result) if story else judge_result
                    sections.pop("判定", None)
            return story, sections, total_tokens
    # [AUDIT-N46] 所有异常统一返回 None,{},0 — 改进日志记录以区分错误类型
    except Exception as e:
        logger.error(f"call_ai failed: {type(e).__name__}: {e}")
        return None, {}, 0


def parse_rpg_reply(text):
    text = text.strip()
    marker_re = r'【([^】]+)】'
    matches = list(re.finditer(marker_re, text))
    if not matches:
        return text, {}

    story = text[:matches[0].start()].strip()
    sections = {}
    for i, m in enumerate(matches):
        key = m.group(1).strip()
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        val = text[start:end].strip().rstrip(',')

        if re.match(r'^\d+$', key):
            story += f"\n【{key}】{val}"
        else:
            sections[key] = val
    return story.strip(), sections


def roll_d20(modifier=0):
    """Roll a d20 with modifier, return (roll, total)"""
    roll = secrets.randbelow(20) + 1
    total = roll + modifier
    return roll, total


def _resolve_judgment(judgment_text, sections=None):
    """Parse a 【判定】 section from AI output, roll dice server-side, return formatted result string."""
    text = judgment_text.strip()

    JUDGE_ATTRS = r'(力量|敏捷|智力|魅力|体质|感知|意志|幸运|洞察|潜行|说服|威吓|表演|巧手|运动|察觉|调查|生存|自然|宗教|历史|医疗|洞悉|欺瞒|威逼|手上功夫)'
    attr_match = re.search(JUDGE_ATTRS, text)

    dc_match = re.search(r'难度[：:]\s*(\d+)', text)
    desc_match = re.search(r'说明[：:](.*?)$', text, re.DOTALL)

    if not attr_match and not dc_match:
        return None

    attr_name = attr_match.group(1) if attr_match else "通用"
    dc = int(dc_match.group(1)) if dc_match else 15
    desc = desc_match.group(1).strip() if desc_match else ""

    attr_value = None
    if sections and attr_name != "通用":
        for key in ['属性', '状态', '技能', '能力']:
            val = sections.get(key, "")
            pattern = re.compile(re.escape(attr_name) + r'[：:]\s*(\d+)', re.IGNORECASE)
            m = pattern.search(val)
            if m:
                attr_value = int(m.group(1))
                break

    if attr_value is not None:
        modifier = max(-4, min(5, attr_value - 5))
    else:
        modifier = 0

    roll, total = roll_d20(modifier)
    natural_20 = (roll == 20)
    natural_1 = (roll == 1)
    success = total >= dc or natural_20

    if natural_20:
        result_label = "🎉 **大成功！**"
        impact = "天时地利人和齐聚，你的行动获得了超乎预期的完美效果！"
    elif natural_1:
        result_label = "💥 **大失败！**"
        impact = "命运开了个残酷的玩笑，事情朝着最坏的方向发展了……"
    elif success:
        result_label = "✅ **检定成功！**"
        impact = "你的行动取得了理想的效果，局势正向有利的方向发展。"
    else:
        result_label = "❌ **检定失败！**"
        impact = "事情并没有按照预想的方向发展，你需要重新调整策略……"

    desc_line = "**检定说明**: " + desc + "\n" if desc else ""
    nat_line = "(自然20！)" if natural_20 else "(自然1……)" if natural_1 else ""
    nat_line_full = nat_line + "\n" if nat_line else "\n"
    attr_val_str = " (" + str(attr_value) + ")" if attr_value is not None else ""

    result = (
        "\n\n━━━━━ 【🎲 技能检定】 ━━━━━\n"
        "**检定类型**: " + attr_name + "\n"
        "**难度等级**: DC " + str(dc) + "\n"
        + desc_line
        + "━━━━━━━━━━━━━━━━━━━━━\n"
        + "🎯 **d20 掷出**: **" + str(roll) + "**\n"
        + nat_line_full
        + "➕ **属性修正**: " + attr_name + attr_val_str + " = " + ("%+d" % modifier) + "\n"
        + "📊 **最终结果**: " + str(roll) + " " + ("%+d" % modifier) + " = **" + str(total) + "** (目标: **" + str(dc) + "**)\n"
        + "━━━━━━━━━━━━━━━━━━━━━\n"
        + result_label + "\n"
        + impact + "\n"
        + "━━━━━━━━━━━━━━━━━━━━━"
    )

    return result


def _parse_relationships(rels_str):
    rmap = {}
    if rels_str:
        for part in rels_str.replace("【", "").replace("】", "").split():
            if ":" in part:
                k, v = part.split(":", 1)
                rmap[k.strip()] = v.strip()
    if not rmap and rels_str:
        for line in rels_str.replace("\r", "").split("\n"):
            line = line.strip()
            if ":" in line and not line.startswith("http"):
                k, v = line.split(":", 1)
                rmap[k.strip()] = v.strip()
    return rmap
