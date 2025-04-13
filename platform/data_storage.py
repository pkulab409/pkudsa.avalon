# 数据存储模块 (使用 TinyDB)

import os
from datetime import datetime
from tinydb import TinyDB, Query

# 从 game 包导入 Baseline 代码获取函数
from game.baselines import get_all_baseline_codes as get_game_baselines

# 确保数据目录存在
data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(data_dir, exist_ok=True)

# 文件路径 (TinyDB 将使用这些文件)
user_file = os.path.join(data_dir, "users.json")
code_file = os.path.join(data_dir, "codes.json")
duel_file = os.path.join(data_dir, "duels.json")

# 初始化 TinyDB 数据库
user_db = TinyDB(user_file, indent=4)
code_db = TinyDB(code_file, indent=4)
duel_db = TinyDB(duel_file, indent=4)

# 查询对象
User = Query()
Code = Query()
Duel = Query()

# --- 用户管理功能 ---


def get_all_users_list():
    """获取所有用户文档的列表"""
    return user_db.all()


def get_all_users():
    """获取所有用户，以字典形式返回 (兼容旧接口)"""
    users_list = get_all_users_list()
    users_dict = {}
    for user_doc in users_list:
        # 假设文档中包含 'username' 键
        username = user_doc.get("username")
        if username:
            # 创建一个不包含 username 键的副本作为值
            user_data = user_doc.copy()
            # del user_data['username'] # 可选：如果调用者不需要 username 在值中
            users_dict[username] = user_data
    return users_dict


# save_users 不再需要，TinyDB 自动保存


def user_exists(username):
    """检查用户是否存在"""
    return user_db.contains(User.username == username)


def register_user(username, password):
    """注册新用户"""
    if user_exists(username):
        return False, "用户名已存在"

    user_data = {
        "username": username,
        "password": password,
        "ladder_points": 1000,  # 初始积分
        "division": "新手区",  # 初始分区
    }
    user_db.insert(user_data)
    return True, "注册成功"


def verify_user(username, password):
    """验证用户登录"""
    user_doc = user_db.get(User.username == username)
    if not user_doc:
        return False, "用户名不存在"
    if user_doc.get("password") != password:
        return False, "密码错误"
    return True, "登录成功"


def get_user_profile(username):
    """获取用户个人资料"""
    user_doc = user_db.get(User.username == username)
    if not user_doc:
        return None
    # 返回文档副本，避免直接修改缓存
    return user_doc.copy()


# --- 代码管理功能 ---


def get_user_codes(username):
    """获取指定用户的所有代码，以字典形式返回 {code_name: content}"""
    user_code_docs = code_db.search(Code.username == username)
    codes_dict = {}
    for doc in user_code_docs:
        codes_dict[doc.get("code_name")] = doc.get("code_content")
    return codes_dict


def save_code(username, code_name, code_content):
    """保存或更新用户的代码"""
    code_data = {
        "username": username,
        "code_name": code_name,
        "code_content": code_content,
    }
    # 使用 upsert: 如果存在则更新，不存在则插入
    code_db.upsert(
        code_data, (Code.username == username) & (Code.code_name == code_name)
    )
    return True, "代码保存成功"


def get_code_content(username, code_name):
    """获取特定代码的内容"""
    code_doc = code_db.get((Code.username == username) & (Code.code_name == code_name))
    return code_doc.get("code_content", "") if code_doc else ""


# --- 对战管理功能 ---


def get_all_duels():
    """获取所有对战记录列表"""
    return duel_db.all()


def save_duel_record(duel_data):
    """保存对战记录"""
    # 确保 duel_data 是字典
    if not isinstance(duel_data, dict):
        print("Error: duel_data must be a dictionary.")
        return  # 或者抛出异常

    duel_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    duel_db.insert(duel_data)


def get_user_duels(username):
    """获取指定用户参与的所有对战记录"""
    return duel_db.search((Duel.user1 == username) | (Duel.user2 == username))


# --- 天梯排名功能 ---


def get_ladder_ranking():
    """获取完整的天梯排名列表 (已排序并添加排名)"""
    users = get_all_users_list()  # 获取用户文档列表
    ranking = []

    for user_doc in users:
        ranking.append(
            {
                "username": user_doc.get("username"),
                "ladder_points": user_doc.get("ladder_points", 1000),
                "division": user_doc.get("division", "新手区"),
            }
        )

    # 按积分降序排序
    ranking.sort(key=lambda x: x["ladder_points"], reverse=True)

    # 添加排名
    for i, user in enumerate(ranking):
        user["rank"] = i + 1

    return ranking


def get_division_ranking(division):
    """获取指定分区的天梯排名列表"""
    all_ranking = get_ladder_ranking()  # 获取完整排名
    division_ranking = [
        user for user in all_ranking if user.get("division") == division
    ]

    # 重新计算分区内排名
    for i, user in enumerate(division_ranking):
        user["division_rank"] = i + 1

    return division_ranking


def update_user_points(username, points_change):
    """更新用户的积分和分区"""
    user_doc = user_db.get(User.username == username)
    if not user_doc:
        return False

    current_points = user_doc.get("ladder_points", 1000)
    new_points = current_points + points_change

    # 根据积分更新分区
    if new_points < 1000:
        new_division = "新手区"
    elif new_points < 1500:
        new_division = "进阶区"
    else:
        new_division = "大师区"

    # 更新数据库
    user_db.update(
        {"ladder_points": new_points, "division": new_division},
        User.username == username,
    )
    return True


# --- 预设和辅助功能 ---


def get_baseline_codes():
    """获取预设的 Baseline 代码 (从 game.baselines 模块)"""
    # 这个函数现在从 game.baselines 获取代码
    return get_game_baselines()


def get_all_divisions():
    """获取所有可能的分区"""
    # 这个函数不涉及数据库，保持不变
    return ["新手区", "进阶区", "大师区"]


# 注意：旧的 users.json, codes.json, duels.json 文件如果存在且格式与 TinyDB 不兼容，
# 可能需要手动迁移数据或删除旧文件让 TinyDB 创建新的。
# TinyDB 的默认格式是 {"_default": { "1": {doc1}, "2": {doc2}, ... }}
# 如果希望保持根对象是列表或字典，可以使用不同的存储格式，但这会使代码更复杂。
# 当前实现使用了 TinyDB 的默认 JSON 存储。
