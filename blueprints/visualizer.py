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
from copy import deepcopy
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

    def _get_user_names(game_id) -> list:
        from database import get_battle_by_id

        battle_obj = get_battle_by_id(game_id)
        player_objs = battle_obj.get_players()
        return [player.username for player in player_objs]

    try:
        # 处理示例回放的特殊情况
        if game_id == "example":
            # 获取 visualizer.py 文件所在的目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 构建相对于 visualizer.py 的 example replay 文件路径
            # visualizer.py 在 platform/blueprints/
            # 目标文件在 platform/example/
            # 需要向上走一层 (..) 到 platform/，再进入 example/
            example_replay_path = os.path.join(
                current_dir, "..", "example", "example_game_replay.json"
            )
            # 标准化路径 (例如，处理 '..')
            log_file = os.path.normpath(example_replay_path)

            # 检查计算出的路径是否存在
            if not os.path.exists(log_file):
                flash("示例回放文件不存在，请确保已正确配置。", "warning")
                return render_template("error.html", message="示例回放文件不存在")

        else:
            # 原有的游戏日志文件路径构建逻辑
            log_file = os.path.join(
                Config._yaml_config.get("DATA_DIR", "./data"),
                f"game_{game_id}_archive.json",
            )

        print(f"尝试读取文件: {log_file}")
        print(f"文件存在: {os.path.exists(log_file)}")

        # 检查文件是否存在
        if not os.path.exists(log_file):
            flash(f"错误：找不到对局记录文件 {os.path.basename(log_file)}", "danger")
            return render_template("error.html", message="对局记录不存在")

        # 读取游戏日志文件
        with open(log_file, "r", encoding="utf-8") as f:
            try:
                game_data = json.load(f)
            except json.JSONDecodeError as json_err:
                flash(
                    f"错误：无法解析对局记录文件 {log_file}。错误：{json_err}", "danger"
                )
                return render_template(
                    "error.html", message=f"加载对局记录时出错: 无效的JSON文件"
                )

        # 验证JSON基本格式
        if not isinstance(game_data, list) or not game_data:
            flash(f"错误：对局记录文件 {log_file} 格式无效或为空。", "danger")
            return render_template(
                "error.html", message=f"加载对局记录时出错: 文件格式无效或为空"
            )

        # 提取基本游戏信息
        game_info = extract_game_info(game_data, game_id)

        # 处理游戏事件
        game_events = process_game_events(game_data)

        # 获取玩家轨迹数据
        player_movements = extract_player_movements(game_data)

        # 检查提取的数据是否有效
        if not game_info.get("map_size"):
            flash(f"错误：无法从对局记录 {game_id} 中提取地图大小。", "danger")
            # 尝试从第一个事件获取，如果存在
            map_size_fallback = game_data[0].get("map_size", 0) if game_data else 0
            if not map_size_fallback:
                return render_template(
                    "error.html", message=f"加载对局记录时出错: 无法确定地图大小"
                )
            game_info["map_size"] = map_size_fallback  # Use fallback

        return render_template(
            "visualizer/game_reveal.html",
            game_id=game_id,
            game_info=game_info,
            game_events=game_events,
            player_movements=player_movements,
            map_size=game_info["map_size"],
            player_usernames=_get_user_names(game_id),
        )
    except Exception as e:
        flash(f"加载对局记录时发生意外错误: {str(e)}", "danger")
        # Log the full error for debugging
        print(f"Error loading replay {game_id}: {e}")
        import traceback

        traceback.print_exc()
        return render_template("error.html", message=f"加载对局记录时出错: {str(e)}")


