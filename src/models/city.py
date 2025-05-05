from datetime import datetime
from src.extensions import db

class City(db.Model):
    """城市模型"""
    __tablename__ = 'cities'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # 城市名称
    province = db.Column(db.String(50))  # 所属省份
    latitude = db.Column(db.Float)  # 纬度
    longitude = db.Column(db.Float)  # 经度
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def __init__(self, name, province=None, latitude=None, longitude=None):
        self.name = name
        self.province = province
        self.latitude = latitude
        self.longitude = longitude

    def __repr__(self):
        return f'<City {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'province': self.province,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        } 