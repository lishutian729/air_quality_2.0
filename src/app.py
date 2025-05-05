from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session, g, make_response
from flask_cors import CORS
from datetime import datetime, timedelta
import pandas as pd
import joblib
from pathlib import Path
import logging
import json
import os
import threading
import time
from src.data_collector import AirQualityCollector
from src.extensions import db
from src.models.user import User, user_favorite_cities
from src.models.city import City
from src.models.admin import Role, Permission, AdminLog, LoginLog
from src.models.alert import AlertConfig, AlertHistory
from src.routes.auth import auth_bp
from src.routes.admin import admin_bp
from src.routes.user import user_bp
from src.routes.data import data_bp
from src.utils.decorators import login_required
import random
from flask_migrate import Migrate
import io
import csv
import math
from src.models.data import AirQualityData

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 获取项目根目录的绝对路径
ROOT_DIR = Path(__file__).parent.parent

# 初始化Flask应用和预测系统
app = Flask(__name__,
    template_folder=str(ROOT_DIR / 'templates'),
    static_folder=str(ROOT_DIR / 'static'))
CORS(app)

# 应用配置
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'your-secret-key-here'),
    SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'mysql://root:lst123456@localhost/air_quality'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    UPLOAD_FOLDER=str(ROOT_DIR / 'static/uploads'),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB max-limit
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),  # 会话有效期7天
    SESSION_COOKIE_SECURE=True,  # 只在HTTPS下发送cookie
    SESSION_COOKIE_HTTPONLY=True,  # 防止JavaScript访问cookie
    SESSION_COOKIE_SAMESITE='Lax'  # 防止CSRF攻击
)

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 初始化数据库
db.init_app(app)
migrate = Migrate(app, db)  # 初始化 Flask-Migrate
with app.app_context():
    db.create_all()  # 创建所有数据库表
    
    # 更新没有头像的用户为默认头像
    users_without_avatar = User.query.filter_by(avatar=None).all()
    for user in users_without_avatar:
        user.avatar = '/static/images/default-avatar.png'
    
    # 创建默认管理员账号
    admin_username = 'admin'
    admin = User.query.filter_by(username=admin_username).first()
    if not admin:
        # 获取或创建超级管理员角色
        admin_role = Role.query.filter_by(name='超级管理员').first()
        if not admin_role:
            admin_role = Role(name='超级管理员', description='系统超级管理员，拥有所有权限')
            db.session.add(admin_role)
            db.session.commit()
        
        admin = User(
            username=admin_username,
            email='admin@example.com',
            role_id=admin_role.id,
            avatar='/static/images/default-avatar.png',
            status=True
        )
        admin.set_password('admin123')  # 设置默认密码
        db.session.add(admin)
        print('创建默认管理员账号成功！')
        print('用户名：admin')
        print('密码：admin123')
    else:
        # 确保现有admin用户有超级管理员角色
        admin_role = Role.query.filter_by(name='超级管理员').first()
        if not admin_role:
            admin_role = Role(name='超级管理员', description='系统超级管理员，拥有所有权限')
            db.session.add(admin_role)
            db.session.commit()
        
        if admin.role_id != admin_role.id:
            admin.role_id = admin_role.id
            print('更新管理员角色成功！')

    db.session.commit()

# 注册蓝图
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(user_bp, url_prefix='/user')
app.register_blueprint(data_bp, url_prefix='/data')

# 初始化预测系统（包含深度学习模型和统计模型）
collector = AirQualityCollector()

# 加载城市数据
try:
    with open(ROOT_DIR / 'data/cities.json', 'r', encoding='utf-8') as f:
        CITIES_DATA = json.load(f)
except FileNotFoundError:
    logger.warning("cities.json not found, using empty dict")
    CITIES_DATA = {}

# 加载城市配置（包含地理信息和环境参数）
try:
    with open(ROOT_DIR / 'data/city_config.json', 'r', encoding='utf-8') as f:
        CITY_CONFIG = json.load(f)
