# author: shihuaidexianyu (refactored by AI assistant)
# date: 2025-04-25
# status: refactored
# description: 用于处理AI代码上传、编辑、删除和激活的蓝图


# 包含页面 html:ai/list.html, ai/upload.html, ai/edit.html

import os
import random
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

# 导入 database 操作函数
from database import (
    get_user_ai_codes as db_get_user_ai_codes,
    create_ai_code as db_create_ai_code,
    set_active_ai_code as db_set_active_ai_code,
    get_ai_code_by_id as db_get_ai_code_by_id,
    update_ai_code as db_update_ai_code,
    delete_ai_code as db_delete_ai_code,
    get_user_active_ai_code as db_get_user_active_ai_code,
    get_ai_code_path_full as db_get_ai_code_path_full,
    get_user_by_id as db_get_user_by_id,
    get_available_ai_instances,
    update_battle_player_count,
    add_player_to_battle,
    create_battle_instance,
)
from database.models import AICode  # 仍然需要模型用于类型提示或特定查询
from datetime import datetime
import importlib.util
import sys
import inspect
import pickle

# 创建蓝图
ai_bp = Blueprint("ai", __name__)


def get_upload_path():
    """获取AI代码上传目录"""
    # 使用 current_app.config 获取配置，更灵活:TODO
    # 这里假设配置中有一个键 "AI_CODE_UPLOAD_FOLDER"
    upload_folder = current_app.config.get(
        "AI_CODE_UPLOAD_FOLDER",
        os.path.join(current_app.root_path, "uploads", "ai_codes"),
    )
    os.makedirs(upload_folder, exist_ok=True)
    return upload_folder


def allowed_file(filename):
    """检查文件是否为允许的类型"""
    ALLOWED_EXTENSIONS = {"py"}
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# api接口定义
@ai_bp.route("/list_ai")
@login_required
def list_ai():
    """显示用户的AI代码列表"""
    # 使用数据库操作函数
    ai_codes = db_get_user_ai_codes(current_user.id)
    return render_template("ai/list.html", ai_codes=ai_codes)


@ai_bp.route("/upload_ai", methods=["GET", "POST"])
@login_required
def upload_ai():
    """上传AI代码"""
    if request.method == "POST":
        if "ai_code" not in request.files:
            flash("没有选择文件", "danger")
            return redirect(request.url)

        file = request.files["ai_code"]

        if file.filename == "":
            flash("没有选择文件", "danger")
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # 使用更安全的相对路径存储，而不是包含用户ID
            unique_suffix = uuid.uuid4().hex[:8]
            relative_path = os.path.join(current_user.id, f"{unique_suffix}_{filename}")
            full_path = os.path.join(get_upload_path(), relative_path)

            # 确保用户目录存在
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            file.save(full_path)

            name = request.form.get("name", "我的AI")
            description = request.form.get("description", "")
            make_active = request.form.get("make_active") == "on"

            # 使用数据库操作函数创建记录
            # 注意：create_ai_code 现在返回 AICode 对象或 None
            new_ai_code = db_create_ai_code(
                user_id=current_user.id,
                name=name,
                code_path=relative_path,  # 存储相对路径
                description=description,
            )

            if new_ai_code:
                flash("AI代码上传成功！", "success")
                # 如果需要设为激活
                if make_active:
                    if db_set_active_ai_code(current_user.id, new_ai_code.id):
                        flash(f"'{new_ai_code.name}' 已被设为当前活跃AI", "info")
                    else:
                        flash("设置活跃AI失败", "warning")
                return redirect(url_for("ai.list_ai"))
            else:
                flash("AI代码保存失败", "danger")
                # 清理已保存的文件
                if os.path.exists(full_path):
                    os.remove(full_path)
                return redirect(request.url)
        else:
            flash("不支持的文件类型", "danger")

    return render_template("ai/upload.html")


