import os
from flask import Flask, send_from_directory, abort, request, jsonify
from dotenv import load_dotenv

app = Flask(__name__)

# 配置文件的存放目录
CWD = os.path.dirname(os.path.abspath(__file__))

# 加载 .env 文件中的密码配置
load_dotenv(dotenv_path=os.path.join(CWD, ".env"))
VALID_PASSWORD = os.getenv("VALID_PASSWORD")


@app.route("/api/config/verify", methods=["POST"])
def verify_password():
    """
    客户端登录验证接口，验证密码是否正确
    """
    try:
        data = request.get_json()
        if not data or "password" not in data:
            return jsonify({"success": False, "message": "Missing password"}), 400
        if data["password"] == VALID_PASSWORD:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "message": "Incorrect password"}), 401
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


def check_auth():
    """
    检查请求中的 Authorization 头部是否有效。
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer ") or auth_header[7:] != VALID_PASSWORD:
        abort(403, description="Unauthorized access. Invalid password.")


@app.route("/api/config/env", methods=["GET"])
def get_env_file():
    """
    提供 .env 文件的下载
    """
    check_auth()
    try:
        print(f"Attempting to send .env from: {os.path.join(CWD, 'game')}")
        return send_from_directory(
            os.path.join(CWD, "game"), ".env", as_attachment=True
        )
    except FileNotFoundError:
        print(f".env file not found in {os.path.join(CWD, 'game')}")
        abort(404, description=".env file not found on server.")
    except Exception as e:
        print(f"Error sending .env file: {e}")
        abort(500, description="Internal server error while retrieving .env file.")


@app.route("/api/config/yaml", methods=["GET"])
def get_yaml_file():
    """
    提供 config.yaml 文件的下载
    """
    check_auth()
    try:
        print(f"Attempting to send config.yaml from: {os.path.join(CWD, 'config')}")
        return send_from_directory(
            os.path.join(CWD, "config"), "config.yaml", as_attachment=True
        )
    except FileNotFoundError:
        print(f"config.yaml file not found in {os.path.join(CWD, 'config')}")
        abort(404, description="config.yaml file not found on server.")
    except Exception as e:
        print(f"Error sending config.yaml file: {e}")
        abort(
            500, description="Internal server error while retrieving config.yaml file."
        )


if __name__ == "__main__":
    # 运行 Flask 应用
    # 在生产环境中，应该使用更健壮的 WSGI 服务器，如 Gunicorn 或 uWSGI
    app.run(host="0.0.0.0", port=5001, debug=False)
