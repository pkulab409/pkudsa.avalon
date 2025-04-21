import logging
from db.database import get_user_db, get_duel_db
import json
import hashlib


def hash_password(password: str) -> str:
    """对密码进行 SHA-256 哈希"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def register_user(username, password) -> tuple[bool,str]:
    """注册新用户"""
    db = get_user_db()
    cursor = db.cursor()

    # 检查用户名是否已存在
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        return False, "用户名已存在"
    
    # 哈希密码后插入
    hashed_pw = hash_password(password)

    # 插入新用户（使用默认积分和分区）
    cursor.execute('''
        INSERT INTO users (username, password, ladder_points, division)
        VALUES (?, ?, ?, ?)
    ''', (username, hashed_pw, 1000, "新手区"))

    db.commit()
    return True, "注册成功"


def verify_user(username, password) -> tuple[bool,str]:
    """验证用户登录"""
    db = get_user_db()
    cursor = db.cursor()

    hashed_pw = hash_password(password)
    cursor.execute(
        "SELECT id FROM users WHERE username = ? AND password = ?",
        (username, hashed_pw)
    )
    result = cursor.fetchone()
    if result:
        return True, f"登录成功，用户ID：{result[0]}"
    return False, "用户名或密码错误"


def get_user_profile(username) -> dict:
    """获取用户个人资料"""
    db = get_user_db()
    cursor = db.cursor()

    cursor.execute(
        "SELECT username, ladder_points, division FROM users WHERE username = ?",
        (username,)
    )
    result = cursor.fetchone()

    if not result:
        return None
    return {
        "username": result[0],
        "ladder_points": result[1],
        "division": result[2]
    }


def get_user_duels(username) -> list[dict]:
    """获取用户的对战记录"""
    db = get_duel_db()
    cursor = db.cursor()

    # 获取用户ID
    user_db = get_user_db()
    user_cursor = user_db.cursor()
    user_cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = user_cursor.fetchone()

    if not user:
        return []

    user_id = user[0]

    # 查询出现在任一玩家位的对战记录
    cursor.execute('''
        SELECT * FROM duels
        WHERE player1_id = ?
           OR player2_id = ?
           OR player3_id = ?
           OR player4_id = ?
           OR player5_id = ?
           OR player6_id = ?
           OR player7_id = ?
    ''', (user_id,) * 7)

    columns = [desc[0] for desc in cursor.description]
    results = cursor.fetchall()
    return [dict(zip(columns, row)) for row in results]


def update_user_points(username, points_change) -> bool:
    """更新用户积分和分区"""
    db = get_user_db()
    cursor = db.cursor()

    # 获取当前积分
    cursor.execute("SELECT ladder_points FROM users WHERE username = ?", (username,))
    result = cursor.fetchone()
    if not result:
        return False

    current_points = result[0]
    new_points = current_points + points_change

    if new_points < 1000:
        new_division = "新手区"
    elif new_points < 1500:
        new_division = "进阶区"
    else:
        new_division = "大师区"

    cursor.execute('''
        UPDATE users
        SET ladder_points = ?, division = ?
        WHERE username = ?
    ''', (new_points, new_division, username))
    db.commit()
    return True
