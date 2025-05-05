from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, session, g, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from src.models.user import User, UserProfile
from src.models.admin import LoginLog
from src.extensions import db
from datetime import datetime
import os
import re

auth_bp = Blueprint('auth', __name__)

def allowed_file(filename):
    """检查文件类型是否允许"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@auth_bp.route('/upload_avatar', methods=['POST'])
def upload_avatar():
    """处理头像上传"""
    if not g.user:
        flash('请先登录', 'error')
        return redirect(url_for('auth.login'))

    if 'avatar' not in request.files:
        flash('没有选择文件', 'error')
        return redirect(url_for('auth.profile'))

    file = request.files['avatar']
    if file.filename == '':
        flash('没有选择文件', 'error')
        return redirect(url_for('auth.profile'))

    if file and allowed_file(file.filename):
        try:
            # 生成安全的文件名
            filename = secure_filename(file.filename)
            # 添加时间戳避免文件名重复
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            # 确保上传目录存在
            upload_folder = os.path.join(current_app.static_folder, 'uploads', 'avatars')
            os.makedirs(upload_folder, exist_ok=True)
            # 保存文件
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)
            # 更新用户头像路径
            g.user.avatar = f'/static/uploads/avatars/{filename}'
            db.session.commit()
            flash('头像上传成功', 'success')
        except Exception as e:
            print(f"Avatar upload error: {str(e)}")
            flash('头像上传失败，请重试', 'error')
    else:
        flash('不支持的文件类型', 'error')

    return redirect(url_for('auth.profile'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """用户注册"""
    if request.method == 'GET':
        return render_template('auth/register.html')
    
    # 获取表单数据
    data = request.form
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    confirm = data.get('confirm_password')
    # 打印数据到控制台
    print(f"用户名: {username}")
    print(f"邮箱: {email}")
    print(f"密码: {password}")
    print(f"确认密码: {confirm}")

    
    # 表单验证
    if not username or not email or not password:
        flash('请填写所有必填字段', 'error')
        return redirect(url_for('auth.register'))
    
    if password != confirm:
        flash('两次输入的密码不一致', 'error')
        return redirect(url_for('auth.register'))
    
    # 检查用户名是否已存在
    if User.query.filter_by(username=username).first():
        flash('用户名已存在', 'error')
        return redirect(url_for('auth.register'))
    
    # 检查邮箱是否已存在
    if User.query.filter_by(email=email).first():
        flash('邮箱已被注册', 'error')
        return redirect(url_for('auth.register'))
    
    # 创建新用户
    user = User(
        username=username,
        email=email,
        avatar='/static/images/default-avatar.png',
        status=True
    )
    user.set_password(password)
    
    try:
        db.session.add(user)
        db.session.commit()
        flash('注册成功，请登录', 'success')
        return redirect(url_for('auth.login'))
    except Exception as e:
        db.session.rollback()
        flash('注册失败，请重试', 'error')
        return redirect(url_for('auth.register'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录"""
    if request.method == 'GET':
        return render_template('auth/login.html')
    
    # 获取表单数据
    data = request.form
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        flash('请输入用户名和密码', 'error')
        return redirect(url_for('auth.login'))
    
    # 查找用户
    user = User.query.filter_by(username=username).first()
    
    # 验证密码
    if not user or not user.check_password(password):
        # 记录失败的登录
        if user:
            log = LoginLog(
                user_id=user.id,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string,
                status=False
            )
            db.session.add(log)
            db.session.commit()
        
        flash('用户名或密码错误', 'error')
        return redirect(url_for('auth.login'))
    
    # 检查用户状态
    if not user.status:
        flash('账号已被禁用，请联系管理员', 'error')
        return redirect(url_for('auth.login'))
    
    # 更新最后登录时间
    user.last_login = datetime.now()
    
    # 记录成功的登录
    log = LoginLog(
        user_id=user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
        status=True
    )
    db.session.add(log)
    
    try:
        db.session.commit()
        # 设置会话
        session['user_id'] = user.id
        session['username'] = user.username
        
        # 如果是管理员，设置管理员会话
        if user.is_admin():
            session['admin_id'] = user.id
            session['admin_name'] = user.username
            flash('登录成功', 'success')
            return redirect(url_for('admin.dashboard'))
        
        flash('登录成功', 'success')
        return redirect(url_for('index'))
    except Exception as e:
        db.session.rollback()
        flash('登录失败，请重试', 'error')
        return redirect(url_for('auth.login'))