# 注意：路由参数类型应与模型ID类型匹配 (String)
@ai_bp.route("/activate_ai/<string:ai_id>", methods=["POST"])
@login_required
def activate_ai(ai_id):
    """激活指定的AI代码"""
    # 使用数据库操作函数设置激活状态
    success = db_set_active_ai_code(current_user.id, ai_id)

    if success:
        # 获取AI名称用于提示信息
        ai_code = db_get_ai_code_by_id(ai_id)
        flash(f"已将 '{ai_code.name if ai_code else 'AI'}' 设为当前活跃AI", "success")
    else:
        # set_active_ai_code 内部会处理权限检查和日志记录
        flash("激活AI失败，请检查AI是否存在或您是否有权限", "danger")

    return redirect(url_for("ai.list_ai"))


# 注意：路由参数类型应与模型ID类型匹配 (String)
@ai_bp.route("/delete_ai/<string:ai_id>", methods=["POST"])
@login_required
def delete_ai(ai_id):
    """删除AI代码"""
    ai_code = db_get_ai_code_by_id(ai_id)

    # 检查权限
    if not ai_code or ai_code.user_id != current_user.id:
        flash("您没有权限删除此AI代码或AI不存在", "danger")
        return redirect(url_for("ai.list_ai"))

    # 先尝试删除文件
    file_deleted = False
    try:
        # 使用 get_ai_code_path_full 获取完整路径
        full_path = db_get_ai_code_path_full(ai_id)
        if full_path and os.path.exists(full_path):
            os.remove(full_path)
            file_deleted = True
        elif full_path:
            current_app.logger.warning(f"AI代码文件未找到，但尝试删除记录: {full_path}")
            file_deleted = True  # 允许继续删除记录
        else:
            current_app.logger.error(f"获取AI代码 {ai_id} 的路径失败，无法删除文件")

    except Exception as e:
        current_app.logger.error(f"删除AI代码文件失败: {str(e)}")
        flash("删除AI代码文件时出错", "warning")

    # 尝试删除数据库记录
    if db_delete_ai_code(ai_code):
        flash("AI代码已删除", "success")
    else:
        flash("删除AI代码数据库记录失败", "danger")
        # 如果数据库删除失败，但文件已删除，可能需要考虑恢复文件或标记记录为孤立:TODO

    return redirect(url_for("ai.list_ai"))


# 注意：路由参数类型应与模型ID类型匹配 (String)
@ai_bp.route("/edit_ai/<string:ai_id>", methods=["GET", "POST"])
@login_required
def edit_ai(ai_id):
    """编辑AI代码信息"""
    ai_code = db_get_ai_code_by_id(ai_id)

    # 检查权限
    if not ai_code or ai_code.user_id != current_user.id:
        flash("您没有权限编辑此AI代码或AI不存在", "danger")
        return redirect(url_for("ai.list_ai"))

    if request.method == "POST":
        updates = {
            "name": request.form.get("name", ai_code.name),
            "description": request.form.get("description", ai_code.description),
        }

        # 使用数据库操作函数更新
        update_success = db_update_ai_code(ai_code, **updates)

        if update_success:
            flash("AI代码信息已更新", "success")
        else:
            flash("AI代码信息更新失败", "danger")

        # 检查是否设为当前活跃AI
        make_active = request.form.get("make_active") == "on"
        if make_active and not ai_code.is_active:  # 检查更新后的状态
            if db_set_active_ai_code(current_user.id, ai_id):
                flash(f"'{ai_code.name}' 已被设为当前活跃AI", "info")
            else:
                flash("设置活跃AI失败", "warning")
        elif not make_active and ai_code.is_active:
            # 如果取消激活 (虽然UI可能没有这个选项，但逻辑上可以处理)
            # 需要一个取消激活的函数，或者 set_active_ai_code 传 None?
            # 目前简单处理：如果取消勾选且当前是激活，则保持不变或提示用户手动激活另一个
            pass

        return redirect(url_for("ai.list_ai"))

    return render_template("ai/edit.html", ai_code=ai_code)


