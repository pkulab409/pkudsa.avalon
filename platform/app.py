from flask import Flask, request, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from config.config import Config
from datetime import timedelta, datetime
import logging


from database.base import db, login_manager
from database import initialize_database


# 初始化csrf保护
csrf = CSRFProtect()


# 创建Flask应用
def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    # 初始化 CSRF 保护
    csrf.init_app(app)

    # 初始化数据库 - 只保留一个初始化调用
    initialize_database(app)

    # 清空房间和参与者表
    with app.app_context():
        try:
            # 先删除房间参与者再删除房间(外键约束)
            from database.models import Room, RoomParticipant

            RoomParticipant.query.delete()
            Room.query.delete()
            db.session.commit()
            app.logger.info("已清空房间和参与者表")
        except Exception as e:
            app.logger.error(f"清空房间和参与者表失败: {str(e)}")
            db.session.rollback()

    # 初始化登录管理器
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "请登录以访问此页面"
    login_manager.login_message_category = "warning"
    login_manager.remember_cookie_duration = timedelta(days=7)

    from blueprints.ranking import ranking_bp
    from blueprints.lobby import lobby_bp
    from blueprints.game import game_bp
    from blueprints.main import main_bp
    from blueprints.auth import auth as auth_bp
    from blueprints.profile import profile_bp
    from blueprints.ai import ai_bp
    from blueprints.visualizer import visualizer_bp

    # 将蓝图注册到应用
    app.register_blueprint(main_bp)
    # 除主页面之外均制定前缀
    # 这里的前缀是为了避免与主页面路由冲突
    app.register_blueprint(ranking_bp, url_prefix="/ranking")
    app.register_blueprint(lobby_bp, url_prefix="/lobby")
    app.register_blueprint(game_bp, url_prefix="/game")
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(profile_bp, url_prefix="/profile")
    app.register_blueprint(ai_bp, url_prefix="/ai")
    app.register_blueprint(visualizer_bp, url_prefix="/visualizer")

    # 确保在应用上下文中创建所有表
    with app.app_context():
        db.create_all()

    # 配置日志
    logging.basicConfig(level=app.config["LOG_LEVEL"])
    app.logger.setLevel(app.config["LOG_LEVEL"])
    app.logger.info("Flask app created and configured.")

    return app
