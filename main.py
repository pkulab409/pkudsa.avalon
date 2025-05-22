# 游戏对战平台主程序入口
from app import create_app
from flask import render_template
import logging
import os
import sys

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


# 健康检查端点
@app.route("/health")
def health_check():
    return {"status": "ok", "service": "game-platform"}, 200


if __name__ == "__main__":
    try:
        # 在此处直接启动Gunicorn (WSGI服务器) 单线程模式
        from gunicorn.app.wsgiapp import WSGIApplication

        # 强制设置生产环境变量
        os.environ["FLASK_ENV"] = "production"
        os.environ["FLASK_DEBUG"] = "0"

        # 准备Gunicorn参数
        sys.argv = [
            "gunicorn",
            "--workers=1",  # 单线程模式
            "--bind=0.0.0.0:5000",
            "main:app",
        ]

        # 启动Gunicorn
        WSGIApplication("%(prog)s [OPTIONS] [APP_MODULE]").run()
    except ImportError:
        print("错误: 请安装gunicorn: pip install gunicorn")
        sys.exit(1)
