# ============================================================
# 文件: utils/security.py | 职责: 输入校验、URL安全、加密、密码、权限装饰器
# ============================================================
import re
import os
import socket
import logging
import base64
import ipaddress
import functools
from urllib.parse import urlparse
from flask import current_app, jsonify
from flask_login import current_user
from models import db

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

logger = logging.getLogger(__name__)

_API_KEY_PATTERN = re.compile(r'(sk-[a-zA-Z0-9]{20,}|api[_-]?key["\']?\s*[:=]\s*["\']?[a-zA-Z0-9]{16,})', re.IGNORECASE)
_UNICODE_CONTROL_RE = re.compile(r'[\u0000-\u0008\u000b\u000c\u000e-\u001f\u200b-\u200f\u2028-\u202f\u2060-\u206f\ufff0-\uffff]')
_PATH_TRAVERSAL_RE = re.compile(r'[\\/]\.\.|[\\/]\.\.[\\/]|~|\.exe|\.bat|\.sh')
_COMMON_PASSWORDS = {'12345678', 'password', 'qwerty123', 'admin123', 'letmein', 'welcome1', 'monkey123', 'dragon123', 'abc12345', 'iloveyou'}


def sanitize_input(text):
    if isinstance(text, str):
        return _UNICODE_CONTROL_RE.sub('', text.strip())
    return text


def validate_id_param(id_value):
    if not id_value or not isinstance(id_value, str):
        return False
    if len(id_value) > 200:
        return False
    if _PATH_TRAVERSAL_RE.search(id_value):
        return False
    return True


def sanitize_log(msg):
    if isinstance(msg, str):
        return _API_KEY_PATTERN.sub('***API_KEY_REDACTED***', msg)
    return msg


def is_safe_url(url):
    try:
        p = urlparse(url)
        if p.scheme not in ('http', 'https'):
            return False, '仅支持 http/https 协议'
        if '@' in p.netloc:
            return False, 'URL包含认证信息，不允许'
        hostname = p.hostname
        if not hostname:
            return False, '无效的主机名'
        if hostname in ('localhost', '127.0.0.1', '0.0.0.0', '::1', 'localhost.localdomain'):
            return False, '不允许访问本地地址'
        try:
            addr = ipaddress.ip_address(hostname)
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
                return False, '不允许访问私有或本地地址'
        except ValueError:
            try:
                resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
                for _, _, _, _, sockaddr in resolved:
                    ip_str = sockaddr[0]
                    try:
                        addr = ipaddress.ip_address(ip_str)
                        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
                            return False, '域名解析到私有或本地地址'
                    except ValueError:
                        pass
            except socket.gaierror:
                pass
        return True, ''
    except Exception:
        return False, 'URL 解析失败'


def get_fernet():
    key_material = current_app.secret_key.encode() if isinstance(current_app.secret_key, str) else current_app.secret_key
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b'tavern-encrypt-v1', iterations=100000)
    key = base64.urlsafe_b64encode(kdf.derive(key_material))
    return Fernet(key)


def encrypt_value(plaintext):
    if not plaintext:
        return None
    if not HAS_CRYPTO:
        logger.error("encrypt_value failed: cryptography library not installed")
        raise RuntimeError("加密依赖未安装，请安装 cryptography 库")
    try:
        key_material = current_app.secret_key.encode() if isinstance(current_app.secret_key, str) else current_app.secret_key
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
        key = base64.urlsafe_b64encode(kdf.derive(key_material))
        f = Fernet(key)
        ciphertext = f.encrypt(plaintext.encode())
        return base64.urlsafe_b64encode(salt + ciphertext).decode()
    except Exception as e:
        logger.error(f"encrypt_value failed: {e}")
        raise RuntimeError(f"加密失败: {e}")


def decrypt_value(ciphertext):
    if not ciphertext:
        return None
    if not HAS_CRYPTO:
        logger.error("decrypt_value failed: cryptography library not installed")
        raise RuntimeError("加密依赖未安装，请安装 cryptography 库")
    try:
        decoded = base64.urlsafe_b64decode(ciphertext)
        if len(decoded) >= 16:
            salt = decoded[:16]
            token = decoded[16:]
            key_material = current_app.secret_key.encode() if isinstance(current_app.secret_key, str) else current_app.secret_key
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
            key = base64.urlsafe_b64encode(kdf.derive(key_material))
            f = Fernet(key)
            return f.decrypt(token).decode()
    except Exception:
        pass
    try:
        f = get_fernet()
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        logger.error(f"decrypt_value failed: invalid ciphertext")
        raise RuntimeError("解密失败：无效的密文")


def safe_commit():
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logger.error(f"Database commit failed: {e}")
        return False


def validate_password(password):
    if len(password) < 8:
        return False, "密码长度至少8位"
    if not re.search(r'[a-z]', password):
        return False, "密码必须包含至少一个小写字母"
    if not re.search(r'[A-Z]', password):
        return False, "密码必须包含至少一个大写字母"
    if not re.search(r'[0-9]', password):
        return False, "密码必须包含至少一个数字"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\;/\']', password):
        return False, "密码必须包含至少一个特殊字符"
    if password.lower() in _COMMON_PASSWORDS:
        return False, "密码过于常见，请使用更复杂的密码"
    return True, ""


def admin_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            return jsonify({"error": "管理员权限不足"}), 403
        return f(*args, **kwargs)
    return decorated_function
