# ============================================================
# 文件: models.py | 职责: SQLAlchemy 实例与 12 个数据模型
# ============================================================
import json
import hashlib
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='user')
    credits = db.Column(db.Integer, default=100)
    total_tokens = db.Column(db.Integer, default=0)
    personal_api_base = db.Column(db.String(500), nullable=True)
    personal_api_key = db.Column(db.String(500), nullable=True)  # 加密存储（encrypt_value 写入，decrypt_value 读取）
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_active = db.Column(db.DateTime, default=datetime.now, index=True)
    token_version = db.Column(db.Integer, default=1)
    password_reset_required = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'credits': self.credits,
            'total_tokens': self.total_tokens,
            'has_personal_api': bool(self.personal_api_base and self.personal_api_key),
            'created_at': self.created_at.isoformat(),
            'last_active': self.last_active.isoformat() if self.last_active else None,
            'password_reset_required': self.password_reset_required or False
        }


class ModelConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    model_id = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    label = db.Column(db.String(100), nullable=False)
    credits_per_1k = db.Column(db.Integer, default=1)
    enabled = db.Column(db.Boolean, default=True)
    api_base = db.Column(db.String(500), nullable=True)
    api_key = db.Column(db.String(500), nullable=True)  # 加密存储（encrypt_value 写入，decrypt_value 读取）
    priority = db.Column(db.Integer, default=100)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'model_id': self.model_id,
            'name': self.name,
            'label': self.label,
            'credits_per_1k': self.credits_per_1k,
            'enabled': self.enabled,
            'priority': self.priority,
            'created_at': self.created_at.isoformat(),
            'source': 'system'
        }

    def to_dict_admin(self):
        data = self.to_dict()
        data['api_base'] = self.api_base
        data['has_api_key'] = bool(self.api_key)
        return data


class UserModelConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    model_id = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    label = db.Column(db.String(100), nullable=False)
    api_base = db.Column(db.String(500), nullable=True)
    api_key = db.Column(db.String(500), nullable=True)  # 加密存储（encrypt_value 写入，decrypt_value 读取）
    priority = db.Column(db.Integer, default=100)
    created_at = db.Column(db.DateTime, default=datetime.now)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'model_id', name='uq_user_model'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'model_id': self.model_id,
            'name': self.name,
            'label': self.label,
            'credits_per_1k': 0,
            'enabled': True,
            'priority': self.priority,
            'created_at': self.created_at.isoformat(),
            'source': 'personal',
            'api_base': self.api_base,
            'has_api_key': bool(self.api_key)
        }


class ApiConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key_name = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(500), nullable=False)
    priority = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {'key_name': self.key_name, 'has_value': bool(self.value), 'priority': self.priority}


class CreditKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False)  # sha256 哈希存储
    key_preview = db.Column(db.String(12), nullable=False, default='')  # 末4位用于显示
    credits = db.Column(db.Integer, nullable=False)
    used = db.Column(db.Boolean, default=False)
    used_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    @staticmethod
    def hash_key(plaintext):
        """返回 (sha256_hexdigest, preview)"""
        return hashlib.sha256(plaintext.encode()).hexdigest(), plaintext[:12]

    def to_dict(self):
        return {
            'id': self.id,
            'key_preview': self.key_preview,
            'credits': self.credits,
            'used': self.used,
            'used_by': self.used_by,
            'created_at': self.created_at.isoformat()
        }


class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
    username = db.Column(db.String(80), nullable=False)  # [AUDIT-Q08] 非规范化存储，用户改名后数据不一致
    category = db.Column(db.String(32), nullable=False, default='suggestion')  # [AUDIT-P04] 无索引
    rating = db.Column(db.Integer, nullable=False, default=3)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='open')  # [AUDIT-P04] 无索引
    admin_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.username,
            'category': self.category,
            'rating': self.rating,
            'title': self.title,
            'content': self.content,
            'status': self.status,
            'admin_note': self.admin_note or '',
            'created_at': self.created_at.isoformat()
        }


