from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
import redis
import json
import time
import uuid
import threading
import importlib.util
import sys
from config.config import Config
from utils.redis_utils import get_redis_client


# 创建蓝图
match_bp = Blueprint("match", __name__)


@match_bp.route("/match/enqueue", methods=["POST"])
@login_required
def enqueue():
    """将玩家加入匹配队列"""
    # 从配置中读取默认游戏类型
    game_type = Config._yaml_config["games"].get("default_type", "default")
    level = request.form.get("level", "beginner")

    redis_client = get_redis_client()
    user_id = current_user.id

    # 检查玩家是否已在队列中
    for queue_level in ["beginner", "intermediate", "advanced"]:
        queue_key = f"match_queue:{game_type}:{queue_level}"
        queue_data = redis_client.lrange(queue_key, 0, -1)
        for item in queue_data:
            if int(item.decode("utf-8")) == user_id:
                return jsonify({"success": False, "message": "您已在匹配队列中"})

    # 将玩家ID添加到匹配队列
    queue_key = f"match_queue:{game_type}:{level}"
    redis_client.rpush(queue_key, user_id)

    # 记录加入时间戳，用于超时处理
    redis_client.set(f"match_timestamp:{user_id}", time.time(), ex=60)

    # 触发匹配处理（可以改为由Celery任务或后台线程处理）
    process_matchmaking()

    return jsonify(
        {
            "success": True,
            "message": "已加入匹配队列",
            "game_type": game_type,
            "level": level,
        }
    )


@match_bp.route("/match/dequeue", methods=["POST"])
@login_required
def dequeue():
    """将玩家从匹配队列中移除"""
    # 从配置中读取默认游戏类型
    game_type = Config._yaml_config["games"].get("default_type", "default")
    user_id = current_user.id
    redis_client = get_redis_client()

    # 检查并从所有等级队列中移除
    removed = False
    for level in ["beginner", "intermediate", "advanced"]:
        queue_key = f"match_queue:{game_type}:{level}"
        queue_data = redis_client.lrange(queue_key, 0, -1)
        for item in queue_data:
            if int(item.decode("utf-8")) == user_id:
                redis_client.lrem(queue_key, 1, item)
                removed = True

    # 删除时间戳记录
    redis_client.delete(f"match_timestamp:{user_id}")

    if removed:
        return jsonify({"success": True, "message": "已退出匹配队列"})
    else:
        return jsonify({"success": False, "message": "您不在匹配队列中"})


@match_bp.route("/match/status")
@login_required
def match_status():
    """检查玩家当前的匹配状态"""
    user_id = current_user.id
    redis_client = get_redis_client()

    # 从配置中读取默认游戏类型
    default_game_type = Config._yaml_config["games"].get("default_type", "default")

    # 检查是否在某个匹配队列中
    in_queue = False
    game_type = None
    level = None

    # 只检查默认游戏类型
    for l_level in ["beginner", "intermediate", "advanced"]:
        queue_key = f"match_queue:{default_game_type}:{l_level}"
        queue_data = redis_client.lrange(queue_key, 0, -1)
        for item in queue_data:
            if int(item.decode("utf-8")) == user_id:
                in_queue = True
                game_type = default_game_type
                level = l_level
                break
        if in_queue:
            break

    # 检查是否已匹配到房间
    room_id = None
    room_keys = redis_client.keys("room:*")
    for key in room_keys:
        room_data = redis_client.hgetall(key.decode("utf-8"))
        if room_data:
            players_json = room_data.get(b"players", b"[]").decode("utf-8")
            players = json.loads(players_json)
            if user_id in players:
                room_id = key.decode("utf-8").split(":")[1]
                break

    return jsonify(
        {
            "in_queue": in_queue,
            "game_type": game_type,
            "level": level,
            "room_id": room_id,
            "timestamp": (
                redis_client.get(f"match_timestamp:{user_id}").decode("utf-8")
                if redis_client.exists(f"match_timestamp:{user_id}")
                else None
            ),
        }
    )


