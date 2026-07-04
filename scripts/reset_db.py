import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'backend'))

from app import app, db, User

with app.app_context():
    db.create_all()
    
    admin = User.query.filter_by(username='admin').first()
    if admin:
        admin.set_password('123456')
        db.session.commit()
        print("管理员密码已重置为 123456")
    else:
        admin = User(username='admin', role='admin')
        admin.set_password('123456')
        db.session.add(admin)
        db.session.commit()
        print("管理员账户已创建，密码为 123456")
    
    users = User.query.filter(User.username != 'admin').all()
    for user in users:
        db.session.delete(user)
    db.session.commit()
    print(f"已删除 {len(users)} 个普通用户")

print("数据库重置完成")
