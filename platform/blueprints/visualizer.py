from flask import (
    Blueprint,
    render_template,
    request,
    abort,
    jsonify,
    redirect,
    url_for,
    flash,
)
from flask_login import login_required, current_user
import json
import os
from datetime import datetime
from config.config import Config
import math
import uuid
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage

# 创建蓝图
visualizer_bp = Blueprint("visualizer", __name__, template_folder="templates")


@visualizer_bp.route("/game/<game_id>")
@login_required
def game_index(game_id):
    """游戏对局索引页面 - 简单重定向到重放页面"""
    return redirect(url_for("visualizer.game_replay", game_id=game_id))


@visualizer_bp.route("/replay/<game_id>")
@login_required
def game_replay(game_id):
    """游戏对局重放页面"""
    try:
        # 构建游戏日志文件路径
        log_file = os.path.join(
            Config._yaml_config.get("data_dir", "./data"), f"game_{game_id}_public.json"
        )

        # 检查文件是否存在
        if not os.path.exists(log_file):
            return render_template("error.html", message="对局记录不存在")

        # 读取游戏日志文件
        with open(log_file, "r", encoding="utf-8") as f:
            game_data = json.load(f)

        # 提取基本游戏信息
        game_info = extract_game_info(game_data)

        # 处理游戏事件
        game_events = process_game_events(game_data)

        # 获取玩家轨迹数据
        player_movements = extract_player_movements(game_data)

        return render_template(
            "visualizer/game_replay.html",
            game_id=game_id,
            game_info=game_info,
            game_events=game_events,
            player_movements=player_movements,
            map_size=game_info["map_size"],
        )
    except Exception as e:
        return render_template("error.html", message=f"加载对局记录时出错: {str(e)}")


