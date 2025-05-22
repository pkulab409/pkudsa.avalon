from flask import Blueprint, render_template, jsonify
import os
import json
import time
import threading

# 创建蓝图
performance_bp = Blueprint("performance", __name__)

# JSON数据文件路径
JSON_DATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "game", "client_usage_times.json"
)

# 全局缓存变量
cache = {"data": None, "last_update": 0, "lock": threading.Lock(), "timer": None}

# 缓存更新间隔（秒）
CACHE_UPDATE_INTERVAL = 10


# 定时更新函数
def update_cache():
    with cache["lock"]:
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

            cache["last_update"] = time.time()
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"缓存更新失败: {str(e)}")
            # 确保出错时至少有一个空数组
            if cache["data"] is None:
                cache["data"] = []

    # 取消旧计时器
    if cache["timer"] is not None:
        cache["timer"].cancel()

    # 安排下一次更新
    cache["timer"] = threading.Timer(CACHE_UPDATE_INTERVAL, update_cache)
    cache["timer"].daemon = True  # 设为守护线程，避免阻止程序退出
    cache["timer"].start()


# 在应用启动时开始缓存更新循环
update_cache()


@performance_bp.route("/")
def performance_report_page():
    """性能报告页面"""
    return render_template("performance/report.html")


@performance_bp.route("/api/usage_times")
def get_usage_data():
    """获取客户端使用时间数据API"""
    try:
        with cache["lock"]:
            if not cache["data"]:
                cache["data"] = []  # 确保至少是一个空数组

        # 计算总记录数
        total_records = len(cache["data"])

        # 只返回最近的1000条数据
        recent_data = (
            cache["data"][-1000:] if len(cache["data"]) > 1000 else cache["data"]
        )

        return jsonify(
            {
                "success": True,
                "data": recent_data,
                "total_records": total_records,
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