except FileNotFoundError:
    logger.warning("city_config.json not found, using empty dict")
    CITY_CONFIG = {"cities": {}}

# 从配置文件获取城市地理坐标数据
CITY_COORDS = {city: {"lat": info["lat"], "lng": info["lng"]} 
               for city, info in CITY_CONFIG.get("cities", {}).items()}

# 模型输入特征
MODEL_FEATURES = [
    'hour', 'dayofweek', 'month', 'season',
    'temperature', 'humidity', 'wind_speed',
    'pressure', 'precipitation'
]

# 特征列名（按照训练时的顺序）
FEATURE_COLUMNS = [
    'hour', 'dayofweek', 'month', 'season',
    'is_weekend', 'is_peak_hour',
    'aqi_ma24', 'pm25_ma24',
    'aqi_lag1', 'pm25_lag1',
    'aqi_lag3', 'pm25_lag3',
    'aqi_lag6', 'pm25_lag6',
    'aqi_lag12', 'pm25_lag12',
    'aqi_lag24', 'pm25_lag24',
    'city_code', 'province_code'
]

# 加载模型
try:
    logger.info("开始加载模型...")
    models_dir = ROOT_DIR / 'data/models'
    
    # 查找最新的AQI和PM2.5模型
    aqi_models = list(models_dir.glob('best_AQI_model_*.joblib'))
    pm25_models = list(models_dir.glob('best_PM2.5_model_*.joblib'))
    
    if not aqi_models or not pm25_models:
        raise FileNotFoundError("未找到训练好的模型文件")
    
    # 获取最新的模型文件
    latest_aqi_model = max(aqi_models, key=lambda x: x.stat().st_mtime)
    latest_pm25_model = max(pm25_models, key=lambda x: x.stat().st_mtime)
    
    logger.info(f"加载AQI模型: {latest_aqi_model.name}")
    logger.info(f"加载PM2.5模型: {latest_pm25_model.name}")
    
    # 加载模型
    aqi_model = joblib.load(latest_aqi_model)
    pm25_model = joblib.load(latest_pm25_model)
    
    # 加载历史数据
    data_file = ROOT_DIR / 'data/processed/hourly_data_processed.csv'
    historical_data = pd.read_csv(data_file, low_memory=False)
    historical_data['date'] = pd.to_datetime(historical_data['date'])
    logger.info("模型和数据加载成功")
    
except Exception as e:
    logger.error(f"加载模型时出错: {str(e)}")

def get_season(month):
    """根据月份获取季节 (1-4分别代表春夏秋冬)"""
    if month in [3, 4, 5]:
        return 1  # 春季
    elif month in [6, 7, 8]:
        return 2  # 夏季
    elif month in [9, 10, 11]:
        return 3  # 秋季
    else:
        return 4  # 冬季

def get_quality_level(aqi):
    """根据AQI获取空气质量等级"""
    if aqi <= 50:
        return '优'
    elif aqi <= 100:
        return '良'
    elif aqi <= 150:
        return '轻度污染'
    elif aqi <= 200:
        return '中度污染'
    elif aqi <= 300:
        return '重度污染'
    else:
        return '严重污染'

