from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# 创建全局db对象
db = SQLAlchemy()
login_manager = LoginManager()
