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


@ai_bp.route("/ai/list")
@login_required
def list_ai():
    """显示用户的AI代码列表"""
    ai_codes = AICode.query.filter_by(user_id=current_user.id).all()
    return render_template("ai/list.html", ai_codes=ai_codes)


@ai_bp.route("/ai/upload", methods=["GET", "POST"])
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


@ai_bp.route("/ai/activate/<int:ai_id>", methods=["POST"])
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


@ai_bp.route("/ai/delete/<int:ai_id>", methods=["POST"])
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


@ai_bp.route("/ai/edit/<int:ai_id>", methods=["GET", "POST"])
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


@ai_bp.route("/api/user/active_ai/<int:user_id>")
def get_active_ai(user_id):
    """API: 获取用户当前激活的AI代码信息"""
    user = User.query.get_or_404(user_id)

    active_ai = user.get_active_ai()

    if not active_ai:
        return jsonify({"success": False, "message": "用户没有激活的AI代码"})

    return jsonify({"success": True, "ai_id": active_ai.id, "name": active_ai.name})


@ai_bp.route("/api/user_ai_codes")
@login_required
def get_user_ai_codes():
    """API: 获取用户的AI代码列表"""

    ai_codes = AICode.query.filter_by(user_id=current_user.id).all()

    result = []
    for ai in ai_codes:
        result.append({"id": ai.id, "name": ai.name, "is_active": ai.is_active})

    return jsonify({"success": True, "ai_codes": result})


@ai_bp.route("/user/api/user_ai_codes", methods=["GET"])
@login_required
def api_user_ai_codes():
    """API: 获取当前登录用户的所有 AI 代码元数据列表

    返回:
        JSON格式的AI代码列表，包含id, name, description, is_active等
    """

    # 从数据库查询当前用户的AI代码
    from database.action import get_user_ai_codes

    ai_codes_data = get_user_ai_codes(current_user.id)

    if not ai_codes_data:
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
    else:
        result = ai_codes_data

    return jsonify({"success": True, "ai_codes": result})


@ai_bp.route("/user/api/load_ai/<int:ai_id>", methods=["GET"])
@login_required
def api_user_load_ai(ai_id):
    """API: 加载指定的AI代码进行校验

    参数:
        ai_id: AI代码ID

    返回:
        加载检查结果，包含是否加载成功和错误信息
    """
    from database.action import get_ai_code_path

    # 检查权限
    ai_code = AICode.query.get_or_404(ai_id)
    if ai_code.user_id != current_user.id:
        return jsonify({"success": False, "message": "您没有权限访问此AI代码"})

    # 获取文件路径
    file_path = get_ai_code_path(ai_id)
    if not file_path or not os.path.exists(file_path):
        return jsonify({"success": False, "message": "AI代码文件不存在"})

    # 仅加载并检查语法和接口，不实例化用于对战
    module, error = get_ai_module(ai_id)
    if error:
        return jsonify({"success": False, "message": f"AI代码校验失败: {error}"})

    # 检查是否有必要的接口
    has_make_move = hasattr(module, "make_move") and callable(
        getattr(module, "make_move")
    )
    if not has_make_move:
        return jsonify(
            {"success": False, "message": "AI代码缺少必要的make_move(game_state)接口"}
        )

    # 加载成功，返回校验通过信息
    return jsonify(
        {
            "success": True,
            "message": "AI代码校验通过",
            "ai_id": ai_id,
            "name": ai_code.name,
        }
    )


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


def load_ai_module(file_path):
    """
    加载AI代码模块并检查语法和接口

    参数:
        file_path: AI代码文件路径

    返回:
        module: 加载的模块对象，失败时返回None
    """
    try:
        # 获取文件名和目录
        directory, filename = os.path.split(file_path)
        module_name = os.path.splitext(filename)[0]

        # 构建加载模块所需的规范
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None:
            current_app.logger.error(f"无法为 {file_path} 创建模块规范")
            return None

        module = importlib.util.module_from_spec(spec)

        # 加载模块
        spec.loader.exec_module(module)

        # 检查必要的接口
        if not hasattr(module, "make_move") or not callable(
            getattr(module, "make_move")
        ):
            current_app.logger.warning(f"AI模块 {module_name} 缺少make_move方法")
            # 不立即返回None，保留警告但仍然返回模块以便上层处理

        return module
    except SyntaxError as e:
        current_app.logger.error(f"AI代码语法错误: {str(e)}")
        return None
    except Exception as e:
        current_app.logger.error(f"加载AI模块失败: {str(e)}")
        return None


@ai_bp.route("/api/load_ai/<int:ai_id>")
@login_required
def api_load_ai(ai_id):
    """API: 加载指定的AI代码并返回Player类"""
    ai_code = AICode.query.get_or_404(ai_id)

    # 检查权限
    if ai_code.user_id != current_user.id:
        return jsonify({"success": False, "message": "您没有权限访问此AI代码"})

    # 获取完整文件路径
    file_path = os.path.join(get_upload_path(), ai_code.code_path)
    if not os.path.exists(file_path):
        return jsonify({"success": False, "message": "AI代码文件不存在"})

    # 加载模块
    module = load_ai_module(file_path)
    if not module:
        return jsonify(
            {"success": False, "message": "AI代码加载失败，请检查代码格式是否符合要求"}
        )

    # 验证成功
    return jsonify(
        {
            "success": True,
            "message": "AI代码加载成功",
            "ai_id": ai_id,
            "name": ai_code.name,
        }
    )


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