def prepare_features(city_data, timestamp):
    """准备模型预测所需的特征"""
    features = pd.DataFrame(index=[0])
    
    # 时间特征
    features['hour'] = timestamp.hour
    features['dayofweek'] = timestamp.dayofweek
    features['month'] = timestamp.month
    features['season'] = get_season(timestamp.month)
    features['is_weekend'] = 1 if timestamp.dayofweek >= 5 else 0
    features['is_peak_hour'] = 1 if timestamp.hour in [7,8,9,17,18,19] else 0
    
    # 获取最近24小时的数据，确保按时间排序
    recent_data = city_data.sort_values('date').tail(24)
    
    # 计算移动平均（使用最近24小时的数据）
    features['aqi_ma24'] = recent_data['aqi'].mean()
    features['pm25_ma24'] = recent_data['pm25'].mean()
    
    # 获取最新数据作为滞后特征
    latest_data = recent_data.iloc[-1]
    features['aqi_lag1'] = latest_data['aqi']
    features['pm25_lag1'] = latest_data['pm25']
    
    # 获取3小时前数据
    lag3_data = recent_data.iloc[-3] if len(recent_data) >= 3 else latest_data
    features['aqi_lag3'] = lag3_data['aqi']
    features['pm25_lag3'] = lag3_data['pm25']
    
    # 获取6小时前数据
    lag6_data = recent_data.iloc[-6] if len(recent_data) >= 6 else latest_data
    features['aqi_lag6'] = lag6_data['aqi']
    features['pm25_lag6'] = lag6_data['pm25']
    
    # 获取12小时前数据
    lag12_data = recent_data.iloc[-12] if len(recent_data) >= 12 else latest_data
    features['aqi_lag12'] = lag12_data['aqi']
    features['pm25_lag12'] = lag12_data['pm25']
    
    # 获取24小时前数据
    lag24_data = recent_data.iloc[-24] if len(recent_data) >= 24 else latest_data
    features['aqi_lag24'] = lag24_data['aqi']
    features['pm25_lag24'] = lag24_data['pm25']
    
    # 城市和省份编码
    features['city_code'] = latest_data['city_code']
    features['province_code'] = latest_data['province_code']
    
    return features[FEATURE_COLUMNS]

@app.before_request
def before_request():
    """在每个请求之前检查用户会话"""
    g.user = None
    g.admin = None
    
    if 'user_id' in session:
        g.user = db.session.get(User, session['user_id'])
        
    if 'admin_id' in session:
        g.admin = db.session.get(User, session['admin_id'])
        if not g.admin or not g.admin.is_admin():
            session.pop('admin_id', None)
            session.pop('admin_name', None)
            g.admin = None

@app.context_processor
def inject_user():
    """向所有模板注入用户信息"""
    return {
        'current_user': g.user,
        'current_admin': g.admin
    }

@app.route('/')
def index():
    """渲染主页"""
    return render_template('map.html', provinces=list(CITIES_DATA.keys()))

@app.route('/map')
def map_view():
    """渲染地图页面"""
    return render_template('map.html', provinces=list(CITIES_DATA.keys()))

@app.route('/prediction')
def prediction_view():
    """渲染预测页面"""
    return render_template('prediction.html', provinces=list(CITIES_DATA.keys()))

@app.route('/data-download')
@login_required
def data_download_view():
    """渲染数据下载页面"""
    return render_template('data_download.html', provinces=list(CITIES_DATA.keys()))

@app.route('/alert-config')
@login_required
def alert_config_view():
    """渲染预警配置页面"""
    return render_template('alert_config.html', provinces=list(CITIES_DATA.keys()))

@app.route('/alert-history')
@login_required
def alert_history_view():
    """渲染预警历史页面"""
    return render_template('alert_history.html', provinces=list(CITIES_DATA.keys()))

@app.route('/api/get_cities')
def get_cities():
    """获取指定省份的城市列表"""
    province = request.args.get('province', '')
    if not province:
        return jsonify([])
    
    try:
        # 直接返回该省份的所有城市
        cities = CITIES_DATA.get(province, [])
        return jsonify(cities)
    except Exception as e:
        app.logger.error(f"获取城市列表失败: {str(e)}")
        return jsonify({
            'error': '获取城市列表失败'
        }), 500

