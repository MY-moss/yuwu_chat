# ============================================================
# 文件: blueprints/feedback.py | 职责: 用户反馈系统（提交/列表/统计/管理）
# ============================================================
import collections
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from models import db, Feedback

feedback_bp = Blueprint('feedback', __name__)


@feedback_bp.route("/feedback")
@login_required
def feedback_page():
    return render_template("feedback.html")


# [AUDIT-S14] 提交反馈无速率限制
@feedback_bp.route("/api/feedback", methods=["POST"])
@login_required
def submit_feedback():
    data = request.json
    title = (data.get("title", "") or "").strip()
    content = (data.get("content", "") or "").strip()
    if not title or not content:
        return jsonify({"error": "标题和内容不能为空"}), 400
    if len(title) > 200:
        return jsonify({"error": "标题不能超过200字"}), 400
    if len(content) > 5000:
        return jsonify({"error": "内容不能超过5000字"}), 400

    category = data.get("category", "suggestion")
    if category not in ["bug", "feature", "suggestion", "praise", "other"]:
        return jsonify({"error": "无效的分类"}), 400

    try:
        rating = int(data.get("rating", 3))
        if not (1 <= rating <= 5):
            return jsonify({"error": "评分必须在1-5之间"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "评分必须为整数"}), 400

    fb = Feedback(
        user_id=current_user.id,
        username=current_user.username,
        category=category,
        rating=rating,
        title=title,
        content=content,
        status="open"
    )
    db.session.add(fb)
    db.session.commit()
    return jsonify({"message": "反馈已提交，感谢您的宝贵意见！", "feedback": fb.to_dict()})


@feedback_bp.route("/api/feedback", methods=["GET"])
@login_required
def list_feedback():
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = max(1, min(100, request.args.get("per_page", 20, type=int) or 20))
    category = request.args.get("category", "")
    status = request.args.get("status", "")
    search = request.args.get("search", "")

    query = Feedback.query
    if current_user.role != "admin":
        query = query.filter_by(user_id=current_user.id)
    if category:
        query = query.filter_by(category=category)
    if status:
        query = query.filter_by(status=status)
    if search:
        escaped_search = search.replace("%", "\\%").replace("_", "\\_")
        search_pattern = f'%{escaped_search}%'
        query = query.filter(
            (Feedback.title.ilike(search_pattern, escape='\\')) |
            (Feedback.content.ilike(search_pattern, escape='\\')) |
            (Feedback.username.ilike(search_pattern, escape='\\'))
        )

    total = query.count()
    items = query.order_by(Feedback.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        "items": [fb.to_dict() for fb in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page)
    })


@feedback_bp.route("/api/feedback/stats", methods=["GET"])
@login_required
def feedback_stats():
    if current_user.role != "admin":
        return jsonify({"error": "无权限"}), 403

    all_fb = Feedback.query.all()
    stats = {"total": len(all_fb), "open": 0, "in_progress": 0, "resolved": 0, "closed": 0,
             "bug": 0, "feature": 0, "suggestion": 0, "praise": 0, "other": 0}
    ratings = []
    for fb in all_fb:
        stats[fb.status] = stats.get(fb.status, 0) + 1
        stats[fb.category] = stats.get(fb.category, 0) + 1
        ratings.append(fb.rating)
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0
    stats["avg_rating"] = avg_rating
    counter = collections.Counter(ratings)
    stats["rating_dist"] = {str(i): counter.get(i, 0) for i in range(1, 6)}
    return jsonify(stats)


@feedback_bp.route("/api/feedback/<int:feedback_id>", methods=["GET"])
@login_required
def get_feedback(feedback_id):
    # [AUDIT-S10] get_or_404 返回 HTML 404 而非 JSON
    fb = Feedback.query.get_or_404(feedback_id)
    if current_user.role != "admin" and fb.user_id != current_user.id:
        return jsonify({"error": "无权限"}), 403
    return jsonify(fb.to_dict())


@feedback_bp.route("/api/feedback/<int:feedback_id>", methods=["PUT"])
@login_required
def update_feedback(feedback_id):
    # [AUDIT-S10] get_or_404 返回 HTML 404 而非 JSON
    fb = Feedback.query.get_or_404(feedback_id)
    if current_user.role != "admin":
        return jsonify({"error": "无权限"}), 403

    data = request.json
    new_status = data.get("status")
    admin_note = data.get("admin_note")

    valid_statuses = ["open", "in_progress", "resolved", "closed"]
    if new_status and new_status in valid_statuses:
        fb.status = new_status
    if admin_note is not None:
        fb.admin_note = admin_note

    db.session.commit()
    return jsonify({"message": "更新成功", "feedback": fb.to_dict()})


@feedback_bp.route("/api/feedback/<int:feedback_id>", methods=["DELETE"])
@login_required
def delete_feedback(feedback_id):
    fb = Feedback.query.get_or_404(feedback_id)
    if current_user.role != "admin" and fb.user_id != current_user.id:
        return jsonify({"error": "无权限"}), 403
    db.session.delete(fb)
    db.session.commit()
    return jsonify({"message": "已删除"})
