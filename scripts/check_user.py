import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'backend'))

from app import app, db, User
with app.app_context():
    user = User.query.filter_by(username='admin').first()
    if user:
        print('User:', user.username)
        print('Password hash:', user.password_hash)
        print('Role:', user.role)
        print('Password 123456 valid:', user.check_password('123456'))
    else:
        print('User not found')
