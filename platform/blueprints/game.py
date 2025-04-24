from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user
from flask_socketio import join_room, leave_room, emit
from config.config import Config
import json
from database.models import db, AICode, User, Room, RoomParticipant
import time
import uuid
from database.models import AICode, User, Battle
from datetime import datetime


def get_room_ai_instance(room_id, user_id):
    """获取房间中指定用户的AI实例"""
    participant = RoomParticipant.query.filter_by(
        room_id=room_id, user_id=user_id, is_ai=False
    ).first()

    if not participant or not participant.selected_ai_code_id:
        return None, None

    ai_code = AICode.query.get(participant.selected_ai_code_id)
    if not ai_code:
        return None, None

    # 从数据库获取AI实例，而不是从内存
    ai_instance = participant.get_ai_instance()
    return ai_instance, participant.selected_ai_code_id


# 创建蓝图
game_bp = Blueprint("game", __name__)


@game_bp.route("/room/<room_id>")
@login_required
def game_room(room_id):
    """加载游戏房间页面"""
    # 查找房间
    room = Room.query.get(room_id)
    if not room:
        return render_template("error.html", message="房间不存在")

    # 检查玩家是否有权限进入房间
    participant = RoomParticipant.query.filter_by(
        room_id=room_id, user_id=current_user.id, is_ai=False
    ).first()

    if not participant:
        return render_template("error.html", message="您没有权限进入该房间")

    # 获取房间中所有玩家的信息
    player_info = []
    participants = RoomParticipant.query.filter_by(room_id=room_id, is_ai=False).all()

    for p in participants:
        if p.user:
            player_info.append(
                {
                    "id": p.user.id,
                    "username": p.user.username,
                }
            )

    # 检查是否是房主
    is_host = current_user.id == room.host_id

    return render_template(
        "game_room.html",
        room_id=room_id,
        room_info=room.to_dict(),
        player_info=player_info,
        is_host=is_host,
    )


@game_bp.route("/game/start/<room_id>", methods=["POST"])
@login_required
def start_game(room_id):
    """开始游戏"""
    # 查找房间
    room = Room.query.get(room_id)
    if not room:
        return jsonify({"success": False, "message": "房间不存在"})

    # 检查是否为房主
    if room.host_id != current_user.id:
        return jsonify({"success": False, "message": "只有房主可以开始游戏"})

    # 检查房间状态
    if room.status != "ready":
        return jsonify({"success": False, "message": "房间还未准备好"})

    # 检查玩家数量
    participants = RoomParticipant.query.filter_by(room_id=room_id).all()
    if len(participants) != room.max_players:
        return jsonify(
            {"success": False, "message": f"需要{room.max_players}名玩家才能开始游戏"}
        )

    # 创建对战记录
    battle_id = str(uuid.uuid4())

    # 获取玩家ID列表
    player_ids = []
    for p in participants:
        if not p.is_ai:
            player_ids.append(p.user_id)
        else:
            # 处理AI参与者
            pass

    # 创建Battle记录
    battle = Battle(
        id=battle_id,
        status="waiting",
        room_id=room_id,
        player_ids=json.dumps(player_ids),
        started_at=datetime.now(),
    )

    # 更新房间状态和关联对战
    room.status = "playing"
    room.current_battle_id = battle_id

    # 保存到数据库
    db.session.add(battle)
    db.session.commit()

    # 此处启动游戏逻辑（使用线程或队列）
    # ...

    return jsonify({"success": True, "message": "游戏已开始", "battle_id": battle_id})


# 添加AI对手
@game_bp.route("/game/add_ai_opponent/<room_id>", methods=["POST"])
@login_required
def add_ai_opponent(room_id):
    """添加AI对手到房间"""
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
    ai_type = data.get("ai_type")

    if not ai_type or ai_type not in ["basic_player", "smart_player"]:
        return jsonify({"success": False, "message": "无效的AI类型"})

    # 生成唯一ID给AI
    ai_id = f"ai_{uuid.uuid4().hex[:8]}"

    # 添加新AI参与者
    ai_name = "基础AI" if ai_type == "basic_player" else "智能AI"
    ai_participant = RoomParticipant(
        room_id=room_id,
        is_ai=True,
        ai_id=ai_id,
        ai_type=ai_type,
        ai_name=ai_name,
        join_time=int(time.time()),
    )

    db.session.add(ai_participant)
    db.session.commit()

    return jsonify({"success": True, "message": "已添加AI对手"})


# 获取房间中的对手列表
@game_bp.route("/game/opponents/<room_id>")
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


@game_bp.route("/game/status/<battle_id>")
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


@game_bp.route("/game/ai_instance_status/<room_id>")
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


# WebSocket事件处理
def register_socket_events(socketio):
    """注册所有游戏相关的Socket.IO事件处理函数"""

    @socketio.on("connect")
    def handle_connect():
        """客户端连接事件处理"""
        print(
            f"Client connected: {current_user.username if current_user.is_authenticated else 'Guest'}"
        )

    @socketio.on("disconnect")
    def handle_disconnect():
        """客户端断开连接事件处理"""
        print(
            f"Client disconnected: {current_user.username if current_user.is_authenticated else 'Guest'}"
        )

    @socketio.on("join_room")
    def handle_join_room(data):
        """玩家加入房间"""
        if not current_user.is_authenticated:
            return {"success": False, "error": "Unauthorized"}

        room_id = data.get("room_id")
        if not room_id:
            return {"success": False, "error": "No room_id provided"}

        # 从数据库获取房间信息
        room = Room.query.get(room_id)
        if not room:
            return {"success": False, "error": "Room does not exist"}

        # 检查玩家是否属于这个房间
        participant = RoomParticipant.query.filter_by(
            room_id=room_id, user_id=current_user.id, is_ai=False
        ).first()

        if not participant:
            return {"success": False, "error": "You are not a member of this room"}

        # 加入Socket.IO房间
        join_room(room_id)

        # 更新玩家状态
        user_info = {
            "user_id": current_user.id,
            "username": current_user.username,
        }

        # 通知房间其他玩家有新玩家加入
        emit("player_joined", user_info, room=room_id, include_self=False)

        # 返回房间信息给加入的玩家
        return {"success": True, "room_info": room.to_dict(), "current_user": user_info}

    @socketio.on("leave")
    def on_leave(data):
        """玩家离开房间"""
        room_id = data.get("room_id")
        if not room_id:
            return

        leave_room(room_id)

        emit(
            "user_left",
            {"user_id": current_user.id, "username": current_user.username},
            room=room_id,
        )