@ai_bp.route("/get_active_ai", methods=["GET"])
@login_required
def get_active_ai():
    """API: 获取用户当前激活的AI代码信息"""
    # 使用数据库操作函数
    active_ai = db_get_user_active_ai_code(current_user.id)
    if not active_ai:
        return jsonify({"success": False, "message": "用户没有激活的AI代码"})
    # 使用 to_dict() 方法获取信息
    return jsonify({"success": True, "ai": active_ai.to_dict()})


@ai_bp.route("/get_user_ai_codes", methods=["GET"])
@login_required
def get_user_ai_codes():
    """API: 获取用户的AI代码列表"""
    try:
        # 使用数据库操作函数
        ai_codes = db_get_user_ai_codes(current_user.id)
        # 使用 to_dict() 方法转换列表
        result = [ai.to_dict() for ai in ai_codes]
        return jsonify({"success": True, "ai_codes": result})
    except Exception as e:
        current_app.logger.error(f"获取AI代码列表失败: {str(e)}")
        return jsonify({"success": False, "message": f"获取AI代码列表失败: {str(e)}"})


# 注意：路由参数类型应与模型ID类型匹配 (String)
@ai_bp.route("/api/user/<string:user_id>/ai_codes", methods=["GET"])
@login_required  # 仍然需要登录才能访问此API
def get_specific_user_ai_codes(user_id):
    """API: 获取指定用户的AI代码列表"""
    try:
        # 验证用户是否存在 (可选，但推荐)
        user = db_get_user_by_id(user_id)
        if not user:
            return jsonify({"success": False, "message": "用户不存在"}), 404

        # 使用数据库操作函数获取指定用户的AI代码
        ai_codes = db_get_user_ai_codes(user_id)
        # 使用 to_dict() 方法转换列表 (假设您的 AICode 模型有 to_dict 方法)
        # 如果没有，您需要手动构建字典列表
        # result = [ai.to_dict() for ai in ai_codes]
        result = [
            {
                "id": ai.id,
                "name": ai.name,
                "description": ai.description,
                "is_active": ai.is_active,
                "created_at": ai.created_at.isoformat() if ai.created_at else None,
                # 添加其他需要的字段
            }
            for ai in ai_codes
        ]
        return jsonify({"success": True, "ai_codes": result})
    except Exception as e:
        current_app.logger.error(f"获取用户 {user_id} 的AI代码列表失败: {str(e)}")
        return (
            jsonify({"success": False, "message": f"获取AI代码列表失败: {str(e)}"}),
            500,
        )


