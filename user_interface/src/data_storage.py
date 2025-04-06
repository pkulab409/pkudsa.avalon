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

# 用户管理功能
def get_all_users():
    with open(user_file, 'r') as f:
        return json.load(f)

def save_users(users):
    with open(user_file, 'w') as f:
        json.dump(users, f, indent=4)

def user_exists(username):
    users = get_all_users()
    return username in users

def register_user(username, password):
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
    users = get_all_users()
    if username not in users:
        return False, "用户名不存在"
    if users[username]["password"] != password:
        return False, "密码错误"
    return True, "登录成功"

def get_user_profile(username):
    users = get_all_users()
    if username not in users:
        return None
    return users[username]

# 代码管理功能
def get_user_codes(username):
    try:
        with open(code_file, 'r') as f:
            all_codes = json.load(f)
        
        return all_codes.get(username, {})
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_code(username, code_name, code_content):
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
    user_codes = get_user_codes(username)
    return user_codes.get(code_name, "")

# 对战管理功能
def get_all_duels():
    try:
        with open(duel_file, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_duel_record(duel_data):
    duels = get_all_duels()
    duel_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    duels.append(duel_data)
    
    with open(duel_file, 'w') as f:
        json.dump(duels, f, indent=4)

def get_user_duels(username):
    all_duels = get_all_duels()
    user_duels = []
    
    for duel in all_duels:
        if duel["user1"] == username or duel["user2"] == username:
            user_duels.append(duel)
    
    return user_duels

# 天梯排名功能
def get_ladder_ranking():
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
    all_ranking = get_ladder_ranking()
    division_ranking = [user for user in all_ranking if user["division"] == division]
    
    # 重新计算分区内排名
    for i, user in enumerate(division_ranking):
        user["division_rank"] = i + 1
    
    return division_ranking

def update_user_points(username, points_change):
    users = get_all_users()
    if username not in users:
        return False
    
    users[username]["ladder_points"] = users[username].get("ladder_points", 1000) + points_change
    
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