@app.route('/api/get_prediction')
def get_prediction():
    """获取城市空气质量预测"""
    city = request.args.get('city', '北京')
    
    try:
        # 使用深度学习模型生成预测
        logger.info(f"正在使用AI模型预测{city}的空气质量...")
        result = collector.get_real_time_and_forecast(city)
        
        # 如果获取数据失败，使用备用方案
        if not result:
            logger.warning(f"无法获取{city}的预测数据，使用备用方案")
            # 使用collector的备用数据生成功能
            current_data = collector._generate_fallback_data(city)
            predictions = collector._generate_predictions(current_data)
            result = {
                'current': current_data,
                'predictions': predictions
            }
        
        # 提取预测结果
        current_data = result['current']
        predictions = result['predictions']
        
        # 获取城市地理信息
        coords = CITY_COORDS.get(city, {"lat": 0, "lng": 0})
        
        # 构造返回数据
        response = {
            'city': city,
            'current': {
                'aqi': current_data['aqi'],
                'pm25': current_data['pm25'],
                'quality_level': current_data['quality_level'],
                'timestamp': current_data['timestamp']
            },
            'predictions': [
                {
                    'timestamp': pred['timestamp'],
                    'aqi': pred['aqi'],
                    'pm25': pred['pm25'],
                    'quality_level': pred['quality_level']
                }
                for pred in predictions
            ],
            'lat': coords['lat'],
            'lng': coords['lng']
        }
        
        # 如果用户已登录，检查是否已收藏该城市
        if g.user:
            city_obj = City.query.filter_by(name=city).first()
            is_favorite = city_obj in g.user.favorite_cities if city_obj else False
            response['is_favorite'] = is_favorite
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"模型预测失败: {str(e)}")
        # 如果发生异常，也使用备用方案
        try:
            # 尝试使用collector的备用数据生成功能
            current_data = collector._generate_fallback_data(city)
            aqi = current_data['aqi']
            pm25 = current_data['pm25']
            current_time = datetime.now()
        except:
            # 如果连备用方案也失败，才使用完全随机数据
            aqi = random.randint(20, 300)
            pm25 = random.randint(10, 150)
            current_time = datetime.now()
        
        # 获取城市坐标
        coords = CITY_COORDS.get(city, {"lat": 0, "lng": 0})
        
        # 检查城市是否在用户的收藏列表中
        is_favorite = False
        if g.user:
            city_obj = City.query.filter_by(name=city).first()
            is_favorite = city_obj in g.user.favorite_cities if city_obj else False
        
        return jsonify({
            'city': city,
            'lng': coords['lng'],
            'lat': coords['lat'],
            'is_favorite': is_favorite,
            'current': {
                'aqi': aqi,
                'pm25': pm25,
                'quality_level': get_quality_level(aqi),
                'timestamp': current_time.strftime('%Y-%m-%d %H:%M:%S')
            }
        })

# 添加调试路由，确认数据蓝图映射正确
@app.route('/data/test')
def data_test():
    return jsonify({
        'success': True,
        'message': 'Data blueprint is working correctly!',
        'routes': [str(rule) for rule in app.url_map.iter_rules() if str(rule).startswith('/data')]
    })