# 增强test_ai函数，使其集成新的对战创建逻辑
@ai_bp.route("/test_ai/<string:ai_id>", methods=["GET", "POST"])
@login_required
def test_ai(ai_id):
    """测试AI代码功能

    GET请求: 显示测试配置表单
    POST请求: 处理测试配置并创建测试对战
    """
    ai_code = db_get_ai_code_by_id(ai_id)

    # 检查AI代码是否存在且属于当前用户
    if not ai_code or ai_code.user_id != current_user.id:
        flash("您没有权限测试此AI代码或AI不存在", "danger")
        return redirect(url_for("ai.list_ai"))

    if request.method == "POST":
        # 获取表单数据
        opponent_type = request.form.get("opponent_type", "smart")
        player_position = request.form.get("player_position", "1")

        # 验证数据
        if opponent_type not in ["smart", "basic", "idiot", "mixed"]:
            flash("无效的对手类型", "danger")
            return redirect(url_for("ai.test_ai", ai_id=ai_id))

        try:
            pos = int(player_position)
            if pos < 1 or pos > 7:
                raise ValueError("位置必须在1-7之间")
        except ValueError:
            flash("无效的玩家位置", "danger")
            return redirect(url_for("ai.test_ai", ai_id=ai_id))

        # 创建测试对战
        try:
            # 创建对战实例
            battle = create_battle_instance(created_by=current_user.id)
            if not battle:
                flash("创建测试对战失败", "danger")
                return redirect(url_for("ai.list_ai"))

            # 添加用户的AI到指定位置
            player = add_player_to_battle(
                battle_id=battle.id,
                user_id=current_user.id,
                position=pos,
                ai_code_id=ai_id
            )

            if not player:
                flash("将AI添加到对战失败", "danger")
                return redirect(url_for("ai.list_ai"))

            # 填充其余位置的AI
            positions = [i for i in range(1, 8) if i != pos]

            if opponent_type == "mixed":
                # 混合模式：随机选择不同类型的AI
                setup_mixed_ai_opponents(battle.id, positions)
            else:
                # 统一模式：使用同一类型的AI
                setup_uniform_ai_opponents(battle.id, positions, opponent_type)

            flash("测试对战创建成功！", "success")
            return redirect(url_for("battle.view", battle_id=battle.id))

        except Exception as e:
            current_app.logger.error(f"创建测试对战时出错: {str(e)}")
            flash("创建测试对战时出错", "danger")
            return redirect(url_for("ai.list_ai"))

    # GET请求显示测试配置表单
    return render_template("ai/test.html", ai_code=ai_code)


def setup_mixed_ai_opponents(battle_id, positions):
    """设置混合AI对手，确保不重复且按位置顺序分配

    参数:
        battle_id: 对战ID
        positions: 需要填充的位置列表
    """
    # 将AI类型映射到用户名前缀
    ai_type_to_prefix_map = {
        "smart": "smart_user",  # 假设smart AI用户的用户名前缀是 "smart_user"
        "basic": "basic_user",  # 假设basic AI用户的用户名前缀是 "basic_user"
        "idiot": "idiot_user",  # 假设idiot AI用户的用户名前缀是 "idiot_user"
    }
    ai_prefixes = list(ai_type_to_prefix_map.values()) # ["smart_user", "basic_user", "idiot_user"]


    used_ai_ids = [] # 已使用的AI实例ID列表，确保不重复使用

    for position in positions:
        random.shuffle(ai_prefixes) # 每次都随机打乱前缀顺序，以实现混合
        selected_ai_instance = None

        for prefix in ai_prefixes:
            # 获取此用户名前缀的所有可用AI实例 (过滤掉已使用的)
            available_ai_for_prefix = get_available_ai_instances(username_prefix=prefix)
            unused_ai_for_prefix = [ai for ai in available_ai_for_prefix if ai.id not in used_ai_ids]

            if unused_ai_for_prefix:
                selected_ai_instance = random.choice(unused_ai_for_prefix)
                break # 找到一个就跳出内层循环

        ai_code_id_to_add = None
        user_id_for_ai = None # AI的user_id

        if selected_ai_instance:
            ai_code_id_to_add = selected_ai_instance.id
            user_id_for_ai = selected_ai_instance.user_id # 获取AI所属用户的ID
            used_ai_ids.append(ai_code_id_to_add)
            current_app.logger.info(f"为位置 {position} 分配AI: {selected_ai_instance.name} (ID: {ai_code_id_to_add}, 用户ID: {user_id_for_ai})")
        else:
            # 如果所有类型的AI都用完了或者没有找到
            current_app.logger.warning(f"没有足够的未使用AI实例来填充位置 {position}。可能需要添加更多AI用户或检查配置。")
            # 可以在这里添加一个备用逻辑，比如从一个默认的 "system_ai_pool" 用户获取AI
            # 或者如果允许，甚至可以不填充这个位置，但这取决于游戏逻辑
            # 为了简单起见，我们暂时不填充
            # ai_code_id_to_add = None # 或者一个系统默认AI的ID
            # user_id_for_ai = some_system_user_id # 系统AI的用户ID

        if user_id_for_ai: # 只有当成功获取到AI时才添加
            add_player_to_battle(
                battle_id=battle_id,
                user_id=user_id_for_ai,  # 使用AI所属用户的ID
                position=position,
                ai_code_id=ai_code_id_to_add
            )
        else:
            # 处理无法分配AI的情况，例如跳过该位置或记录错误
            current_app.logger.error(f"无法为位置 {position} 分配AI")


