# author: shihuaidexianyu (refactored by AI assistant)
# date: 2025-04-25
# status: need to be modified
# description: 用于用户认证的蓝图，包含登录、注册和登出功能。
# 该蓝图使用 Flask-WTF 表单处理库来处理用户输入，并使用 Flask-Login 来管理用户会话。


from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError
from database.models import User
from database.base import db

auth = Blueprint("auth", __name__)

PARTITION_NUMBER = 6

# 创建登录表单类
class LoginForm(FlaskForm):
    email = StringField("邮箱", validators=[DataRequired(), Email()])
    password = PasswordField("密码", validators=[DataRequired(), Length(min=6)])
    remember_me = BooleanField("记住我")
    submit = SubmitField("登录")


# 创建注册表单类
class RegisterForm(FlaskForm):
    username = StringField("用户名", validators=[DataRequired(), Length(min=3, max=20)])
    partition = SelectField(
        "赛区",
        coerce=int,  # 转换为整数类型
        choices=[(i+1, f"分区{i+1}") for i in range(PARTITION_NUMBER)],
        validators=[DataRequired()],
    )
    email = StringField("邮箱", validators=[DataRequired(), Email()])
    password = PasswordField("密码", validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField(
        "确认密码",
        validators=[
            DataRequired(),
            EqualTo("password", message="两次输入的密码不匹配"),
        ],
    )
    type = "player"
    submit = SubmitField("注册")

    # 自定义验证器
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError("该用户名已被使用，请选择其他用户名")

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError("该邮箱已被注册，请使用其他邮箱")


@auth.route("/login", methods=["GET", "POST"])
def login():
    # 创建表单实例
    form = LoginForm()

    # 处理表单提交
    if form.validate_on_submit():
        # 查找用户
        user = User.query.filter_by(email=form.email.data).first()

        # 验证用户和密码
        if user and user.check_password(form.password.data):
            # 登录用户
            login_user(user, remember=form.remember_me.data)
            # 获取next参数，如果存在则重定向到该URL
            next_page = request.args.get("next")
            # 重定向到首页或next页面
            return redirect(next_page or url_for("main.home"))
        else:
            # 登录失败提示
            flash("邮箱或密码不正确", "danger")

    # 渲染模板并传递表单
    return render_template("auth/login.html", form=form)


@auth.route("/register", methods=["GET", "POST"])
def register():
    # 如果用户已登录，重定向到首页
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    # 创建注册表单实例
    form = RegisterForm()

    # 处理表单提交
    if form.validate_on_submit():
        # 创建新用户
        user = User(username=form.username.data, email=form.email.data, partition=form.partition.data)
        user.set_password(form.password.data)

        # 保存到数据库
        try:
            db.session.add(user)
            db.session.commit()
            flash("注册成功！现在您可以登录了", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            db.session.rollback()
            flash(f"注册失败: {str(e)}", "danger")

    return render_template("auth/register.html", form=form)


@auth.route("/logout")
@login_required
def logout():
    # 登出逻辑
    logout_user()
    return redirect(url_for("main.home"))
