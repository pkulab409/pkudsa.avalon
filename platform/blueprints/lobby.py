from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user
import redis
import json
import time
import uuid
from config.config import Config
from utils.redis_utils import get_redis_client
from database.models import User

# 创建蓝图
lobby_bp = Blueprint("lobby", __name__)

@lobby_bp.route("/lobby")
@login_required
def lobby():
    """游戏大厅页面"""
    redis_client = get_redis_client()

    # 将配置信息传递给模板
    game_config = {
        "games": {
            "default_type": Config._yaml_config["games"].get("default_type", "default"),
            "default_type_name": Config._yaml_config["games"].get("default_type_name", "默认游戏"),
            "default_players": get_required_players(Config._yaml_config["games"].get("default_type", "default"))
        }
    }

    active_rooms = []
    room_keys = redis_client.keys("room:*")
    for key in room_keys:
        room_data = redis_client.hgetall(key)
        if room_data:
            room_info = room_data
            if room_info.get("is_public") == "true" and room_info.get("status") == "waiting":
                room_info["room_id"] = key.split(":")[1]
                room_info["created_time"] = format_timestamp(room_info.get("created_at"))
                room_info["host_name"] = get_host_name(room_info.get("host_id"))
                active_rooms.append(room_info)

    return render_template("lobby.html", active_rooms=active_rooms, config=game_config, game_types=[{"id": "default", "name": "默认游戏"}])

@lobby_bp.route("/lobby/create_room", methods=["POST"])
@login_required
def create_room():
    """创建游戏房间"""
    room_name = request.form.get("room_name", "")
    is_public = request.form.get("is_public", "true") == "true"
    game_type = Config._yaml_config["games"].get("default_type", "default")
    max_players = get_required_players(game_type)

    if not room_name or len(room_name) < 3:
        return jsonify({"success": False, "message": "房间名称至少需要3个字符"})

    room_id = str(uuid.uuid4())
    redis_client = get_redis_client()

    room_data = {
        "room_id": room_id,
        "room_name": room_name,
        "host_id": str(current_user.id),
        "host_name": current_user.username,
        "game_type": game_type,
        "max_players": str(max_players),
        "current_players": "1",
        "players": json.dumps([current_user.id]),
        "status": "waiting",
        "is_public": "true" if is_public else "false",
        "created_at": str(int(time.time())),
        "updated_at": str(int(time.time())),
    }

    redis_client.hmset(f"room:{room_id}", room_data)
    redis_client.expire(f"room:{room_id}", 3600)  # 1小时过期

    return jsonify({"success": True, "message": "房间创建成功", "room_id": room_id})

def get_required_players(game_type):
    """获取指定游戏类型需要的玩家人数"""
    game_configs = Config._yaml_config["games"]["types"]
    for game_config in game_configs:
        if game_config["id"] == game_type:
            return game_config.get("players", 2)
    return 2

def format_timestamp(timestamp):
    """格式化时间戳"""
    if int(timestamp) > 0:
        import datetime
        return datetime.datetime.fromtimestamp(int(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
    return ""

def get_host_name(host_id):
    """获取房主用户名"""
    if int(host_id) > 0:
        host = User.query.get(host_id)
        return host.username if host else "未知用户"
    return "未知用户"

@lobby_bp.route("/lobby/join_room/<room_id>", methods=["POST"])
@login_required
def join_room(room_id):
    """加入房间"""
    redis_client = get_redis_client()
    room_key = f"room:{room_id}"

    if not redis_client.exists(room_key):
        return jsonify({"success": False, "message": "房间不存在或已过期"})

    room_data = redis_client.hgetall(room_key)
    room_info = room_data

    if room_info.get("status") != "waiting":
        return jsonify({"success": False, "message": "房间不可加入，可能已开始游戏或已结束"})

    current_players = int(room_info.get("current_players", "0"))
    max_players = int(room_info.get("max_players", "2"))

    if current_players >= max_players:
        return jsonify({"success": False, "message": "房间已满"})

    players_json = room_info.get("players", "[]")
    players = json.loads(players_json)

    if current_user.id in players:
        return jsonify({"success": True, "room_id": room_id, "message": "正在进入房间..."})

    players.append(current_user.id)
    current_players += 1

    # 使用 Redis 事务确保并发安全
    with redis_client.pipeline() as pipe:
        pipe.multi()
        pipe.hset(room_key, "players", json.dumps(players))
        pipe.hset(room_key, "current_players", str(current_players))
        if current_players >= max_players:
            pipe.hset(room_key, "status", "ready")
        pipe.execute()

    room_update = {
        "event": "room_updated",
        "data": {
            "room_id": room_id,
            "player_joined": {"id": current_user.id, "username": current_user.username},
            "current_players": current_players,
            "status": "ready" if current_players >= max_players else "waiting",
        },
    }
    redis_client.publish("room_updates", json.dumps(room_update))

    return jsonify({"success": True, "room_id": room_id, "status": "ready" if current_players >= max_players else "waiting", "message": "成功加入房间"})

@lobby_bp.route("/lobby/leave_room/<room_id>", methods=["POST"])
@login_required
def leave_room(room_id):
    """离开房间"""
    redis_client = get_redis_client()
    room_key = f"room:{room_id}"

    if not redis_client.exists(room_key):
        return jsonify({"success": False, "message": "房间不存在或已过期"})

    room_data = redis_client.hgetall(room_key)
    room_info = room_data

    players_json = room_info.get("players", "[]")
    players = json.loads(players_json)

    if current_user.id not in players:
        return jsonify({"success": False, "message": "您不在该房间中"})

    room_status = room_info.get("status", "waiting")

    players.remove(current_user.id)
    current_players = len(players)

    if str(current_user.id) == room_info.get("host_id") or current_players == 0:
        redis_client.delete(room_key)
        return jsonify({"success": True, "message": "房间已关闭"})

    redis_client.hset(room_key, "players", json.dumps(players))
    redis_client.hset(room_key, "current_players", str(current_players))

    event_type = "game_player_left" if room_status == "playing" else "room_updated"

    room_update = {
        "event": event_type,
        "data": {
            "room_id": room_id,
            "player_left": {"id": current_user.id, "username": current_user.username},
            "current_players": current_players,
            "status": room_status,
        },
    }
    redis_client.publish("room_updates", json.dumps(room_update))

    return jsonify({"success": True, "message": "已离开房间"})

@lobby_bp.route("/lobby/rooms")
@login_required
def list_rooms():
    """获取活跃房间列表（API）"""
    redis_client = get_redis_client()
    active_rooms = []
    room_keys = redis_client.keys("room:*")
    for key in room_keys:
        room_data = redis_client.hgetall(key)
        if room_data:
            room_info = room_data
            if room_info.get("is_public") == "true" and room_info.get("status") == "waiting":
                room_info["room_id"] = key.split(":")[1]
                active_rooms.append(room_info)

    return jsonify({"success": True, "rooms": active_rooms})