class Agent(db.Model):
    __tablename__ = 'agent'
    id = db.Column(db.String(100), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    avatar = db.Column(db.String(500), nullable=False, default='🤖')
    model = db.Column(db.String(100), nullable=False)
    system_prompt = db.Column(db.Text, nullable=False)
    temperature = db.Column(db.Float, default=0.8)
    max_tokens = db.Column(db.Integer, default=1024)
    greeting = db.Column(db.String(500), nullable=True)
    mock_replies = db.Column(db.Text, nullable=True)
    mock_default = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        d = {
            'id': self.id, 'name': self.name, 'avatar': self.avatar,
            'model': self.model, 'system_prompt': self.system_prompt,
            'temperature': self.temperature, 'max_tokens': self.max_tokens
        }
        if self.greeting:
            d['greeting'] = self.greeting
        if self.mock_replies:
            try: d['mock_replies'] = json.loads(self.mock_replies)
            except Exception: d['mock_replies'] = {}
        if self.mock_default:
            d['mock_default'] = self.mock_default
        return d

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data.get('id'), name=data.get('name', ''),
            avatar=data.get('avatar', '🤖'), model=data.get('model', ''),
            system_prompt=data.get('system_prompt', ''),
            temperature=data.get('temperature', 0.8),
            max_tokens=data.get('max_tokens', 1024),
            greeting=data.get('greeting'),
            mock_replies=json.dumps(data.get('mock_replies', {}), ensure_ascii=False) if data.get('mock_replies') else None,
            mock_default=data.get('mock_default')
        )


class WorldBook(db.Model):
    __tablename__ = 'world_book'
    id = db.Column(db.String(100), primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    emoji = db.Column(db.String(20), default='📖')
    genre = db.Column(db.String(100), default='')
    desc = db.Column(db.Text, default='')
    system_prompt = db.Column(db.Text, default='')
    temperature = db.Column(db.Float, default=0.85)
    max_tokens = db.Column(db.Integer, default=700)
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'emoji': self.emoji,
            'genre': self.genre, 'desc': self.desc,
            'system_prompt': self.system_prompt,
            'temperature': self.temperature, 'max_tokens': self.max_tokens,
            'order': self.order
        }


class WorldRating(db.Model):
    __tablename__ = 'world_rating'
    id = db.Column(db.Integer, primary_key=True)
    world_id = db.Column(db.String(100), db.ForeignKey('world_book.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    username = db.Column(db.String(80), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    review = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        db.UniqueConstraint('world_id', 'user_id', name='uq_world_user_rating'),
    )

    def to_dict(self):
        return {
            'user_id': self.user_id, 'username': self.username,
            'rating': self.rating, 'review': self.review,
            'created_at': self.created_at.isoformat()
        }


class WorldSubmission(db.Model):
    __tablename__ = 'world_submission'
    id = db.Column(db.String(100), primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    emoji = db.Column(db.String(20), default='📖')
    genre = db.Column(db.String(100), default='')
    desc = db.Column(db.Text, default='')
    system_prompt = db.Column(db.Text, default='')
    temperature = db.Column(db.Float, default=0.85)
    max_tokens = db.Column(db.Integer, default=700)
    submitted_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    submitter = db.Column(db.String(80), default='')
    status = db.Column(db.String(20), default='pending', index=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'emoji': self.emoji,
            'genre': self.genre, 'desc': self.desc,
            'system_prompt': self.system_prompt,
            'temperature': self.temperature, 'max_tokens': self.max_tokens,
            'submitted_by': self.submitted_by, 'submitter': self.submitter,
            'status': self.status, 'created_at': self.created_at.isoformat()
        }


class UsageLog(db.Model):
    __tablename__ = 'usage_log'
    __table_args__ = (
        db.Index('idx_usage_user_created', 'user_id', 'created_at'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    username = db.Column(db.String(80), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    tokens = db.Column(db.Integer, default=0)
    cost = db.Column(db.Float, default=0.0)
    endpoint = db.Column(db.String(50), default='chat')
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)

    def to_dict(self):
        return {
            'id': self.id, 'user_id': self.user_id,
            'username': self.username, 'model': self.model,
            'tokens': self.tokens, 'cost': self.cost,
            'endpoint': self.endpoint,
            'time': self.created_at.isoformat()
        }


class RateLimitEntry(db.Model):
    __tablename__ = 'rate_limit_entry'
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(32), nullable=False, index=True)
    key = db.Column(db.String(128), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)
