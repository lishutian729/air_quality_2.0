from datetime import datetime
from extensions import db

class AdminLog(db.Model):
    """管理员操作日志"""
    __tablename__ = 'admin_logs'

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(255), nullable=False)  # 操作描述
    ip_address = db.Column(db.String(45))  # IP地址
    user_agent = db.Column(db.String(255))  # 浏览器信息
    created_at = db.Column(db.DateTime, default=datetime.now)

    # 关联管理员用户
    admin = db.relationship('User', backref=db.backref('admin_logs', lazy='dynamic'))

    def __init__(self, admin_id, action, ip_address=None, user_agent=None):
        self.admin_id = admin_id
        self.action = action
        self.ip_address = ip_address
        self.user_agent = user_agent

    def __repr__(self):
        return f'<AdminLog {self.action}>' 