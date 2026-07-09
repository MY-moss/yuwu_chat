# ============================================================
# 文件: blueprints/auth.py | 职责: 用户认证、密码、个人API配置、用户模型CRUD
# ============================================================
import re
import secrets
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, ModelConfig, UserModelConfig
from config import _INITIAL_CREDITS
from utils.security import (sanitize_input, validate_password, is_safe_url,
                            encrypt_value, sanitize_log, admin_required)
from utils.json_io import check_rate_limit

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    if len(username) < 2 or len(username) > 32:
        return jsonify({"error": "用户名长度必须在2-32位之间"}), 400
    if not re.match(r'^[a-zA-Z0-9\u4e00-\u9fa5_]+$', username):
        return jsonify({"error": "用户名只能包含字母、数字、中文和下划线"}), 400
    if len(password) > 128:
        return jsonify({"error": "密码长度不能超过128位"}), 400
    valid_pwd, pwd_msg = validate_password(password)
    if not valid_pwd:
        return jsonify({"error": pwd_msg}), 400

    client_ip = request.remote_addr
    if not check_rate_limit('register', client_ip, max_attempts=3, window=3600):
        return jsonify({"error": "注册过于频繁，请稍后再试"}), 429

    user = User(username=username, credits=_INITIAL_CREDITS)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        if 'UNIQUE constraint failed' in str(e) or 'duplicate key' in str(e).lower():
            return jsonify({"error": "用户名已存在"}), 400
        logger.error(f"Registration failed for username: {username}")
        return jsonify({"error": "注册失败，请重试"}), 500

    login_user(user)
    _cycle_session(session)
    session.permanent = True
    session['_user_token_version'] = user.token_version or 1
    session['_csrf_token'] = secrets.token_hex(16)
    return jsonify({"message": "注册成功", "user": user.to_dict(), "csrf_token": session['_csrf_token']}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.json
    username = sanitize_input(data.get("username", ""))
    password = data.get("password", "").strip()

    client_ip = request.remote_addr

    if not check_rate_limit('login', client_ip, max_attempts=5, window=60):
        return jsonify({"error": "登录尝试过于频繁，请稍后再试"}), 429

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "用户名或密码错误"}), 401

    login_user(user)
    _cycle_session(session)
    session.permanent = True
    session['_user_token_version'] = user.token_version or 1
    session['_csrf_token'] = secrets.token_hex(16)

    return jsonify({"message": "登录成功", "user": user.to_dict(), "password_reset_required": user.password_reset_required or False, "csrf_token": session['_csrf_token']})


def _cycle_session(session):
    old_data = dict(session)
    session.clear()
    for key, value in old_data.items():
        session[key] = value
    session.modified = True


@auth_bp.route("/reset-admin-password", methods=["POST"])
@login_required
@admin_required
def reset_admin_password():
    admin = User.query.filter_by(username='admin').first()
    if admin:
        new_pwd = secrets.token_urlsafe(12)
        admin.set_password(new_pwd)
        admin.password_reset_required = True
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error("Admin password reset failed")
            return jsonify({"error": "密码重置失败"}), 500
        logger.info("Admin password reset completed")
        return jsonify({"message": "管理员密码已重置", "new_password": new_pwd})
    return jsonify({"error": "管理员用户不存在"}), 404


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    session['_csrf_token'] = secrets.token_hex(16)
    return jsonify({"message": "退出成功", "csrf_token": session['_csrf_token']})


