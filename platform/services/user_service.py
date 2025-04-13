import logging
from db.database import get_user_db
from tinydb import Query

User = Query()


def register_user(username, password):
    """注册新用户"""
    db = get_user_db()

    if db.contains(User.username == username):
        return False, "用户名已存在"

    user_data = {
        "username": username,
        "password": password,  # 生产环境应该哈希密码
        "ladder_points": 1000,  # 初始积分
        "division": "新手区",  # 初始分区
    }
    db.insert(user_data)
    return True, "注册成功"


def verify_user(username, password):
    """验证用户登录"""
    db = get_user_db()
    user_doc = db.get(User.username == username)

    if not user_doc:
        return False, "用户名不存在"
    if user_doc.get("password") != password:
        return False, "密码错误"
    return True, "登录成功"


def get_user_profile(username):
    """获取用户个人资料"""
    db = get_user_db()
    user_doc = db.get(User.username == username)

    if not user_doc:
        return None
    return user_doc.copy()


def get_user_duels(username):
    """获取用户的对战记录"""
    from db.database import get_duel_db

    Duel = Query()

    duel_db = get_duel_db()
    return duel_db.search((Duel.user1 == username) | (Duel.user2 == username))


def update_user_points(username, points_change):
    """更新用户积分"""
    db = get_user_db()
    user_doc = db.get(User.username == username)

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

    db.update(
        {"ladder_points": new_points, "division": new_division},
        User.username == username,
    )
    return True
