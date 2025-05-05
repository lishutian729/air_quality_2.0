from functools import wraps
from flask import g, flash, redirect, url_for, abort
from src.models.admin import Role, Permission

def login_required(f):
    """检查用户是否已登录"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.user:
            flash('请先登录', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def permission_required(permission_name):
    """检查用户是否拥有指定权限"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not g.admin:
                flash('请先登录', 'error')
                return redirect(url_for('admin.login'))
            
            if g.admin.is_admin():  # 超级管理员拥有所有权限
                return f(*args, **kwargs)
            
            # 获取用户角色
            role = Role.query.filter_by(name=g.admin.role).first()
            if not role:
                abort(403)  # 没有角色，禁止访问
            
            # 检查角色是否拥有权限
            permission = Permission.query.filter_by(name=permission_name).first()
            if not permission or permission not in role.permissions:
                abort(403)  # 没有权限，禁止访问
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def admin_required(f):
    """检查用户是否是管理员"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.admin:
            flash('请先登录', 'error')
            return redirect(url_for('admin.login'))
        
        if not g.admin.is_admin():
            abort(403)  # 不是管理员，禁止访问
        
        return f(*args, **kwargs)
    return decorated_function

def role_required(role_name):
    """检查用户是否拥有指定角色"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not g.user:
                flash('请先登录', 'error')
                return redirect(url_for('auth.login'))
            
            if g.user.role == 'admin':  # 超级管理员拥有所有角色权限
                return f(*args, **kwargs)
            
            if not g.user.role == role_name:
                abort(403)  # 不是指定角色，禁止访问
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator 