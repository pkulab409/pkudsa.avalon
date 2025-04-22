import logging
from db.database import get_code_db
import sqlite3

# 配置日志记录
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_user_codes(username: str) -> dict[str, str]:
    """获取指定用户的所有代码"""
    if not username:
        logging.warning("get_user_codes: 用户名为空")
        return {}

    db = get_code_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT code_name, code_content FROM codes WHERE username = ?", (username,))
        result = cursor.fetchall()

        codes_dict = {code_name: code_content for code_name, code_content in result}
        logging.info(f"get_user_codes: 获取到 {len(codes_dict)} 条代码记录 for {username}")
        return codes_dict
    except sqlite3.Error as e:
        logging.error(f"get_user_codes: 数据库错误 - {e}")
        return {}
    finally:
        cursor.close()  # 确保游标关闭


def save_code(username: str, code_name: str, code_content: str) -> tuple[bool, str]:
    """保存或更新用户的代码"""
    if not username or not code_name or not code_content:
        logging.warning("save_code: 用户名、代码名称或代码内容为空")
        return False, "用户名、代码名称和内容都不能为空"

    db = get_code_db()
    cursor = db.cursor()
    try:
        cursor.execute('''
            INSERT INTO codes (username, code_name, code_content)
            VALUES (?, ?, ?)
            ON CONFLICT(username, code_name) DO UPDATE SET code_content=excluded.code_content
        ''', (username, code_name, code_content))
        db.commit()
        logging.info(f"save_code: 代码 '{code_name}' 已成功保存/更新 for {username}")
        return True, "代码保存成功"
    except sqlite3.Error as e:
        logging.error(f"save_code: 数据库错误 - {e}")
        return False, f"数据库错误：{e}"
    finally:
        cursor.close()  # 确保游标关闭


def get_code_content(username: str, code_name: str) -> str:
    """获取特定代码的内容"""
    if not username or not code_name:
        logging.warning("get_code_content: 用户名或代码名称为空")
        return ""

    db = get_code_db()
    cursor = db.cursor()
    try:
        cursor.execute('''
            SELECT code_content FROM codes
            WHERE username = ? AND code_name = ?
        ''', (username, code_name))
        result = cursor.fetchone()
        if result:
            logging.info(f"get_code_content: 获取到代码 '{code_name}' for {username}")
            return result[0]
        else:
            logging.info(f"get_code_content: 未找到代码 '{code_name}' for {username}")
            return ""
    except sqlite3.Error as e:
        logging.error(f"get_code_content: 数据库错误 - {e}")
        return ""
    finally:
        cursor.close()  # 确保游标关闭


AVALON_CODE_TEMPLATE = r'''
import random
import re
from game.avalon_game_helper import (
    askLLM,
    read_public_lib,
    read_private_lib,
    write_into_private,
)


class Player:
    def __init__(self):
        pass


    def set_player_index(self, index: int):
        """设置玩家编号"""
        pass


    def set_role_type(self, role_type: str):
        """设置角色类型"""
        pass


    def pass_role_sight(self, role_sight: dict[str, int]):
        """传递角色视野信息"""
        pass


    def pass_map(self, map_data: list[list[str]]):
        """传递地图数据"""
        pass


    def pass_message(self, content: tuple[int, str]):
        """传递其他玩家发言"""
        pass


    def pass_mission_members(self, leader: int, members: list[int]):
        """告知任务队长和队员"""
        pass


    def decide_mission_member(self, member_number: int) -> list[int]:
        """选择任务队员"""
        pass


    def walk(self) -> tuple[str, ...]:
        """走步，返回(方向,...)"""
        pass


    def say(self) -> str:
        """发言"""
        pass


    def mission_vote1(self) -> bool:
        """公投表决"""
        pass


    def mission_vote2(self) -> bool:
        """任务执行投票"""
        pass


    def assass(self) -> int:
        """刺杀（只有刺客角色会被调用）"""
        pass

'''

def get_code_templates() -> dict[str, str]:
    """获取预定义的代码模板"""
    templates = {
        "Avalon - Player 类模板": AVALON_CODE_TEMPLATE
    }

    return templates
