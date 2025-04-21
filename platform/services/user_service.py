import logging
from db.database import get_user_db, get_duel_db
import hashlib
import sqlite3

# 配置日志记录
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def hash_password(password: str) -> str:
    """对密码进行 SHA-256 哈希"""
    hashed = hashlib.sha256(password.encode('utf-8')).hexdigest()
    logging.debug(f"hash_password: 密码哈希为 {hashed}")
    return hashed


def register_user(username: str, password: str) -> tuple[bool, str]:
    """注册新用户"""
    db = get_user_db()
    try:
        cursor = db.cursor()

        # 检查用户名是否已存在
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            logging.warning(f"register_user: 用户名 {username} 已存在")
            return False, "用户名已存在"
        
        # 哈希密码后插入
        hashed_pw = hash_password(password)

        # 插入新用户（使用默认积分和分区）
        cursor.execute('''
            INSERT INTO users (username, password, ladder_points, division)
            VALUES (?, ?, ?, ?)
        ''', (username, hashed_pw, 1000, "新手区"))
        db.commit()
        logging.info(f"register_user: 用户 {username} 注册成功")
        return True, "注册成功"
    except sqlite3.Error as e:
        logging.error(f"register_user: 数据库错误 {e}")
        raise Exception(f"数据库错误：{e}")
    except Exception as e:
        logging.error(f"register_user: 未知错误 {e}")
        raise Exception(f"未知错误：{e}")
    finally:
        cursor.close()


def verify_user(username: str, password: str) -> tuple[bool, str]:
    """验证用户登录"""
    db = get_user_db()
    try:
        cursor = db.cursor()

        hashed_pw = hash_password(password)
        cursor.execute(
            "SELECT id FROM users WHERE username = ? AND password = ?",
            (username, hashed_pw)
        )
        result = cursor.fetchone()
        if result:
            logging.info(f"verify_user: 用户 {username} 登录成功，用户ID：{result[0]}")
            return True, f"登录成功，用户ID：{result[0]}"
        logging.warning(f"verify_user: 用户名或密码错误，用户名: {username}")
        return False, "用户名或密码错误"
    except sqlite3.Error as e:
        logging.error(f"verify_user: 数据库错误 {e}")
        raise Exception(f"数据库错误：{e}")
    except Exception as e:
        logging.error(f"verify_user: 未知错误 {e}")
        raise Exception(f"未知错误：{e}")
    finally:
        cursor.close()


def get_user_profile(username: str) -> dict:
    """获取用户个人资料"""
    db = get_user_db()
    try:
        cursor = db.cursor()

        cursor.execute(
            "SELECT username, ladder_points, division FROM users WHERE username = ?",
            (username,)
        )
        result = cursor.fetchone()

        if not result:
            logging.warning(f"get_user_profile: 用户 {username} 不存在")
            return None
        profile = {
            "username": result[0],
            "ladder_points": result[1],
            "division": result[2]
        }
        logging.info(f"get_user_profile: 用户 {username} 的个人资料：{profile}")
        return profile
    except sqlite3.Error as e:
        logging.error(f"get_user_profile: 数据库错误 {e}")
        raise Exception(f"数据库错误：{e}")
    except Exception as e:
        logging.error(f"get_user_profile: 未知错误 {e}")
        raise Exception(f"未知错误：{e}")
    finally:
        cursor.close()


def get_user_duels(username: str) -> list[dict]:
    """获取用户的对战记录"""
    db = get_duel_db()
    try:
        cursor = db.cursor()

        # 获取用户ID
        user_db = get_user_db()
        user_cursor = user_db.cursor()
        user_cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        user = user_cursor.fetchone()

        if not user:
            logging.warning(f"get_user_duels: 用户 {username} 不存在")
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
        duels = [dict(zip(columns, row)) for row in results]
        logging.info(f"get_user_duels: 获取到 {len(duels)} 条对战记录 for {username}")
        return duels
    except sqlite3.Error as e:
        logging.error(f"get_user_duels: 数据库错误 {e}")
        raise Exception(f"数据库错误：{e}")
    except Exception as e:
        logging.error(f"get_user_duels: 未知错误 {e}")
        raise Exception(f"未知错误：{e}")
    finally:
        cursor.close()


def update_user_points(username: str, points_change: int) -> bool:
    """更新用户积分和分区"""
    db = get_user_db()
    try:
        cursor = db.cursor()

        # 获取当前积分
        cursor.execute("SELECT ladder_points FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()
        if not result:
            logging.warning(f"update_user_points: 用户 {username} 不存在")
            return False

        current_points = result[0]
        new_points = current_points + points_change

        # 更新分区
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
        logging.info(f"update_user_points: 用户 {username} 积分更新为 {new_points}，分区更新为 {new_division}")
        return True
    except sqlite3.Error as e:
        logging.error(f"update_user_points: 数据库错误 {e}")
        raise Exception(f"数据库错误：{e}")
    except Exception as e:
        logging.error(f"update_user_points: 未知错误 {e}")
        raise Exception(f"未知错误：{e}")
    finally:
        cursor.close()