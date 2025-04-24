from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user
from config.config import Config
import json
from database.models import db, AICode, User, Room, RoomParticipant, Battle
import time
import uuid
from datetime import datetime

# 创建蓝图
game_bp = Blueprint("game", __name__)


@game_bp.route("/game_room/<room_id>")
@login_required
def game_room(room_id):
    """加载游戏房间页面"""
    # 查找房间
    room = Room.query.get(room_id)
    if not room:
        return render_template("error.html", message="房间不存在")

    # 获取房间中所有玩家的信息
    player_info = []
    participants = RoomParticipant.query.filter_by(room_id=room_id, is_ai=False).all()

    for p in participants:
        if p.user:
            player_info.append({"id": p.user.id})

    # 检查是否是房主
    is_host = current_user.id == room.host_id

    return render_template(
        "game_room.html",
        room_id=room_id,
        room_info=room.to_dict(),
        player_info=player_info,
        is_host=is_host,
    )


@game_bp.route("/start_game/<room_id>", methods=["POST"])
@login_required
def start_game(room_id):
    """开始游戏"""
    try:
        # 获取当前用户
        current_user_id = current_user.id

        # 验证房间信息
        room = Room.query.get(room_id)
        if not room:
            return jsonify({"success": False, "message": "房间不存在"})

        # 验证用户是否是房主
        if room.owner_id != current_user_id:
            return jsonify({"success": False, "message": "只有房主可以开始游戏"})

        # 检查房间状态
        if room.status != "ready":
            return jsonify(
                {"success": False, "message": f"房间状态不允许开始游戏: {room.status}"}
            )

        # 获取房间参与者
        participants = RoomParticipant.query.filter_by(room_id=room_id).all()
        if len(participants) < 7:  # 阿瓦隆需要7名玩家
            return jsonify({"success": False, "message": "需要7名玩家才能开始游戏"})

        # 获取对战管理器
        from utils.battle_manager_utils import get_battle_manager

        battle_manager = get_battle_manager()

        # 创建并启动对战
        battle_id = battle_manager.create_battle(room_id)
        if not battle_id:
            return jsonify({"success": False, "message": "创建对战失败"})

        # 如果前面的create_battle没有更新房间状态，这里可以补充更新
        # 但通常这部分已经在battle_manager.create_battle中通过调用database.action.create_battle完成

        return jsonify(
            {"success": True, "message": "游戏已开始", "battle_id": battle_id}
        )

    except Exception as e:
        current_app.logger.error(f"开始游戏失败: {str(e)}")
        return jsonify({"success": False, "message": f"开始游戏失败: {str(e)}"})


# 添加AI对手
@game_bp.route("/game/add_ai_opponent/<room_id>", methods=["POST"])
@login_required
def add_ai_opponent(room_id):
    """添加AI对手到房间"""
    try:
        # 检查是否为房主
        room = Room.query.get(room_id)
        if not room:
            return jsonify({"success": False, "message": "房间不存在"})

        if room.host_id != current_user.id:
            return jsonify({"success": False, "message": "只有房主可以添加AI对手"})

        # 检查房间状态
        if room.status != "waiting":
            return jsonify({"success": False, "message": "只能在等待状态添加AI对手"})

        # 解析请求数据
        data = request.get_json()
        ai_type = data.get("ai_type")  # 'basic_player', 'smart_player', 'user_ai'
        ai_code_id = data.get("ai_code_id")  # 如果选择用户AI，需要提供ai_code_id

        if not ai_type:
            return jsonify({"success": False, "message": "未指定AI类型"})

        # 生成唯一ID给AI
        ai_id = f"ai_{uuid.uuid4().hex[:8]}"
        ai_name = None
        selected_ai_code_id = None

        if ai_type in ["basic_player", "smart_player"]:
            # 基准AI类型
            ai_name = "基础AI" if ai_type == "basic_player" else "智能AI"
        elif ai_type == "user_ai" and ai_code_id:
            # 用户上传的AI
            ai_code = AICode.query.get(ai_code_id)
            if not ai_code:
                return jsonify({"success": False, "message": "指定的AI代码不存在"})

            ai_name = f"{ai_code.name} (玩家AI)"
            selected_ai_code_id = ai_code.id
        else:
            return jsonify({"success": False, "message": "无效的AI类型或缺少AI代码ID"})

        # 添加新AI参与者
        ai_participant = RoomParticipant(
            room_id=room_id,
            is_ai=True,
            ai_id=ai_id,
            ai_type=ai_type,
            ai_name=ai_name,
            join_time=int(time.time()),
            selected_ai_code_id=selected_ai_code_id,  # 设置选择的AI代码ID
        )

        db.session.add(ai_participant)
        db.session.commit()

        return jsonify(
            {"success": True, "message": f"已添加AI对手: {ai_name}", "ai_id": ai_id}
        )

    except Exception as e:
        current_app.logger.error(f"添加AI对手失败: {str(e)}")
        return jsonify({"success": False, "message": f"添加AI对手失败: {str(e)}"})


