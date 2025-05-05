from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, g, session, send_file
from src.models.user import User
from src.models.admin import Role, Permission, AdminLog, LoginLog
from src.extensions import db
from functools import wraps
from datetime import datetime, timedelta
import platform
import sys
from sqlalchemy import func, text
from src.utils.decorators import admin_required, permission_required
from werkzeug.security import generate_password_hash
import csv
import io
import os
from src.models.data import AirQualityData
import pandas as pd
from io import BytesIO

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.before_request
def load_logged_in_admin():
    """在请求之前加载管理员信息"""
    admin_id = session.get('admin_id')
    if admin_id is None:
        g.admin = None
    else:
        g.admin = User.query.get(admin_id)

    # 允许访问登录页面
    if request.endpoint == 'admin.login':
        return
    
    # 其他页面需要验证管理员身份
    if g.admin is None:
        return redirect(url_for('admin.login'))

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """管理员登录"""
    # 如果已经登录，直接跳转到仪表板
    if g.admin:
        return redirect(url_for('admin.dashboard'))
        
    if request.method == 'GET':
        return render_template('admin/login.html')
    
    data = request.form
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        flash('用户名和密码不能为空', 'error')
        return redirect(url_for('admin.login'))
    
    # 查找用户并验证是否是管理员
    user = User.query.filter_by(username=username).first()
    
    if not user or not user.check_password(password):
        flash('用户名或密码错误', 'error')
        return redirect(url_for('admin.login'))
        
    # 验证用户是否是管理员
    if not user.is_admin():
        flash('您没有管理员权限', 'error')
        return redirect(url_for('admin.login'))
    
    # 记录登录日志
    log = LoginLog(
        user_id=user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
        status=True
    )
    db.session.add(log)
    
    # 设置管理员会话
    session['admin_id'] = user.id
    session['admin_name'] = user.username
    
    try:
        db.session.commit()
        flash('登录成功', 'success')
        return redirect(url_for('admin.dashboard'))
    except Exception as e:
        db.session.rollback()
        flash('登录失败，请重试', 'error')
        return redirect(url_for('admin.login'))

@admin_bp.route('/')
@admin_required
def dashboard():
    """管理后台首页"""
    # 获取统计数据
    stats = {
        'user_count': User.query.count(),
        'today_login': LoginLog.query.filter(
            LoginLog.created_at >= datetime.now().date()
        ).count(),
        'today_register': User.query.filter(
            User.created_at >= datetime.now().date()
        ).count(),
        'total_visits': LoginLog.query.count()
    }
    
    # 获取最近活动记录
    recent_logs = AdminLog.query.order_by(AdminLog.created_at.desc()).limit(10).all()
    
    # 获取系统信息
    system_info = {
        'python_version': platform.python_version(),
        'os_info': f"{platform.system()} {platform.release()}",
        'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'db_version': db.session.execute(text('SELECT VERSION()')).scalar()
    }
    
    return render_template('admin/dashboard.html',
                         stats=stats,
                         recent_logs=recent_logs,
                         **system_info)

@admin_bp.route('/users')
@admin_required
def user_list():
    """用户列表"""
    page = request.args.get('page', 1, type=int)
    users = User.query.paginate(page=page, per_page=10)
    roles = Role.query.all()
    return render_template('admin/user_list.html', users=users, roles=roles)

@admin_bp.route('/users/<int:user_id>', methods=['GET'])
@admin_required
def get_user(user_id):
    """获取用户信息"""
    user = User.query.get_or_404(user_id)
    return jsonify({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role_id': user.role_id,
        'status': user.status
    })

