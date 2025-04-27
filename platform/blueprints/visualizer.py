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
            Config._yaml_config.get("data_dir", "./data"), f"game_{game_id}_archive.json"
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
            Config._yaml_config.get("data_dir", "./data"), f"game_{game_id}_archive.json"
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
            Config._yaml_config.get("data_dir", "./data"), f"game_{game_id}_archive.json"
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
            filename = f"game_{game_id}_archive.json"
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
    if not isinstance(first_event, dict) or first_event.get("event_type") != "game_start":
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
        if event.get("event_type") == "GameStart":
            game_info["player_count"] = event.get("player_count", 0)
            game_info["map_size"] = event.get("map_size", 0)
            game_info["start_time"] = event.get("timestamp", "")

        if event.get("event_type") == "RoleAssign":
            game_info["roles"] = event.get("event_data", {})

        # 从游戏结束事件提取信息
        if event.get("event_type") == "GameResult":
            info = event.get("event_data", [])
            game_info["end_time"] = event.get("timestamp", "")
            game_info["winner"] = info[0]
            game_info["win_reason"] = info[1]
        
        if event.get("event_type") == "FinalScore":
            info = event.get("event_data", [])
            game_info["blue_wins"] = info[0]
            game_info["red_wins"] = info[1]
            game_info["rounds_played"] = info[0] + info[1]

    # 检查游戏是否异常终止 (没有game_end事件)
    if not game_info["end_time"]:
        game_info["is_completed"] = False
        game_info["end_time"] = "游戏未正常结束"
        game_info["winner"] = "未知"
        game_info["win_reason"] = "游戏异常终止"
        
        # 尝试从最后一个任务结果事件中获取部分信息
        for event in reversed(game_data):
            flag1,flag2 = 0,0
            if event.get("event_type") == "MissionResult":
                info = event.get("event_data", ())
                game_info["rounds_played"] = info[0]
                flag1 = 1
            if event.get("event_type") == "ScoreBoard":
                info = event.get("event_data", [])
                game_info["blue_wins"] = info[0]
                game_info["red_wins"] = info[1]
                flag2 = 1
            if flag1 and flag2:
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
        "Assass": None,
        "GameEnd": None
    }
    
    round_num = 0
    for event in game_data:
        event_type = event.get("event_type")
        event_data = event.get("event_data")
        
        # 处理特殊事件
        if event_type in special_events:
            special_events[event_type] = event
            continue
            
        if event_type == "RoundStart":
            round_num = event_data

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
            "public_speeches": {},
            "private_speeches": {},
            "public_vote_result": {"votes":{}, "approve_count":0, "result":""},
            "private_vote_result": None,
            "mission_result": None,
            "movements": {},
            "consecutive_rejections": False,
        }

        # 处理回合中的各种事件
        for event in round_events:
            event_type = event.get("event_type")
            event_data = event.get("event_data")

            if event_type == "Leader":
                round_info["leader"] = event_data
                
            elif event_type == "TeamPropose":
                round_info["team_members"] = event_data
                round_info["member_count"] = len(round_info["team_members"])

            elif event_type == "PublicSpeech":
                round_info["public_speeches"][event_data[0]] = event_data[1]
                # {1:"blabla", "2":"blabla"}

            elif event_type == "PrivateSpeech":
                round_info["public_speeches"][event_data[0]] = event_data[1]
                # {1:"blabla", "2":"blabla"}


            elif event_type == "Positions":
                round_info["movements"] = event_data
                # dict 玩家位置

            elif event_type == "PublicVote":
                round_info["vote_result"]["votes"][event_data[0]] = event_data[1]
                #{1:"Approve", "2":"Reject"}

            elif event_type == "PublicVoteResult":
                round_info["vote_result"]["approve_count"] = event_data[0] 
                round_info["vote_result"]["reject_count"] = event_data[1]
                #int

            elif event_type == "MissionApproved":
                round_info["vote_result"]["result"] = True
                
            elif event_type == "MissionRejected":
                round_info["vote_result"]["result"] = False
                round_info["consecutive_rejections"] = True

            elif event_type == "MissionVote":
                fail_votes = 0
                for i in event_data:
                    if event_data[i] == False:
                        fail_votes += 1
                round_info["mission_execution"] = {
                    "fail_votes": fail_votes
                }

            elif event_type == "MissionResult":
                if event_data[1] == "Success":
                    round_info["mission_execution"]["success"] = True
                else:
                    round_info["mission_execution"]["success"] = False

            elif event_type == "MissionResult":
                flag = False
                if event_data[1] == "Success":
                    flag = True
                round_info["mission_result"] = {
                    "result": flag,
                    "blue_wins": int(flag),
                    "red_wins": 1 - int(flag),
                }

        # 只添加非零回合
        if round_num > 0:
            game_events.append(round_info)
    
    # 添加刺杀信息
    if special_events["assassination"]:
        assassination_event = special_events["assassination"]
        flag = False
        if assassination_event[3] == "Success":
            flag = True
        assassination_info = {
            "assassin": assassination_event[0],
            "target": assassination_event[1],
            "target_role": assassination_event[2],
            "success": flag
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
    
    for event in game_data:
        event_type = event.get("event_type")
        event_data = event.get("event_data")

        # 初始化玩家位置
        if event_type == "DefaultPositions":
            round_num = 1
            player_positions = event_data
            player_count = len(player_positions)
            for i in range(1, player_count + 1):
                movements_by_player[i] = []
                
        # 记录每轮移动后的位置
        if event_type == "Move":
            player_id = event_data[0]
            movements_by_player[player_id].append({
                    "round": round_num,
                    "position": event_data[1][1],
                    "moves": event_data[1][0]
                })
            """
            "Move" 
                -- tuple(int, list), 
                    int: 0表示开始,8表示结束,其他数字对应玩家编号
                    list: [valid_moves, new_pos]
            """

        if event_type == "Positions":
            round_num += 1
            # 记录这个回合的位置
            player_positions = event_data  # 更新当前位置
                

    return movements_by_player
