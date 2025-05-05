from datetime import datetime
from src.extensions import db

class AlertConfig(db.Model):
    """空气质量预警配置"""
    __tablename__ = 'alert_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    city = db.Column(db.String(50), nullable=False)
    blue_threshold = db.Column(db.Integer, default=101)  # 蓝色预警阈值 (AQI > 100)
    yellow_threshold = db.Column(db.Integer, default=151)  # 黄色预警阈值 (AQI > 150)
    orange_threshold = db.Column(db.Integer, default=201)  # 橙色预警阈值 (AQI > 200)
    red_threshold = db.Column(db.Integer, default=301)  # 红色预警阈值 (AQI > 300)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联
    user = db.relationship('User', backref=db.backref('alert_configs', lazy=True))
    
    def get_alert_level(self, aqi):
        """根据AQI值获取预警级别"""
        if aqi >= self.red_threshold:
            return "红色"
        elif aqi >= self.orange_threshold:
            return "橙色"
        elif aqi >= self.yellow_threshold:
            return "黄色"
        elif aqi >= self.blue_threshold:
            return "蓝色"
        else:
            return None
    
    def to_dict(self):
        return {
            'id': self.id,
            'city': self.city,
            'blue_threshold': self.blue_threshold,
            'yellow_threshold': self.yellow_threshold,
            'orange_threshold': self.orange_threshold,
            'red_threshold': self.red_threshold,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        }

class AlertHistory(db.Model):
    """空气质量预警历史记录"""
    __tablename__ = 'alert_histories'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    config_id = db.Column(db.Integer, db.ForeignKey('alert_configs.id'), nullable=False)
    city = db.Column(db.String(50), nullable=False)
    alert_level = db.Column(db.String(20), nullable=False)  # 蓝色、黄色、橙色、红色
    aqi = db.Column(db.Integer, nullable=False)
    pm25 = db.Column(db.Float, nullable=False)
    prediction_time = db.Column(db.DateTime, nullable=False)  # 预测的时间点
    read_status = db.Column(db.Boolean, default=False)  # 是否已读
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # 关联
    user = db.relationship('User', backref=db.backref('alert_histories', lazy=True))
    config = db.relationship('AlertConfig', backref=db.backref('alert_histories', lazy=True))
    
    def to_dict(self):
        return {
            'id': self.id,
            'city': self.city,
            'alert_level': self.alert_level,
            'aqi': self.aqi,
            'pm25': self.pm25,
            'prediction_time': self.prediction_time.strftime('%Y-%m-%d %H:%M:%S'),
            'read_status': self.read_status,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        } 