# author: shihuaidexianyu (refactored by AI assistant)
# date: 2025-04-25
# status: need to be modified
# description: 游戏相关的蓝图，包含对战大厅、创建对战、查看对战详情等功能。


import logging, json, os
from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
    current_app,
    jsonify,
    send_file,
)
from flask_login import login_required, current_user


# 导入新的数据库操作和模型
from database import (
    get_user_by_id,
    get_ai_code_by_id,
    get_user_active_ai_code,
    create_battle as db_create_battle,
    get_battle_by_id as db_get_battle_by_id,
    get_battle_players_for_battle as db_get_battle_players_for_battle,
    get_user_ai_codes as db_get_user_ai_codes,
    get_battles_paginated_filtered,
)
from database.models import Battle, BattlePlayer, User, AICode
from utils.battle_manager_utils import get_battle_manager
from utils.automatch_utils import get_automatch
from datetime import datetime # For date filtering
game_bp = Blueprint("game", __name__)
logger = logging.getLogger(__name__)

# =================== 页面路由 ===================


@game_bp.route("/lobby")
@login_required
def lobby():
    """显示游戏大厅页面，列出最近的对战，支持筛选和分页"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)  # Or your preferred default
    status_filter = request.args.get('status', None, type=str)
    date_from_str = request.args.get('date_from', None, type=str)
    date_to_str = request.args.get('date_to', None, type=str)

    # Get multiple players (can be passed as a list from form)
    player_filters = request.args.getlist('players')  # Use getlist to get all values with the same name

    filters = {}
    if status_filter and status_filter != 'all':  # 'all' means no status filter
        filters['status'] = status_filter

    try:
        if date_from_str:
            filters['date_from'] = datetime.strptime(date_from_str, '%Y-%m-%d')
        if date_to_str:
            # Adjust to include the whole day
            filters['date_to'] = datetime.strptime(date_to_str + " 23:59:59", '%Y-%m-%d %H:%M:%S')
    except ValueError:
        flash('日期格式无效，请使用 YYYY-MM-DD 格式。', 'danger')
        filters.pop('date_from', None)
        filters.pop('date_to', None)

    if player_filters:
        # Pass the list of player filters to the database function
        filters['players'] = player_filters  # Now passing a list of players instead of a single player

    # Fetch battles using the enhanced database function
    battles_pagination = get_battles_paginated_filtered(
        filters=filters,
        page=page,
        per_page=per_page
    )

    # Fetch all users for the datalist suggestion
    all_users = User.query.order_by(User.username).all()

    return render_template(
        "lobby.html",
        battles_pagination=battles_pagination,
        automatch_is_on=get_automatch().is_on,
        all_users=all_users,
        current_filters={  # Pass current filters back to the template
            'status': status_filter,
            'date_from': date_from_str,
            'date_to': date_to_str,
            'players': player_filters  # Now passing the list of players back to the template
        }
    )


@game_bp.route("/create_battle_page")
@login_required
def create_battle_page():
    """显示创建对战页面"""
    # 获取当前用户的所有AI代码供选择
    user_ai_codes = db_get_user_ai_codes(current_user.id)
    # 获取所有用户（或一部分用户）作为潜在的AI对手
    # 注意：实际应用中可能需要更复杂的对手选择机制，例如好友、排行榜用户等
    potential_opponents = User.query.filter(User.id != current_user.id).all()
    return render_template(
        "create_battle.html",  # 需要创建 create_battle.html
        user_ai_codes=user_ai_codes,
        potential_opponents=potential_opponents,
    )


@game_bp.route("/api/battle/<int:battle_id>/status")
@login_required
def check_battle_status(battle_id):
    battle = db_get_battle_by_id(battle_id)
    if not battle:
        return jsonify({"error": "Battle not found"}), 404
    return jsonify({"status": battle.status})


@game_bp.route("/battle/<string:battle_id>")
@login_required
def view_battle(battle_id):
    """显示对战详情页面（进行中或已完成）"""
    battle = db_get_battle_by_id(battle_id)
    if not battle:
        flash("对战不存在", "danger")
        return redirect(url_for("game.lobby"))

    battle_players = db_get_battle_players_for_battle(battle_id)

    # 检查当前用户是否参与了此对战，以决定是否显示私有信息（如果需要）
    is_participant = any(bp.user_id == current_user.id for bp in battle_players)

    # 如果游戏已完成，可以传递结果给模板
    game_result = {"roles": {}}  # 初始化为带有空roles字典的对象
    error_info = {}
    if battle.status == "completed" or battle.status == "error":
        # battle.results 存储了JSON字符串
        try:
            if battle.results:
                game_result = json.loads(battle.results)
                # 确保game_result有roles键，即使它是空的
                if "roles" not in game_result:
                    game_result["roles"] = {}

            if battle.status == "error":
                # 验证公共日志文件路径
                PUBLIC_LIB_FILE_DIR = game_result.get("public_log_file")
                if not PUBLIC_LIB_FILE_DIR:
                    logger.error(f"[Battle {battle_id}] 缺少公共日志文件路径")
                    error_info["error_msg"] = (
                        "无法获取对战详细错误信息：缺少日志文件路径"
                    )
                else:
                    # 读取公共日志获取错误玩家
                    try:
                        with open(PUBLIC_LIB_FILE_DIR, "r", encoding="utf-8") as plib:
                            data = json.load(plib)
                            # 从日志中查找错误记录（从后向前搜索）
                            error_record = None
                            for record in reversed(data):
                                if "type" in record and record["type"] in [
                                    "critical_player_ERROR",
                                    "player_ruturn_ERROR",
                                ]:
                                    error_record = record
                                    break

                            if error_record:
                                error_pid_in_game = error_record.get("error_code_pid")
                                if (
                                    error_pid_in_game is not None
                                    and 1 <= error_pid_in_game <= 7
                                ):
                                    error_type = error_record.get("type")
                                    error_code_method = error_record.get(
                                        "error_code_method"
                                    )
                                    error_msg = error_record.get("error_msg")

                                    # 提取错误玩家的用户ID
                                    err_player_index = error_pid_in_game - 1
                                    if err_player_index < len(battle_players):
                                        err_user_id = battle_players[
                                            err_player_index
                                        ].user_id

                                        # 获取玩家信息
                                        err_user = get_user_by_id(err_user_id)
                                        err_username = (
                                            err_user.username
                                            if err_user
                                            else f"玩家 {err_user_id}"
                                        )

                                        # 包装错误信息
                                        error_info["error_type"] = error_type
                                        error_info["error_user_id"] = err_user_id
                                        error_info["error_username"] = err_username
                                        error_info["error_pid_in_game"] = (
                                            error_pid_in_game
                                        )
                                        error_info["error_code_method"] = (
                                            error_code_method
                                        )
                                        error_info["error_msg"] = error_msg

                                        # 计算ELO扣分
                                        err_player = next(
                                            (
                                                bp
                                                for bp in battle_players
                                                if bp.user_id == err_user_id
                                            ),
                                            None,
                                        )
                                        if err_player:
                                            error_info["elo_initial"] = (
                                                err_player.initial_elo
                                            )
                                            error_info["elo_change"] = (
                                                err_player.elo_change
                                            )
                                            error_info["elo_final"] = (
                                                err_player.initial_elo
                                                + err_player.elo_change
                                            )

                                        # 优化错误信息显示（针对常见错误类型）
                                        if error_code_method == "walk":
                                            if "direction type" in error_msg:
                                                error_info["friendly_msg"] = (
                                                    "移动方向必须是字符串类型（如'up'、'down'、'left'、'right'），而非数字或其他类型"
                                                )
                                            elif "invalid move" in error_msg:
                                                error_info["friendly_msg"] = (
                                                    "移动方向无效，必须是'up'、'down'、'left'、'right'之一"
                                                )
                                            elif "occupied position" in error_msg:
                                                error_info["friendly_msg"] = (
                                                    "移动位置已被其他玩家占据"
                                                )
                                            else:
                                                error_info["friendly_msg"] = (
                                                    "移动操作出现错误"
                                                )
                                        elif (
                                            error_code_method == "decide_mission_member"
                                        ):
                                            if "non-list" in error_msg:
                                                error_info["friendly_msg"] = (
                                                    "选择队员函数必须返回列表类型"
                                                )
                                            elif "invalid member" in error_msg:
                                                error_info["friendly_msg"] = (
                                                    "选择的队员ID无效，必须是1-7之间的整数"
                                                )
                                            elif "duplicate member" in error_msg:
                                                error_info["friendly_msg"] = (
                                                    "选择了重复的队员"
                                                )
                                            elif "many(few)" in error_msg:
                                                error_info["friendly_msg"] = (
                                                    "选择的队员数量不符合要求"
                                                )
                                            else:
                                                error_info["friendly_msg"] = (
                                                    "队伍选择操作出现错误"
                                                )
                                        elif error_code_method == "mission_vote2":
                                            if "non-bool" in error_msg:
                                                error_info["friendly_msg"] = (
                                                    "任务投票必须返回布尔值（True/False）"
                                                )
                                            elif (
                                                "Blue player" in error_msg
                                                and "against execution" in error_msg
                                            ):
                                                error_info["friendly_msg"] = (
                                                    "蓝方玩家不允许对任务投失败票"
                                                )
                                            else:
                                                error_info["friendly_msg"] = (
                                                    "任务投票操作出现错误"
                                                )
                                        elif error_code_method == "say":
                                            if "non-string speech" in error_msg:
                                                error_info["friendly_msg"] = (
                                                    "发言函数必须返回字符串"
                                                )
                                            else:
                                                error_info["friendly_msg"] = (
                                                    "发言操作出现错误"
                                                )
                                        elif error_code_method == "assass":
                                            if "invalid target" in error_msg:
                                                error_info["friendly_msg"] = (
                                                    "刺杀目标无效，必须是1-7之间的整数（且不能是自己）"
                                                )
                                            elif "targeted himself" in error_msg:
                                                error_info["friendly_msg"] = (
                                                    "刺客不能刺杀自己"
                                                )
                                            else:
                                                error_info["friendly_msg"] = (
                                                    "刺杀操作出现错误"
                                                )
                                        elif error_code_method == "__init__":
                                            error_info["friendly_msg"] = (
                                                "AI代码初始化失败，这可能是由于代码语法错误或类定义问题"
                                            )
                                        else:
                                            # 通用错误提示
                                            error_info["friendly_msg"] = (
                                                f"AI代码在执行 {error_code_method} 函数时出现错误"
                                            )
                                    else:
                                        error_info["error_msg"] = (
                                            f"无法识别玩家：索引 {err_player_index} 超出范围"
                                        )
                                else:
                                    error_info["error_msg"] = (
                                        f"无效的错误玩家PID: {error_pid_in_game}"
                                    )
                            else:
                                # 如果找不到标准错误记录，尝试查找最后一条记录
                                last_record = data[-1] if data else None
                                if last_record and "error" in str(last_record):
                                    error_info["error_msg"] = (
                                        f"游戏错误: {last_record.get('error', '未知错误')}"
                                    )

                                    # 尝试从错误消息提取更多信息
                                    if isinstance(last_record.get("error"), str):
                                        error_msg = last_record.get("error")

                                        # 尝试从错误消息中提取玩家ID
                                        import re

                                        player_match = re.search(
                                            r"Player (\d+)", error_msg
                                        )
                                        if player_match:
                                            try:
                                                pid = int(player_match.group(1))
                                                if 1 <= pid <= 7 and pid - 1 < len(
                                                    battle_players
                                                ):
                                                    err_user_id = battle_players[
                                                        pid - 1
                                                    ].user_id
                                                    err_user = get_user_by_id(
                                                        err_user_id
                                                    )
                                                    error_info["error_user_id"] = (
                                                        err_user_id
                                                    )
                                                    error_info["error_username"] = (
                                                        err_user.username
                                                        if err_user
                                                        else f"玩家 {err_user_id}"
                                                    )
                                                    error_info["error_pid_in_game"] = (
                                                        pid
                                                    )

                                                    # 尝试提取错误方法
                                                    method_match = re.search(
                                                        r"method '([^']+)'|executing ([^ ]+)",
                                                        error_msg,
                                                    )
                                                    if method_match:
                                                        method = method_match.group(
                                                            1
                                                        ) or method_match.group(2)
                                                        error_info[
                                                            "error_code_method"
                                                        ] = method

                                                        # 添加友好错误消息
                                                        if "walk" in method:
                                                            error_info[
                                                                "friendly_msg"
                                                            ] = "移动操作出现错误"
                                                        elif "mission" in method:
                                                            error_info[
                                                                "friendly_msg"
                                                            ] = "任务相关操作出现错误"
                                                        else:
                                                            error_info[
                                                                "friendly_msg"
                                                            ] = f"AI代码在执行 {method} 函数时出现错误"
                                            except (ValueError, IndexError) as e:
                                                logger.error(
                                                    f"[Battle {battle_id}] 尝试提取玩家ID时出错: {str(e)}"
                                                )
                                else:
                                    error_info["error_msg"] = "未找到具体错误信息"
                    except Exception as e:
                        logger.error(
                            f"[Battle {battle_id}] 读取公共日志失败: {str(e)}",
                            exc_info=True,
                        )
                        error_info["error_msg"] = f"读取错误日志失败: {str(e)}"

        except Exception as e:
            logger.error(
                f"无法解析对战 {battle_id} 的结果JSON: {str(e)}", exc_info=True
            )
            game_result = {"error": "结果解析失败", "roles": {}}  # 确保有roles键
            error_info["error_msg"] = f"结果解析失败: {str(e)}"

    # 根据状态渲染不同模板或页面部分
    if battle.status in ["waiting", "playing"]:
        return render_template(
            "battle_ongoing.html",
            battle=battle,
            battle_players=battle_players,
            is_participant=is_participant,
        )  # 需要创建 battle_ongoing.html
    elif battle.status in ["completed", "error", "cancelled"]:
        # 对于已完成的游戏，重定向到回放页面可能更好
        # return redirect(url_for('visualizer.game_replay', battle_id=battle_id))
        # 或者渲染一个包含结果摘要和回放链接的页面
        return render_template(
            "battle_completed.html",
            battle=battle,
            battle_players=battle_players,
            game_result=game_result,
            error_info=error_info,  # 如果没有报错， error_info 是空字典
        )  # 需要创建 battle_completed.html
    else:
        flash(f"未知的对战状态: {battle.status}", "warning")
        return redirect(url_for("game.lobby"))


# =================== API 路由 ===================


@game_bp.route("/create_battle", methods=["POST"])
@login_required
def create_battle_action():
    """处理创建对战的请求"""
    try:
        data = request.get_json()
        # 添加日志记录收到的原始数据
        current_app.logger.info(f"收到创建对战请求数据: {data}")

        if not data:
            current_app.logger.warning("创建对战请求未收到JSON数据")  # 修改日志记录器
            return jsonify({"success": False, "message": "无效的请求数据"})

        # participant_data: [{'user_id': '...', 'ai_code_id': '...'}, ...]
        participant_data = data.get("participants")
        # 添加日志记录解析后的参与者数据
        current_app.logger.info(f"解析后的参与者数据: {participant_data}")

        if not participant_data or not isinstance(participant_data, list):
            current_app.logger.warning(
                "创建对战请求缺少或格式错误的参与者信息"
            )  # 修改日志记录器
            return jsonify({"success": False, "message": "缺少参与者信息"})

        # 验证参与者数据
        # 至少需要当前用户
        if not any(p.get("user_id") == current_user.id for p in participant_data):
            current_app.logger.warning(
                f"创建对战请求中不包含当前用户 {current_user.id}"
            )  # 修改日志记录器
            return jsonify({"success": False, "message": "当前用户必须参与对战"})

        # 这里可以做初步检查
        if len(participant_data) != 7:  # 阿瓦隆固定7人
            current_app.logger.warning(
                f"创建对战请求参与者数量不是7: {len(participant_data)}"
            )  # 修改日志记录器
            return jsonify({"success": False, "message": "阿瓦隆对战需要正好7位参与者"})

        for p_data in participant_data:
            if not p_data.get("user_id") or not p_data.get("ai_code_id"):
                # 添加更详细的日志
                current_app.logger.warning(
                    f"创建对战请求中发现不完整的参与者数据: {p_data}"
                )
                return jsonify({"success": False, "message": "参与者信息不完整"})
            # 可以在这里添加更多验证，例如检查AI代码是否属于对应用户

        # 调用数据库操作创建 Battle 和 BattlePlayer 记录
        # 使用 db_ 前缀以明确区分
        battle = db_create_battle(participant_data, status="waiting")

        if battle:
            current_app.logger.info(
                f"用户 {current_user.id} 创建对战 {battle.id} 成功"
            )  # 修改日志记录器
            # 对战创建成功后，可以立即开始，或者等待某种触发条件
            # 这里我们假设创建后就尝试启动
            battle_manager = get_battle_manager()
            start_success = battle_manager.start_battle(battle.id, participant_data)

            if start_success:
                return jsonify(
                    {
                        "success": True,
                        "battle_id": battle.id,
                        "message": "对战已创建并开始",
                    }
                )
            else:
                # 如果启动失败，可能需要更新 battle 状态为 error 或 cancelled
                # db_update_battle(battle, status='error', results=json.dumps({'error': '启动失败'}))
                current_app.logger.error(
                    f"对战 {battle.id} 创建成功但启动失败"
                )  # 修改日志记录器
                return jsonify(
                    {
                        "success": False,
                        "battle_id": battle.id,
                        "message": "对战创建成功但启动失败",
                    }
                )
        else:
            # db_create_battle 内部会记录详细错误
            current_app.logger.error(
                f"用户 {current_user.id} 创建对战数据库记录失败"
            )  # 修改日志记录器
            return jsonify({"success": False, "message": "创建对战数据库记录失败"})

    except Exception as e:
        current_app.logger.exception(
            f"创建对战时发生未预料的错误: {e}"
        )  # 修改日志记录器
        return jsonify({"success": False, "message": f"服务器内部错误: {str(e)}"})


@game_bp.route("/get_game_status/<string:battle_id>", methods=["GET"])
@login_required
def get_game_status(battle_id):
    """获取游戏状态、快照和结果"""
    try:
        battle_manager = get_battle_manager()

        # 获取对战状态
        status = battle_manager.get_battle_status(battle_id)  # 需要进一步修改
        if status is None:  # 注意：get_battle_status 可能返回 None
            # 尝试从数据库获取状态，以防 battle_manager 重启丢失内存状态
            battle = db_get_battle_by_id(battle_id)
            if battle:
                status = battle.status
            else:
                return jsonify({"success": False, "message": "对战不存在"})

        # 获取对战快照 (只对进行中的游戏有意义)
        snapshots = []
        if status == "playing":  # 或者 'running' 取决于 battle_manager 的状态定义
            snapshots = battle_manager.get_snapshots_queue(battle_id)

        # 如果对战已完成，获取结果
        result = None
        if status == "completed":
            result = battle_manager.get_battle_result(battle_id)
            # {"winner": "blue" / "red"}
            # 如果内存中没有结果，尝试从数据库加载
            if result is None:
                battle = db_get_battle_by_id(battle_id)
                if battle and battle.results:
                    try:
                        result = json.loads(battle.results)
                    except json.JSONDecodeError:
                        result = {"error": "无法解析数据库中的结果"}
                elif battle:
                    result = {"message": "数据库中无详细结果"}

            snapshots = battle_manager.get_snapshots_archive(battle_id)

        return jsonify(
            {
                "success": True,
                "status": status,
                "snapshots": snapshots,
                "result": result,
            }
        )

    except Exception as e:
        current_app.logger.error(f"获取游戏状态失败: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": f"获取游戏状态失败: {str(e)}"})


# 可能需要添加获取对战列表的API
@game_bp.route("/get_battles", methods=["GET"])
@login_required
def get_battles():
    """获取对战列表（例如，最近的、进行中的）"""
    # 可以根据需要组合不同状态的对战
    recent_completed = db_get_recent_battles(limit=10)
    # playing_battles = Battle.query.filter_by(status='playing').order_by(Battle.started_at.desc()).limit(10).all()
    # waiting_battles = Battle.query.filter_by(status='waiting').order_by(Battle.created_at.desc()).limit(10).all()

    # 简化：只返回最近完成的
    battles_data = []
    for battle in recent_completed:
        players_info = [
            bp.to_dict() for bp in db_get_battle_players_for_battle(battle.id)
        ]
        battles_data.append(
            {
                "id": battle.id,
                "status": battle.status,
                "created_at": (
                    battle.created_at.isoformat() if battle.created_at else None
                ),
                "ended_at": battle.ended_at.isoformat() if battle.ended_at else None,
                "players": players_info,
                # 可以添加获胜方等摘要信息
            }
        )

    return jsonify({"success": True, "battles": battles_data})


@game_bp.route("/download_logs/<battle_id>", methods=["GET"])
@login_required
def download_logs(battle_id):
    """下载对战日志"""
    log_file_full_path = "path_not_calculated_yet"
    try:
        # 1. 获取当前文件所在的目录 (例如 /Users/ceciliaguo/Desktop/Tuvalon/pkudsa.avalon/platform/blueprints)
        current_file_dir = os.path.dirname(__file__)

        # 2. 计算 'data' 目录的路径
        data_directory_path = os.path.abspath(
            os.path.join(current_file_dir, "..", "data")
        )

        # 3. 构造日志文件名
        log_file_name = f"game_{battle_id}_archive.json"

        # 4. 构造完整的日志文件路径，用于检查文件是否存在
        log_file_full_path = os.path.join(data_directory_path, log_file_name)

        # 打印出我们实际正在检查和试图访问的路径，用于调试验证
        current_app.logger.info(
            f"[INFO] Attempting to access log at: {log_file_full_path}"
        )

        # 检查日志文件是否存在于计算出的正确路径
        if not os.path.exists(log_file_full_path):
            flash(f"对战 {battle_id} 的日志文件不存在", "danger")
            current_app.logger.warning(
                f"对战 {battle_id} 的日志文件不存在，路径为: {log_file_full_path}"
            )
            return redirect(url_for("game.view_battle", battle_id=battle_id))

        # 使用 send_file 而不是 send_from_directory
        return send_file(log_file_full_path, as_attachment=True)

    except Exception as e:
        # 在错误日志中包含我们计算的路径，帮助排查
        current_app.logger.error(
            f"下载对战 {battle_id} 日志失败 from path {log_file_full_path}: {str(e)}",
            exc_info=True,
        )
        flash("下载日志失败", "danger")
        return redirect(url_for("game.view_battle", battle_id=battle_id))


@game_bp.route("/download_private/<battle_id>", methods=["GET"])
@login_required
def download_private(battle_id):
    """下载对战私有日志"""
    log_file_full_path = "path_not_calculated_yet"
    try:
        # 1. 获取当前文件所在的目录 (例如 /Users/ceciliaguo/Desktop/Tuvalon/pkudsa.avalon/platform/blueprints)
        current_file_dir = os.path.dirname(__file__)

        # 2. 计算 'data' 目录的路径
        data_directory_path = os.path.abspath(
            os.path.join(current_file_dir, "..", "data")
        )

        # 3'. 找人
        battle = db_get_battle_by_id(battle_id)
        if not battle:
            return jsonify({"success": False, "message": "对战不存在"})
        players_id = [player.id for player in battle.get_players()]
        if current_user.id in players_id:
            player_idx = players_id.index(current_user.id) + 1
        else:
            flash(f"您没有参与这场对战，不能下载私有库", "danger")
            current_app.logger.warning(
                f"{current_user.id} 访问其没有参与的对战 {battle_id}私有库被拒"
            )
            return redirect(url_for("game.view_battle", battle_id=battle_id))

        # 3. 构造日志文件名
        log_file_name = f"game_{battle_id}_player_{player_idx}_private.json"

        # 4. 构造完整的日志文件路径，用于检查文件是否存在
        log_file_full_path = os.path.join(data_directory_path, log_file_name)

        # 打印出我们实际正在检查和试图访问的路径，用于调试验证
        current_app.logger.info(
            f"[INFO] Attempting to access log at: {log_file_full_path}"
        )

        # 检查日志文件是否存在于计算出的正确路径
        if not os.path.exists(log_file_full_path):
            flash(f"对战 {battle_id} 的 {player_idx} 号玩家私有库不存在", "danger")
            current_app.logger.warning(
                f"对战 {battle_id} 的 {player_idx} 号玩家私有库不存在，路径为: {log_file_full_path}"
            )
            return redirect(url_for("game.view_battle", battle_id=battle_id))

        # 使用 send_file 而不是 send_from_directory
        return send_file(log_file_full_path, as_attachment=True)

    except Exception as e:
        # 在错误日志中包含我们计算的路径，帮助排查
        current_app.logger.error(
            f"下载对战 {battle_id} 日志失败 from path {log_file_full_path}: {str(e)}",
            exc_info=True,
        )
        flash("下载日志失败", "danger")
        return redirect(url_for("game.view_battle", battle_id=battle_id))


@game_bp.route("/cancel_battle/<string:battle_id>", methods=["POST"])
@login_required
def cancel_battle(battle_id):
    """取消正在进行的对战"""
    try:
        # 验证对战是否存在
        battle = db_get_battle_by_id(battle_id)
        if not battle:
            current_app.logger.warning(f"尝试取消不存在的对战: {battle_id}")
            return jsonify({"success": False, "message": "对战不存在"})

        # 验证对战状态是否允许取消
        if battle.status not in ["waiting", "playing"]:
            current_app.logger.warning(
                f"尝试取消状态为 {battle.status} 的对战: {battle_id}"
            )
            return jsonify(
                {"success": False, "message": f"对战状态为 {battle.status}，无法取消"}
            )

        # 验证用户权限（可选：仅允许参与者或管理员取消）
        battle_players = db_get_battle_players_for_battle(battle_id)
        is_participant = any(bp.user_id == current_user.id for bp in battle_players)
        if not is_participant and not current_user.is_admin:
            current_app.logger.warning(
                f"用户 {current_user.id} 尝试取消非本人参与的对战: {battle_id}"
            )
            return jsonify({"success": False, "message": "您没有权限取消此对战"})

        # 获取取消原因（可选）
        data = request.get_json() or {}
        reason = data.get("reason", f"由用户 {current_user.username} 手动取消")

        # 调用battle_manager取消对战
        battle_manager = get_battle_manager()
        if battle_manager.cancel_battle(battle_id, reason):
            current_app.logger.info(f"对战 {battle_id} 已成功取消: {reason}")
            return jsonify(
                {"success": True, "message": "对战已成功取消", "battle_id": battle_id}
            )
        else:
            current_app.logger.error(f"取消对战 {battle_id} 失败")
            return jsonify(
                {
                    "success": False,
                    "message": "取消对战失败，请稍后再试",
                    "battle_id": battle_id,
                }
            )

    except Exception as e:
        current_app.logger.exception(f"取消对战 {battle_id} 时发生错误: {str(e)}")
        return jsonify(
            {
                "success": False,
                "message": f"服务器内部错误: {str(e)}",
                "battle_id": battle_id,
            }
        )
