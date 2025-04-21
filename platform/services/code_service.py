import logging
from db.database import get_code_db
from tinydb import Query
import io
import sys
import traceback
import threading
import types


Code = Query()

# 代码执行锁，保护全局资源
code_exec_lock = threading.Lock()


def get_user_codes(username):
    """获取指定用户的所有代码"""
    if not username:
        return {}

    db = get_code_db()
    user_code_docs = db.search(Code.username == username)
    codes_dict = {}
    for doc in user_code_docs:
        codes_dict[doc.get("code_name")] = doc.get("code_content")
    return codes_dict


def save_code(username, code_name, code_content):
    """保存或更新用户的代码"""
    if not username or not code_name or not code_content:
        return False, "用户名、代码名称和内容都不能为空"

    code_data = {
        "username": username,
        "code_name": code_name,
        "code_content": code_content,
    }

    db = get_code_db()
    # 使用upsert: 如果存在则更新，不存在则插入
    db.upsert(code_data, (Code.username == username) & (Code.code_name == code_name))
    return True, "代码保存成功"


def get_code_content(username, code_name):
    """获取特定代码的内容"""
    if not username or not code_name:
        return ""

    db = get_code_db()
    code_doc = db.get((Code.username == username) & (Code.code_name == code_name))
    return code_doc.get("code_content", "") if code_doc else ""


def _restricted_importer(name, globals=None, locals=None, fromlist=(), level=0):
    """安全模块导入器"""
    allowed_modules = {
        'random': (None, __import__('random')),
        're': (None, __import__('re')),
        'game': ('game', None),
        'game.avalon_game_helper': ('game.avalon_game_helper', None)
    }
    
    if name in allowed_modules:
        module_path, preload = allowed_modules[name]
        if preload is None:
            # 动态加载已创建的模块实例
            return sys.modules.get(module_path or name)
        return preload
    
    # 抛出精确的错误信息
    if any(name.startswith(m) for m in ['os', 'sys', 'subprocess']):
        raise ImportError(f"禁止导入系统模块: {name}")
    raise ImportError(f"模块不在白名单中: {name}")


def execute_code_safely(code_content, input_params=None):
    """
    在隔离环境中安全地执行用户代码

    Args:
        code_content: 要执行的代码内容
        input_params: 可选的代码输入参数

    Returns:
        tuple: (stdout_output, stderr_output, execution_result)
    """
    if not code_content:
        return "", "代码内容为空", None

    # 使用锁确保执行的线程安全性
    with code_exec_lock:
        # 捕获标准输出和错误
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        redirected_output = io.StringIO()
        redirected_error = io.StringIO()
        sys.stdout = redirected_output
        sys.stderr = redirected_error

        result = None
        try:
            # 准备执行环境
            safe_builtins = {
                "print": print,
                "len": len,
                "range": range,
                "int": int,
                "float": float,
                "str": str,
                "list": list,
                "dict": dict,
                "tuple": tuple,
                "sum": sum,
                "min": min,
                "max": max,
                "round": round,
                "abs": abs,
                "all": all,
                "any": any,
                "enumerate": enumerate,
                "zip": zip,
                "map": map,
                "filter": filter,
                "sorted": sorted,
                "reversed": reversed,
                "bool": bool,
                "True": True,
                "False": False,
                "None": None,
                "__build_class__": __build_class__,
                "__name__": "__main__",
                "__import__": _restricted_importer
            }

            # 创建安全的执行环境
            exec_globals = {"__builtins__": safe_builtins, "input_params": input_params}


            # 安全导入game模块函数
            game_module = types.ModuleType('game')
            avalon_helper = types.ModuleType('avalon_game_helper')
            
            # 从实际模块导入允许的函数
            original_module = __import__('game.avalon_game_helper', fromlist=['*'])
            for func in ['askLLM', 'read_public_lib', 'read_private_lib', 'write_into_private']:
                setattr(avalon_helper, func, getattr(original_module, func))
            
            game_module.avalon_game_helper = avalon_helper
            exec_globals['game'] = game_module

            # # 允许使用random模块(常用于策略生成)
            # import random
            # import re

            # exec_globals["random"] = __import__('random')
            # exec_globals["re"] = __import__('re')

            # 执行代码
            exec(code_content, exec_globals)

            # 尝试获取play_game函数的结果
            if "play_game" in exec_globals and callable(exec_globals["play_game"]):
                result = exec_globals["play_game"]()
                print(f"play_game() 返回结果: {result}")
        except Exception as e:
            print(f"执行错误: {str(e)}")
            traceback.print_exc(file=sys.stderr)
        finally:
            # 恢复标准输出和错误
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        return redirected_output.getvalue(), redirected_error.getvalue(), result


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


def get_code_templates():
    """获取预定义的代码模板"""
    templates = {
        "Avalon - Player 类模板": AVALON_CODE_TEMPLATE
    }

    return templates
