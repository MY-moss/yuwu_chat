import os
import sys
import secrets
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'backend'))

from app import app, db, User

with app.app_context():
    db.create_all()
    
    new_pwd = secrets.token_urlsafe(12)
    
    admin = User.query.filter_by(username='admin').first()
    if admin:
        admin.set_password(new_pwd)
        db.session.commit()
        print(f"[SECURITY] 管理员密码已重置: {new_pwd}")
    else:
        admin = User(username='admin', role='admin')
        admin.set_password(new_pwd)
        db.session.add(admin)
        db.session.commit()
        print(f"[SECURITY] 管理员账户已创建，密码: {new_pwd}")
    
    users = User.query.filter(User.username != 'admin').all()
    for user in users:
        db.session.delete(user)
    db.session.commit()
    print(f"已删除 {len(users)} 个普通用户")

print("数据库重置完成")
