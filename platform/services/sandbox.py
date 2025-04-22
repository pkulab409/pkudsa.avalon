import sys
import io
import traceback
import threading

# 代码执行锁，保护全局资源
code_exec_lock = threading.Lock()

def _restricted_importer(name, globals=None, locals=None, fromlist=(), level=0):
    """安全模块导入器"""
    allowed_modules = {
        'random': (None, __import__('random')),
        're': (None, __import__('re')),
        'game': ('game', None),
        'game.avalon_game_helper': ('game.avalon_game_helper', None),
        'collections': (None, __import__('collections'))
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

            # 允许使用random模块(常用于策略生成)
            import random
            import re
            exec_globals["random"] = __import__('random')
            exec_globals["re"] = __import__('re')

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

