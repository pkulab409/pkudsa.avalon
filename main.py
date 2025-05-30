# 游戏对战平台主程序入口
from app import create_app
from flask import render_template
import logging
import os
import sys
import resource
import psutil
from game.avalon_game_helper import shutdown_helpers
from game.client_manager import get_client_manager
import atexit

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


# 程序退出前的清理函数
def cleanup_resources():
    """程序退出前清理资源"""
    print("正在清理资源...")
    # 关闭GameHelper实例
    shutdown_helpers()
    # 关闭客户端管理器
    client_manager = get_client_manager()
    if client_manager:
        client_manager.shutdown()
    print("资源清理完成")


# 在主程序退出前调用
atexit.register(cleanup_resources)

if __name__ == "__main__":
    try:
        # 在此处直接启动Gunicorn (WSGI服务器)
        from gunicorn.app.wsgiapp import WSGIApplication

        # 强制设置生产环境变量
        os.environ["FLASK_ENV"] = "production"
        os.environ["FLASK_DEBUG"] = "0"

        # 准备Gunicorn参数
        sys.argv = [
            "gunicorn",
            "--workers=1",  # 单线程模式
            "--timeout=300",  # 增加超时时间到5分钟，避免长时间操作被终止
            "--graceful-timeout=120",  # 优雅停止的超时时间
            "--max-requests=1000",  # 工作进程处理多少请求后自动重启，避免内存泄漏
            "--max-requests-jitter=100",  # 添加随机性，避免所有工作进程同时重启
            "--bind=0.0.0.0:5000",
            "main:app",
        ]

        # 启动Gunicorn
        WSGIApplication("%(prog)s [OPTIONS] [APP_MODULE]").run()
    except ImportError:
        print("错误: 请安装gunicorn: pip install gunicorn")
        sys.exit(1)