def process_matchmaking():
    """处理匹配逻辑，尝试将队列中的玩家匹配在一起"""
    redis_client = get_redis_client()

    # 从配置中读取默认游戏类型
    default_game_type = Config._yaml_config["games"].get("default_type", "default")

    # 只处理默认游戏类型
    for level in ["beginner", "intermediate", "advanced"]:
        queue_key = f"match_queue:{default_game_type}:{level}"

        # 获取该游戏类型需要的玩家人数
        required_players = get_required_players(default_game_type)

        # 检查队列中是否有足够的玩家
        queue_length = redis_client.llen(queue_key)
        if queue_length >= required_players:
            # 从队列中获取所需数量的玩家
            players = []
            for _ in range(required_players):
                player_id = int(redis_client.lpop(queue_key).decode("utf-8"))
                players.append(player_id)

            # 创建房间
            room_id = str(uuid.uuid4())
            room_key = f"room:{room_id}"

            # 房间数据
            room_data = {
                "players": json.dumps(players),
                "current_players": str(len(players)),
                "max_players": str(required_players),
                "status": "ready",
                "game_type": default_game_type,
                "level": level,
                "current_turn": str(players[0]),  # 默认第一个玩家先行
                "created_at": str(int(time.time())),
                "game_state": "{}",
                "host_id": str(players[0]),  # 设置第一个玩家为房主
                "room_name": f"{default_game_type.capitalize()}游戏房间",
            }

            # 写入Redis并设置过期时间
            redis_client.hmset(room_key, room_data)
            redis_client.expire(room_key, 3600)  # 1小时过期

            # 删除所有玩家的匹配时间戳
            for player_id in players:
                redis_client.delete(f"match_timestamp:{player_id}")

            # 通过Redis发布订阅通知玩家匹配成功
            match_notification = {
                "event": "match_found",
                "data": {
                    "room_id": room_id,
                    "game_type": default_game_type,
                    "level": level,
                    "players": players,
                },
            }
            redis_client.publish("match_notifications", json.dumps(match_notification))

            # 记录日志
            from flask import current_app

            current_app.logger.info(
                f"匹配成功: {len(players)}名玩家({', '.join(map(str, players))})在{default_game_type}游戏{level}级别被匹配到房间{room_id}"
            )

            # 在创建房间后，添加AI代码信息
            for player_id in players:
                from database.models import User

                user = User.query.get(player_id)
                if user:
                    # 获取玩家的活跃AI代码
                    active_ai = user.get_active_ai(default_game_type)
                    if active_ai:
                        # 将AI代码信息添加到房间数据中
                        player_ai_info = {
                            "user_id": user.id,
                            "ai_id": active_ai.id,
                            "ai_name": active_ai.name,
                        }
                        ai_info = json.loads(
                            redis_client.hget(room_key, "ai_info") or "[]"
                        )
                        ai_info.append(player_ai_info)
                        redis_client.hset(room_key, "ai_info", json.dumps(ai_info))


def get_required_players(game_type):
    """获取指定游戏类型需要的玩家人数"""
    # 从配置中获取游戏类型配置
    game_configs = Config._yaml_config["games"]["types"]

    # 查找指定游戏类型的配置
    for game_config in game_configs:
        if game_config["id"] == game_type:
            # 返回配置的玩家人数，默认为2
            return game_config.get("players", 2)

    # 如果未找到配置，默认为2名玩家
    return 2


def load_ai_module(file_path, module_name="ai_module"):
    """
    动态加载AI代码文件

    参数:
        file_path: AI代码文件路径
        module_name: 模块名称

    返回:
        加载的模块对象或None
    """
    try:
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if not spec:
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # 验证模块是否包含必要的函数
        if not hasattr(module, "make_move"):
            current_app.logger.error(f"AI代码缺少make_move函数: {file_path}")
            return None

        return module
    except Exception as e:
        current_app.logger.error(f"加载AI代码失败: {str(e)}")
        return None
