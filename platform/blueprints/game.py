from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user
from flask_socketio import join_room, leave_room, emit
import redis
from config.config import Config
import json
from database.models import db
import time
from utils.redis_utils import get_redis_client

# 创建蓝图
game_bp = Blueprint("game", __name__)


@game_bp.route("/room/<room_id>")
@login_required
def game_room(room_id):
    """加载游戏房间页面"""
    from database.models import User  # 添加这行导入

    redis_client = get_redis_client()
    room_key = f"room:{room_id}"
    if not redis_client.exists(room_key):
        return render_template("error.html", message="房间不存在")

    # 获取房间数据
    room_data = redis_client.hgetall(room_key)
    room_info = room_data

    # 检查玩家是否有权限进入房间
    players_json = room_info.get("players", "[]")
    players = json.loads(players_json)
    if current_user.id not in players:
        return render_template("error.html", message="您没有权限进入该房间")

    # 获取房间中所有玩家的信息
    player_info = []
    for player_id in players:
        user = User.query.get(player_id)
        if user:
            player_info.append(
                {
                    "id": user.id,
                    "username": user.username,
                }
            )

    game_type = room_info.get("game_type", "default")
    # 添加这行：检查当前用户是否是房主
    is_host = str(current_user.id) == room_info.get("host_id", "")

    return render_template(
        "game_room.html",
        room_id=room_id,
        room_info=room_info,
        player_info=player_info,
        game_type=game_type,
        is_host=is_host,  # 添加这个变量
    )


@game_bp.route("/game/start/<room_id>", methods=["POST"])
@login_required
def start_game(room_id):
    """开始游戏"""
    redis_client = get_redis_client()
    room_key = f"room:{room_id}"

    # 检查房间是否存在
    if not redis_client.exists(room_key):
        current_app.logger.error(f"游戏开始失败：房间 {room_id} 不存在或已过期")
        return jsonify({"success": False, "message": "房间不存在或已过期"})

    # 获取房间信息
    room_info = redis_client.hgetall(room_key)

    # 检查是否是房主
    if str(current_user.id) != room_info.get("host_id"):
        current_app.logger.error(
            f"游戏开始失败：用户 {current_user.id} 不是房间 {room_id} 的房主"
        )
        return jsonify({"success": False, "message": "只有房主可以开始游戏"})

    # 获取最新的玩家信息
    players_json = room_info.get("players", "[]")
    players = json.loads(players_json)
    current_players = len(players)

    # 更新玩家数量（保证数据一致性）
    redis_client.hset(room_key, "current_players", str(current_players))

    # 检查玩家数量
    if current_players < 2:
        current_app.logger.error(
            f"游戏开始失败：房间 {room_id} 中的玩家数量 {current_players} 少于2"
        )
        return jsonify({"success": False, "message": "至少需要2名玩家才能开始游戏"})

    # 更新房间状态
    redis_client.hset(room_key, "status", "playing")

    # 发布房间状态更新消息
    room_update = {
        "event": "game_started",
        "data": {
            "room_id": room_id,
            "started_by": {"id": current_user.id, "username": current_user.username},
        },
    }
    redis_client.publish("room_updates", json.dumps(room_update))

    current_app.logger.info(f"游戏成功开始：房间 {room_id}，玩家数量 {current_players}")
    return jsonify({"success": True, "message": "游戏已开始"})


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

        # 从Redis获取房间信息
        redis_client = get_redis_client()
        room_key = f"room:{room_id}"

        if not redis_client.exists(room_key):
            return {"success": False, "error": "Room does not exist"}

        # 获取房间数据
        room_data = redis_client.hgetall(room_key)
        room_info = room_data  # 无需再手动解码

        # 检查玩家是否属于这个房间
        players_json = room_info.get("players", "[]")
        players = json.loads(players_json)

        if current_user.id not in players:
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
        return {"success": True, "room_info": room_info, "current_user": user_info}

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
