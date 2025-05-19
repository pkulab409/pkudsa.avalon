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
cache = {
    "data": None,
    "last_update": 0,
    "lock": threading.Lock()
}

# 缓存更新间隔（秒）
CACHE_UPDATE_INTERVAL = 10

# 定时更新函数
def update_cache():
    with cache["lock"]:
        try:
            with open(JSON_DATA_FILE, "r", encoding="utf-8") as f:
                cache["data"] = json.load(f)
                cache["last_update"] = time.time()
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"缓存更新失败: {str(e)}")
    
    # 安排下一次更新
    threading.Timer(CACHE_UPDATE_INTERVAL, update_cache).start()

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
                return jsonify({"success": False, "error": "数据尚未加载"}), 503
                
            data = cache["data"]
            last_update = cache["last_update"]

        # 计算总记录数
        total_records = len(data)

        # 只返回最近的1000条数据
        recent_data = data[-1000:] if len(data) > 1000 else data

        return jsonify({
            "success": True, 
            "data": recent_data, 
            "total_records": total_records,
            "last_update": last_update,
            "next_update": last_update + CACHE_UPDATE_INTERVAL
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
