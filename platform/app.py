from flask import Flask, request, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from config.config import Config
from datetime import timedelta, datetime
import logging
from utils.battle_manager_utils import init_battle_manager_utils

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

    # 初始化登录管理器
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "请登录以访问此页面"
    login_manager.login_message_category = "warning"
    login_manager.remember_cookie_duration = timedelta(days=7)

    from blueprints.ranking import ranking_bp
    from blueprints.game import game_bp
    from blueprints.main import main_bp
    from blueprints.auth import auth as auth_bp
    from blueprints.profile import profile_bp
    from blueprints.ai import ai_bp
    from blueprints.visualizer import visualizer_bp
    from blueprints.docs import docs_bp

    # 将蓝图注册到应用
    app.register_blueprint(main_bp)
    # 除主页面之外均制定前缀
    # 这里的前缀是为了避免与主页面路由冲突
    app.register_blueprint(ranking_bp, url_prefix="/ranking")
    app.register_blueprint(game_bp, url_prefix="/game")
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(profile_bp, url_prefix="/profile")
    app.register_blueprint(ai_bp, url_prefix="/ai")
    app.register_blueprint(visualizer_bp, url_prefix="/visualizer")
    app.register_blueprint(docs_bp, url_prefix="/docs")

    # 确保在应用上下文中创建所有表
    with app.app_context():
        db.create_all()

    # 配置日志
    logging.basicConfig(level=app.config["LOG_LEVEL"])
    app.logger.setLevel(app.config["LOG_LEVEL"])

    # 初始化预设用户和AI代码
    # 使用大写键 'INITIAL_USERS' 访问配置
    if app.config.get("INITIAL_USERS"):
        from database import (
            get_user_by_email,
            create_user,
            create_ai_code,
            set_active_ai_code,
            # 如果需要检查用户是否存在，可能还需要 get_user_by_id
            # get_user_by_id,
        )
        import os
        import shutil

        # 确保数据库操作在应用上下文中执行
        with app.app_context():
            app.logger.info("开始初始化预设用户和AI代码...")

            # 确保上传目录存在
            # 尝试从配置获取上传文件夹，否则使用默认值
            upload_folder = app.config.get(
                "AI_CODE_UPLOAD_FOLDER",
                os.path.join(app.root_path, "uploads", "ai_codes"),
            )
            os.makedirs(upload_folder, exist_ok=True)
            app.logger.info(f"AI 代码上传目录: {upload_folder}")

            # 使用大写键 'INITIAL_USERS' 访问配置
            for user_config in app.config.get("INITIAL_USERS"):
                # 检查用户是否已存在
                existing_user = get_user_by_email(user_config["email"])
                user = existing_user  # 先假设用户已存在

                if not existing_user:
                    # 创建新用户
                    app.logger.info(f"尝试创建新用户: {user_config['username']}")
                    user = create_user(
                        username=user_config["username"],
                        email=user_config["email"],
                        password=user_config["password"],
                    )
                    if user:
                        app.logger.info(
                            f"成功创建初始用户: {user.username} (ID: {user.id})"
                        )
                    else:
                        app.logger.error(f"创建初始用户失败: {user_config['username']}")
                        continue  # 如果用户创建失败，跳过后续AI代码处理
                else:
                    app.logger.info(f"初始用户已存在: {user.username} (ID: {user.id})")

                # 确保 user 对象有效再继续处理 AI 代码
                if user and "ai_code" in user_config:
                    ai_config = user_config["ai_code"]
                    # 检查 AI 代码源文件是否存在
                    source_path = os.path.join(app.root_path, ai_config["file_path"])
                    app.logger.info(f"检查 AI 代码源文件: {source_path}")

                    if os.path.exists(source_path):
                        # 创建用户特定的上传子目录
                        user_upload_dir = os.path.join(upload_folder, user.id)
                        os.makedirs(user_upload_dir, exist_ok=True)

                        # 目标文件名和相对路径
                        filename = os.path.basename(source_path)
                        relative_path = os.path.join(user.id, filename)  # 存储相对路径
                        target_path = os.path.join(upload_folder, relative_path)

                        # 复制 AI 代码文件
                        try:
                            shutil.copy2(source_path, target_path)
                            app.logger.info(f"已将 AI 代码复制到: {target_path}")
                        except Exception as e:
                            app.logger.error(f"复制 AI 代码文件失败: {e}")
                            continue  # 复制失败则跳过数据库记录创建

                        # 创建 AI 代码数据库记录
                        # (可以添加逻辑检查是否已存在同名AI，避免重复创建)
                        ai_code = create_ai_code(
                            user_id=user.id,
                            name=ai_config["name"],
                            code_path=relative_path,  # 存储相对路径
                            description=ai_config.get("description", ""),
                        )

                        if ai_code:
                            app.logger.info(
                                f"为用户 {user.username} 创建 AI 记录: {ai_config['name']} (ID: {ai_code.id})"
                            )
                            # 设置为活跃 AI
                            if ai_config.get("make_active", False):
                                if set_active_ai_code(user.id, ai_code.id):
                                    app.logger.info(
                                        f"已将 AI '{ai_config['name']}' 设置为用户 {user.username} 的活动 AI"
                                    )
                                else:
                                    app.logger.error(
                                        f"设置活动 AI '{ai_config['name']}' 失败"
                                    )
                        else:
                            app.logger.error(
                                f"为用户 {user.username} 创建 AI 数据库记录失败: {ai_config['name']}"
                            )
                    else:
                        app.logger.warning(f"AI 代码源文件不存在，跳过: {source_path}")
            # 日志移到循环外
            app.logger.info("预设用户和AI代码初始化完成。")

    # 在这里初始化 battle manager 工具
    init_battle_manager_utils(app)

    app.logger.info("Flask app created and configured.")

    return app