def get_ai_module(ai_id):
    """
    获取指定AI代码的模块对象并进行语法和接口检查

    参数:
        ai_id: AI代码ID

    返回:
        (模块对象, 错误信息) 元组，成功时错误信息为None
    """
    ai_code = AICode.query.get(ai_id)
    if not ai_code:
        return None, "AI代码不存在"

    from database.action import get_ai_code_path

    file_path = get_ai_code_path(ai_id)
    if not file_path:
        file_path = os.path.join(get_upload_path(), ai_code.code_path)

    if not os.path.exists(file_path):
        return None, "AI代码文件不存在"

    module = load_ai_module(file_path)
    if not module:
        return None, "AI代码加载失败，可能存在语法错误"

    # 检查必要的接口
    if not hasattr(module, "make_move") or not callable(getattr(module, "make_move")):
        return module, "AI代码缺少必要的make_move(game_state)接口"

    return module, None


@ai_bp.route("/api/instantiate_player/<int:ai_id>", methods=["POST"])
@login_required
def instantiate_player(ai_id):
    try:
        # 获取请求数据
        data = request.get_json()
        room_id = data.get("room_id")

        if not room_id:
            return jsonify({"success": False, "message": "未提供房间ID"})

        # 检查AI代码
        ai_code = AICode.query.filter_by(id=ai_id, user_id=current_user.id).first()
        if not ai_code:
            return jsonify(
                {"success": False, "message": "无效的AI代码ID或您无权使用此代码"}
            )

        # 检查用户是否在房间中
        participant = RoomParticipant.query.filter_by(
            room_id=room_id, user_id=current_user.id, is_ai=False
        ).first()

        if not participant:
            return jsonify({"success": False, "message": "您不在此房间中"})

        # 加载代码并创建实例
        file_path = os.path.join(get_upload_path(), ai_code.code_path)
        if not os.path.exists(file_path):
            return jsonify({"success": False, "message": "AI代码文件不存在"})

        # 加载模块
        module = load_ai_module(file_path)
        if not module:
            return jsonify({"success": False, "message": "AI代码加载失败"})

        # 实例化Player类
        try:
            Player = getattr(module, "Player")
            player_instance = Player()
        except Exception as e:
            return jsonify(
                {"success": False, "message": f"Player类实例化失败: {str(e)}"}
            )

        # 将实例存储到数据库
        instance_id = participant.store_ai_instance(player_instance)

        # 更新参与者的AI代码信息
        participant.selected_ai_code_id = ai_id
        participant.ai_name = ai_code.name
        db.session.commit()

        return jsonify(
            {
                "success": True,
                "message": "Player实例创建成功",
                "ai_id": ai_id,
                "instance_id": instance_id,
            }
        )
    except Exception as e:
        current_app.logger.error(f"创建Player实例失败: {str(e)}")
        return jsonify({"success": False, "message": f"Player实例创建失败: {str(e)}"})


def store_ai_instance(ai_id, player_instance, room_id=None, user_id=None):
    """
    存储AI Player实例到数据库

    参数:
        ai_id: AI代码ID
        player_instance: Player实例
        room_id: 游戏房间ID
        user_id: 用户ID

    返回:
        实例ID
    """
    instance_id = None

    # 存储关联信息以便查询
    if room_id and user_id:
        # 更新数据库中的关系
        participant = RoomParticipant.query.filter_by(
            room_id=room_id, user_id=user_id, is_ai=False
        ).first()

        if participant:
            # 更新选择的AI代码ID
            ai_code = AICode.query.get(ai_id)
            if ai_code:
                participant.selected_ai_code_id = ai_id
                participant.ai_name = ai_code.name

                # 存储实例到数据库
                instance_id = participant.store_ai_instance(player_instance)
                db.session.commit()

    return instance_id


@ai_bp.route("/game/select_ai/<room_id>", methods=["POST"])
@login_required
def select_ai(room_id):
    """选择AI代码用于游戏"""
    data = request.get_json()
    ai_id = data.get("ai_id")

    if not ai_id:
        return jsonify({"success": False, "message": "未提供AI ID"})

    # 检查AI代码是否存在且属于当前用户
    ai_code = AICode.query.get(ai_id)
    if not ai_code or ai_code.user_id != current_user.id:
        return jsonify({"success": False, "message": "无效的AI代码"})

    # 检查用户是否在房间中
    participant = RoomParticipant.query.filter_by(
        room_id=room_id, user_id=current_user.id, is_ai=False
    ).first()

    if not participant:
        return jsonify({"success": False, "message": "您不在该房间中"})

    # 更新选择的AI代码
    participant.selected_ai_code_id = ai_id
    db.session.commit()

    return jsonify({"success": True, "message": "AI代码已选择"})
