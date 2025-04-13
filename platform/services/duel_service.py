import logging
import time
from db.database import get_duel_db
from datetime import datetime
from tinydb import Query
import threading

from services.code_service import get_code_content
from services.user_service import update_user_points
from game.referee import run_single_round
from game.baselines import get_all_baseline_codes

# 创建线程锁保护队列访问
queue_lock = threading.Lock()
# 全局对战队列
duel_queue = []


def get_baseline_codes():
    """获取所有基准代码"""
    return get_all_baseline_codes()


def save_duel_record(duel_data):
    """保存对战记录到数据库"""
    if not isinstance(duel_data, dict):
        logging.error("Error: duel_data must be a dictionary.")
        return False

    # 添加时间戳
    duel_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 保存到数据库
    db = get_duel_db()
    db.insert(duel_data)
    return True


def get_all_duels():
    """获取所有对战记录"""
    db = get_duel_db()
    return db.all()


def get_user_duels(username):
    """获取用户参与的所有对战"""
    if not username:
        return []

    Duel = Query()
    db = get_duel_db()
    return db.search((Duel.user1 == username) | (Duel.user2 == username))


def start_test_duel(username, user_code_name, opponent_code_name):
    """
    开始一场测试对战

    Args:
        username: 用户名
        user_code_name: 用户代码名称
        opponent_code_name: 基准代码名称

    Returns:
        tuple: (duel_process_text, result_code)
    """
    if not username or not user_code_name or not opponent_code_name:
        return "请先登录并选择代码", "invalid"

    # 获取代码内容
    user_code = get_code_content(username, user_code_name)
    baseline_codes = get_baseline_codes()
    opponent_code = baseline_codes.get(opponent_code_name, "")

    if not user_code or not opponent_code:
        return "获取代码内容失败", "invalid"

    # 调用裁判执行对战
    user_move, opponent_move, result_code = run_single_round(user_code, opponent_code)

    # 记录对战过程
    duel_process = [
        f"您的代码 ({user_code_name}) 出招: {user_move}",
        f"对手代码 ({opponent_code_name}) 出招: {opponent_move}",
    ]

    # 根据结果添加描述
    if result_code == "player1_win":
        duel_process.append("结果: 您的代码获胜！")
        final_result_desc = "胜利"
    elif result_code == "player2_win":
        duel_process.append("结果: 对手代码获胜！")
        final_result_desc = "失败"
    elif result_code == "draw":
        duel_process.append("结果: 平局！")
        final_result_desc = "平局"
    else:
        duel_process.append(f"结果: 无效对战 (裁判判定: {result_code})")
        if (
            "error" in str(user_move)
            or "not_found" in str(user_move)
            or "invalid_move" in str(user_move)
        ):
            duel_process.append(f"原因: 您的代码执行出错或返回无效 ({user_move})")
        if (
            "error" in str(opponent_move)
            or "not_found" in str(opponent_move)
            or "invalid_move" in str(opponent_move)
        ):
            duel_process.append(f"原因: 对手代码执行出错或返回无效 ({opponent_move})")
        final_result_desc = "无效"

    # 保存对战记录
    duel_data = {
        "type": "test",
        "user1": username,
        "code1": user_code_name,
        "move1": user_move,
        "user2": "Baseline",
        "code2": opponent_code_name,
        "move2": opponent_move,
        "result": final_result_desc,
        "result_code": result_code,
        "process": duel_process,
    }
    save_duel_record(duel_data)

    return "\n".join(duel_process), result_code


def join_ladder_duel(username, code_name):
    """
    加入天梯对战队列

    Args:
        username: 用户名
        code_name: 代码名称

    Returns:
        tuple: (status, message, result_code)
    """
    if not username or not code_name:
        return "错误", "请先登录并选择代码", None

    with queue_lock:
        # 检查用户是否已在队列
        if any(req["username"] == username for req in duel_queue):
            return "正在匹配对手...", "您已在队列中，请耐心等待", None

        # 添加对战请求到队列
        duel_request = {
            "username": username,
            "code_name": code_name,
            "timestamp": time.time(),
        }
        duel_queue.append(duel_request)

        # 检查是否可以匹配
        if len(duel_queue) >= 2:
            matchable = False
            player1_idx = None
            player2_idx = None

            # 寻找可匹配的对手
            for i in range(len(duel_queue)):
                for j in range(i + 1, len(duel_queue)):
                    if duel_queue[i]["username"] != duel_queue[j]["username"]:
                        player1_idx = i
                        player2_idx = j
                        matchable = True
                        break
                if matchable:
                    break

            # 如果找到匹配对手，进行对战
            if matchable:
                player2_req = duel_queue.pop(player2_idx)
                player1_req = duel_queue.pop(
                    player1_idx if player1_idx < player2_idx else player1_idx - 1
                )

                # 放在队列外执行对战，避免长时间占用锁
                status, message, result_code = (
                    "对战结束",
                    "已匹配到对手，即将开始对战",
                    None,
                )

    # 如果有匹配，执行对战
    if matchable:
        return conduct_ladder_duel(player1_req, player2_req)
    else:
        return "正在匹配对手...", f"队列中 {len(duel_queue)} 人，等待匹配...", None


