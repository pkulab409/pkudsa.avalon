from flask import Flask, request, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from config.config import Config
from datetime import timedelta, datetime
import logging
import os
import shutil
from utils.battle_manager_utils import init_battle_manager_utils

from database.base import db, login_manager
from database import initialize_database
from database import (
    get_user_by_email,
    create_user,
    create_ai_code,
    set_active_ai_code,
    User,
    AICode
)

# 初始化csrf保护
csrf = CSRFProtect()


def initialize_default_data(app):
    """初始化预设用户、管理员和AI代码"""
    with app.app_context():
        try:
            app.logger.info("🚀 开始初始化预设数据...")

            # ================= 初始化准备 =================
            upload_folder = app.config.get(
                "AI_CODE_UPLOAD_FOLDER",
                os.path.join(app.root_path, "uploads", "ai_codes"),
            )
            os.makedirs(upload_folder, exist_ok=True)
            app.logger.info(f"📁 创建AI代码上传目录: {upload_folder}")

            admin_count = 0
            total_users = 0
            admin_emails = []

            # ================= 用户初始化循环 =================
            for idx, user_config in enumerate(app.config.get("INITIAL_USERS", []), 1):
                try:
                    email = user_config["email"]
                    is_admin = user_config.get("is_admin", False)
                    app.logger.info(f"🔧 正在处理用户 {idx}/{len(app.config['INITIAL_USERS'])}: {email}")

                    # ================= 用户存在性检查 =================
                    existing_user = User.query.filter_by(email=email).first()
                    action = "已存在"

                    if not existing_user:
                        # ================= 创建新用户 =================
                        user = User(
                            username=user_config["username"],
                            email=email,
                            is_admin=is_admin,
                            created_at=datetime.utcnow(),
                        )
                        user.set_password(user_config["password"])
                        db.session.add(user)
                        db.session.flush()  # 获取ID但不提交事务
                        action = "创建"
                        total_users += 1

                        if is_admin:
                            admin_count += 1
                            admin_emails.append(email)
                            app.logger.warning(f"⚠️ 新建管理员账户: {email}")
                    else:
                        # ================= 更新现有用户 =================
                        user = existing_user
                        updated = False

                        # 同步管理员状态
                        if user.is_admin != is_admin:
                            user.is_admin = is_admin
                            updated = True
                            app.logger.warning(f"🛠 更新用户权限: {email} -> 管理员={is_admin}")

                        # 同步用户名
                        if user.username != user_config["username"]:
                            user.username = user_config["username"]
                            updated = True
                            app.logger.warning(f"🛠 更新用户名: {email} -> {user_config['username']}")

                        if updated:
                            user.modified_at = datetime.utcnow()
                            db.session.commit()
                            action = "更新"

                    # ================= AI代码处理 =================
                    ai_config = user_config.get("ai_code")
                    if ai_config and ai_config.get("file_path"):
                        if is_admin and not ai_config.get("make_active", False):
                            app.logger.info(f"⏭ 跳过管理员 {email} 的AI代码初始化")
                            continue

                        # 安全路径验证
                        source_path = os.path.abspath(
                            os.path.join(app.root_path, ai_config["file_path"])
                        )
                        if not source_path.startswith(os.path.abspath(app.root_path)):
                            app.logger.error(f"❌ 非法文件路径: {source_path}")
                            continue

                        if not os.path.exists(source_path):
                            app.logger.warning(f"⚠️ AI代码源文件不存在: {source_path}")
                            continue

                        # 创建用户上传目录
                        user_dir = os.path.join(upload_folder, str(user.id))
                        os.makedirs(user_dir, exist_ok=True)

                        # 复制文件
                        filename = os.path.basename(source_path)
                        dest_path = os.path.join(user_dir, filename)
                        try:
                            shutil.copy(source_path, dest_path)
                            app.logger.info(f"📄 复制AI代码: {source_path} -> {dest_path}")
                        except Exception as e:
                            app.logger.error(f"❌ 文件复制失败: {str(e)}")
                            continue

                        # 创建AI记录
                        ai = AICode(
                            user_id=user.id,
                            name=ai_config["name"],
                            code_path=os.path.join(str(user.id), filename),
                            description=ai_config.get("description", ""),
                            is_active=ai_config.get("make_active", False),
                            created_at=datetime.utcnow()
                        )
                        db.session.add(ai)

                    db.session.commit()

                except KeyError as e:
                    db.session.rollback()
                    app.logger.error(f"❌ 配置格式错误: 缺少字段 {str(e)}")
                except Exception as e:
                    db.session.rollback()
                    app.logger.error(f"❌ 初始化用户 {email} 失败: {str(e)}")

            # ================= 最终安全检查 =================
            app.logger.info(f"✅ 初始化完成！共处理 {total_users} 个新用户")

        except Exception as e:
            app.logger.critical(f"💥 初始化过程严重失败: {str(e)}")
            raise


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    # 初始化 CSRF 保护
    csrf.init_app(app)

    # 初始化数据库
    initialize_database(app)

    # 初始化登录管理器
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "请登录以访问此页面"
    login_manager.login_message_category = "warning"
    login_manager.remember_cookie_duration = timedelta(days=7)

    # 注册蓝图
    from blueprints.ranking import ranking_bp
    from blueprints.game import game_bp
    from blueprints.main import main_bp
    from blueprints.auth import auth as auth_bp
    from blueprints.profile import profile_bp
    from blueprints.ai import ai_bp
    from blueprints.visualizer import visualizer_bp
    from blueprints.docs import docs_bp
    from blueprints.admin import admin_bp

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
    app.register_blueprint(admin_bp)

    # 创建数据库表
    with app.app_context():
        db.create_all()

    # 配置日志
    logging.basicConfig(level=app.config["LOG_LEVEL"])
    app.logger.setLevel(app.config["LOG_LEVEL"])

    # 初始化预设数据
    if app.config.get("INITIAL_USERS"):
        app.logger.info("⚙️ 发现 INITIAL_USERS 配置，开始执行初始化...")
        try:
            initialize_default_data(app)
        except RuntimeError as e:
            app.logger.critical(f"应用启动失败: {str(e)}")
            raise
    else:
        app.logger.warning("⚠️ 未检测到 INITIAL_USERS 配置，跳过初始化用户流程。")

    # 初始化对战管理器
    init_battle_manager_utils(app)

    app.logger.info("Flask应用初始化完成")
    return app