# 获取房间中的对手列表
@game_bp.route("/game/opponents/<room_id>", methods=["GET"])
@login_required
def get_opponents(room_id):
    """获取房间中的所有对手"""
    room = Room.query.get(room_id)
    if not room:
        return jsonify({"success": False, "message": "房间不存在"})

    # 构建对手列表
    opponents = []

    # 获取所有参与者
    participants = RoomParticipant.query.filter_by(room_id=room_id).all()

    for p in participants:
        # 跳过当前用户
        if not p.is_ai and p.user_id == current_user.id:
            continue

        opponents.append(p.to_dict())

    return jsonify({"success": True, "opponents": opponents})


# 移除对手
@game_bp.route("/game/remove_opponent/<room_id>", methods=["POST"])
@login_required
def remove_opponent(room_id):
    """从房间中移除对手"""
    room = Room.query.get(room_id)
    if not room:
        return jsonify({"success": False, "message": "房间不存在"})

    # 检查是否为房主
    if room.host_id != current_user.id:
        return jsonify({"success": False, "message": "只有房主可以移除对手"})

    # 解析请求数据
    data = request.get_json()
    opponent_id = data.get("id")
    opponent_type = data.get("type")

    if not opponent_id or not opponent_type:
        return jsonify({"success": False, "message": "参数错误"})

    if opponent_type == "human":
        # 移除人类玩家
        participant = RoomParticipant.query.filter_by(
            room_id=room_id, user_id=int(opponent_id), is_ai=False
        ).first()
    else:
        # 移除AI玩家
        participant = RoomParticipant.query.filter_by(
            room_id=room_id, ai_id=opponent_id, is_ai=True
        ).first()

    if participant:
        db.session.delete(participant)
        db.session.commit()

    return jsonify({"success": True, "message": "已移除对手"})


@game_bp.route("/game/status/<battle_id>", methods=["GET"])
@login_required
def get_game_status(battle_id):
    """获取游戏状态"""
    try:
        from utils.battle_manager_utils import get_battle_manager

        battle_manager = get_battle_manager()

        # 获取对战状态
        status = battle_manager.get_battle_status(battle_id)
        if not status:
            return jsonify({"success": False, "message": "对战不存在"})

        # 获取对战快照
        snapshots = battle_manager.get_snapshots_queue(battle_id)

        # 如果对战已完成，获取结果
        result = None
        if status == "completed":
            result = battle_manager.get_battle_result(battle_id)

        return jsonify(
            {
                "success": True,
                "status": status,
                "snapshots": snapshots,
                "result": result,
            }
        )

    except Exception as e:
        current_app.logger.error(f"获取游戏状态失败: {str(e)}")
        return jsonify({"success": False, "message": f"获取游戏状态失败: {str(e)}"})


