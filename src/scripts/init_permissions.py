import os
import sys

# 将项目根目录添加到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, project_root)

from src.models.admin import Role, Permission
from src.models.user import User
from src.models.city import City
from src.extensions import db
from flask import Flask

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:lst123456@localhost/air_quality'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'your-secret-key'
    
    db.init_app(app)
    
    return app

def init_permissions(app):
    """初始化系统权限"""
    with app.app_context():
        # 用户管理权限
        permissions = [
            # 用户管理
            {
                'name': 'user_view',
                'description': '查看用户列表',
                'module': '用户管理'
            },
            {
                'name': 'user_create',
                'description': '创建用户',
                'module': '用户管理'
            },
            {
                'name': 'user_edit',
                'description': '编辑用户',
                'module': '用户管理'
            },
            {
                'name': 'user_delete',
                'description': '删除用户',
                'module': '用户管理'
            },
            
            # 角色管理
            {
                'name': 'role_view',
                'description': '查看角色列表',
                'module': '角色管理'
            },
            {
                'name': 'role_create',
                'description': '创建角色',
                'module': '角色管理'
            },
            {
                'name': 'role_edit',
                'description': '编辑角色',
                'module': '角色管理'
            },
            {
                'name': 'role_delete',
                'description': '删除角色',
                'module': '角色管理'
            },
            
            # 权限管理
            {
                'name': 'permission_view',
                'description': '查看权限列表',
                'module': '权限管理'
            },
            
            # 数据管理
            {
                'name': 'data_view',
                'description': '查看数据列表',
                'module': '数据管理'
            },
            {
                'name': 'data_edit',
                'description': '编辑数据',
                'module': '数据管理'
            },
            {
                'name': 'data_export',
                'description': '导出数据',
                'module': '数据管理'
            },
            
            # 日志管理
            {
                'name': 'log_view',
                'description': '查看日志',
                'module': '日志管理'
            },
            {
                'name': 'log_export',
                'description': '导出日志',
                'module': '日志管理'
            }
        ]
        
        # 创建权限
        for perm_data in permissions:
            perm = Permission.query.filter_by(name=perm_data['name']).first()
            if not perm:
                perm = Permission(**perm_data)
                db.session.add(perm)
                print(f"创建权限: {perm_data['name']}")
        
        # 创建超级管理员角色
        admin_role = Role.query.filter_by(name='超级管理员').first()
        if not admin_role:
            admin_role = Role(
                name='超级管理员',
                description='系统超级管理员，拥有所有权限'
            )
            db.session.add(admin_role)
            print("创建超级管理员角色")
        
        # 为超级管理员角色分配所有权限
        all_permissions = Permission.query.all()
        admin_role.permissions = all_permissions
        
        # 确保admin用户存在并拥有超级管理员角色
        admin_user = User.query.filter_by(username='admin').first()
        if admin_user:
            admin_user.role = admin_role
            print("更新admin用户角色为超级管理员")
        
        db.session.commit()
        print("权限初始化完成！")

if __name__ == '__main__':
    app = create_app()
    init_permissions(app) 