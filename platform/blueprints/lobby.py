from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user
import json
import time
import uuid
from config.config import Config
from database.models import db, Room, RoomParticipant, User

# 创建蓝图
lobby_bp = Blueprint("lobby", __name__)


@lobby_bp.route("/lobby")
@login_required
def lobby():
    """游戏大厅页面"""

    # 获取所有公开且等待加入的房间
    active_rooms = []
    room_query = Room.query.filter_by(is_public=True, status="waiting").all()

    for room in room_query:
        room_info = room.to_dict()

        # 获取房主用户名
        host = User.query.get(room_info.get("host_id"))
        if host:
            room_info["host_name"] = host.username
        else:
            room_info["host_name"] = "未知"

        # 确保room_id键存在
        room_info["room_id"] = room_info["id"]

        # 格式化创建时间
        created_at = int(room_info.get("created_at", "0"))
        if created_at > 0:
            import datetime

            room_info["created_time"] = datetime.datetime.fromtimestamp(
                created_at
            ).strftime("%Y-%m-%d %H:%M:%S")

        active_rooms.append(room_info)

    # 添加这个return语句，渲染并返回游戏大厅模板
    return render_template(
        "lobby.html",
        active_rooms=active_rooms,
    )


@lobby_bp.route("/lobby/create_room", methods=["POST"])
@login_required
def create_room():
    """创建游戏房间"""
    # 自动生成房间名称（使用UUID）
    room_name = f"Room-{str(uuid.uuid4())[:8]}"

    # 默认设置为公开房间
    is_public = True

    # 生成房间ID
    room_id = str(uuid.uuid4())

    # 创建房间记录
    room = Room(
        id=room_id,
        name=room_name,
        host_id=current_user.id,
        status="waiting",
        is_public=is_public,
        created_at=int(time.time()),
    )

    # 添加房主作为第一个参与者
    participant = RoomParticipant(
        room_id=room_id,
        user_id=current_user.id,
        is_ai=False,
        join_time=int(time.time()),
    )

    # 保存到数据库
    db.session.add(room)
    db.session.add(participant)
    db.session.commit()

    return jsonify({"success": True, "message": "房间创建成功", "room_id": room_id})


@lobby_bp.route("/lobby/join_room/<room_id>", methods=["POST"])
@login_required
def join_room(room_id):
    """加入房间"""
    # 查找房间
    room = Room.query.get(room_id)
    if not room:
        return jsonify({"success": False, "message": "房间不存在或已过期"})

    # 检查房间状态
    if room.status != "waiting":
        return jsonify(
            {"success": False, "message": "房间不可加入，可能已开始游戏或已结束"}
        )

    # 检查是否已满
    current_players = room.get_current_players_count()
    if current_players >= room.max_players:
        return jsonify({"success": False, "message": "房间已满"})

    # 检查玩家是否已在房间中
    existing_participant = RoomParticipant.query.filter_by(
        room_id=room_id, user_id=current_user.id, is_ai=False
    ).first()

    if existing_participant:
        return jsonify(
            {"success": True, "room_id": room_id, "message": "正在进入房间..."}
        )

    # 添加新参与者
    participant = RoomParticipant(
        room_id=room_id,
        user_id=current_user.id,
        is_ai=False,
        join_time=int(time.time()),
    )
    db.session.add(participant)

    # 如果达到最大人数，更新状态为ready
    if current_players + 1 >= room.max_players:
        room.status = "ready"

    db.session.commit()

    return jsonify(
        {
            "success": True,
            "room_id": room_id,
            "status": room.status,
            "message": "成功加入房间",
        }
    )


@lobby_bp.route("/lobby/leave_room/<room_id>", methods=["POST"])
@login_required
def leave_room(room_id):
    """离开房间"""
    # 查找房间
    room = Room.query.get(room_id)
    if not room:
        return jsonify({"success": False, "message": "房间不存在或已过期"})

    # 查找参与者记录
    participant = RoomParticipant.query.filter_by(
        room_id=room_id, user_id=current_user.id, is_ai=False
    ).first()

    if not participant:
        return jsonify({"success": False, "message": "您不在该房间中"})

    # 删除参与者记录
    db.session.delete(participant)

    # 如果是房主离开或没有人了，删除房间
    if room.host_id == current_user.id or room.get_current_players_count() <= 1:
        db.session.delete(room)
        db.session.commit()
        return jsonify({"success": True, "message": "房间已关闭"})

    db.session.commit()

    return jsonify({"success": True, "message": "已离开房间"})


@lobby_bp.route("/lobby/rooms")
@login_required
def list_rooms():
    """获取活跃房间列表（API）"""
    active_rooms = []

    # 查询所有公开且等待加入的房间
    room_query = Room.query.filter_by(is_public=True, status="waiting").all()

    for room in room_query:
        active_rooms.append(room.to_dict())

    return jsonify({"success": True, "rooms": active_rooms})
