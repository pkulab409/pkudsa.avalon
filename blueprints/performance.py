from flask import Blueprint, render_template, jsonify
import os
import json

# 创建蓝图
performance_bp = Blueprint("performance", __name__)

# JSON数据文件路径
JSON_DATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "game", "client_usage_times.json"
)


@performance_bp.route("/")
def performance_report_page():
    """性能报告页面"""
    return render_template("performance/report.html")


@performance_bp.route("/api/usage_times")
def get_usage_data():
    """获取客户端使用时间数据API"""
    try:
        with open(JSON_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify({"success": True, "data": data})
    except FileNotFoundError:
        return jsonify({"success": False, "error": "数据文件不存在"}), 404
    except json.JSONDecodeError:
        return jsonify({"success": False, "error": "JSON数据解析错误"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