@visualizer_bp.route("/api/replay/<game_id>")
@login_required
def game_replay_data(game_id):
    """获取游戏对局数据API"""
    try:
        log_file = os.path.join(
            Config._yaml_config.get("data_dir", "./data"), f"game_{game_id}_public.json"
        )

        if not os.path.exists(log_file):
            return jsonify({"success": False, "message": "对局记录不存在"})

        with open(log_file, "r", encoding="utf-8") as f:
            game_data = json.load(f)

        return jsonify({"success": True, "game_id": game_id, "data": game_data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@visualizer_bp.route("/api/replay/<game_id>/round/<int:round_num>")
@login_required
def get_round_data(game_id, round_num):
    """获取特定回合的详细数据"""
    try:
        log_file = os.path.join(
            Config._yaml_config.get("data_dir", "./data"), f"game_{game_id}_public.json"
        )

        if not os.path.exists(log_file):
            return jsonify({"success": False, "message": "对局记录不存在"})

        with open(log_file, "r", encoding="utf-8") as f:
            game_data = json.load(f)

        # 过滤特定回合的事件
        round_events = [event for event in game_data if event.get("round") == round_num]

        return jsonify({"success": True, "round": round_num, "events": round_events})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@visualizer_bp.route("/api/replay/<game_id>/movements")
@login_required
def get_movement_data(game_id):
    """获取所有玩家的移动轨迹数据"""
    try:
        log_file = os.path.join(
            Config._yaml_config.get("data_dir", "./data"), f"game_{game_id}_public.json"
        )

        if not os.path.exists(log_file):
            return jsonify({"success": False, "message": "对局记录不存在"})

        with open(log_file, "r", encoding="utf-8") as f:
            game_data = json.load(f)

        player_movements = extract_player_movements(game_data)

        return jsonify({"success": True, "movements": player_movements})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@visualizer_bp.route("/upload", methods=["GET"])
@login_required
def upload_game_json():
    """游戏对局JSON上传页面"""
    return render_template("visualizer/upload.html")


@visualizer_bp.route("/upload", methods=["POST"])
@login_required
def process_upload():
    """处理上传的游戏对局JSON文件"""
    if "game_json" not in request.files:
        flash("未选择文件", "danger")
        return redirect(request.url)

    file = request.files["game_json"]
    if file.filename == "":
        flash("未选择文件", "danger")
        return redirect(request.url)

    if file and allowed_json_file(file.filename):
        try:
            # 验证JSON格式
            json_data = json.loads(file.read())
            file.seek(0)  # 重置文件指针

            # 验证是否符合游戏对局格式
            if not is_valid_game_json(json_data):
                flash("上传的JSON文件格式不符合游戏对局要求", "danger")
                return redirect(request.url)

            # 为上传的文件生成唯一ID
            game_id = str(uuid.uuid4())

            # 确保目录存在
            data_dir = Config._yaml_config.get("data_dir", "./data")
            os.makedirs(data_dir, exist_ok=True)

            # 保存文件
            filename = f"game_{game_id}_public.json"
            file_path = os.path.join(data_dir, filename)
            file.save(file_path)

            flash("文件上传成功，正在跳转到可视化页面", "success")
            return redirect(url_for("visualizer.game_replay", game_id=game_id))

        except json.JSONDecodeError:
            flash("无效的JSON文件", "danger")
            return redirect(request.url)
        except Exception as e:
            flash(f"上传失败: {str(e)}", "danger")
            return redirect(request.url)
    else:
        flash("只允许上传JSON文件", "danger")
        return redirect(request.url)


def allowed_json_file(filename):
    """检查是否为允许的JSON文件"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() == "json"


def is_valid_game_json(json_data):
    """验证JSON是否符合游戏对局格式"""
    # 基本验证：检查是否为列表且至少包含game_start事件
    if not isinstance(json_data, list) or len(json_data) == 0:
        return False

    # 检查第一个事件是否为game_start
    first_event = json_data[0]
    if not isinstance(first_event, dict) or first_event.get("type") != "game_start":
        return False

    # 检查是否包含必要的字段
    required_fields = ["game_id", "player_count", "map_size"]
    return all(field in first_event for field in required_fields)


def extract_game_info(game_data):
    """从游戏数据中提取基本信息"""
    game_info = {
        "player_count": 0,
        "map_size": 0,
        "start_time": "",
        "end_time": "",
        "winner": "",
        "rounds_played": 0,
        "roles": {},
        "win_reason": "",
        "blue_wins": 0,
        "red_wins": 0,
        "is_completed": True,  # 默认假设游戏正常完成
    }

    # 从游戏开始事件提取信息
    for event in game_data:
        if event.get("type") == "game_start":
            game_info["player_count"] = event.get("player_count", 0)
            game_info["map_size"] = event.get("map_size", 0)
            game_info["start_time"] = event.get("timestamp", "")

        # 从游戏结束事件提取信息
        if event.get("type") == "game_end":
            game_info["end_time"] = event.get("timestamp", "")
            result = event.get("result", {})
            game_info["winner"] = result.get("winner", "")
            game_info["rounds_played"] = result.get("rounds_played", 0)
            game_info["roles"] = result.get("roles", {})
            game_info["win_reason"] = result.get("win_reason", "")
            game_info["blue_wins"] = result.get("blue_wins", 0)
            game_info["red_wins"] = result.get("red_wins", 0)

    # 检查游戏是否异常终止 (没有game_end事件)
    if not game_info["end_time"]:
        game_info["is_completed"] = False
        game_info["end_time"] = "游戏未正常结束"
        game_info["winner"] = "未知"
        game_info["win_reason"] = "游戏异常终止"
        
        # 尝试从最后一个任务结果事件中获取部分信息
        for event in reversed(game_data):
            if event.get("type") == "mission_result":
                game_info["blue_wins"] = event.get("blue_wins", 0)
                game_info["red_wins"] = event.get("red_wins", 0)
                game_info["rounds_played"] = event.get("round", 0)
                break

    # 格式化时间戳
    if game_info["start_time"] and game_info["start_time"] != "游戏未正常结束":
        try:
            dt = datetime.strptime(game_info["start_time"], "%Y-%m-%d %H:%M:%S.%f")
            game_info["start_time_formatted"] = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            game_info["start_time_formatted"] = game_info["start_time"]

    if game_info["end_time"] and game_info["end_time"] != "游戏未正常结束":
        try:
            dt = datetime.strptime(game_info["end_time"], "%Y-%m-%d %H:%M:%S.%f")
            game_info["end_time_formatted"] = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            game_info["end_time_formatted"] = game_info["end_time"]

    # 计算游戏时长
    if game_info["start_time"] and game_info["end_time"] and game_info["is_completed"]:
        try:
            start = datetime.strptime(game_info["start_time"], "%Y-%m-%d %H:%M:%S.%f")
            end = datetime.strptime(game_info["end_time"], "%Y-%m-%d %H:%M:%S.%f")
            duration = end - start
            minutes = math.floor(duration.total_seconds() / 60)
            seconds = math.floor(duration.total_seconds() % 60)
            game_info["duration"] = f"{minutes}分{seconds}秒"
        except ValueError:
            game_info["duration"] = "未知"
    else:
        game_info["duration"] = "未完成"

    return game_info


def process_game_events(game_data):
    """处理游戏事件用于可视化"""
    # 按回合分组事件
    events_by_round = {}
    # 特殊事件(不按回合分组)
    special_events = {
        "assassination": None,
        "game_end": None
    }

    for event in game_data:
        event_type = event.get("type")
        
        # 处理特殊事件
        if event_type in special_events:
            special_events[event_type] = event
            continue
            
        round_num = event.get("round", 0)
        if round_num not in events_by_round:
            events_by_round[round_num] = []

        events_by_round[round_num].append(event)

    # 整理每轮的关键信息
    game_events = []

    for round_num in sorted(events_by_round.keys()):
        round_events = events_by_round[round_num]
        round_info = {
            "round": round_num,
            "leader": None,
            "team_members": [],
            "speeches": [],
            "vote_result": None,
            "mission_result": None,
            "movements": [],
            "consecutive_rejections": False,
        }

        # 处理回合中的各种事件
        for event in round_events:
            event_type = event.get("type")

            if event_type == "mission_start":
                round_info["leader"] = event.get("leader")
                round_info["member_count"] = event.get("member_count")

            elif event_type == "team_proposed":
                round_info["team_members"] = event.get("members", [])

            elif event_type == "global_speech":
                round_info["speeches"] = event.get("speeches", [])

            elif event_type == "movement":
                round_info["movements"] = event.get("movements", [])

            elif event_type == "public_vote":
                round_info["vote_result"] = {
                    "votes": event.get("votes", {}),
                    "approve_count": event.get("approve_count", 0),
                    "result": event.get("result", ""),
                }
            
            elif event_type == "team_rejected":
                round_info["vote_result"] = {
                    "result": "rejected",
                    "reject_count": event.get("reject_count", 0)
                }

            elif event_type == "consecutive_rejections":
                round_info["consecutive_rejections"] = True

            elif event_type == "mission_execution":
                round_info["mission_execution"] = {
                    "fail_votes": event.get("fail_votes", 0),
                    "success": event.get("success", False),
                }

            elif event_type == "mission_result":
                round_info["mission_result"] = {
                    "result": event.get("result", ""),
                    "blue_wins": event.get("blue_wins", 0),
                    "red_wins": event.get("red_wins", 0),
                }

        # 只添加非零回合
        if round_num > 0:
            game_events.append(round_info)
    
    # 添加刺杀信息
    if special_events["assassination"]:
        assassination_event = special_events["assassination"]
        assassination_info = {
            "assassin": assassination_event.get("assassin"),
            "target": assassination_event.get("target"),
            "target_role": assassination_event.get("target_role"),
            "success": assassination_event.get("success", False)
        }
        game_events.append({
            "round": "assassination",
            "assassination": assassination_info
        })
    
    return game_events


def extract_player_movements(game_data):
    """提取玩家移动轨迹数据"""
    movements_by_player = {}
    player_positions = {}  # 用于跟踪玩家的当前位置
    
    # 初始化玩家位置
    for event in game_data:
        if event.get("type") == "game_start":
            player_count = event.get("player_count", 0)
            # 假设初始位置为地图中心, 需要根据实际游戏逻辑调整
            default_position = [4, 4]  # 默认在9x9地图中心位置
            
            for i in range(1, player_count + 1):
                player_positions[i] = default_position.copy()
                movements_by_player[i] = []
                
    # 记录每轮移动后的位置
    for event in game_data:
        if event.get("type") == "movement":
            round_num = event.get("round", 0)
            for movement in event.get("movements", []):
                player_id = movement.get("player_id")
                if player_id not in movements_by_player:
                    movements_by_player[player_id] = []
                
                # 记录这个回合的位置
                position = movement.get("final_position", player_positions.get(player_id, [0, 0]))
                player_positions[player_id] = position  # 更新当前位置
                
                movements_by_player[player_id].append({
                    "round": round_num,
                    "position": position,
                    "moves": movement.get("executed_moves", []),
                })

    return movements_by_player
