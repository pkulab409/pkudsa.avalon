# 游戏对战平台主程序入口
from app import create_app
from flask import render_template, jsonify  # 添加这一行导入render_template函数

# 创建应用实例
app = create_app()


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


# 查看最后一次 commit 信息
@app.route("/commit-info")
def commit_info():
    try:
        import subprocess

        result = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%h - %an, %ad : %s"],
            capture_output=True,
            text=True,
        )
        return jsonify(commit=result.stdout.strip())
    except Exception:
        return "Cannot get the latest commit info"


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
