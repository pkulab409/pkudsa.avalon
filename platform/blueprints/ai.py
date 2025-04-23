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
from database.models import db, AICode, User
from datetime import datetime

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
            game_type = request.form.get("game_type", "default")
            description = request.form.get("description", "")

            # 检查是否设为当前活跃AI
            make_active = request.form.get("make_active") == "on"

            # 创建数据库记录
            ai_code = AICode(
                user_id=current_user.id,
                name=name,
                game_type=game_type,
                code_path=new_filename,
                description=description,
                is_active=make_active,
            )

            # 如果设为当前活跃AI，需要将其他同类型的AI设为非活跃
            if make_active:
                AICode.query.filter_by(
                    user_id=current_user.id, game_type=game_type, is_active=True
                ).update({"is_active": False})

            db.session.add(ai_code)
            db.session.commit()

            flash("AI代码上传成功！", "success")
            return redirect(url_for("ai.list_ai"))
        else:
            flash("不支持的文件类型", "danger")

    # GET请求展示上传表单
    game_types = [
        {"id": "default", "name": "默认游戏"},
        # 可以根据配置动态生成
    ]
    return render_template("ai/upload.html", game_types=game_types)


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
    AICode.query.filter_by(
        user_id=current_user.id, game_type=ai_code.game_type, is_active=True
    ).update({"is_active": False})

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
            AICode.query.filter_by(
                user_id=current_user.id, game_type=ai_code.game_type, is_active=True
            ).update({"is_active": False})
            ai_code.is_active = True

        db.session.commit()
        flash("AI代码信息已更新", "success")
        return redirect(url_for("ai.list_ai"))

    return render_template("ai/edit.html", ai_code=ai_code)


@ai_bp.route("/api/user/active_ai/<int:user_id>")
def get_active_ai(user_id):
    """API: 获取用户当前激活的AI代码信息"""
    game_type = request.args.get("game_type", "default")
    user = User.query.get_or_404(user_id)

    active_ai = user.get_active_ai(game_type)

    if not active_ai:
        return jsonify({"success": False, "message": "用户没有激活的AI代码"})

    return jsonify(
        {
            "success": True,
            "ai_id": active_ai.id,
            "name": active_ai.name,
            "game_type": active_ai.game_type,
            "updated_at": active_ai.updated_at.isoformat(),
        }
    )
