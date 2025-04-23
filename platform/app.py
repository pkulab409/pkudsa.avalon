import os
from flask import Flask, g, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from config.config import Config
from datetime import timedelta, datetime
import logging

# Import db instance from database package
from database import db, initialize_database  # Removed initialize_course_data

# Initialize CSRF protection globally
csrf = CSRFProtect()
# Initialize LoginManager globally
login_manager = LoginManager()


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    # 初始化 CSRF 保护
    csrf.init_app(app)

    # 初始化数据库
    initialize_database(app)

    # 添加数据库迁移支持
    migrate = Migrate(app, db)

    # 初始化登录管理器
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "请登录以访问此页面"
    login_manager.login_message_category = "warning"
    login_manager.remember_cookie_duration = timedelta(days=7)

    from blueprints.ranking import ranking_bp

    from blueprints.lobby import lobby_bp
    from blueprints.match import match_bp
    from blueprints.game import game_bp
    from blueprints.main import main_bp  # 导入 main 蓝图
    from blueprints.auth import auth as auth_bp  # 导入 auth 蓝图
    from blueprints.profile import profile_bp
    from blueprints.ai import ai_bp

    # 将蓝图注册到应用
    app.register_blueprint(main_bp)  # 注册 main 蓝图
    app.register_blueprint(ranking_bp)
    app.register_blueprint(lobby_bp)
    app.register_blueprint(match_bp, url_prefix="/match")
    app.register_blueprint(game_bp, url_prefix="/game")
    app.register_blueprint(auth_bp, url_prefix="/auth")  # 注册 auth 蓝图
    app.register_blueprint(profile_bp, url_prefix="/user")  # 注册 profile 蓝图
    app.register_blueprint(ai_bp, url_prefix="/user")  # 注册 ai 蓝图

    # 确保在应用上下文中创建所有表
    with app.app_context():
        db.create_all()

    # 用户加载函数
    @login_manager.user_loader
    def load_user(user_id):
        from database.models import User  # Import here to avoid circular dependency

        return User.query.get(int(user_id))

    # 配置日志
    logging.basicConfig(level=app.config["LOG_LEVEL"])
    app.logger.setLevel(app.config["LOG_LEVEL"])
    app.logger.info("Flask app created and configured.")

    return app
