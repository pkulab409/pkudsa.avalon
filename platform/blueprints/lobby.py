from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user
import redis
import json
import time
import uuid
from config.config import Config
from utils.redis_utils import get_redis_client

# 创建蓝图
lobby_bp = Blueprint("lobby", __name__)


@lobby_bp.route("/lobby")
@login_required
def lobby():
    """游戏大厅页面"""
    # 获取所有活跃房间
    redis_client = get_redis_client()

    # 将配置信息传递给模板
    game_config = {
        "games": {
            "default_type": Config._yaml_config["games"].get("default_type", "default"),
            "default_type_name": Config._yaml_config["games"].get(
                "default_type_name", "默认游戏"
            ),
            "default_players": get_required_players(
                Config._yaml_config["games"].get("default_type", "default")
            ),
        }
    }

    active_rooms = []

    # 获取所有公开且等待加入的房间
    room_keys = redis_client.keys("room:*")
    for key in room_keys:
        room_data = redis_client.hgetall(key)  # 无需decode
        if room_data:
            # 由于设置了decode_responses=True，这里无需再解码
            room_info = room_data

            # 只显示公开且状态为waiting的房间
            if (
                room_info.get("is_public") == "true"  # 确保使用"true"字符串
                and room_info.get("status") == "waiting"
            ):
                room_id = key.split(":")[1]  # 无需decode

                # 添加房间ID到信息中
                room_info["room_id"] = room_id

                # 格式化创建时间
                created_at = int(room_info.get("created_at", "0"))
                if created_at > 0:
                    import datetime

                    room_info["created_time"] = datetime.datetime.fromtimestamp(
                        created_at
                    ).strftime("%Y-%m-%d %H:%M:%S")

                # 获取房主信息
                from database.models import User

                host_id = int(room_info.get("host_id", "0"))
                if host_id > 0:
                    host = User.query.get(host_id)
                    if host:
                        room_info["host_name"] = host.username

                active_rooms.append(room_info)

    # 添加这个return语句，渲染并返回游戏大厅模板
    return render_template(
        "lobby.html",
        active_rooms=active_rooms,
        config=game_config,
        game_types=[{"id": "default", "name": "默认游戏"}],
    )


@lobby_bp.route("/lobby/create_room", methods=["POST"])
@login_required
def create_room():
    """创建游戏房间"""
    room_name = request.form.get("room_name", "")
    is_public = request.form.get("is_public", "true") == "true"
    game_type = Config._yaml_config["games"].get("default_type", "default")
    max_players = get_required_players(game_type)  # 从配置中获取

    # 验证房间名称
    if not room_name or len(room_name) < 3:
        return jsonify({"success": False, "message": "房间名称至少需要3个字符"})

    # 生成房间ID
    room_id = str(uuid.uuid4())

    # 连接Redis
    redis_client = get_redis_client()

    # 房间数据
    room_data = {
        "room_id": room_id,
        "room_name": room_name,
        "host_id": str(current_user.id),
        "host_name": current_user.username,
        "game_type": game_type,
        "max_players": str(max_players),
        "current_players": "1",  # 创建者自动加入
        "players": json.dumps([current_user.id]),  # 玩家列表
        "status": "waiting",
        "is_public": (
            "true" if is_public else "false"
        ),  # 修改这里，使用"true"/"false"字符串
        "created_at": str(int(time.time())),  # 使用统一的时间戳格式
        "updated_at": str(int(time.time())),
    }

    # 保存房间数据到Redis
    redis_client.hmset(f"room:{room_id}", room_data)
    redis_client.expire(f"room:{room_id}", 3600)  # 1小时过期

    return jsonify({"success": True, "message": "房间创建成功", "room_id": room_id})


def get_required_players(game_type):
    """获取指定游戏类型需要的玩家人数"""
    # 从配置中获取游戏类型配置
    game_configs = Config._yaml_config["games"]["types"]

    # 查找指定游戏类型的配置
    for game_config in game_configs:
        if game_config["id"] == game_type:
            # 返回配置的玩家人数
            return game_config.get("players", 2)

    # 如果未找到配置，默认为2名玩家
    return 2


