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
import time
import json

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
    update_battle,
    get_game_stats_by_user_id,
    create_game_stats,
)
from database.models import AICode, BattlePlayer  # 仍然需要模型用于类型提示或特定查询
from datetime import datetime
import importlib.util
import sys
import inspect
import pickle
import json
import time

PARTITION_NUMBER = 6
from utils.battle_manager_utils import get_battle_manager

# 创建蓝图
ai_bp = Blueprint("ai", __name__)

import time

# 用户请求计数和限流机制
TEST_REQUEST_COUNTS = {}  # 格式: {user_id: {'count': n, 'timestamp': time}}
MAX_TESTS_PER_USER = 10  # 每用户5分钟内最多10次测试请求
RATE_LIMIT_RESET_TIME = 300  # 5分钟重置


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


def check_rate_limit(user_id):
    """检查用户是否超出测试请求限制"""
    current_time = int(time.time())

    # 清理过期记录
    for uid in list(TEST_REQUEST_COUNTS.keys()):
        if current_time - TEST_REQUEST_COUNTS[uid]["timestamp"] > RATE_LIMIT_RESET_TIME:
            del TEST_REQUEST_COUNTS[uid]

    # 检查当前用户
    if user_id not in TEST_REQUEST_COUNTS:
        TEST_REQUEST_COUNTS[user_id] = {"count": 1, "timestamp": current_time}
        return True

    # 检查时间是否已重置
    if current_time - TEST_REQUEST_COUNTS[user_id]["timestamp"] > RATE_LIMIT_RESET_TIME:
        TEST_REQUEST_COUNTS[user_id] = {"count": 1, "timestamp": current_time}
        return True

    # 检查是否超过次数限制
    if TEST_REQUEST_COUNTS[user_id]["count"] >= MAX_TESTS_PER_USER:
        return False

    # 增加计数
    TEST_REQUEST_COUNTS[user_id]["count"] += 1
    return True


# api接口定义
@ai_bp.route("/list_ai")
@login_required
def list_ai():
    """显示用户的AI代码列表"""
    user_id = current_user.id
    ai_codes = db_get_user_ai_codes(user_id)

    # 检查用户是否已加入当前分区的天梯
    has_ranking_stats = (
        get_game_stats_by_user_id(user_id, ranking_id=current_user.partition)
        is not None
    )

    return render_template(
        "ai/list.html", ai_codes=ai_codes, has_ranking_stats=has_ranking_stats
    )


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
                # 确保用户有榜单0的GameStats记录（用于测试赛）
                default_stats = get_game_stats_by_user_id(current_user.id, ranking_id=0)
                if not default_stats:
                    # 如果用户还没有榜单0的统计，创建一个
                    default_stats = create_game_stats(current_user.id, ranking_id=0)
                    if default_stats:
                        current_app.logger.info(
                            f"为用户 {current_user.id} 创建榜单0（测试赛）的统计记录"
                        )
                    else:
                        current_app.logger.warning(
                            f"为用户 {current_user.id} 创建榜单0的统计记录失败"
                        )

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

    # # 先尝试删除文件
    # file_deleted = False
    # try:
    #     # 使用 get_ai_code_path_full 获取完整路径
    #     full_path = db_get_ai_code_path_full(ai_id)
    #     if full_path and os.path.exists(full_path):
    #         os.remove(full_path)
    #         file_deleted = True
    #     elif full_path:
    #         current_app.logger.warning(f"AI代码文件未找到，但尝试删除记录: {full_path}")
    #         file_deleted = True  # 允许继续删除记录
    #     else:
    #         current_app.logger.error(f"获取AI代码 {ai_id} 的路径失败，无法删除文件")

    # except Exception as e:
    #     current_app.logger.error(f"删除AI代码文件失败: {str(e)}")
    #     flash("删除AI代码文件时出错", "warning")

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