def conduct_ladder_duel(request1, request2):
    """
    执行天梯对战

    Args:
        request1: 玩家1请求
        request2: 玩家2请求

    Returns:
        tuple: (status, duel_process_text, result_code)
    """
    user1 = request1["username"]
    code1_name = request1["code_name"]
    user2 = request2["username"]
    code2_name = request2["code_name"]

    # 获取代码内容
    user1_code = get_code_content(user1, code1_name)
    user2_code = get_code_content(user2, code2_name)

    if not user1_code or not user2_code:
        return "对战取消", "错误：获取一方或双方代码内容失败", None

    # 执行对战
    move1, move2, result_code = run_single_round(user1_code, user2_code)

    # 记录对战过程
    duel_process = [
        f"{user1} ({code1_name}) 出招: {move1}",
        f"{user2} ({code2_name}) 出招: {move2}",
    ]

    # 更新积分和结果描述
    points_change = 20

    if result_code == "player1_win":
        duel_process.append(f"结果: {user1} 获胜！")
        update_user_points(user1, points_change)
        update_user_points(user2, -points_change)
        final_result_desc = (
            f"{user1} 胜利 (+{points_change}分), {user2} 失败 (-{points_change}分)"
        )
    elif result_code == "player2_win":
        duel_process.append(f"结果: {user2} 获胜！")
        update_user_points(user1, -points_change)
        update_user_points(user2, points_change)
        final_result_desc = (
            f"{user2} 胜利 (+{points_change}分), {user1} 失败 (-{points_change}分)"
        )
    elif result_code == "draw":
        duel_process.append(f"结果: 平局！")
        final_result_desc = "平局 (积分不变)"
    else:
        duel_process.append(f"结果: 无效对战 (裁判判定: {result_code})")
        if (
            "error" in str(move1)
            or "not_found" in str(move1)
            or "invalid_move" in str(move1)
        ):
            duel_process.append(f"原因: {user1} 代码执行出错或返回无效 ({move1})")
        if (
            "error" in str(move2)
            or "not_found" in str(move2)
            or "invalid_move" in str(move2)
        ):
            duel_process.append(f"原因: {user2} 代码执行出错或返回无效 ({move2})")
        final_result_desc = "无效对战 (积分不变)"

    # 保存对战记录
    duel_data = {
        "type": "ladder",
        "user1": user1,
        "code1": code1_name,
        "move1": move1,
        "user2": user2,
        "code2": code2_name,
        "move2": move2,
        "result": final_result_desc,
        "result_code": result_code,
        "process": duel_process,
    }
    save_duel_record(duel_data)

    return "对战结束", "\n".join(duel_process), result_code


def get_duel_details(duel_index_str):
    """
    获取对战详情

    Args:
        duel_index_str: 对战索引字符串

    Returns:
        tuple: (details_text, move1, move2, result_code)
    """
    if (
        not duel_index_str
        or ":" not in duel_index_str
        or not duel_index_str.startswith("对战 ")
    ):
        return "请选择一个有效的对战记录", None, None, None

    try:
        parts = duel_index_str.split(":")
        duel_header = parts[0]
        index_part = duel_header.replace("对战 ", "").strip()
        duel_index = int(index_part) - 1

        all_duels = get_all_duels()
        all_duels.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        if 0 <= duel_index < len(all_duels):
            duel = all_duels[duel_index]
            details = [
                f"对战类型: {duel.get('type', '未知')}",
                f"玩家1: {duel.get('user1', '?')} ({duel.get('code1', '?')})",
                f"玩家2: {duel.get('user2', '?')} ({duel.get('code2', '?')})",
                f"玩家1出招: {duel.get('move1', '未记录')}",
                f"玩家2出招: {duel.get('move2', '未记录')}",
                f"结果: {duel.get('result', '未记录')}",
                f"时间戳: {duel.get('timestamp', '未知')}",
                "\n对战过程:",
            ]
            details.extend(duel.get("process", ["无详细过程"]))

            return (
                "\n".join(details),
                duel.get("move1"),
                duel.get("move2"),
                duel.get("result_code"),
            )
        else:
            return "选择的对战索引无效", None, None, None
    except Exception as e:
        logging.error(f"获取对战详情时出错: {e}", exc_info=True)
        return f"获取对战详情时出错: {e}", None, None, None


def get_duel_records():
    """获取所有对战记录的列表描述"""
    all_duels = get_all_duels()
    all_duels.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return [
        f"对战 {i+1}: {duel.get('user1','?')} vs {duel.get('user2','?')} ({duel.get('result','?')})"
        for i, duel in enumerate(all_duels)
    ]