# [AUDIT-S13] 修改密码端点无速率限制，可被暴力尝试
@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    client_ip = request.remote_addr
    if not check_rate_limit('change_password', client_ip, max_attempts=5, window=300):
        return jsonify({"error": "操作过于频繁，请5分钟后再试"}), 429
    data = request.json
    old_password = data.get("old_password")
    new_password = data.get("new_password")

    if not old_password or not new_password:
        return jsonify({"error": "请输入原密码和新密码"}), 400

    if len(new_password) > 128:
        return jsonify({"error": "新密码长度不能超过128位"}), 400
    valid_pwd, pwd_msg = validate_password(new_password)
    if not valid_pwd:
        return jsonify({"error": "新" + pwd_msg}), 400

    if not current_user.check_password(old_password):
        return jsonify({"error": "原密码不正确"}), 401

    current_user.set_password(new_password)
    current_user.password_reset_required = False
    current_user.token_version = (current_user.token_version or 1) + 1
    db.session.commit()

    logout_user()
    session['_csrf_token'] = secrets.token_hex(16)

    return jsonify({"message": "密码修改成功，请重新登录", "csrf_token": session['_csrf_token']})


@auth_bp.route("/me")
def get_current_user():
    if current_user.is_authenticated:
        now = datetime.now()
        if not current_user.last_active or (now - current_user.last_active).total_seconds() > 60:
            current_user.last_active = now
            db.session.commit()
        return jsonify(current_user.to_dict())
    return jsonify({"error": "未登录"}), 401


@auth_bp.route("/ping", methods=["POST"])
@login_required
def ping():
    current_user.last_active = datetime.now()
    db.session.commit()
    return jsonify({"status": "ok", "message": "session active"})


@auth_bp.route("/api-config", methods=["GET", "PUT"])
@login_required
def user_api_config():
    if request.method == "GET":
        return jsonify({
            "api_base": current_user.personal_api_base or "",
            "has_personal_api": bool(current_user.personal_api_base and current_user.personal_api_key)
        })
    data = request.json
    if "api_base" in data:
        v = data.get("api_base", "")
        if v:
            safe, msg = is_safe_url(v)
            if not safe:
                return jsonify({"error": "API地址不安全: " + msg}), 400
            current_user.personal_api_base = v.strip()
        else:
            current_user.personal_api_base = None
    if "api_key" in data:
        v = data.get("api_key", "")
        current_user.personal_api_key = encrypt_value(v.strip()) if v else None
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(sanitize_log(f"Save API config failed: {e}"))
        return jsonify({"error": "保存失败"}), 500
    return jsonify({"status": "ok", "has_personal_api": bool(current_user.personal_api_base and current_user.personal_api_key)})


@auth_bp.route("/models", methods=["GET"])
@login_required
def list_user_models():
    models = UserModelConfig.query.filter_by(user_id=current_user.id).order_by(UserModelConfig.priority).all()
    return jsonify([m.to_dict() for m in models])


@auth_bp.route("/models", methods=["POST"])
@login_required
def add_user_model():
    data = request.json
    model_id = data.get("model_id", "").strip()
    name = data.get("name", "").strip()
    label = data.get("label", "").strip()

    if not model_id or not name or not label:
        return jsonify({"error": "模型ID、名称和标签不能为空"}), 400

    existing = UserModelConfig.query.filter_by(user_id=current_user.id, model_id=model_id).first()
    if existing:
        return jsonify({"error": "该模型已存在"}), 400

    model = UserModelConfig(
        user_id=current_user.id,
        model_id=model_id,
        name=name,
        label=label,
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


@auth_bp.route("/models/<model_id>", methods=["PUT"])
@login_required
def update_user_model(model_id):
    model = UserModelConfig.query.filter_by(user_id=current_user.id, model_id=model_id).first()
    if not model:
        return jsonify({"error": "模型不存在"}), 404

    data = request.json
    if "name" in data:
        model.name = data["name"].strip()
    if "label" in data:
        model.label = data["label"].strip()
    if "priority" in data:
        model.priority = data["priority"]
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
        elif not v:
            model.api_key = None

    db.session.commit()
    return jsonify(model.to_dict())


@auth_bp.route("/models/<model_id>", methods=["DELETE"])
@login_required
def delete_user_model(model_id):
    model = UserModelConfig.query.filter_by(user_id=current_user.id, model_id=model_id).first()
    if not model:
        return jsonify({"error": "模型不存在"}), 404

    db.session.delete(model)
    db.session.commit()
    return jsonify({"status": "ok"})
