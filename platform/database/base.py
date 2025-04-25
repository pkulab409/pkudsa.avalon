# author: shihuaidexianyu
# date: 2025-04-24
# status: developing
# description: 这个文件通常只包含核心数据库和登录管理器的实例。


from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# 创建 SQLAlchemy 实例
db = SQLAlchemy()

# 创建 LoginManager 实例
login_manager = LoginManager()

# 可选：在这里或在应用工厂中配置 login_manager
# login_manager.login_view = 'auth.login' # 示例：指定登录视图
# login_manager.login_message_category = 'info' # 示例：设置消息类别
