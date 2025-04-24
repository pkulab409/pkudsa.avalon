import os
import uuid
from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
    current_app,
    jsonify,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from database.models import db, AICode, User, Room, RoomParticipant
from datetime import datetime
import importlib.util
import sys
import inspect
import pickle

# 创建蓝图
ai_bp = Blueprint("ai", __name__)


def get_upload_path():
    """获取AI代码上传目录"""
    base_path = os.path.join(current_app.root_path, "uploads", "ai_codes")
    os.makedirs(base_path, exist_ok=True)
    return base_path


def allowed_file(filename):
    """检查文件是否为允许的类型"""
    ALLOWED_EXTENSIONS = {"py"}
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# api接口定义
@ai_bp.route("/list_ai")
@login_required
def list_ai():
    """显示用户的AI代码列表"""
    ai_codes = AICode.query.filter_by(user_id=current_user.id).all()
    return render_template("ai/list.html", ai_codes=ai_codes)


@ai_bp.route("/upload_ai", methods=["GET", "POST"])
@login_required
def upload_ai():
    """上传AI代码"""
    if request.method == "POST":
        # 检查是否有文件
        if "ai_code" not in request.files:
            flash("没有选择文件", "danger")
            return redirect(request.url)

        file = request.files["ai_code"]

        # 如果用户未选择文件
        if file.filename == "":
            flash("没有选择文件", "danger")
            return redirect(request.url)

        if file and allowed_file(file.filename):
            # 保存文件
            filename = secure_filename(file.filename)
            unique_id = str(uuid.uuid4())
            new_filename = f"{current_user.id}_{unique_id}_{filename}"
            file_path = os.path.join(get_upload_path(), new_filename)
            file.save(file_path)

            # 获取表单数据
            name = request.form.get("name", "我的AI")
            description = request.form.get("description", "")

            # 检查是否设为当前活跃AI
            make_active = request.form.get("make_active") == "on"

            # 创建数据库记录
            ai_code = AICode(
                user_id=current_user.id,
                name=name,
                code_path=new_filename,
                description=description,
                is_active=make_active,
            )

            # 如果设为当前活跃AI，需要将其他同类型的AI设为非活跃
            if make_active:
                AICode.query.filter_by(user_id=current_user.id, is_active=True).update(
                    {"is_active": False}
                )

            db.session.add(ai_code)
            db.session.commit()

            flash("AI代码上传成功！", "success")
            return redirect(url_for("ai.list_ai"))
        else:
            flash("不支持的文件类型", "danger")

    return render_template("ai/upload.html")


@ai_bp.route("/activate_ai/<int:ai_id>", methods=["POST"])
@login_required
def activate_ai(ai_id):
    """激活指定的AI代码"""
    ai_code = AICode.query.get_or_404(ai_id)

    # 检查权限
    if ai_code.user_id != current_user.id:
        flash("您没有权限修改此AI代码", "danger")
        return redirect(url_for("ai.list_ai"))

    # 将同一游戏类型的其他AI设为非活跃
    AICode.query.filter_by(user_id=current_user.id, is_active=True).update(
        {"is_active": False}
    )

    # 设置当前AI为活跃
    ai_code.is_active = True
    db.session.commit()

    flash(f"已将 '{ai_code.name}' 设为当前活跃AI", "success")
    return redirect(url_for("ai.list_ai"))


@ai_bp.route("/delete_ai/<int:ai_id>", methods=["POST"])
@login_required
def delete_ai(ai_id):
    """删除AI代码"""
    ai_code = AICode.query.get_or_404(ai_id)

    # 检查权限
    if ai_code.user_id != current_user.id:
        flash("您没有权限删除此AI代码", "danger")
        return redirect(url_for("ai.list_ai"))

    # 删除文件
    try:
        file_path = os.path.join(get_upload_path(), ai_code.code_path)
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        current_app.logger.error(f"删除AI代码文件失败: {str(e)}")

    # 删除数据库记录
    db.session.delete(ai_code)
    db.session.commit()

    flash("AI代码已删除", "success")
    return redirect(url_for("ai.list_ai"))