@admin_bp.route('/users', methods=['POST'])
@admin_required
def create_user():
    """创建用户"""
    data = request.get_json()
    
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': '用户名已存在'}), 400
    
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': '邮箱已存在'}), 400
    
    user = User(
        username=data['username'],
        email=data['email'],
        password=generate_password_hash(data['password']),
        role_id=data['role_id'],
        status=data['status']
    )
    
    try:
        db.session.add(user)
        db.session.commit()
        
        # 记录操作日志
        admin_log = AdminLog(
            user_id=g.admin.id,
            module='用户管理',
            action='创建',
            description=f'创建用户: {user.username}',
            ip_address=request.remote_addr
        )
        db.session.add(admin_log)
        db.session.commit()
        
        return jsonify({'message': '创建成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    """更新用户信息"""
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    
    # 检查用户名是否已存在
    if data['username'] != user.username and \
       User.query.filter_by(username=data['username']).first():
        return jsonify({'error': '用户名已存在'}), 400
    
    # 检查邮箱是否已存在
    if data['email'] != user.email and \
       User.query.filter_by(email=data['email']).first():
        return jsonify({'error': '邮箱已存在'}), 400
    
    try:
        user.username = data['username']
        user.email = data['email']
        if 'password' in data and data['password']:  # 只有当密码字段存在且不为空时才更新密码
            user.password = generate_password_hash(data['password'])
        if 'role_id' in data:  # 允许role_id为空字符串，表示删除角色
            user.role_id = data['role_id'] if data['role_id'] else None
        user.status = data['status']
        
        db.session.commit()
        
        # 记录操作日志
        admin_log = AdminLog(
            user_id=g.admin.id,
            module='用户管理',
            action='更新',
            description=f'更新用户: {user.username}',
            ip_address=request.remote_addr
        )
        db.session.add(admin_log)
        db.session.commit()
        
        return jsonify({'message': '更新成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """删除用户"""
    user = User.query.get_or_404(user_id)
    
    if user.id == g.admin.id:
        return jsonify({'error': '不能删除当前登录用户'}), 400
    
    try:
        username = user.username
        db.session.delete(user)
        
        # 记录操作日志
        admin_log = AdminLog(
            user_id=g.admin.id,
            module='用户管理',
            action='删除',
            description=f'删除用户: {username}',
            ip_address=request.remote_addr
        )
        db.session.add(admin_log)
        db.session.commit()
        
        return jsonify({'message': '删除成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/roles')
@admin_required
def role_list():
    """角色列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    roles = Role.query.order_by(Role.id).paginate(page=page, per_page=per_page)
    permissions = Permission.query.all()
    return render_template('admin/role_list.html', roles=roles, permissions=permissions)

@admin_bp.route('/roles/<int:role_id>', methods=['GET'])
@admin_required
def get_role(role_id):
    """获取角色信息"""
    role = Role.query.get_or_404(role_id)
    return jsonify({
        'id': role.id,
        'name': role.name,
        'description': role.description,
        'permissions': [p.id for p in role.permissions]
    })

@admin_bp.route('/roles', methods=['POST'])
@admin_required
def create_role():
    """创建角色"""
    data = request.get_json()
    
    if Role.query.filter_by(name=data['name']).first():
        return jsonify({'error': '角色名称已存在'}), 400
    
    role = Role(
        name=data['name'],
        description=data['description']
    )
    
    # 添加权限
    if 'permissions' in data:
        permissions = Permission.query.filter(Permission.id.in_(data['permissions'])).all()
        role.permissions = permissions
    
    try:
        db.session.add(role)
        db.session.commit()
        
        # 记录操作日志
        admin_log = AdminLog(
            user_id=g.admin.id,
            module='角色管理',
            action='创建',
            description=f'创建角色: {role.name}',
            ip_address=request.remote_addr
        )
        db.session.add(admin_log)
        db.session.commit()
        
        return jsonify({'message': '创建成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/roles/<int:role_id>', methods=['PUT'])
@admin_required
def update_role(role_id):
    """更新角色信息"""
    role = Role.query.get_or_404(role_id)
    data = request.get_json()
    
    # 检查角色名是否已存在
    if data['name'] != role.name and \
       Role.query.filter_by(name=data['name']).first():
        return jsonify({'error': '角色名称已存在'}), 400
    
    try:
        role.name = data['name']
        role.description = data['description']
        
        # 更新权限
        if 'permissions' in data:
            permissions = Permission.query.filter(Permission.id.in_(data['permissions'])).all()
            role.permissions = permissions
        
        db.session.commit()
        
        # 记录操作日志
        admin_log = AdminLog(
            user_id=g.admin.id,
            module='角色管理',
            action='更新',
            description=f'更新角色: {role.name}',
            ip_address=request.remote_addr
        )
        db.session.add(admin_log)
        db.session.commit()
        
        return jsonify({'message': '更新成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/roles/<int:role_id>', methods=['DELETE'])
@admin_required
def delete_role(role_id):
    """删除角色"""
    role = Role.query.get_or_404(role_id)
    
    # 检查是否有用户正在使用该角色
    if User.query.filter_by(role_id=role_id).first():
        return jsonify({'error': '该角色下还有用户，无法删除'}), 400
    
    try:
        role_name = role.name
        db.session.delete(role)
        
        # 记录操作日志
        admin_log = AdminLog(
            user_id=g.admin.id,
            module='角色管理',
            action='删除',
            description=f'删除角色: {role_name}',
            ip_address=request.remote_addr
        )
        db.session.add(admin_log)
        db.session.commit()
        
        return jsonify({'message': '删除成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/permissions')
@admin_required
@permission_required('permission_view')
def permission_list():
    """权限管理"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    permissions = Permission.query.order_by(Permission.id).paginate(page=page, per_page=per_page)
    return render_template('admin/permission_list.html', permissions=permissions)

@admin_bp.route('/admin_logs')
@admin_required
@permission_required('log_view')
def admin_log_list():
    """操作日志"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    logs = AdminLog.query.order_by(AdminLog.created_at.desc()).paginate(page=page, per_page=per_page)
    return render_template('admin/admin_log_list.html', logs=logs)

@admin_bp.route('/login_logs')
@admin_required
@permission_required('log_view')
def login_log_list():
    """登录日志"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    logs = LoginLog.query.order_by(LoginLog.created_at.desc()).paginate(page=page, per_page=per_page)
    return render_template('admin/login_log_list.html', logs=logs)

@admin_bp.route('/logout')
def logout():
    """管理员登出"""
    session.pop('admin_id', None)
    session.pop('admin_name', None)
    flash('已退出管理后台', 'success')
    return redirect(url_for('admin.login'))

@admin_bp.route('/export_login_logs')
def export_login_logs():
    """导出登录日志"""
    if not g.admin or not g.admin.is_admin():
        flash('您没有权限访问此页面', 'error')
        return redirect(url_for('auth.login'))
    
    try:
        # 创建内存中的文件对象
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 写入表头
        writer.writerow(['ID', '用户名', 'IP地址', '浏览器', '登录状态', '登录时间'])
        
        # 获取所有登录日志
        logs = LoginLog.query.join(User).order_by(LoginLog.created_at.desc()).all()
        
        # 写入数据
        for log in logs:
            writer.writerow([
                log.id,
                log.user.username if log.user else '未知用户',
                log.ip_address,
                log.user_agent,
                '成功' if log.status else '失败',
                log.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        # 将指针移到文件开头
        output.seek(0)
        
        # 生成文件名
        filename = f'login_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        # 返回CSV文件
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8-sig')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        flash('导出登录日志失败', 'error')
        return redirect(url_for('admin.login_logs'))

@admin_bp.route('/export_admin_logs')
def export_admin_logs():
    """导出操作日志"""
    if not g.admin or not g.admin.is_admin():
        flash('您没有权限访问此页面', 'error')
        return redirect(url_for('auth.login'))
    
    try:
        # 创建内存中的文件对象
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 写入表头
        writer.writerow(['ID', '管理员', '模块', '操作', '描述', 'IP地址', '操作时间'])
        
        # 获取所有操作日志
        logs = AdminLog.query.join(User).order_by(AdminLog.created_at.desc()).all()
        
        # 写入数据
        for log in logs:
            writer.writerow([
                log.id,
                log.user.username if log.user else '未知用户',
                log.module,
                log.action,
                log.description,
                log.ip_address,
                log.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        # 将指针移到文件开头
        output.seek(0)
        
        # 生成文件名
        filename = f'admin_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        # 返回CSV文件
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8-sig')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        flash('导出操作日志失败', 'error')
        return redirect(url_for('admin.admin_logs'))

@admin_bp.route('/data')
@admin_required
def data_list():
    """数据管理"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # 构建查询
    query = AirQualityData.query
    
    # 应用筛选条件
    city = request.args.get('city')
    if city:
        query = query.filter(AirQualityData.city == city)
        
    province = request.args.get('province')
    if province:
        query = query.filter(AirQualityData.province == province)
        
    quality_level = request.args.get('quality_level')
    if quality_level:
        query = query.filter(AirQualityData.quality_level == quality_level)
        
    start_date = request.args.get('start_date')
    if start_date:
        query = query.filter(AirQualityData.date >= start_date)
        
    end_date = request.args.get('end_date')
    if end_date:
        query = query.filter(AirQualityData.date <= end_date)
    
    # 获取分页数据
    pagination = query.order_by(AirQualityData.timestamp.desc()).paginate(page=page, per_page=per_page)
    
    # 获取所有城市和省份列表（用于筛选）
    cities = db.session.query(AirQualityData.city.distinct()).order_by(AirQualityData.city).all()
    provinces = db.session.query(AirQualityData.province.distinct()).order_by(AirQualityData.province).all()
    
    return render_template('admin/data_list.html',
                         data=pagination.items,
                         pagination=pagination,
                         cities=[city[0] for city in cities],
                         provinces=[province[0] for province in provinces])

@admin_bp.route('/data/export')
@admin_required
def export_data():
    """导出数据"""
    # 构建查询
    query = AirQualityData.query
    
    # 应用筛选条件
    city = request.args.get('city')
    if city:
        query = query.filter(AirQualityData.city == city)
        
    province = request.args.get('province')
    if province:
        query = query.filter(AirQualityData.province == province)
        
    quality_level = request.args.get('quality_level')
    if quality_level:
        query = query.filter(AirQualityData.quality_level == quality_level)
        
    start_date = request.args.get('start_date')
    if start_date:
        query = query.filter(AirQualityData.date >= start_date)
        
    end_date = request.args.get('end_date')
    if end_date:
        query = query.filter(AirQualityData.date <= end_date)
    
    # 获取数据
    data = query.order_by(AirQualityData.timestamp).all()
    
    # 转换为DataFrame
    df = pd.DataFrame([{
        '日期': item.date,
        '时间': f"{item.hour}:00",
        '城市': item.city,
        '省份': item.province,
        'AQI': item.aqi,
        'PM2.5': item.pm25,
        '空气质量等级': item.quality_level,
        '主要污染物': item.main_pollutant,
        'AQI 24小时移动平均': item.aqi_ma24,
        'PM2.5 24小时移动平均': item.pm25_ma24
    } for item in data])
    
    # 创建Excel文件
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='空气质量数据')
    output.seek(0)
    
    # 生成文件名
    filename = f'air_quality_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    
    # 返回Excel文件
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

@admin_bp.route('/data/<int:data_id>')
@admin_required
def get_data(data_id):
    """获取单条数据"""
    data = AirQualityData.query.get_or_404(data_id)
    return jsonify({
        'id': data.id,
        'aqi': data.aqi,
        'pm25': data.pm25,
        'quality_level': data.quality_level,
        'main_pollutant': data.main_pollutant
    })

@admin_bp.route('/data/<int:data_id>', methods=['PUT'])
@admin_required
def update_data(data_id):
    """更新数据"""
    data = AirQualityData.query.get_or_404(data_id)
    json_data = request.get_json()
    
    try:
        data.aqi = float(json_data.get('aqi', data.aqi))
        data.pm25 = float(json_data.get('pm25', data.pm25))
        data.quality_level = json_data.get('quality_level', data.quality_level)
        data.main_pollutant = json_data.get('main_pollutant', data.main_pollutant)
        
        db.session.commit()
        return jsonify({'message': '更新成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400 