def setup_uniform_ai_opponents(battle_id, positions, opponent_type):
    """设置统一类型的AI对手，确保不重复且按位置顺序分配

    参数:
        battle_id: 对战ID
        positions: 需要填充的位置列表
        opponent_type: AI类型 ("smart", "basic", "idiot")
    """
    ai_type_to_prefix_map = {
        "smart": "smart_user",
        "basic": "basic_user",
        "idiot": "idiot_user",
    }
    target_prefix = ai_type_to_prefix_map.get(opponent_type)

    if not target_prefix:
        current_app.logger.error(f"无效的对手类型: {opponent_type}，无法映射到用户名前缀。")
        return

    # 获取此类型的所有可用AI实例
    available_ai = get_available_ai_instances(username_prefix=target_prefix)
    used_ai_ids = []

    for position in positions:
        unused_ai_for_prefix = [ai for ai in available_ai if ai.id not in used_ai_ids]
        selected_ai_instance = None
        ai_code_id_to_add = None
        user_id_for_ai = None

        if unused_ai_for_prefix:
            selected_ai_instance = random.choice(unused_ai_for_prefix)
            ai_code_id_to_add = selected_ai_instance.id
            user_id_for_ai = selected_ai_instance.user_id
            used_ai_ids.append(ai_code_id_to_add)
            current_app.logger.info(f"为位置 {position} 分配 {opponent_type} AI: {selected_ai_instance.name} (ID: {ai_code_id_to_add}, 用户ID: {user_id_for_ai})")
        else:
            current_app.logger.warning(
                f"没有足够的 {opponent_type} (前缀: {target_prefix}) 类型未使用AI实例来填充位置 {position}。"
            )
            # ai_code_id_to_add = None
            # user_id_for_ai = some_system_user_id

        if user_id_for_ai:
            add_player_to_battle(
                battle_id=battle_id,
                user_id=user_id_for_ai, # 使用AI所属用户的ID
                position=position,
                ai_code_id=ai_code_id_to_add
            )
        else:
            current_app.logger.error(f"无法为位置 {position} 分配 {opponent_type} AI")

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
            # 清理已加载的模块
            if module_name in sys.modules:
                del sys.modules[module_name]
            return None

        # 验证Player类是否包含必要的方法 (根据实际游戏引擎调整)
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
        missing_methods = [m for m in required_methods if not hasattr(player_class, m)]

        if missing_methods:
            current_app.logger.error(
                f"AI代码 {file_path} 缺少必要的方法: {', '.join(missing_methods)}"
            )
            if module_name in sys.modules:
                del sys.modules[module_name]
            return None

        return module
    except Exception as e:
        current_app.logger.error(
            f"加载AI代码 {file_path} 失败: {str(e)}", exc_info=True
        )
        if "module_name" in locals() and module_name in sys.modules:
            del sys.modules[module_name]
        return None


def get_ai_module(ai_id):
    """
    获取指定AI代码的模块对象

    参数:
        ai_id: AI代码ID

    返回:
        (模块对象, 错误信息) 元组，成功时错误信息为None
    """
    # 使用数据库操作函数获取完整路径
    file_path = db_get_ai_code_path_full(ai_id)

    if not file_path:
        # get_ai_code_path_full 内部会记录日志
        return None, "获取AI代码路径失败或文件不存在"

    module = load_ai_module(file_path)
    if not module:
        # load_ai_module 内部会记录日志
        return None, "AI代码加载或验证失败"

    return module, None

# ------------------------------------------------------------------------------------