# 游戏对战平台主程序入口
from app import create_app
from flask import render_template
import logging
import os
import sys
import resource
import psutil

# 创建应用实例
app = create_app()

# 在生产环境中设置适当的日志级别
if os.environ.get("FLASK_ENV") == "production":
    app.logger.setLevel(logging.INFO)
else:
    app.logger.setLevel(logging.DEBUG)


# 全局错误处理
@app.errorhandler(404)
def page_not_found(e):
    return render_template("errors/404.html"), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template("errors/500.html"), 500


# 健康检查端点增强版
@app.route("/health")
def health_check():
    process = psutil.Process()
    memory_info = process.memory_info()
    return {
        "status": "ok",
        "service": "game-platform",
        "memory_usage_mb": memory_info.rss / 1024 / 1024,
        "cpu_percent": process.cpu_percent(),
    }, 200


if __name__ == "__main__":
    # 开发模式直接运行
    app.run(host="0.0.0.0", port=5000, debug=False)
