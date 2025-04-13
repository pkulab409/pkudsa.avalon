import os
from tinydb import TinyDB

# 确保数据目录存在
data_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
)
os.makedirs(data_dir, exist_ok=True)

# 文件路径
user_file = os.path.join(data_dir, "users.json")
code_file = os.path.join(data_dir, "codes.json")
duel_file = os.path.join(data_dir, "duels.json")

# 数据库连接池
user_db = None
code_db = None
duel_db = None


def get_user_db():
    """获取用户数据库连接"""
    global user_db
    if user_db is None:
        user_db = TinyDB(user_file, indent=4)
    return user_db


def get_code_db():
    """获取代码数据库连接"""
    global code_db
    if code_db is None:
        code_db = TinyDB(code_file, indent=4)
    return code_db


def get_duel_db():
    """获取对战数据库连接"""
    global duel_db
    if duel_db is None:
        duel_db = TinyDB(duel_file, indent=4)
    return duel_db