@game_bp.route("/select_ai/<room_id>", methods=["POST"])
@login_required
def select_ai_for_game(room_id):
    """为当前游戏选择AI代码"""
    try:
        # 获取请求数据
        data = request.get_json()
        ai_id = data.get("ai_id")

        if not ai_id:
            return jsonify({"success": False, "message": "未提供AI代码ID"})

        # 检查AI代码是否存在且属于当前用户
        ai_code = AICode.query.filter_by(id=ai_id, user_id=current_user.id).first()
        if not ai_code:
            return jsonify(
                {"success": False, "message": "无效的AI代码ID或您无权使用此代码"}
            )

        # 检查用户是否在房间中
        participant = RoomParticipant.query.filter_by(
            room_id=room_id, user_id=current_user.id, is_ai=False
        ).first()

        if not participant:
            return jsonify({"success": False, "message": "您不在此房间中"})

        # 设置选择的AI代码
        participant.selected_ai_code_id = ai_id
        participant.ai_name = ai_code.name
        db.session.commit()

        return jsonify({"success": True, "message": f"已选择AI代码: {ai_code.name}"})

    except Exception as e:
        current_app.logger.error(f"选择AI代码失败: {str(e)}")
        return jsonify({"success": False, "message": f"选择AI代码失败: {str(e)}"})


@game_bp.route("/game/ai_instance_status/<room_id>", methods=["GET"])
@login_required
def get_ai_instance_status(room_id):
    """获取玩家在房间中的AI实例状态"""
    try:
        # 检查用户是否在房间中
        participant = RoomParticipant.query.filter_by(
            room_id=room_id, user_id=current_user.id, is_ai=False
        ).first()

        if not participant:
            return jsonify({"success": False, "message": "您不在此房间中"})

        # 检查是否有选择的AI代码
        if not participant.selected_ai_code_id:
            return jsonify(
                {"success": True, "has_ai": False, "message": "未选择AI代码"}
            )

        # 获取AI代码信息
        ai_code = AICode.query.get(participant.selected_ai_code_id)
        if not ai_code:
            return jsonify(
                {"success": True, "has_ai": False, "message": "所选AI代码不存在"}
            )

        # 检查是否有AI实例
        has_instance = participant.ai_instance_data is not None

        return jsonify(
            {
                "success": True,
                "has_ai": True,
                "is_instantiated": has_instance,
                "ai_code": {"id": ai_code.id, "name": ai_code.name},
                "instance_id": participant.ai_instance_id,
            }
        )

    except Exception as e:
        current_app.logger.error(f"获取AI实例状态失败: {str(e)}")
        return jsonify({"success": False, "message": f"获取AI实例状态失败: {str(e)}"})


@game_bp.route("/game/available_ai_codes", methods=["GET"])
@login_required
def get_available_ai_codes():
    """获取所有可用的AI代码（包括基准AI和用户上传的）"""
    try:
        result = {
            "baseline_ai": [
                {"id": "basic_player", "name": "基础AI", "type": "baseline"},
                {"id": "smart_player", "name": "智能AI", "type": "baseline"},
            ],
            "user_ai": [],
        }

        # 获取用户上传的所有AI代码
        ai_codes = AICode.query.filter_by(user_id=current_user.id).all()
        for ai in ai_codes:
            result["user_ai"].append(
                {
                    "id": ai.id,
                    "name": ai.name,
                    "description": ai.description,
                    "type": "user_ai",
                }
            )

        return jsonify({"success": True, "ai_codes": result})
    except Exception as e:
        current_app.logger.error(f"获取可用AI代码失败: {str(e)}")
        return jsonify({"success": False, "message": f"获取可用AI代码失败: {str(e)}"})


@game_bp.route("/ai/api/user_ai_codes", methods=["GET"])
@login_required
def get_user_ai_codes():
    """获取用户的AI代码列表"""
    try:
        # 获取用户上传的所有AI代码
        ai_codes = AICode.query.filter_by(user_id=current_user.id).all()
        user_ai_list = []

        for ai in ai_codes:
            user_ai_list.append(
                {
                    "id": ai.id,
                    "name": ai.name,
                    "description": ai.description,
                    "created_at": ai.created_at,
                }
            )

        return jsonify({"success": True, "ai_codes": user_ai_list})
    except Exception as e:
        current_app.logger.error(f"获取用户AI代码失败: {str(e)}")
        return jsonify({"success": False, "message": f"获取用户AI代码失败: {str(e)}"})
