from datetime import datetime
from src.extensions import db

class AirQualityData(db.Model):
    """空气质量数据模型"""
    __tablename__ = 'air_quality_data'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    hour = db.Column(db.Integer, nullable=False)
    city = db.Column(db.String(50), nullable=False)
    province = db.Column(db.String(50), nullable=False)
    aqi = db.Column(db.Integer, nullable=False)
    pm25 = db.Column(db.Float, nullable=False)
    quality_level = db.Column(db.String(20), nullable=False)
    main_pollutant = db.Column(db.String(50))
    aqi_ma24 = db.Column(db.Float)  # AQI 24小时移动平均
    pm25_ma24 = db.Column(db.Float)  # PM2.5 24小时移动平均
    timestamp = db.Column(db.DateTime, default=datetime.now)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def __init__(self, date, hour, city, province, aqi, pm25, quality_level, 
                 main_pollutant=None, aqi_ma24=None, pm25_ma24=None):
        self.date = date
        self.hour = hour
        self.city = city
        self.province = province
        self.aqi = aqi
        self.pm25 = pm25
        self.quality_level = quality_level
        self.main_pollutant = main_pollutant
        self.aqi_ma24 = aqi_ma24
        self.pm25_ma24 = pm25_ma24
    
    def __repr__(self):
        return f'<AirQualityData {self.city} {self.date} {self.hour}:00>'
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'date': self.date.strftime('%Y-%m-%d'),
            'hour': self.hour,
            'city': self.city,
            'province': self.province,
            'aqi': self.aqi,
            'pm25': self.pm25,
            'quality_level': self.quality_level,
            'main_pollutant': self.main_pollutant,
            'aqi_ma24': self.aqi_ma24,
            'pm25_ma24': self.pm25_ma24,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        } 