@auth_bp.route('/logout')
def logout():
    """用户登出"""
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('admin_id', None)
    session.pop('admin_name', None)
    flash('已退出登录', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/profile', methods=['GET'])
def profile():
    """用户个人资料页面"""
    if not g.user:
        flash('请先登录', 'error')
        return redirect(url_for('auth.login'))
    
    # 获取用户详细信息
    user_profile = UserProfile.query.filter_by(user_id=g.user.id).first()
    if not user_profile:
        # 如果用户还没有详细信息，创建一个
        user_profile = UserProfile(user_id=g.user.id)
        db.session.add(user_profile)
        db.session.commit()
    
    # 获取用户收藏的城市
    favorite_cities = g.user.favorite_cities
    return render_template('auth/profile.html', 
                         favorite_cities=favorite_cities,
                         user_profile=user_profile)

@auth_bp.route('/update_profile', methods=['POST'])
def update_profile():
    """更新用户详细信息"""
    if not g.user:
        flash('请先登录', 'error')
        return redirect(url_for('auth.login'))
    
    data = request.form
    email = data.get('email')
    nickname = data.get('nickname')
    phone = data.get('phone')
    location = data.get('location')
    
    try:
        # 验证邮箱格式
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash('邮箱格式不正确', 'error')
            return redirect(url_for('auth.profile'))
        
        # 检查邮箱是否被其他用户使用
        if email != g.user.email:
            existing_user = User.query.filter_by(email=email).first()
            if existing_user and existing_user.id != g.user.id:
                flash('该邮箱已被其他用户使用', 'error')
                return redirect(url_for('auth.profile'))
            g.user.email = email
        
        # 更新用户详细信息
        user_profile = UserProfile.query.filter_by(user_id=g.user.id).first()
        if not user_profile:
            user_profile = UserProfile(user_id=g.user.id)
            db.session.add(user_profile)
        
        user_profile.nickname = nickname
        user_profile.phone = phone
        user_profile.location = location
        
        db.session.commit()
        flash('个人资料更新成功', 'success')
    except Exception as e:
        db.session.rollback()
        flash('更新失败，请重试', 'error')
    
    return redirect(url_for('auth.profile'))

@auth_bp.route('/change_password', methods=['POST'])
def change_password():
    """修改密码"""
    if not g.user:
        flash('请先登录', 'error')
        return redirect(url_for('auth.login'))
    
    data = request.form
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')
    
    if not current_password or not new_password or not confirm_password:
        flash('所有密码字段都必须填写', 'error')
        return redirect(url_for('auth.profile'))
    
    if new_password != confirm_password:
        flash('新密码两次输入不一致', 'error')
        return redirect(url_for('auth.profile'))
    
    if not g.user.check_password(current_password):
        flash('当前密码错误', 'error')
        return redirect(url_for('auth.profile'))
    
    try:
        g.user.set_password(new_password)
        db.session.commit()
        flash('密码修改成功', 'success')
    except Exception as e:
        db.session.rollback()
        flash('密码修改失败，请重试', 'error')
    
    return redirect(url_for('auth.profile'))

@auth_bp.route('/toggle_favorite_city', methods=['POST'])
def toggle_favorite_city():
    """添加或取消收藏城市"""
    if not g.user:
        return jsonify({'success': False, 'message': '请先登录'}), 401
    
    data = request.get_json()
    city_name = data.get('city')
    action = data.get('action')  # 'add' or 'remove'
    
    if not city_name or not action:
        return jsonify({'success': False, 'message': '参数错误'}), 400
    
    try:
        from src.models.city import City
        city = City.query.filter_by(name=city_name).first()
        
        if not city:
            return jsonify({'success': False, 'message': '城市不存在'}), 404
        
        if action == 'add':
            if city not in g.user.favorite_cities:
                g.user.favorite_cities.append(city)
                message = '添加收藏成功'
        elif action == 'remove':
            if city in g.user.favorite_cities:
                g.user.favorite_cities.remove(city)
                message = '取消收藏成功'
        else:
            return jsonify({'success': False, 'message': '不支持的操作'}), 400
        
        db.session.commit()
        return jsonify({'success': True, 'message': message})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500 