@lobby_bp.route("/lobby/join_room/<room_id>", methods=["POST"])
@login_required
def join_room(room_id):
    """加入房间"""
    redis_client = get_redis_client()
    room_key = f"room:{room_id}"

    if not redis_client.exists(room_key):
        return jsonify({"success": False, "message": "房间不存在或已过期"})

    # 获取房间数据 - 无需解码
    room_data = redis_client.hgetall(room_key)
    room_info = room_data  # 由于设置了decode_responses=True，这里无需再解码

    # 检查房间状态
    if room_info.get("status") != "waiting":
        return jsonify(
            {"success": False, "message": "房间不可加入，可能已开始游戏或已结束"}
        )

    # 检查是否已满
    current_players = int(room_info.get("current_players", "0"))
    max_players = int(room_info.get("max_players", "2"))

    if current_players >= max_players:
        return jsonify({"success": False, "message": "房间已满"})

    # 获取当前玩家列表并添加新玩家
    players_json = room_info.get("players", "[]")
    players = json.loads(players_json)

    # 修改这里：如果玩家已在房间中，直接返回成功
    if current_user.id in players:
        return jsonify(
            {"success": True, "room_id": room_id, "message": "正在进入房间..."}
        )

    players.append(current_user.id)
    current_players += 1

    # 更新Redis中的房间数据
    redis_client.hset(room_key, "players", json.dumps(players))
    redis_client.hset(room_key, "current_players", str(current_players))

    # 如果达到最大人数，更新状态为ready
    if current_players >= max_players:
        redis_client.hset(room_key, "status", "ready")

    # 发布房间更新消息（可由WebSocket订阅）
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

    return jsonify(
        {
            "success": True,
            "room_id": room_id,
            "status": "ready" if current_players >= max_players else "waiting",
            "message": "成功加入房间",
        }
    )


@lobby_bp.route("/lobby/leave_room/<room_id>", methods=["POST"])
@login_required
def leave_room(room_id):
    """离开房间"""
    redis_client = get_redis_client()
    room_key = f"room:{room_id}"

    if not redis_client.exists(room_key):
        return jsonify({"success": False, "message": "房间不存在或已过期"})

    # 获取房间数据 - 无需再解码
    room_data = redis_client.hgetall(room_key)
    room_info = room_data  # 由于设置了decode_responses=True，这里无需再解码

    # 获取当前玩家列表
    players_json = room_info.get("players", "[]")
    players = json.loads(players_json)

    if current_user.id not in players:
        return jsonify({"success": False, "message": "您不在该房间中"})

    # 获取房间状态
    room_status = room_info.get("status", "waiting")

    # 移除玩家
    players.remove(current_user.id)
    current_players = len(players)

    # 如果房主离开，删除房间
    if str(current_user.id) == room_info.get("host_id") or current_players == 0:
        redis_client.delete(room_key)
        return jsonify({"success": True, "message": "房间已关闭"})

    # 更新Redis中的房间数据
    redis_client.hset(room_key, "players", json.dumps(players))
    redis_client.hset(room_key, "current_players", str(current_players))

    # 如果游戏已开始，添加特殊通知
    event_type = "game_player_left" if room_status == "playing" else "room_updated"

    # 发布房间更新消息
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

    # 获取所有公开且等待加入的房间
    room_keys = redis_client.keys("room:*")
    for key in room_keys:
        # 由于 decode_responses=True，Redis 返回的已经是字符串
        room_data = redis_client.hgetall(key)
        if room_data:
            # 不需要再解码
            room_info = room_data

            # 只显示公开且状态为waiting的房间
            if (
                room_info.get("is_public") == "true"  # 确保使用"true"字符串
                and room_info.get("status") == "waiting"
            ):
                room_id = key.split(":")[1]
                room_info["room_id"] = room_id
                active_rooms.append(room_info)

    return jsonify({"success": True, "rooms": active_rooms})