def allowed_file(filename):
    """检查文件类型是否允许"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 在请求之前加载用户信息
@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = db.session.get(User, user_id)

# 模板上下文处理器
@app.context_processor
def inject_user():
    return {'current_user': g.user}

def get_dashboard_stats():
    """获取仪表盘统计数据"""
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    
    stats = {
        'user_count': User.query.count(),
        'today_login': LoginLog.query.filter(
            LoginLog.created_at >= today,
            LoginLog.created_at < tomorrow,
            LoginLog.status == True
        ).count(),
        'today_register': User.query.filter(
            User.created_at >= today,
            User.created_at < tomorrow
        ).count(),
        'total_visits': LoginLog.query.filter_by(status=True).count()
    }
    
    return stats

def get_recent_activities():
    """获取最近活动"""
    return AdminLog.query.order_by(AdminLog.created_at.desc()).limit(10).all()

@app.context_processor
def inject_admin_data():
    """向管理后台模板注入数据"""
    if request.path.startswith('/admin'):
        return {
            'stats': get_dashboard_stats(),
            'recent_logs': get_recent_activities()
        }
    return {}

# 添加一个直接的下载路由用于测试
@app.route('/direct-download')
def direct_download():
    """测试下载功能"""
    try:
        # 创建一个简单的CSV数据
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 写入CSV头
        writer.writerow(['日期', '城市', 'AQI', 'PM2.5'])
        
        # 写入一些测试数据
        for i in range(10):
            writer.writerow([
                (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d'),
                '测试城市',
                random.randint(20, 300),
                round(random.uniform(10, 150), 1)
            ])
        
        output.seek(0)
        
        # 返回CSV文件
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename=test_data.csv"
        response.headers["Content-type"] = "text/csv"
        
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'测试下载失败: {str(e)}'}), 500

# 添加真实的下载功能到主应用
@app.route('/app-download/history')
@login_required
def app_download_history():
    """直接在应用中下载历史空气质量数据"""
    city = request.args.get('city', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    
    if not city:
        return jsonify({'success': False, 'message': '请指定城市名称'}), 400
    
    try:
        # 格式化日期
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
        else:
            start_date = datetime.now() - timedelta(days=30)
            
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
        else:
            end_date = datetime.now()
        
        # 输出调试信息
        print(f"开始查询城市 {city} 从 {start_date.date()} 到 {end_date.date()} 的数据")
        
        # 直接从数据库查询
        query = AirQualityData.query.filter_by(city=city)
        query = query.filter(AirQualityData.date >= start_date.date())
        query = query.filter(AirQualityData.date <= end_date.date())
        query = query.order_by(AirQualityData.date, AirQualityData.hour)
        
        # 获取SQL语句 (仅用于调试)
        sql = str(query.statement.compile(compile_kwargs={"literal_binds": True}))
        print(f"执行SQL查询: {sql}")
        
        # 执行查询
        records = query.all()
        print(f"查询结果: 找到 {len(records)} 条记录")
        
        # 如果没有记录，则生成一些示例数据
        if not records:
            print(f"未找到 {city} 的数据，生成示例数据")
            
            # 检查数据库中是否有任何数据
            total_records = AirQualityData.query.count()
            print(f"数据库中共有 {total_records} 条记录")
            
            # 查询数据库中所有可用的城市
            cities = db.session.query(AirQualityData.city).distinct().all()
            available_cities = [c[0] for c in cities]
            print(f"数据库中可用的城市: {available_cities}")
            
            # 生成测试数据
            example_records = []
            current_date = start_date
            
            while current_date <= end_date:
                for hour in range(0, 24, 6):  # 每天生成4个时间点的数据
                    example_records.append({
                        'date': current_date.date(),
                        'hour': hour,
                        'city': city,
                        'province': '测试省份',
                        'aqi': random.randint(50, 200),
                        'pm25': random.randint(20, 150),
                        'quality_level': '测试数据',
                        'main_pollutant': 'PM2.5'
                    })
                current_date += timedelta(days=1)
        
        # 创建带BOM的UTF-8编码StringIO
        output = io.StringIO()
        output.write('\ufeff')  # 添加UTF-8 BOM
        
        writer = csv.writer(output)
        
        # 写入CSV头
        writer.writerow(['日期', '小时', '城市', '省份', 'AQI', 'PM2.5', '空气质量等级', '主要污染物'])
        
        # 写入数据库数据
        if records:
            print("写入真实数据库记录")
            for record in records:
                writer.writerow([
                    record.date.strftime('%Y-%m-%d'),
                    record.hour,
                    record.city,
                    record.province,
                    record.aqi,
                    record.pm25,
                    record.quality_level,
                    record.main_pollutant
                ])
        else:
            # 写入示例数据
            print("写入示例数据")
            for record in example_records:
                writer.writerow([
                    record['date'].strftime('%Y-%m-%d'),
                    record['hour'],
                    record['city'],
                    record['province'],
                    record['aqi'],
                    record['pm25'],
                    record['quality_level'],
                    record['main_pollutant']
                ])
        
        output.seek(0)
        
        # 使用英文和日期作为文件名，避免中文编码问题
        # 使用ASCII兼容的文件名并包含城市拼音或英文代码
        filename = f"airquality_{city.encode('ascii', 'ignore').decode()}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv"
        
        print(f"准备下载文件: {filename}")
        
        # 添加合适的Content-Type和Content-Disposition头
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        response.headers["Content-type"] = "text/csv; charset=utf-8-sig"
        
        return response
        
    except Exception as e:
        print(f"数据导出失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'数据导出失败: {str(e)}'}), 500

# 添加预警历史相关接口到主应用
@app.route('/app/alerts/history')
@login_required
def app_get_alert_history():
    """获取预警历史，直接在主应用中实现"""
    try:
        # 获取参数
        city = request.args.get('city', '')
        status = request.args.get('status', None)
        
        # 构建查询
        query = AlertHistory.query.filter_by(user_id=g.user.id)
        
        if city:
            query = query.filter_by(city=city)
            
        if status is not None:
            query = query.filter_by(read_status=(status == 'read'))
            
        # 按时间倒序排列
        query = query.order_by(AlertHistory.created_at.desc())
        
        # 获取结果
        alerts = query.all()
        
        return jsonify({
            'success': True,
            'alerts': [alert.to_dict() for alert in alerts]
        })
        
    except Exception as e:
        logger.error(f"获取预警历史失败: {str(e)}")
        return jsonify({'success': False, 'message': f'获取预警历史失败: {str(e)}'}), 500

@app.route('/app/alerts/history/unread-count')
@login_required
def app_get_unread_alert_count():
    """获取未读预警数量"""
    try:
        # 查询真实的未读预警数量
        count = AlertHistory.query.filter_by(
            user_id=g.user.id,
            read_status=False
        ).count()
        
        return jsonify({
            'success': True,
            'count': count
        })
    except Exception as e:
        logger.error(f"获取未读预警数量失败: {str(e)}")
        return jsonify({'success': False, 'message': f'获取未读预警数量失败: {str(e)}'}), 500

@app.route('/app/alerts/history/<int:alert_id>/read', methods=['PUT'])
@login_required
def app_mark_alert_as_read(alert_id):
    """将预警标记为已读"""
    try:
        # 查找指定ID的预警记录
        alert = AlertHistory.query.filter_by(id=alert_id, user_id=g.user.id).first()
        if not alert:
            return jsonify({'success': False, 'message': '预警记录不存在'}), 404
        
        # 修改为已读状态
        alert.read_status = True
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '预警已标记为已读'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"标记预警状态失败: {str(e)}")
        return jsonify({'success': False, 'message': f'标记预警状态失败: {str(e)}'}), 500

@app.route('/app/alerts/history/mark-all-read', methods=['PUT'])
@login_required
def app_mark_all_alerts_as_read():
    """将所有预警标记为已读"""
    try:
        # 查找用户所有未读的预警
        unread_alerts = AlertHistory.query.filter_by(
            user_id=g.user.id,
            read_status=False
        ).all()
        
        # 修改为已读状态
        count = 0
        for alert in unread_alerts:
            alert.read_status = True
            count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'已将{count}条预警标记为已读',
            'count': count
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"标记所有预警已读失败: {str(e)}")
        return jsonify({'success': False, 'message': f'标记所有预警已读失败: {str(e)}'}), 500

def run_alert_check():
    """定期执行预警检查"""
    with app.app_context():
        logger.info("启动预警检查任务")
        while True:
            try:
                # 使用现有的预警检查路由
                from src.routes.data import check_all_alerts
                result = check_all_alerts()
                logger.info(f"预警检查完成: {result.get_json()['message'] if result.is_json else '未返回JSON数据'}")
                
                # 等待下一次检查
                time.sleep(3600)  # 每小时检查一次
            except Exception as e:
                logger.error(f"预警检查任务失败: {str(e)}")
                time.sleep(300)  # 如果发生异常，5分钟后重试

if __name__ == '__main__':
    with app.app_context():
        # 创建所有数据库表
        db.create_all()
    
    # 启动预警检查后台任务
    alert_thread = threading.Thread(target=run_alert_check, daemon=True)
    alert_thread.start()
    logger.info("预警检查后台任务已启动")
    
    app.run(debug=True, port=5000) 