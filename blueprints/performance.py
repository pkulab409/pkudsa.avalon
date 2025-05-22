from flask import Blueprint, render_template, jsonify
import os
import json
import time
import threading
import math

# 创建蓝图
performance_bp = Blueprint("performance", __name__)

# JSON数据文件路径
JSON_DATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "game", "client_usage_times.json"
)

# 全局缓存变量
# 移除了 "timer" 键，last_update 初始化为 0 以确保首次访问时加载数据
cache = {"data": None, "last_update": 0, "lock": threading.Lock()}

# 缓存更新间隔（秒）
CACHE_UPDATE_INTERVAL = 10


# 核心缓存更新逻辑（假定锁已被获取）
def _perform_cache_update_locked():
    """
    执行实际的缓存更新操作，从JSON文件加载数据。
    此函数假定 cache["lock"] 已被调用者获取。
    """
    try:
        # 检查文件是否存在，不存在则创建空文件
        if not os.path.exists(JSON_DATA_FILE):
            os.makedirs(os.path.dirname(JSON_DATA_FILE), exist_ok=True)
            with open(JSON_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)
            cache["data"] = []
        else:
            with open(JSON_DATA_FILE, "r", encoding="utf-8") as f:
                cache["data"] = json.load(f)

        cache["last_update"] = time.time()  # 仅在成功加载后更新时间戳
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"缓存更新失败 (JSON error): {str(e)}")
        if cache["data"] is None:  # 确保 data 至少是一个空列表
            cache["data"] = []
    except OSError as e:  # 捕获其他 OS 错误，例如权限错误
        print(f"缓存更新失败 (OS error): {str(e)}")
        if cache["data"] is None:
            cache["data"] = []
    except Exception as e:  # 捕获更新缓存时的任何其他意外错误
        print(f"缓存更新失败 (Unexpected error): {str(e)}")
        if cache["data"] is None:
            cache["data"] = []


# 应用启动时进行一次初始缓存加载
def initial_cache_load():
    with cache["lock"]:
        _perform_cache_update_locked()
        # 确保即使加载失败，cache["data"] 也被初始化为一个列表
        if cache["data"] is None:
            cache["data"] = []
        # 如果 _perform_cache_update_locked 失败，last_update 将保持为0，
        # 这将导致第一次API调用时尝试更新。


initial_cache_load()


@performance_bp.route("/")
def performance_report_page():
    """性能报告页面"""
    return render_template("performance/report.html")


# 辅助函数，用于清理数据中的 NaN/Infinity 值
def clean_usage_data(records):
    cleaned_records = []
    if not isinstance(records, list):  # 添加检查以确保 records 是列表
        return []

    for record in records:
        if not isinstance(record, dict):  # 跳过非字典类型的记录
            cleaned_records.append(record)
            continue

        cleaned_record = record.copy()
        usage_time = cleaned_record.get("usage_time")
        if isinstance(usage_time, float):
            if math.isnan(usage_time) or math.isinf(usage_time):
                cleaned_record["usage_time"] = None  # 替换为 None
        cleaned_records.append(cleaned_record)
    return cleaned_records


@performance_bp.route("/api/usage_times")
def get_usage_data():
    """获取客户端使用时间数据API"""
    try:
        with cache["lock"]:
            current_time = time.time()
            # 如果缓存从未更新过 (last_update == 0) 或缓存已过期，则更新缓存
            if cache["last_update"] == 0 or (
                current_time - cache["last_update"] > CACHE_UPDATE_INTERVAL
            ):
                print(
                    f"缓存过期或未初始化，执行更新。上次更新时间: {cache['last_update']}"
                )
                _perform_cache_update_locked()

            # 确保 cache["data"] 始终是一个列表，即使更新失败
            if cache["data"] is None:
                cache["data"] = []

            # 计算总记录数
            total_records = len(cache["data"])

            # 只返回最近的1000条数据
            recent_data = (
                cache["data"][-1000:] if total_records > 1000 else cache["data"]
            )

            # 清理数据以确保 JSON 可序列化
            cleaned_recent_data = clean_usage_data(recent_data)

        return jsonify(
            {
                "success": True,
                "data": cleaned_recent_data,
                "total_records": total_records,
            }
        )
    except Exception as e:
        # 实际应用中应使用更完善的日志记录
        print(f"处理 /api/usage_times 请求时发生错误: {str(e)}")
        return jsonify({"success": False, "error": "服务器内部错误"}), 500
