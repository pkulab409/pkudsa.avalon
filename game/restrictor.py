"""
restrictor.py -- 限制用户代码的 __builtins__
"""

import types


def _restricted_importer(name, globals=None, locals=None, fromlist=(), level=0):
    """安全模块导入器"""
    if name == "game.avalon_game_helper":
        # 正确导入子模块
        helper_module = __import__(name, globals, locals, fromlist, level)

        # 创建受限模块对象
        restricted_module = types.ModuleType(name)
        # 暴露允许的接口
        allowed_attrs = [
            "write_into_private",
            "read_private_lib",
            "read_public_lib",
            "askLLM",
        ]
        for attr in allowed_attrs:
            setattr(restricted_module, attr, getattr(helper_module, attr))
        return restricted_module

    # 白名单
    allowed_modules = {
        "random": __import__("random"),
        "re": __import__("re"),
        "collections": __import__("collections"),
        "math": __import__("math"),
        "json": __import__("json"),
        # 建议添加的模块
        "itertools": __import__("itertools"),  # 提供高效的循环迭代工具
        "functools": __import__("functools"),  # 高阶函数和操作可调用对象的工具
        "copy": __import__("copy"),  # 提供深浅拷贝功能
        "heapq": __import__("heapq"),  # 堆队列算法
        "datetime": __import__("datetime"),  # 日期时间处理
        "string": __import__("string"),  # 常用字符串常量和操作
        "bisect": __import__("bisect"),  # 数组二分查找算法
        "statistics": __import__("statistics"),  # 提供数学统计功能
        "typing": __import__("typing"),  # 类型提示支持
    }

    if name in allowed_modules:
        return allowed_modules[name]

    # Raise precise error messages
    if any(name.startswith(m) for m in ["os", "sys", "subprocess"]):
        raise ImportError(f"禁止导入系统模块: {name}")
    raise ImportError(f"模块不在白名单中: {name}")


RESTRICTED_BUILTINS = {
    "print": print,
    "len": len,
    "range": range,
    "int": int,
    "float": float,
    "str": str,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
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
    "pow": pow,
    "divmod": divmod,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "id": id,
    "chr": chr,
    "ord": ord,
    "hex": hex,
    "oct": oct,
    "bin": bin,
    "format": format,
    "slice": slice,
    "hash": hash,
    "help": help,
    "dir": dir,
    "repr": repr,
    "callable": callable,
    "frozenset": frozenset,
    "memoryview": memoryview,
    "bytearray": bytearray,
    "bytes": bytes,
    "complex": complex,
    "property": property,
    "staticmethod": staticmethod,
    "classmethod": classmethod,
    "super": super,
    "object": object,
    # 没有 open, globals, locals, eval, exec
    "__build_class__": __build_class__,
    "__name__": "platform",
    "__import__": _restricted_importer,
    # 部分异常类
    "Exception": Exception,
    "ValueError": ValueError,
    "IndexError": IndexError,
    # 新增的内置函数
    "ascii": ascii,
    "iter": iter,
    "next": next,
    "getattr": getattr,
    "hasattr": hasattr,
    "setattr": setattr,
    "delattr": delattr,
    "type": type,
    "vars": vars,
    "__doc__": __doc__,
    # 更多异常类
    "TypeError": TypeError,
    "KeyError": KeyError,
    "AttributeError": AttributeError,
    "StopIteration": StopIteration,
    "NameError": NameError,
    "SyntaxError": SyntaxError,
    "RuntimeError": RuntimeError,
    "ZeroDivisionError": ZeroDivisionError,
    "AssertionError": AssertionError,
    "ImportError": ImportError,
}
