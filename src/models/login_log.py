from datetime import datetime
from extensions import db

class LoginLog(db.Model):
    """用户登录日志"""
    __tablename__ = 'login_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ip_address = db.Column(db.String(45))  # IP地址
    user_agent = db.Column(db.String(255))  # 浏览器信息
    status = db.Column(db.Boolean, default=True)  # 登录状态：True成功，False失败
    created_at = db.Column(db.DateTime, default=datetime.now)

    # 关联用户
    user = db.relationship('User', backref=db.backref('login_logs', lazy='dynamic'))

    def __init__(self, user_id, ip_address=None, user_agent=None, status=True):
        self.user_id = user_id
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.status = status

    def __repr__(self):
        return f'<LoginLog {self.user_id} {self.status}>' 