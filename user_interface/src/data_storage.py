'''实现一个简单的后端数据管理系统，用于管理用户、代码、对战记录以及天梯排名。主要功能包括：

 - 数据初始化：在当前文件同级的data目录下存储JSON数据文件，包括用户数据、代码数据和对战记录数据。
 - 用户管理：实现了用户注册、登录验证、查询用户信息等功能。
 - 代码管理：实现了用户代码的存储与读取。
 - 对战管理：提供对战记录的保存与查询功能。
 - 天梯排名：根据用户积分生成全局及分区排名，并根据积分变化更新用户分区。
 - 预设Baseline代码：返回系统预设的基础代码示例。
 - 分区查询：返回系统支持的所有分区。

各功能均基于JSON文件持久化数据，适用于简单的命令行或Web后端系统。
'''


import json
import os
from datetime import datetime

# 确保数据目录存在
data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(data_dir, exist_ok=True)

# 文件路径
user_file = os.path.join(data_dir, 'users.json')
code_file = os.path.join(data_dir, 'codes.json')
duel_file = os.path.join(data_dir, 'duels.json')

# 初始化数据文件
if not os.path.exists(user_file):
    with open(user_file, 'w') as f:
        json.dump({}, f)

if not os.path.exists(code_file):
    with open(code_file, 'w') as f:
        json.dump({}, f)

if not os.path.exists(duel_file):
    with open(duel_file, 'w') as f:
        json.dump([], f)


# --- 用户管理功能 ---

def get_all_users():
    '''从 JSON 文件中加载所有用户数据。'''
    with open(user_file, 'r') as f:
        return json.load(f)


def save_users(users):
    '''将用户数据保存到 JSON 文件中。'''
    with open(user_file, 'w') as f:
        json.dump(users, f, indent=4)


def user_exists(username):
    '''检查用户名是否已经存在。'''
    users = get_all_users()
    return username in users


def register_user(username, password):
    '''注册新用户。

    检查用户名是否已存在，若不存在则添加新用户，并初始化用户积分和分区。'''
    users = get_all_users()
    if username in users:
        return False, "用户名已存在"

    users[username] = {
        "password": password,
        "ladder_points": 1000,  # 初始积分
        "division": "新手区"  # 初始分区
    }
    save_users(users)
    return True, "注册成功"


def verify_user(username, password):
    '''验证用户登录信息。检查用户名是否存在以及密码是否正确。'''
    users = get_all_users()
    if username not in users:
        return False, "用户名不存在"
    if users[username]["password"] != password:
        return False, "密码错误"
    return True, "登录成功"


def get_user_profile(username):
    '''获取指定用户的详细信息。'''
    users = get_all_users()
    if username not in users:
        return None
    return users[username]


# --- 代码管理功能 ---

def get_user_codes(username):
    '''获取指定用户的所有代码。'''
    try:
        with open(code_file, 'r') as f:
            all_codes = json.load(f)

        return all_codes.get(username, {})
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def save_code(username, code_name, code_content):
    '''保存或更新指定用户的代码。

    读取当前代码数据，更新指定用户的代码内容后写入 JSON 文件。'''
    try:
        with open(code_file, 'r') as f:
            all_codes = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        all_codes = {}

    if username not in all_codes:
        all_codes[username] = {}

    all_codes[username][code_name] = code_content

    with open(code_file, 'w') as f:
        json.dump(all_codes, f, indent=4)

    return True, "代码保存成功"


def get_code_content(username, code_name):
    '''获取指定用户、指定名称的代码内容。'''
    user_codes = get_user_codes(username)
    return user_codes.get(code_name, "")


# --- 对战管理功能 ---

def get_all_duels():
    '''获取所有对战记录。'''
    try:
        with open(duel_file, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def save_duel_record(duel_data):
    '''保存一条新的对战记录。'''
    duels = get_all_duels()
    duel_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    duels.append(duel_data)

    with open(duel_file, 'w') as f:
        json.dump(duels, f, indent=4)


def get_user_duels(username):
    '''获取指定用户参与的所有对战记录。'''
    all_duels = get_all_duels()
    user_duels = []

    for duel in all_duels:
        if duel["user1"] == username or duel["user2"] == username:
            user_duels.append(duel)

    return user_duels


# --- 天梯排名功能 ---

def get_ladder_ranking():
    '''获取所有用户的天梯排名。'''
    users = get_all_users()
    ranking = []

    for username, data in users.items():
        ranking.append({
            "username": username,
            "ladder_points": data.get("ladder_points", 1000),
            "division": data.get("division", "新手区")
        })

    # 按积分降序排序
    ranking.sort(key=lambda x: x["ladder_points"], reverse=True)

    # 添加排名
    for i, user in enumerate(ranking):
        user["rank"] = i + 1

    return ranking


def get_division_ranking(division):
    '''获取指定分区内用户的天梯排名。'''
    all_ranking = get_ladder_ranking()
    division_ranking = [
        user for user in all_ranking if user["division"] == division]

    # 重新计算分区内排名
    for i, user in enumerate(division_ranking):
        user["division_rank"] = i + 1

    return division_ranking


def update_user_points(username, points_change):
    '''更新指定用户的积分，并根据最新积分更新用户分区。'''
    users = get_all_users()
    if username not in users:
        return False

    users[username]["ladder_points"] = users[username].get(
        "ladder_points", 1000) + points_change

    # 根据积分更新分区
    points = users[username]["ladder_points"]
    if points < 1000:
        users[username]["division"] = "新手区"
    elif points < 1500:
        users[username]["division"] = "进阶区"
    else:
        users[username]["division"] = "大师区"

    save_users(users)
    return True


# 预设baseline代码
def get_baseline_codes():
    return {
        "Baseline 代码 A": "def play_game():\n    # 简单的策略\n    return 'paper'\n",
        "Baseline 代码 B": "def play_game():\n    # 随机策略\n    import random\n    choices = ['rock', 'paper', 'scissors']\n    return random.choice(choices)\n"
    }


# 获取所有分区
def get_all_divisions():
    return ["新手区", "进阶区", "大师区"]