@ai_bp.route("/join_ranking", methods=["POST"])
@login_required
def join_ranking():
    """
    加入天梯赛初赛(分区赛)
    后续晋级将自动注册到新榜单
    创建ranking_id=1~6的GameStats记录
    """
    try:
        # 检查用户是否已有活跃AI
        active_ai = db_get_user_active_ai_code(current_user.id)
        if not active_ai:
            return jsonify(
                {"success": False, "message": "您没有设置活跃AI，请先设置一个活跃AI"}
            )

        # 检查用户是否已有当前分区的天梯统计
        existing_stats = get_game_stats_by_user_id(
            current_user.id, ranking_id=current_user.partition
        )
        if existing_stats:
            return jsonify({"success": False, "message": "您已经加入了天梯赛"})

        # 创建当前分区的天梯统计
        stats = create_game_stats(current_user.id, ranking_id=current_user.partition)
        if not stats:
            return jsonify(
                {"success": False, "message": "创建天梯统计失败，请稍后重试"}
            )

        return jsonify(
            {"success": True, "message": "成功加入天梯赛！您的初始ELO分数为1200"}
        )
    except Exception as e:
        current_app.logger.error(f"加入天梯失败: {str(e)}")
        return jsonify({"success": False, "message": "服务器错误，请稍后重试"})


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
                ai_code_id=ai_id,
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
    ai_prefixes = list(
        ai_type_to_prefix_map.values()
    )  # ["smart_user", "basic_user", "idiot_user"]

    used_ai_ids = []  # 已使用的AI实例ID列表，确保不重复使用

    for position in positions:
        random.shuffle(ai_prefixes)  # 每次都随机打乱前缀顺序，以实现混合
        selected_ai_instance = None

        for prefix in ai_prefixes:
            # 获取此用户名前缀的所有可用AI实例 (过滤掉已使用的)
            available_ai_for_prefix = get_available_ai_instances(username_prefix=prefix)
            unused_ai_for_prefix = [
                ai for ai in available_ai_for_prefix if ai.id not in used_ai_ids
            ]

            if unused_ai_for_prefix:
                selected_ai_instance = random.choice(unused_ai_for_prefix)
                break  # 找到一个就跳出内层循环

        ai_code_id_to_add = None
        user_id_for_ai = None  # AI的user_id

        if selected_ai_instance:
            ai_code_id_to_add = selected_ai_instance.id
            user_id_for_ai = selected_ai_instance.user_id  # 获取AI所属用户的ID
            used_ai_ids.append(ai_code_id_to_add)
            current_app.logger.info(
                f"为位置 {position} 分配AI: {selected_ai_instance.name} (ID: {ai_code_id_to_add}, 用户ID: {user_id_for_ai})"
            )
        else:
            # 如果所有类型的AI都用完了或者没有找到
            current_app.logger.warning(
                f"没有足够的未使用AI实例来填充位置 {position}。可能需要添加更多AI用户或检查配置。"
            )
            # 可以在这里添加一个备用逻辑，比如从一个默认的 "system_ai_pool" 用户获取AI
            # 或者如果允许，甚至可以不填充这个位置，但这取决于游戏逻辑
            # 为了简单起见，我们暂时不填充
            # ai_code_id_to_add = None # 或者一个系统默认AI的ID
            # user_id_for_ai = some_system_user_id # 系统AI的用户ID

        if user_id_for_ai:  # 只有当成功获取到AI时才添加
            add_player_to_battle(
                battle_id=battle_id,
                user_id=user_id_for_ai,  # 使用AI所属用户的ID
                position=position,
                ai_code_id=ai_code_id_to_add,
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
        current_app.logger.error(
            f"无效的对手类型: {opponent_type}，无法映射到用户名前缀。"
        )
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
            current_app.logger.info(
                f"为位置 {position} 分配 {opponent_type} AI: {selected_ai_instance.name} (ID: {ai_code_id_to_add}, 用户ID: {user_id_for_ai})"
            )
        else:
            current_app.logger.warning(
                f"没有足够的 {opponent_type} (前缀: {target_prefix}) 类型未使用AI实例来填充位置 {position}。"
            )
            # ai_code_id_to_add = None
            # user_id_for_ai = some_system_user_id

        if user_id_for_ai:
            add_player_to_battle(
                battle_id=battle_id,
                user_id=user_id_for_ai,  # 使用AI所属用户的ID
                position=position,
                ai_code_id=ai_code_id_to_add,
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
@ai_bp.route("/start_ai_series_test", methods=["POST"])
@login_required
def start_ai_series_test():
    data = request.get_json()
    ai_code_id_to_test = data.get("ai_code_id")

    # 添加限流检查
    if not check_rate_limit(current_user.id):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "您的测试请求过于频繁，请稍后再试（限制为每5分钟10次）",
                }
            ),
            429,
        )

    if not ai_code_id_to_test:
        return jsonify({"success": False, "message": "未提供要测试的AI代码ID"}), 400

    ai_to_test = db_get_ai_code_by_id(ai_code_id_to_test)
    if not ai_to_test or ai_to_test.user_id != current_user.id:
        return (
            jsonify({"success": False, "message": "AI代码不存在或您没有权限测试此AI"}),
            403,
        )

    current_app.logger.info(
        f"用户 {current_user.username} (ID: {current_user.id}) 请求为AI {ai_to_test.name} (ID: {ai_code_id_to_test}) 启动系列测试。"
    )

    # 获取 "smart_user" 前缀的AI用于填充
    # 假设您的 get_available_ai_instances 接受 username_prefix
    # 并且 config.yaml 中有 smart_user1, smart_user2... smart_user6/7 这样的用户
    smart_ai_prefix = "smart_user"
    available_smart_ais = get_available_ai_instances(username_prefix=smart_ai_prefix)

    if len(available_smart_ais) < 6:  # 需要至少6个不同的smart AI来填充
        current_app.logger.error(
            f"系列测试启动失败：没有足够的 Smart AI (需要至少6个，实际找到 {len(available_smart_ais)}) 来填充对战。请检查config.yaml中的用户定义。"
        )
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"Smart AI 数量不足 (需要至少6个，找到 {len(available_smart_ais)} 个)，无法启动系列测试。",
                }
            ),
            500,
        )

    battle_manager = get_battle_manager()

    MAX_PLAYERS = 7
    # 将7个位置分成3批次处理
    BATCH_SIZE = 3
    positions_to_test = list(range(1, MAX_PLAYERS + 1))
    batches = [
        positions_to_test[i : i + BATCH_SIZE]
        for i in range(0, len(positions_to_test), BATCH_SIZE)
    ]

    battles_created_ids = []

    # 分批处理位置测试
    for batch_index, batch_positions in enumerate(batches):
        # 处理当前批次的位置
        for position_of_test_ai in batch_positions:
            try:
                # 1. 创建对战实例
                # 注意：create_battle_instance 只是创建了Battle记录，并不添加玩家
                # ranking_id可以设为特殊值，或者依赖 is_elo_exempt
                battle = create_battle_instance(
                    created_by=current_user.id, ranking_id=0
                )  # 或一个特殊的ranking_id for tests
                if not battle:
                    current_app.logger.error(
                        f"系列测试：为位置 {position_of_test_ai} 创建Battle记录失败。"
                    )
                    continue  # 跳过这个位置的测试

                # 2. 更新Battle记录为ELO豁免和测试类型
                update_success = update_battle(
                    battle, is_elo_exempt=True, battle_type="ai_series_test"
                )
                if not update_success:
                    current_app.logger.error(
                        f"系列测试：更新Battle {battle.id} 的豁免状态失败。"
                    )
                    # 可以选择删除已创建的battle或标记为错误

                # 3. 准备参与者数据列表
                participant_data_for_bm = []  # 用于传递给 BattleManager
                players_for_db_battle = []  # 用于直接操作BattlePlayer表 (如果需要的话)

                # 添加被测试的AI
                # add_player_to_battle 会创建 BattlePlayer 记录
                player_added = add_player_to_battle(
                    battle_id=battle.id,
                    user_id=ai_to_test.user_id,  # AI的拥有者
                    position=position_of_test_ai,
                    ai_code_id=ai_to_test.id,
                )
                if not player_added:
                    current_app.logger.error(
                        f"系列测试：无法将测试AI {ai_to_test.id} 添加到对战 {battle.id} 的位置 {position_of_test_ai}。"
                    )
                    # 可能需要清理这个battle
                    continue
                participant_data_for_bm.append(
                    {"user_id": ai_to_test.user_id, "ai_code_id": ai_to_test.id}
                )

                # 填充剩余的Smart AI
                if len(available_smart_ais) < 6:
                    # 当Smart AI不足6个时，允许重复使用
                    smart_ais_to_fill = []
                    while len(smart_ais_to_fill) < MAX_PLAYERS - 1:
                        # 循环添加AI直到数量足够
                        for ai in available_smart_ais:
                            if len(smart_ais_to_fill) < MAX_PLAYERS - 1:
                                smart_ais_to_fill.append(ai)
                    current_app.logger.info(
                        f"智能AI不足，启用重复使用模式。使用 {len(available_smart_ais)} 个智能AI填充 {MAX_PLAYERS-1} 个位置"
                    )
                else:
                    # 如果足够，仍然使用不重复的
                    smart_ais_to_fill = random.sample(
                        available_smart_ais, k=MAX_PLAYERS - 1
                    )

                current_smart_ai_index = 0
                for pos in range(1, MAX_PLAYERS + 1):
                    if pos == position_of_test_ai:
                        continue  # 跳过测试AI的位置

                    if current_smart_ai_index >= len(smart_ais_to_fill):
                        current_app.logger.error(
                            f"系列测试：Smart AI 样本不足以填充位置 {pos} (对战 {battle.id})。"
                        )
                        # 这个情况理论上不应该发生，因为前面检查了数量并用了sample
                        break

                    smart_ai_opponent = smart_ais_to_fill[current_smart_ai_index]
                    current_smart_ai_index += 1

                    opponent_added = add_player_to_battle(
                        battle_id=battle.id,
                        user_id=smart_ai_opponent.user_id,  # Smart AI的拥有者
                        position=pos,
                        ai_code_id=smart_ai_opponent.id,
                    )
                    if not opponent_added:
                        current_app.logger.error(
                            f"系列测试：无法将Smart AI {smart_ai_opponent.id} 添加到对战 {battle.id} 的位置 {pos}。"
                        )
                        # 标记此battle为失败并跳过启动
                        update_battle(
                            battle,
                            status="error",
                            results=json.dumps(
                                {"error": f"Failed to add Smart AI to pos {pos}"}
                            ),
                        )
                        break  # 中断这个battle的填充
                    participant_data_for_bm.append(
                        {
                            "user_id": smart_ai_opponent.user_id,
                            "ai_code_id": smart_ai_opponent.id,
                        }
                    )

                # 如果填充参与者过程中断，跳过启动
                if len(participant_data_for_bm) != MAX_PLAYERS:
                    current_app.logger.error(
                        f"系列测试：未能为对战 {battle.id} 集齐 {MAX_PLAYERS} 位玩家。实际数量: {len(participant_data_for_bm)}"
                    )
                    if battle.status != "error":  # 如果之前没标记错误
                        update_battle(
                            battle,
                            status="error",
                            results=json.dumps(
                                {"error": f"Failed to gather {MAX_PLAYERS} players."}
                            ),
                        )
                    continue  # 跳到下一个位置的测试

                # 4. 启动对战 (通过BattleManager)
                # BattleManager 的 start_battle 需要完整的 participant_data (包含user_id和ai_code_id)
                # 它内部会根据ai_code_id去获取路径
                # 注意：participant_data_for_bm 中的顺序可能不重要，因为 BattleManager/Referee 会根据 BattlePlayer 表中的 position 来安排
                # 但最好是按照位置顺序来组织，尽管 add_player_to_battle 已经按位置创建了记录

                # 获取实际创建的 BattlePlayer 记录，确保顺序和数据正确
                # db_battle_players = BattlePlayer.query.filter_by(battle_id=battle.id).order_by(BattlePlayer.position).all()
                # final_participant_data_for_bm = [
                #     {"user_id": bp.user_id, "ai_code_id": bp.selected_ai_code_id} for bp in db_battle_players
                # ]
                # 为简化，我们假设 add_player_to_battle 成功后，BattleManager能正确处理
                # BattleManager 的 start_battle 现在只需要 battle_id 和 participant_data (包含user_id, ai_code_id)

                # 重新从数据库获取完整的参与者信息，确保顺序和信息正确传递给BattleManager
                final_participants_from_db = []
                battle_players_for_this_game = (
                    BattlePlayer.query.filter_by(battle_id=battle.id)
                    .order_by(BattlePlayer.position)
                    .all()
                )
                if len(battle_players_for_this_game) == MAX_PLAYERS:
                    for bp_db in battle_players_for_this_game:
                        final_participants_from_db.append(
                            {
                                "user_id": bp_db.user_id,
                                "ai_code_id": bp_db.selected_ai_code_id,
                                # BattleManager的start_battle会用ai_code_id获取路径
                            }
                        )

                    start_success = battle_manager.start_battle(
                        battle.id, final_participants_from_db
                    )
                    if start_success:
                        battles_created_ids.append(battle.id)
                        current_app.logger.info(
                            f"系列测试：对战 {battle.id} (测试AI位置: {position_of_test_ai}) 已成功启动。"
                        )
                    else:
                        current_app.logger.error(
                            f"系列测试：启动对战 {battle.id} 失败。BattleManager返回错误。"
                        )
                        # BattleManager内部应该已经标记了错误状态
                else:
                    current_app.logger.error(
                        f"系列测试：对战 {battle.id} 玩家数量不足 ({len(battle_players_for_this_game)}/{MAX_PLAYERS})，无法启动。"
                    )
                    update_battle(
                        battle,
                        status="error",
                        results=json.dumps(
                            {"error": "Player count mismatch before start."}
                        ),
                    )

                # # 可选：在创建每个对战之间加入短暂延时，避免瞬间大量请求
                # time.sleep(0.5)  # 0.5秒延时

            except Exception as e:
                current_app.logger.error(
                    f"为AI {ai_to_test.name} 创建位置 {position_of_test_ai} 的系列测试赛时发生严重错误: {str(e)}",
                    exc_info=True,
                )
                # 这里可以记录更详细的错误到某个地方或返回给用户

    if battles_created_ids:
        return jsonify(
            {
                "success": True,
                "message": f"已为AI '{ai_to_test.name}' 启动 {len(battles_created_ids)}/{MAX_PLAYERS} 场系列测试赛。请在对战大厅查看。",
                "battle_ids": battles_created_ids,
            }
        )
    else:
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"未能为AI '{ai_to_test.name}' 启动任何系列测试赛。请检查日志。",
                }
            ),
            500,
        )
