from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from src.extensions import db

class User(db.Model):
    """用户模型"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))
    status = db.Column(db.Boolean, default=True)  # True表示启用，False表示禁用
    avatar = db.Column(db.String(255))  # 头像路径
    created_at = db.Column(db.DateTime, default=db.func.now())
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())
    last_login = db.Column(db.DateTime)

    # 关联关系
    role = db.relationship('Role', backref=db.backref('users', lazy=True))
    favorite_cities = db.relationship('City', secondary='user_favorite_cities',
                                    backref=db.backref('favorited_by', lazy='dynamic'))

    def __init__(self, username, email, password=None, role_id=None, avatar=None, status=True):
        self.username = username
        self.email = email
        self.role_id = role_id
        self.avatar = avatar
        self.status = status
        if password:
            self.set_password(password)

    def set_password(self, password):
        """设置密码"""
        self.password = generate_password_hash(password)

    def check_password(self, password):
        """验证密码"""
        return check_password_hash(self.password, password)

    def is_admin(self):
        """判断是否是管理员"""
        return self.role and self.role.name == '超级管理员'

    def has_permission(self, permission_name):
        """检查用户是否拥有特定权限"""
        if not self.role:
            return False
        return any(p.name == permission_name for p in self.role.permissions)

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role.name if self.role else None,
            'status': self.status,
            'avatar': self.avatar,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        }

    def __repr__(self):
        return f'<User {self.username}>'

class UserProfile(db.Model):
    __tablename__ = 'user_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    nickname = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    location = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'nickname': self.nickname,
            'phone': self.phone,
            'location': self.location
        }

# 用户收藏城市关联表
user_favorite_cities = db.Table('user_favorite_cities',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('city_id', db.Integer, db.ForeignKey('cities.id'), primary_key=True),
    db.Column('created_at', db.DateTime, default=datetime.utcnow)
)