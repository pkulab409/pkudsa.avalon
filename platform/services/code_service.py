import logging
from db.database import get_code_db
from tinydb import Query
import io
import sys
import traceback
import threading

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
            }

            # 创建安全的执行环境
            exec_globals = {"__builtins__": safe_builtins, "input_params": input_params}

            # 允许使用random模块(常用于策略生成)
            import random

            exec_globals["random"] = random

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


def get_code_templates():
    """获取预定义的代码模板"""
    templates = {
        "基础策略": """def play_game():
    # 返回 'rock', 'paper', 或 'scissors'
    return 'rock'
""",
        "随机策略": """def play_game():
    import random
    choices = ['rock', 'paper', 'scissors']
    return random.choice(choices)
""",
        "记忆策略": """# 全局变量用于记忆对手历史
opponent_moves = []

def play_game():
    import random
    choices = ['rock', 'paper', 'scissors']
    
    # 如果没有历史数据，随机选择
    if not opponent_moves:
        return random.choice(choices)
        
    # 根据对手历史选择最优策略
    # 这只是一个示例实现
    last_move = opponent_moves[-1]
    if last_move == 'rock':
        return 'paper'  # 克制石头
    elif last_move == 'paper':
        return 'scissors'  # 克制布
    else:
        return 'rock'  # 克制剪刀
""",
    }

    return templates
