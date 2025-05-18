from flask import Flask, request, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from blueprints import ranking
from config.config import Config
from datetime import timedelta, datetime
import logging
import os
import shutil
from utils.battle_manager_utils import init_battle_manager_utils
from utils.automatch_utils import init_automatch_utils, get_automatch

from database.base import db, login_manager
from database import initialize_database
from database import (
    get_user_by_email,
    create_user,
    create_ai_code,
    set_active_ai_code,
    User,
    AICode,
    GameStats,
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
            user = None
            # ================= 用户初始化循环 =================
            for idx, user_config in enumerate(app.config.get("INITIAL_USERS", []), 1):
                try:
                    email = user_config["email"]
                    is_admin = user_config.get("is_admin", False)
                    partition = user_config.get("partition", None)
                    app.logger.info(
                        f"🔧 正在处理用户 {idx}/{len(app.config['INITIAL_USERS'])}: {email}"
                    )

                    # ================= 用户存在性检查 =================
                    existing_user = User.query.filter_by(email=email).first()
                    action = "已存在"

                    if not existing_user:
                        # ================= 创建新用户 =================
                        user = User(
                            username=user_config["username"],
                            email=email,
                            is_admin=is_admin,
                            partition=partition,
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
                            app.logger.warning(
                                f"🛠 更新用户权限: {email} -> 管理员={is_admin}"
                            )

                        # 同步用户名
                        if user.username != user_config["username"]:
                            user.username = user_config["username"]
                            updated = True
                            app.logger.warning(
                                f"🛠 更新用户名: {email} -> {user_config['username']}"
                            )

                        if updated:
                            user.modified_at = datetime.utcnow()
                            db.session.commit()
                            action = "更新"

                    # 确保用户有对应 partition 的 GameStats 记录
                    existing_stats = GameStats.query.filter_by(
                        user_id=user.id, ranking_id=partition
                    ).first()
                    if not existing_stats:
                        stats = GameStats(user_id=user.id, ranking_id=partition)
                        db.session.add(stats)
                        app.logger.info(
                            f"📊 为用户 {email} 创建 ranking_id={partition} 的游戏统计记录"
                        )
                        db.session.flush()

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
                            app.logger.info(
                                f"📄 复制AI代码: {source_path} -> {dest_path}"
                            )
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
                            created_at=datetime.utcnow(),
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


def cleanup_stale_battles(app):
    """在服务器启动时删除所有标记为playing、waiting或cancelled状态的对局"""
    with app.app_context():
        try:
            from database.models import Battle, GameStats, BattlePlayer, db
            from database.action import delete_battle

            # 修改查询条件，也包括已取消的对局
            stale_battles = Battle.query.filter(
                Battle.status.in_(["playing", "waiting", "cancelled"])
            ).all()

            if not stale_battles:
                app.logger.info("✅ 没有发现需要清理的对局")
                return

            app.logger.warning(
                f"⚠️ 发现 {len(stale_battles)} 个需要清理的对局(playing、waiting或cancelled)，开始删除..."
            )

            for battle in stale_battles:
                try:
                    # 先处理日志文件删除（避免删除对局后无法访问ID）
                    data_dir = app.config.get("DATA_DIR", "./data")
                    log_files = [
                        os.path.join(data_dir, f"game_{battle.id}_public.json"),
                        os.path.join(data_dir, f"game_{battle.id}_archive.json"),
                    ]

                    # 处理所有玩家的私有日志
                    for player_id in range(1, 8):  # 假设最多7个玩家
                        log_files.append(
                            os.path.join(
                                data_dir,
                                f"game_{battle.id}_player_{player_id}_private.json",
                            )
                        )

                    # 删除存在的日志文件
                    for log_file in log_files:
                        if os.path.exists(log_file):
                            os.remove(log_file)
                            app.logger.info(f"🗑️ 已删除日志文件: {log_file}")

                    # 处理ELO变化 (恢复所有可能的ELO变化)
                    battle_players = battle.players.all()
                    for bp in battle_players:
                        if bp.elo_change is not None:
                            stats = GameStats.query.filter_by(
                                user_id=bp.user_id, ranking_id=battle.ranking_id
                            ).first()
                            if stats:
                                stats.elo_score -= bp.elo_change
                                db.session.add(stats)

                    # 使用cascade删除选项，直接删除对局及其相关记录
                    app.logger.info(
                        f"🗑️ 开始删除对局 {battle.id} (状态: {battle.status})"
                    )

                    # 使用数据库操作直接删除
                    if delete_battle(battle):
                        app.logger.info(f"✅ 对局 {battle.id} 已成功删除")
                    else:
                        # 如果delete_battle失败，尝试手动删除
                        app.logger.warning(
                            f"⚠️ 使用delete_battle删除失败，尝试手动删除..."
                        )

                        # 先删除所有相关的BattlePlayer记录
                        BattlePlayer.query.filter_by(battle_id=battle.id).delete()

                        # 再删除Battle记录
                        db.session.delete(battle)
                        db.session.commit()
                        app.logger.info(f"✅ 对局 {battle.id} 已手动删除")

                except Exception as e:
                    app.logger.error(
                        f"❌ 删除对局 {battle.id} 时出错: {str(e)}", exc_info=True
                    )
                    db.session.rollback()  # 确保回滚任何失败的事务

            app.logger.info(f"✅ 已完成删除 {len(stale_battles)} 个对局")

        except Exception as e:
            app.logger.critical(
                f"💥 清理对局过程中发生严重错误: {str(e)}", exc_info=True
            )


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    # 初始化 CSRF 保护
    csrf.init_app(app)

    @app.template_filter("color_hash")
    def color_hash(username):
        """生成基于用户名的HSL颜色"""
        hue = hash(username) % 360  # 确保色相值在0-359之间
        return f"hsl({hue}, 70%, 45%)"

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
    from blueprints.performance import performance_bp

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
    app.register_blueprint(performance_bp, url_prefix="/performance")

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

    # 先初始化对战管理器
    init_battle_manager_utils(app)

    # 初始化AutoMatch工具，并确保重启时清理旧状态
    init_automatch_utils(app)
    automatch = get_automatch()
    automatch.terminate_all_and_clear()  # 确保应用启动时没有遗留的运行实例

    # 再清理意外中断的对局
    cleanup_stale_battles(app)

    app.logger.info("Flask应用初始化完成")
    return app
