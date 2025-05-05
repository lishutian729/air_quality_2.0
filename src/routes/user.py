from flask import Blueprint, render_template, request, redirect, url_for, flash, g, jsonify
from werkzeug.security import check_password_hash
from src.models.user import User
from src.models.city import City
from src.extensions import db
from src.utils.decorators import login_required

user_bp = Blueprint('user', __name__)

@user_bp.route('/profile')
@login_required
def profile():
    """用户个人中心"""
    return render_template('auth/profile.html')

@user_bp.route('/change_password', methods=['POST'])
@login_required
def change_password():
    """修改密码"""
    old_password = request.form.get('old_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not old_password or not new_password or not confirm_password:
        return jsonify({'success': False, 'message': '请填写所有密码字段'})
    
    if new_password != confirm_password:
        return jsonify({'success': False, 'message': '两次输入的新密码不一致'})
    
    if not g.user.check_password(old_password):
        return jsonify({'success': False, 'message': '原密码错误'})
    
    if len(new_password) < 6:
        return jsonify({'success': False, 'message': '新密码长度至少6位'})
    
    g.user.set_password(new_password)
    db.session.commit()
    
    return jsonify({'success': True, 'message': '密码修改成功'})

@user_bp.route('/favorites')
@login_required
def favorites():
    """获取用户收藏的城市列表"""
    favorite_cities = g.user.favorite_cities
    return jsonify([city.to_dict() for city in favorite_cities])

@user_bp.route('/add_favorite/<city_name>', methods=['POST'])
@login_required
def add_favorite(city_name):
    """添加收藏城市"""
    city = City.query.filter_by(name=city_name).first()
    if not city:
        city = City(name=city_name)
        db.session.add(city)
    
    if city not in g.user.favorite_cities:
        g.user.favorite_cities.append(city)
        db.session.commit()
        return jsonify({'success': True, 'message': '添加收藏成功'})
    
    return jsonify({'success': False, 'message': '该城市已在收藏列表中'})

@user_bp.route('/remove_favorite/<city_name>', methods=['POST'])
@login_required
def remove_favorite(city_name):
    """取消收藏城市"""
    city = City.query.filter_by(name=city_name).first()
    if city and city in g.user.favorite_cities:
        g.user.favorite_cities.remove(city)
        db.session.commit()
        return jsonify({'success': True, 'message': '取消收藏成功'})
    
    return jsonify({'success': False, 'message': '该城市不在收藏列表中'}) 