# 游戏对战平台主程序入口
from app import create_app
from flask_socketio import SocketIO
from blueprints.game import register_socket_events
from flask import render_template  # 添加这一行导入render_template函数

# 创建应用实例
app = create_app()

# 初始化Socket.IO支持实时游戏通信
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

# 注册Socket.IO事件处理器
register_socket_events(socketio)


# 全局错误处理
@app.errorhandler(404)
def page_not_found(e):
    return render_template("errors/404.html"), 404  # 使用导入的render_template函数


@app.errorhandler(500)
def internal_server_error(e):
    return render_template("errors/500.html"), 500  # 这里也需要修改


# 健康检查端点
@app.route("/health")
def health_check():
    return {"status": "ok", "service": "game-platform"}, 200


if __name__ == "__main__":
    # 使用socketio.run代替app.run以支持WebSocket
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)
    # 生产环境部署请使用：
    # gunicorn --worker-class gevent --workers 4 --bind 0.0.0.0:5000 main:app