@visualizer_bp.route("/api/replay/<game_id>")
@login_required
def game_replay_data(game_id):
    """获取游戏对局数据API (此API似乎未使用，但保持原样)"""
    try:
        log_file = os.path.join(
            Config._yaml_config.get("DATA_DIR", "./data"),
            f"game_{game_id}_public.json",  # 注意：这里用的是 public.json
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
    """获取特定回合的详细数据 (此API似乎未使用，但保持原样)"""
    try:
        log_file = os.path.join(
            Config._yaml_config.get("DATA_DIR", "./data"),
            f"game_{game_id}_archive.json",
        )

        if not os.path.exists(log_file):
            return jsonify({"success": False, "message": "对局记录不存在"})

        with open(log_file, "r", encoding="utf-8") as f:
            game_data = json.load(f)

        # 过滤特定回合的事件 (注意：需要根据 observer.py 的结构调整过滤逻辑)
        round_events = []
        current_round = 0
        for event in game_data:
            if event.get("event_type") == "RoundStart":
                current_round = event.get("event_data")
            if current_round == round_num:
                round_events.append(event)
            # Stop if round number increases beyond target
            elif current_round > round_num:
                break

        return jsonify({"success": True, "round": round_num, "events": round_events})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@visualizer_bp.route("/api/replay/<game_id>/movements")
@login_required
def get_movement_data(game_id):
    """获取所有玩家的移动轨迹数据 (此API似乎未使用，但保持原样)"""
    try:
        log_file = os.path.join(
            Config._yaml_config.get("DATA_DIR", "./data"),
            f"game_{game_id}_archive.json",
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
            # 读取文件内容进行验证
            file_content = file.read()
            try:
                json_data = json.loads(file_content)
            except json.JSONDecodeError:
                flash("无效的JSON文件", "danger")
                return redirect(request.url)

            file.seek(0)  # 重置文件指针以便保存

            # 验证是否符合游戏对局格式
            if not is_valid_game_json(json_data):
                flash("上传的JSON文件格式不符合游戏对局要求", "danger")
                return redirect(request.url)

            # 为上传的文件生成唯一ID (使用原始文件名中的ID，如果存在且符合格式)
            # 尝试从文件名提取 game_id
            base_name = os.path.splitext(secure_filename(file.filename))[0]
            if base_name.startswith("game_") and base_name.endswith("_archive"):
                potential_id = base_name[len("game_") : -len("_archive")]
                # 简单的UUID格式检查 (不严格)
                if len(potential_id) > 10:  # Basic check
                    game_id = potential_id
                    filename = f"game_{game_id}_archive.json"
                    print(f"Using game_id from filename: {game_id}")
                else:
                    game_id = str(uuid.uuid4())
                    filename = f"game_{game_id}_archive.json"
                    print(f"Generated new game_id: {game_id}")
            else:
                game_id = str(uuid.uuid4())
                filename = f"game_{game_id}_archive.json"
                print(f"Generated new game_id: {game_id}")

            # 确保目录存在
            data_dir = Config._yaml_config.get("DATA_DIR", "./data")
            os.makedirs(data_dir, exist_ok=True)

            # 保存文件
            file_path = os.path.join(data_dir, filename)

            # # 检查文件是否已存在
            # if os.path.exists(file_path):
            #     flash(
            #         f"文件 {filename} 已存在。如果需要覆盖，请先删除旧文件。", "warning"
            #     )
            #     # 可以选择不覆盖并重定向，或者添加覆盖逻辑
            #     return redirect(request.url)  # 重定向回上传页面

            if not os.path.exists(file_path):
                file.save(file_path)

            flash("文件上传成功，正在跳转到可视化页面", "success")
            return redirect(url_for("visualizer.game_replay", game_id=game_id))

        except Exception as e:
            flash(f"上传失败: {str(e)}", "danger")
            print(f"Upload error: {e}")
            import traceback

            traceback.print_exc()
            return redirect(request.url)
    else:
        flash("只允许上传JSON文件", "danger")
        return redirect(request.url)


def allowed_json_file(filename):
    """检查是否为允许的JSON文件"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() == "json"


def is_valid_game_json(json_data):
    """验证JSON是否符合游戏对局格式 (基于 observer.py)"""
    if not isinstance(json_data, list) or len(json_data) == 0:
        print("Validation failed: Not a list or empty.")
        return False

    # 检查第一个事件是否为 GameStart
    first_event = json_data[0]
    if (
        not isinstance(first_event, dict)
        or first_event.get("event_type") != "GameStart"
    ):
        print(
            f"Validation failed: First event is not GameStart. Found: {first_event.get('event_type')}"
        )
        return False

    # 检查 GameStart 事件是否包含必要字段
    required_fields = ["battle_id", "player_count", "map_size", "timestamp"]
    if not all(field in first_event for field in required_fields):
        print(
            f"Validation failed: Missing fields in GameStart. Required: {required_fields}, Found: {first_event.keys()}"
        )
        return False

    # 可以添加更多检查，例如是否存在 RoleAssign, RoundStart 等
    has_role_assign = any(
        event.get("event_type") == "RoleAssign" for event in json_data
    )
    if not has_role_assign:
        print(
            "Validation warning: Missing RoleAssign event."
        )  # Warning, not necessarily invalid

    return True


def extract_game_info(game_data, game_id_from_url):
    """从游戏数据中提取基本信息 (基于 observer.py)"""
    game_info = {
        "game_id": game_id_from_url,  # Use ID from URL/filename as primary
        "player_count": 0,
        "map_size": 0,
        "start_time": None,
        "end_time": None,
        "winner": "未知",
        "rounds_played": 0,
        "roles": {},
        "win_reason": "未知",
        "blue_wins": 0,
        "red_wins": 0,
        "is_completed": False,  # Assume not completed until GameResult is found
        "start_time_formatted": "未知",
        "end_time_formatted": "未知",
        "duration": "未知",
    }
    last_round_num = 0
    last_scoreboard = None

    # 从游戏开始事件提取信息
    for event in game_data:
        event_type = event.get("event_type")
        event_data = event.get("event_data")
        timestamp = event.get("timestamp")  # Get timestamp from event

        if event_type == "GameStart":
            game_info["player_count"] = event.get("player_count", 0)
            game_info["map_size"] = event.get("map_size", 0)
            game_info["start_time"] = timestamp  # Use event timestamp
            # Use battle_id from event if needed, but prefer URL one
            # game_info["game_id"] = event.get("battle_id", game_id_from_url)

        elif event_type == "RoleAssign":
            # Ensure keys are strings if they are numbers in JSON
            game_info["roles"] = (
                {str(k): v for k, v in event_data.items()}
                if isinstance(event_data, dict)
                else {}
            )

        elif event_type == "RoundStart":
            if isinstance(event_data, int):
                last_round_num = max(last_round_num, event_data)

        elif event_type == "ScoreBoard":
            if isinstance(event_data, list) and len(event_data) == 2:
                last_scoreboard = event_data  # Store the latest scoreboard

        # 从游戏结束事件提取信息
        elif event_type == "GameResult":
            if isinstance(event_data, (list, tuple)) and len(event_data) >= 2:
                game_info["winner"] = event_data[
                    0
                ].lower()  # Ensure lowercase 'blue' or 'red'
                game_info["win_reason"] = event_data[1]
                game_info["end_time"] = timestamp  # Use event timestamp
                game_info["is_completed"] = True

        elif event_type == "FinalScore":
            if isinstance(event_data, list) and len(event_data) == 2:
                game_info["blue_wins"] = event_data[0]
                game_info["red_wins"] = event_data[1]
                game_info["rounds_played"] = (
                    game_info["blue_wins"] + game_info["red_wins"]
                )

    # 如果游戏未正常结束 (没有 GameResult)
    if not game_info["is_completed"]:
        game_info["end_time_formatted"] = "游戏未正常结束"
        game_info["win_reason"] = "游戏未记录结束状态"
        # 使用最后记录的回合数和计分板（如果存在）
        game_info["rounds_played"] = last_round_num
        if last_scoreboard:
            game_info["blue_wins"] = last_scoreboard[0]
            game_info["red_wins"] = last_scoreboard[1]
            # Try to infer winner based on last score if game didn't finish
            if game_info["blue_wins"] >= 3:
                game_info["winner"] = "blue"
                game_info["win_reason"] = "游戏中断时蓝方已达3胜"
            elif game_info["red_wins"] >= 3:
                game_info["winner"] = "red"
                game_info["win_reason"] = "游戏中断时红方已达3胜"

    # 格式化时间戳
    time_format_in = "%Y-%m-%d %H:%M:%S"  # Format from observer
    time_format_out = "%Y-%m-%d %H:%M"  # Shorter format for display

    if game_info["start_time"]:
        try:
            # Handle potential fractional seconds if present
            dt_start = datetime.strptime(
                game_info["start_time"].split(".")[0], time_format_in
            )
            game_info["start_time_formatted"] = dt_start.strftime(time_format_out)
        except (ValueError, TypeError):
            game_info["start_time_formatted"] = str(game_info["start_time"])  # Fallback

    if game_info["end_time"] and game_info["is_completed"]:
        try:
            dt_end = datetime.strptime(
                game_info["end_time"].split(".")[0], time_format_in
            )
            game_info["end_time_formatted"] = dt_end.strftime(time_format_out)
        except (ValueError, TypeError):
            # Keep "游戏未正常结束" or fallback
            if game_info["end_time_formatted"] == "未知":
                game_info["end_time_formatted"] = str(game_info["end_time"])

    # 计算游戏时长
    if game_info["start_time"] and game_info["end_time"] and game_info["is_completed"]:
        try:
            start = datetime.strptime(
                game_info["start_time"].split(".")[0], time_format_in
            )
            end = datetime.strptime(game_info["end_time"].split(".")[0], time_format_in)
            duration = end - start
            total_seconds = duration.total_seconds()
            if total_seconds >= 0:
                minutes = math.floor(total_seconds / 60)
                seconds = math.floor(total_seconds % 60)
                game_info["duration"] = f"{minutes}分{seconds}秒"
            else:
                game_info["duration"] = "时间戳错误"
        except (ValueError, TypeError):
            game_info["duration"] = "无法计算"
    elif not game_info["is_completed"]:
        game_info["duration"] = "未完成"

    # Ensure roles has string keys for template
    game_info["roles"] = {str(k): v for k, v in game_info.get("roles", {}).items()}

    return game_info


def process_game_events(game_data):
    """处理游戏事件用于可视化 (基于 observer.py)"""
    events_by_round = {}
    round_num = 0
    assassination_info = None

    for event in game_data:
        event_type = event.get("event_type")
        event_data = event.get("event_data")

        # --- Special Events Handling ---
        if event_type == "Assass":
            if isinstance(event_data, list) and len(event_data) == 4:
                assassination_info = {
                    "assassin": str(event_data[0]),  # Ensure string ID
                    "target": str(event_data[1]),  # Ensure string ID
                    "target_role": event_data[2],
                    "success": event_data[3] == "Success",
                }
            continue  # Processed special event

        # --- Round Based Events Handling ---
        if event_type == "RoundStart":
            if isinstance(event_data, int):
                round_num = event_data
                if round_num > 0 and round_num not in events_by_round:
                    # Initialize round structure when RoundStart is encountered
                    events_by_round[round_num] = {
                        "round": round_num,
                        "leader": None,
                        "team_members": [],
                        # Combined list of events: [(type, data)]
                        "events": [],
                        # {success: bool, fail_votes: int}
                        "mission_execution": None,
                        # {success: bool} - Simplified for badge
                        "mission_result": None,
                    }
            continue  # Processed RoundStart

        # Only process other events if a valid round structure exists
        if round_num > 0 and round_num in events_by_round:
            current_round = events_by_round[round_num]

            if event_type == "Leader":
                current_round["leader"] = str(event_data)  # Ensure string ID
            elif event_type == "TeamPropose":
                # Ensure members are strings
                members = (
                    [str(m) for m in event_data] if isinstance(event_data, list) else []
                )
                current_round["team_members"] = members
                current_round["events"].append(
                    {
                        "type": "team_propose",
                        "data": {
                            "leader": current_round["leader"],
                            "team_members": members,
                        },
                    }
                )
            elif event_type == "PublicSpeech":
                if isinstance(event_data, (list, tuple)) and len(event_data) == 2:
                    # 标记为公开发言
                    current_round["events"].append(
                        {
                            "type": "speech",
                            "data": (
                                str(event_data[0]),
                                event_data[1],
                                "public",
                                ["ALL"],
                            ),
                        }
                    )
            elif event_type == "PrivateSpeech":
                if isinstance(event_data, (list, tuple)) and len(event_data) == 3:
                    # 标记为有限范围发言
                    current_round["events"].append(
                        {
                            "type": "speech",
                            "data": (
                                str(event_data[0]),
                                event_data[1],
                                "private",
                                event_data[2],
                            ),
                        }
                    )
            elif event_type == "PublicVote":
                if isinstance(event_data, (list, tuple)) and len(event_data) == 2:
                    # 检查是否需要创建新的投票尝试
                    if (
                        not current_round["events"]
                        or current_round["events"][-1]["type"] != "vote_attempt"
                    ):
                        current_round["events"].append(
                            {
                                "type": "vote_attempt",
                                "data": {
                                    "votes": {},
                                    "approved": None,
                                    "approve_count": 0,
                                    "reject_count": 0,
                                },
                            }
                        )
                    # 更新最新的投票尝试
                    current_round["events"][-1]["data"]["votes"][str(event_data[0])] = (
                        event_data[1] == "Approve"
                    )
            elif event_type == "PublicVoteResult":
                if isinstance(event_data, list) and len(event_data) == 2:
                    # 确保存在投票尝试
                    if (
                        not current_round["events"]
                        or current_round["events"][-1]["type"] != "vote_attempt"
                    ):
                        current_round["events"].append(
                            {
                                "type": "vote_attempt",
                                "data": {
                                    "votes": {},
                                    "approved": None,
                                    "approve_count": 0,
                                    "reject_count": 0,
                                },
                            }
                        )
                    # 更新投票结果
                    current_round["events"][-1]["data"]["approve_count"] = event_data[0]
                    current_round["events"][-1]["data"]["reject_count"] = event_data[1]
            elif event_type == "MissionApproved":
                # 确保存在投票尝试
                if (
                    not current_round["events"]
                    or current_round["events"][-1]["type"] != "vote_attempt"
                ):
                    current_round["events"].append(
                        {
                            "type": "vote_attempt",
                            "data": {
                                "votes": {},
                                "approved": None,
                                "approve_count": 0,
                                "reject_count": 0,
                            },
                        }
                    )
                # 更新投票结果
                current_round["events"][-1]["data"]["approved"] = True
            elif event_type == "MissionRejected":
                # 确保存在投票尝试
                if (
                    not current_round["events"]
                    or current_round["events"][-1]["type"] != "vote_attempt"
                ):
                    current_round["events"].append(
                        {
                            "type": "vote_attempt",
                            "data": {
                                "votes": {},
                                "approved": None,
                                "approve_count": 0,
                                "reject_count": 0,
                            },
                        }
                    )
                # 更新投票结果
                current_round["events"][-1]["data"]["approved"] = False
            elif event_type == "MissionVote":
                if isinstance(event_data, dict):
                    fail_votes = sum(1 for vote in event_data.values() if not vote)
                    # Initialize mission_execution if not already done
                    if current_round["mission_execution"] is None:
                        current_round["mission_execution"] = {}
                    current_round["mission_execution"]["fail_votes"] = fail_votes
            elif event_type == "MissionResult":
                if isinstance(event_data, (list, tuple)) and len(event_data) == 2:
                    success = event_data[1] == "Success"
                    if current_round["mission_execution"] is None:
                        current_round["mission_execution"] = {}
                    current_round["mission_execution"]["success"] = success
                    # Also store simplified mission result for badge color
                    current_round["mission_result"] = {"success": success}
            # 处理玩家移动
            elif event_type == "Move":
                if isinstance(event_data, (int, list)) and len(event_data) == 2:
                    current_round["events"].append(
                        {
                            "type": "move",
                            "data": {
                                "player_id": int(event_data[0]),
                                "valid_moves": deepcopy(event_data[1][0]),
                                "new_pos": deepcopy(event_data[1][1]),
                            },
                        }
                    )

    # Convert dict to list and sort by round number
    game_events_list = sorted(events_by_round.values(), key=lambda x: x["round"])

    # Append assassination info at the end if it exists
    if assassination_info:
        game_events_list.append(
            {
                "round": "assassination",  # Special key for template logic
                "assassination": assassination_info,
            }
        )

    return game_events_list


def extract_player_movements(game_data):
    """提取玩家移动轨迹数据 (基于 observer.py)"""
    movements_by_player = {}
    current_round_num = 0

    # 处理所有事件前，先确保玩家列表初始化
    # 1. 初始化玩家列表（处理所有RoleAssign事件）
    for event in game_data:
        if event.get("event_type") == "RoleAssign":
            event_data = event.get("event_data")
            if isinstance(event_data, dict):
                for player_id in event_data.keys():
                    player_id_str = str(player_id)
                    if player_id_str not in movements_by_player:
                        movements_by_player[player_id_str] = []

    # 2. 处理DefaultPositions事件（动态补充未初始化的玩家）
    for event in game_data:
        if event.get("event_type") == "DefaultPositions":
            event_data = event.get("event_data")
            if isinstance(event_data, dict):
                for player_id, pos in event_data.items():
                    player_id_str = str(player_id)
                    # 若玩家未初始化，补充初始化
                    if player_id_str not in movements_by_player:
                        movements_by_player[player_id_str] = []
                    # 添加第0轮的位置（仅当不存在时）
                    if not any(
                        entry["round"] == 0
                        for entry in movements_by_player[player_id_str]
                    ):
                        movements_by_player[player_id_str].append(
                            {
                                "round": 0,
                                "position": (
                                    deepcopy(pos) if isinstance(pos, list) else None
                                ),
                                "moves": [],
                            }
                        )

    # 3. 处理回合和移动事件
    for event in game_data:
        event_type = event.get("event_type")
        event_data = event.get("event_data")

        if event_type == "RoundStart" and isinstance(event_data, int):
            current_round_num = event_data
            # 确保所有玩家都有当前回合的条目
            for player_id in movements_by_player:
                entries = movements_by_player[player_id]
                if entries:
                    last_entry = entries[-1]
                    # 仅当当前回合尚未添加时创建新条目
                    if last_entry["round"] != current_round_num:
                        new_entry = {
                            "round": current_round_num,
                            "position": deepcopy(last_entry["position"]),
                            "moves": [],
                        }
                        entries.append(new_entry)
                else:
                    # 若玩家无任何条目（异常情况），初始化一个空位置
                    entries.append(
                        {"round": current_round_num, "position": None, "moves": []}
                    )

        elif event_type == "Move":
            if isinstance(event_data, list) and len(event_data) >= 2:
                player_id = str(event_data[0])
                move_details = event_data[1]
                if isinstance(move_details, list) and len(move_details) >= 2:
                    new_pos = move_details[1]
                    if player_id in movements_by_player:
                        entries = movements_by_player[player_id]
                        if entries and entries[-1]["round"] == current_round_num:
                            entries[-1]["position"] = deepcopy(new_pos)
                            entries[-1]["moves"] = deepcopy(move_details[0])

    return deepcopy(movements_by_player)
