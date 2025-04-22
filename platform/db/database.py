import os
import sqlite3

# 确保数据目录存在
data_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
)
os.makedirs(data_dir, exist_ok=True)

# 文件路径
user_file = os.path.join(data_dir, "users.db")
code_file = os.path.join(data_dir, "codes.db")
duel_file = os.path.join(data_dir, "duels.db")

# 数据库连接池
user_db = None
code_db = None
duel_db = None


def get_user_db():
    """获取用户数据库连接"""
    global user_db
    if user_db is None:
        user_db = sqlite3.connect(user_file)
        create_user_table(user_db)
    return user_db


def get_code_db():
    """获取代码数据库连接"""
    global code_db
    if code_db is None:
        code_db = sqlite3.connect(code_file)
        create_code_table(code_db)
    return code_db


def get_duel_db():
    """获取对战数据库连接"""
    global duel_db
    if duel_db is None:
        duel_db = sqlite3.connect(duel_file)
        create_duel_table(duel_db)
    return duel_db


# 创建用户表
def create_user_table(db):
    cursor = db.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            ladder_points INTEGER DEFAULT 1000,
            division TEXT DEFAULT '新手区'
        )
    ''')
    db.commit()


# 创建代码表
def create_code_table(db):
    cursor = db.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            code_name TEXT NOT NULL,
            code_content TEXT NOT NULL,
            UNIQUE(username, code_name) -- 确保每个用户的代码名称唯一
        )
    ''')
    db.commit()


# 创建对战表
def create_duel_table(db):
    cursor = db.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS duels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player1_id INTEGER,
            player2_id INTEGER,
            player3_id INTEGER,
            player4_id INTEGER,
            player5_id INTEGER,
            player6_id INTEGER,
            player7_id INTEGER,
            winner_team TEXT,  -- 例如 "Good" 或 "Evil"，也可以存储 JSON 字符串
            winner_ids TEXT,          -- JSON 格式字符串，如 "[3, 5, 7]"
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(player1_id) REFERENCES users(id),
            FOREIGN KEY(player2_id) REFERENCES users(id),
            FOREIGN KEY(player3_id) REFERENCES users(id),
            FOREIGN KEY(player4_id) REFERENCES users(id),
            FOREIGN KEY(player5_id) REFERENCES users(id),
            FOREIGN KEY(player6_id) REFERENCES users(id),
            FOREIGN KEY(player7_id) REFERENCES users(id)
        )
    ''')
    db.commit()