@ai_bp.route("/edit_ai/<int:ai_id>", methods=["GET", "POST"])
@login_required
def edit_ai(ai_id):
    """编辑AI代码信息"""
    ai_code = AICode.query.get_or_404(ai_id)

    # 检查权限
    if ai_code.user_id != current_user.id:
        flash("您没有权限编辑此AI代码", "danger")
        return redirect(url_for("ai.list_ai"))

    if request.method == "POST":
        # 更新信息
        ai_code.name = request.form.get("name", ai_code.name)
        ai_code.description = request.form.get("description", ai_code.description)

        # 检查是否设为当前活跃AI
        make_active = request.form.get("make_active") == "on"

        if make_active and not ai_code.is_active:
            # 将同一游戏类型的其他AI设为非活跃
            AICode.query.filter_by(user_id=current_user.id, is_active=True).update(
                {"is_active": False}
            )
            ai_code.is_active = True

        db.session.commit()
        flash("AI代码信息已更新", "success")
        return redirect(url_for("ai.list_ai"))

    return render_template("ai/edit.html", ai_code=ai_code)


@ai_bp.route("/get_active_ai/")
def get_active_ai(user_id):
    """API: 获取用户当前激活的AI代码信息"""
    active_ai = current_user.get_active_ai()
    if not active_ai:
        return jsonify({"success": False, "message": "用户没有激活的AI代码"})
    return jsonify({"success": True, "ai_id": active_ai.id, "name": active_ai.name})


@ai_bp.route("/get_user_ai_codes", methods=["GET"])
@login_required
def get_user_ai_codes():
    """获取用户的AI代码列表

    返回:
        JSON格式的AI代码列表，包含id, name, description, is_active等
    """
    try:
        # 从数据库获取当前用户的所有AI代码
        ai_codes = AICode.query.filter_by(user_id=current_user.id).all()
        result = []
        for ai in ai_codes:
            result.append(
                {
                    "id": ai.id,
                    "name": ai.name,
                    "description": ai.description,
                    "is_active": ai.is_active,
                }
            )
        return jsonify({"success": True, "ai_codes": result})
    except Exception as e:
        current_app.logger.error(f"获取AI代码列表失败: {str(e)}")
        return jsonify({"success": False, "message": f"获取AI代码列表失败: {str(e)}"})


# 工具函数
# ------------------------------------------------------------------------------------
def load_ai_module(file_path):
    """
    动态加载用户上传的AI代码文件

    参数:
        file_path: AI代码文件的完整路径

    返回:
        导入的模块对象或None(如果导入失败)
    """
    try:
        # 生成唯一的模块名以避免冲突
        module_name = f"user_ai_{uuid.uuid4().hex}"

        # 从文件加载模块规格
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if not spec:
            current_app.logger.error(f"无法从{file_path}创建模块规格")
            return None

        # 创建模块并加载
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # 验证模块是否包含Player类
        if not hasattr(module, "Player"):
            current_app.logger.error(f"AI代码缺少Player类: {file_path}")
            return None

        # 验证Player类是否包含必要的方法
        required_methods = [
            "set_player_index",
            "set_role_type",
            "pass_role_sight",
            "pass_map",
            "pass_message",
            "pass_mission_members",
            "decide_mission_member",
            "walk",
            "say",
            "mission_vote1",
            "mission_vote2",
            "assass",
        ]

        player_class = getattr(module, "Player")
        missing_methods = []

        for method in required_methods:
            if not hasattr(player_class, method):
                missing_methods.append(method)

        if missing_methods:
            current_app.logger.error(
                f"AI代码缺少必要的方法: {', '.join(missing_methods)}"
            )
            return None

        return module
    except Exception as e:
        current_app.logger.error(f"加载AI代码失败: {str(e)}")
        return None


def get_ai_module(ai_id):
    """
    获取指定AI代码的模块对象

    参数:
        ai_id: AI代码ID

    返回:
        (模块对象, 错误信息) 元组，成功时错误信息为None
    """
    ai_code = AICode.query.get(ai_id)
    if not ai_code:
        return None, "AI代码不存在"

    file_path = os.path.join(get_upload_path(), ai_code.code_path)
    if not os.path.exists(file_path):
        return None, "AI代码文件不存在"

    module = load_ai_module(file_path)
    if not module:
        return None, "AI代码加载失败"

    return module, None


# ------------------------------------------------------------------------------------
