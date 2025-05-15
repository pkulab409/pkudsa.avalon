# admin.py 完整代码
from datetime import datetime
import logging
import sys
from flask import Blueprint, request, jsonify, render_template, abort
from flask_login import login_required, current_user
from functools import wraps
from sqlalchemy.orm import joinedload
from database.models import User, Battle, GameStats, AICode, BattlePlayer
from database import db
from utils.automatch_utils import get_automatch

# 管理员蓝图
admin_bp = Blueprint("admin", __name__)

# 日志配置
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@admin_bp.errorhandler(400)
@admin_bp.errorhandler(403)
@admin_bp.errorhandler(404)
@admin_bp.errorhandler(500)
def handle_errors(e):
    """统一错误处理器（强制返回JSON）"""
    return (
        jsonify(
            {
                "error": e.name,
                "message": (
                    e.description.split(": ")[-1]
                    if ":" in e.description
                    else e.description
                ),
            }
        ),
        e.code,
    )


def admin_required(f):
    """管理员权限装饰器"""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403, description="管理员权限不足")
        return f(*args, **kwargs)

    return decorated


@admin_bp.route("/admin/delete_user/<uuid:user_id>", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    try:
        target = User.query.get_or_404(str(user_id))
        admin_id = User.query.get_or_404(str(user_id))

        if target.is_admin:
            abort(403, description="不能删除其他管理员账户")

        # 0. 转移用户创建的对战到管理员（假设Battle模型有creator_id字段）
        from database.models import Battle

        user_created_battles = Battle.query.filter_by(creator_id=target.id).all()
        for battle in user_created_battles:
            battle.creator_id = admin_id  # 转移给管理员
            db.session.add(battle)

        # 1. 处理用户关联的AI代码和BattlePlayer记录
        ai_code_ids = [ai.id for ai in AICode.query.filter_by(user_id=target.id).all()]

        # 删除AI代码关联的BattlePlayer（不触发ELO回滚）
        BattlePlayer.query.filter(
            BattlePlayer.selected_ai_code_id.in_(ai_code_ids)
        ).delete(synchronize_session=False)
        # 删除用户AI代码
        AICode.query.filter_by(user_id=target.id).delete(synchronize_session=False)
        # 删除用户参与的BattlePlayer（不触发ELO变化）
        BattlePlayer.query.filter_by(user_id=target.id).delete(
            synchronize_session=False
        )

        # 2. 删除用户统计数据
        GameStats.query.filter_by(user_id=target.id).delete()

        # 3. 清理无玩家的空对战（保持数据整洁）
        empty_battles = Battle.query.filter(~Battle.players.any()).all()
        for battle in empty_battles:
            db.session.delete(battle)

        # 4. 删除用户本身
        db.session.delete(target)
        db.session.commit()

        # 5. 触发前端对战列表更新（通过WebSocket或轮询机制）
        # 示例：假设使用Flask-SocketIO广播更新
        from flask_socketio import emit

        emit(
            "battles_updated",
            {"action": "user_deleted"},
            namespace="/battles",
            broadcast=True,
        )

        return (
            jsonify(
                {
                    "message": "用户及关联数据已删除",
                    "details": {
                        "deleted_ai_codes": len(ai_code_ids),
                        "transferred_battles": len(user_created_battles),
                        "cleaned_empty_battles": len(empty_battles),
                    },
                }
            ),
            200,
        )

    except Exception as e:
        db.session.rollback()
        logging.error(f"删除用户失败: {str(e)}", exc_info=True)
        abort(500, description=f"删除失败: {str(e)}")


@admin_bp.route("/admin/set_elo/<string:user_id>", methods=["POST"])
@login_required
@admin_required
def set_elo(user_id):
    try:
        data = request.get_json()
        if not data or "elo" not in data:
            abort(400, description="请求需要包含elo参数")

        u = User.query.get_or_404(user_id)
        new_elo = int(data["elo"])

        stats = GameStats.query.filter_by(user_id=u.id).first()
        if not stats:
            stats = GameStats(user_id=u.id, elo_score=new_elo)
            db.session.add(stats)
        else:
            stats.elo_score = new_elo

        db.session.commit()
        return jsonify({"message": f"Elo已更新为{new_elo}"}), 200

    except ValueError:
        abort(400, description="Elo必须是整数")
    except Exception as e:
        db.session.rollback()
        logging.error(f"设置Elo失败: {str(e)}")
        abort(500, description="服务器内部错误")


@admin_bp.route("/admin/terminate_game/<string:game_id>", methods=["POST"])
@login_required
@admin_required
def terminate_game(game_id):
    try:
        game = Battle.query.get_or_404(game_id)
        if game.status != "playing":
            abort(400, description="只能终止进行中的对局")

        # 使用battle_manager取消对战，确保状态在所有地方一致
        from utils.battle_manager_utils import get_battle_manager

        battle_manager = get_battle_manager()

        # 调用battle_manager的cancel_battle方法
        reason = f"由管理员 {current_user.username} 手动终止"
        if battle_manager.cancel_battle(game_id, reason):
            logging.info(f"对战 {game_id} 已成功取消: {reason}")

            # 处理ELO变化（如果有）
            battle_players = game.players.all()
            for bp in battle_players:
                if bp.elo_change is not None:
                    stats = GameStats.query.filter_by(user_id=bp.user_id).first()
                    if stats:
                        stats.elo_score -= bp.elo_change
                bp.outcome = "cancelled"
                bp.elo_change = None
                db.session.add(bp)

            # 确保对局结束时间设置
            if not game.ended_at:
                game.ended_at = datetime.now()
                db.session.add(game)

            db.session.commit()

            return (
                jsonify(
                    {
                        "message": "对局已终止",
                        "details": {
                            "battle_id": game.id,
                            "cancelled_at": (
                                game.ended_at.isoformat()
                                if game.ended_at
                                else datetime.now().isoformat()
                            ),
                            "affected_players": [bp.user_id for bp in battle_players],
                        },
                    }
                ),
                200,
            )
        else:
            abort(500, description=f"取消对战失败，请检查战局状态")

    except Exception as e:
        db.session.rollback()
        logging.error(f"终止对局失败: {str(e)}", exc_info=True)
        abort(500, description=f"终止对局失败: {str(e)}")


@admin_bp.route("/admin/delete_game/<string:game_id>", methods=["POST"])
@login_required
@admin_required
def delete_game(game_id):
    try:
        game = Battle.query.get_or_404(game_id)
        allowed_statuses = ["completed", "cancelled", "error"]
        if game.status not in allowed_statuses:
            abort(400, description="只能删除已结束的对局")

        battle_players = game.players.all()
        for bp in battle_players:
            if bp.elo_change is not None and bp.user:
                stats = GameStats.query.filter_by(user_id=bp.user.id).first()
                if stats:
                    stats.elo_score -= bp.elo_change
                    db.session.add(stats)

        db.session.delete(game)
        db.session.commit()
        return jsonify({"message": "对局已删除并恢复Elo"}), 200

    except Exception as e:
        db.session.rollback()
        logging.error(f"删除对局失败: {str(e)}")
        abort(500, description=f"删除对局失败: {str(e)}")


@admin_bp.route("/admin/start_auto_match", methods=["POST"])
@admin_required
def start_auto_match():
    automatch = get_automatch()
    if automatch.start():
        return (
            jsonify(
                {
                    "status": "success",
                    "message": "后台自动对战已启动",
                }
            ),
            200,
        )
    else:
        return jsonify({"status": "error", "message": f"后台自动对战已在运行."}), 500


@admin_bp.route("/admin/stop_auto_match", methods=["POST"])
@admin_required
def stop_auto_match():
    automatch = get_automatch()
    if automatch.stop():
        return (
            jsonify(
                {
                    "status": "success",
                    "message": "后台自动对战已停止",
                }
            ),
            200,
        )
    else:
        return jsonify({"status": "error", "message": f"后台自动对战未在运行."}), 500


@admin_bp.route("/admin/terminate_auto_match", methods=["POST"])
@admin_required
def terminate_auto_match():
    automatch = get_automatch()
    automatch.terminate()
    return (
        jsonify(
            {
                "status": "success",
                "message": "后台自动对战已终止并重置",
            }
        ),
        200,
    )


@admin_bp.route("/admin/toggle_admin/<string:user_id>", methods=["POST"])
@login_required
@admin_required
def toggle_admin(user_id):
    try:
        target = User.query.get_or_404(str(user_id))
        if target.id == current_user.id:
            abort(400, description="不能修改自己的管理员状态")

        target.is_admin = not target.is_admin
        db.session.commit()

        action = "授予" if target.is_admin else "撤销"
        return (
            jsonify({"message": f"管理员权限已{action}", "is_admin": target.is_admin}),
            200,
        )

    except Exception as e:
        db.session.rollback()
        logging.error(f"修改管理员权限失败: {str(e)}")
        abort(500, description=f"操作失败: {str(e)}")


@admin_bp.route("/admin/users")
@login_required
@admin_required
def get_users():
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)

        users = User.query.options(joinedload(User.game_stats)).paginate(
            page=page, per_page=per_page
        )

        return (
            jsonify(
                {
                    "users": [
                        {
                            "id": user.id,
                            "username": user.username,
                            "email": user.email,
                            "is_admin": user.is_admin,
                            "elo": user.game_stats.elo_score if user.game_stats else 0,
                        }
                        for user in users.items
                    ],
                    "total_pages": users.pages,
                    "current_page": users.page,
                    "total_users": users.total,
                }
            ),
            200,
        )

    except Exception as e:
        logging.error(f"获取用户列表失败: {str(e)}")
        abort(500, description="获取用户列表失败")


@admin_bp.route("/admin/dashboard")
@login_required
@admin_required
def admin_dashboard():
    # 新增分页参数处理
    page = request.args.get("page", 1, type=int)
    per_page = 10  # 每页显示15个用户

    # 修改查询方式为分页查询
    users_pagination = User.query.order_by(User.username.asc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template(
        "admin/dashboard.html",
        users=users_pagination,
        current_page=page,
        total_pages=users_pagination.pages,
    )


@admin_bp.route("/admin/search_user", methods=["GET"])
@login_required
@admin_required
def search_user():
    try:
        username = request.args.get("username")
        if not username:
            abort(400, description="用户名参数缺失")
        # 模糊搜索并限制结果数量
        users = User.query.filter(User.username.ilike(f"%{username}%")).limit(10).all()
        return (
            jsonify(
                {
                    "users": [
                        {
                            "id": user.id,
                            "username": user.username,
                            "is_admin": user.is_admin,
                            "elo": user.game_stats.elo_score if user.game_stats else 0,
                        }
                        for user in users
                    ]
                }
            ),
            200,
        )
    except Exception as e:
        logging.error(f"搜索用户失败: {str(e)}")
        abort(500, description="搜索用户失败")
