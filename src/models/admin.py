from datetime import datetime
from src.extensions import db

# 角色-权限关联表
role_permissions = db.Table('role_permissions',
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True),
    db.Column('permission_id', db.Integer, db.ForeignKey('permissions.id'), primary_key=True),
    db.Column('created_at', db.DateTime, default=datetime.now)
)

class Role(db.Model):
    """角色模型"""
    __tablename__ = 'roles'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # 角色名称
    description = db.Column(db.String(255))  # 角色描述
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # 角色-权限多对多关系
    permissions = db.relationship('Permission', secondary=role_permissions,
                                backref=db.backref('roles', lazy='dynamic'))

    def __init__(self, name, description=None):
        self.name = name
        self.description = description

    def __repr__(self):
        return f'<Role {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'permissions': [p.to_dict() for p in self.permissions],
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        }

class Permission(db.Model):
    """权限模型"""
    __tablename__ = 'permissions'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # 权限名称
    description = db.Column(db.String(255))  # 权限描述
    module = db.Column(db.String(50))  # 所属模块
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def __init__(self, name, description=None, module=None):
        self.name = name
        self.description = description
        self.module = module

    def __repr__(self):
        return f'<Permission {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'module': self.module,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        }

class AdminLog(db.Model):
    """管理员操作日志"""
    __tablename__ = 'admin_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    module = db.Column(db.String(50), nullable=False)  # 操作模块
    action = db.Column(db.String(50), nullable=False)  # 操作类型
    description = db.Column(db.String(255))  # 操作描述
    ip_address = db.Column(db.String(50))  # IP地址
    created_at = db.Column(db.DateTime, default=db.func.now())
    
    # 关联关系
    user = db.relationship('User', backref=db.backref('admin_logs', lazy=True))
    
    def __init__(self, user_id, module, action, description, ip_address):
        self.user_id = user_id
        self.module = module
        self.action = action
        self.description = description
        self.ip_address = ip_address
    
    def to_dict(self):
        return {
            'id': self.id,
            'user': self.user.username,
            'module': self.module,
            'action': self.action,
            'description': self.description,
            'ip_address': self.ip_address,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }

class LoginLog(db.Model):
    __tablename__ = 'login_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(200))  # 浏览器信息
    status = db.Column(db.Boolean, default=True)  # True: 成功, False: 失败
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # 关联用户
    user = db.relationship('User', backref='login_logs')
    
    def to_dict(self):
        return {
            'id': self.id,
            'user': self.user.username,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'status': '成功' if self.status else '失败',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        } 