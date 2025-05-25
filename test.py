import os
import sys
import random
import string
import json
from datetime import datetime, timedelta
from flask import Flask
from werkzeug.security import generate_password_hash

# 确保当前目录在路径中，以便导入应用模块
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from config.config import Config
from database.base import db
from database.models import User, AICode, Battle, BattlePlayer, GameStats
from utils.battle_manager_utils import get_battle_manager


def create_app_for_testing():
    """创建一个用于测试的Flask应用实例"""
    app = Flask(__name__)
    app.config.from_object(Config)
    # 禁用CSRF保护，因为这是脚本不需要
    app.config["WTF_CSRF_ENABLED"] = False
    # 使用内存中的SQLite数据库进行测试，或使用实际的数据库
    # app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    db.init_app(app)

    # 创建数据库表结构
    with app.app_context():
        db.create_all()

    return app


def random_string(length=10):
    """生成随机字符串"""
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def random_email():
    """生成随机邮箱"""
    return f"{random_string(8)}@example.com"


def random_username():
    """生成随机用户名"""
    return f"user_{random_string(6)}"


def create_users(count, app):
    """创建指定数量的用户"""
    user_ids = []  # 改为存储ID而不是对象
    with app.app_context():
        for i in range(count):
            username = random_username()
            email = random_email()
            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash("password123"),
                is_admin=False,
                partition=random.randint(0, 3),
                created_at=datetime.now() - timedelta(days=random.randint(0, 30)),
            )
            db.session.add(user)
            db.session.flush()  # 获取ID但不提交
            user_ids.append(user.id)  # 存储ID

            # 每100个用户提交一次，避免大事务
            if i % 100 == 99:
                db.session.commit()
                print(f"已创建 {i+1} 个用户...")

        # 提交剩余的用户
        db.session.commit()
        print(f"总共创建了 {len(user_ids)} 个用户")
    return user_ids  # 返回ID列表


def create_ai_codes(user_ids, app):
    """为每个用户创建1-3个AI代码"""
    ai_code_ids = []  # 存储ID而不是对象
    with app.app_context():
        for i, user_id in enumerate(user_ids):
            # 查询用户对象
            user = User.query.get(user_id)
            if not user:
                print(f"警告: 找不到ID为 {user_id} 的用户，跳过")
                continue

            # 为每个用户创建1-3个AI代码
            num_codes = random.randint(1, 3)
            for j in range(num_codes):
                name = f"AI_{random_string(6)}"
                code_path = f"{user.id}/{name}.py"
                is_active = j == 0  # 第一个AI代码设为激活状态

                ai_code = AICode(
                    user_id=user.id,
                    name=name,
                    code_path=code_path,
                    description=f"这是{user.username}的第{j+1}个AI代码",
                    is_active=is_active,
                    created_at=datetime.now() - timedelta(days=random.randint(0, 30)),
                    version=1,
                )
                db.session.add(ai_code)
                db.session.flush()  # 获取ID但不提交
                ai_code_ids.append(ai_code.id)  # 存储ID而不是对象

            # 创建用户的游戏统计记录
            for ranking_id in range(4):
                stats = GameStats(
                    user_id=user.id,
                    elo_score=random.randint(1000, 1600),
                    games_played=random.randint(0, 50),
                    wins=random.randint(0, 30),
                    losses=random.randint(0, 20),
                    draws=random.randint(0, 5),
                    ranking_id=ranking_id,
                )
                db.session.add(stats)

            # 每20个用户提交一次
            if i % 20 == 19:
                db.session.commit()
                print(f"已为 {i+1} 个用户创建AI代码和游戏统计...")

        # 提交剩余的记录
        db.session.commit()
        print(f"总共创建了 {len(ai_code_ids)} 个AI代码")
    return ai_code_ids  # 返回ID列表而不是对象列表


def create_battles(user_ids, ai_code_ids, count, app):
    """创建指定数量的对战记录"""
    battles = []
    statuses = ["completed", "playing", "waiting", "error", "cancelled"]
    status_weights = [0.7, 0.1, 0.1, 0.05, 0.05]

    with app.app_context():
        # 获取所有用户对象
        users = User.query.filter(User.id.in_(user_ids)).all()

        # 重新查询AI代码对象
        ai_codes = AICode.query.filter(AICode.id.in_(ai_code_ids)).all()

        user_ai_map = {}
        # 创建用户->AI代码的映射
        for ai_code in ai_codes:
            if ai_code.user_id not in user_ai_map:
                user_ai_map[ai_code.user_id] = []
            user_ai_map[ai_code.user_id].append(ai_code)

        for i in range(count):
            # 随机选择状态
            status = random.choices(statuses, status_weights)[0]

            # 创建对战记录
            created_at = datetime.now() - timedelta(
                days=random.randint(0, 30),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )

            # 设置开始和结束时间
            started_at = None
            ended_at = None
            if status != "waiting":
                started_at = created_at + timedelta(minutes=random.randint(1, 10))
                if status in ["completed", "error", "cancelled"]:
                    ended_at = started_at + timedelta(minutes=random.randint(5, 30))

            # 随机排行榜ID
            ranking_id = random.choices([0, 1, 2, 3], [0.4, 0.3, 0.2, 0.1])[0]

            # 创建Battle记录
            battle = Battle(
                status=status,
                ranking_id=ranking_id,
                created_at=created_at,
                started_at=started_at,
                ended_at=ended_at,
                is_elo_exempt=(random.random() < 0.2),  # 20%的对战不计入ELO
                battle_type=random.choice(["standard", "ai_series_test"]),
            )

            # 对于已完成的对战，添加结果
            if status == "completed":
                result = {
                    "winner": random.randint(1, 2),  # 随机胜利方
                    "rounds": random.randint(3, 5),  # 随机回合数
                    "moves": random.randint(10, 30),  # 随机移动次数
                }
                battle.results = json.dumps(result)

            db.session.add(battle)
            db.session.flush()  # 获取battle.id但不提交事务

            # 添加参与者 (7人对战)
            selected_users = random.sample(users, 7)
            for j, user in enumerate(selected_users):
                # 获取用户的AI代码
                user_ai_codes = user_ai_map.get(user.id, [])
                if not user_ai_codes:
                    continue  # 跳过没有AI代码的用户

                selected_ai = random.choice(user_ai_codes)

                # 设置结果
                outcome = None
                elo_change = 0
                if status == "completed":
                    # 随机设置胜负
                    if j < 3:  # 前3个玩家为一队
                        outcome = "win" if result["winner"] == 1 else "loss"
                    else:  # 后4个玩家为另一队
                        outcome = "win" if result["winner"] == 2 else "loss"
                    elo_change = random.randint(-25, 25)

                # 创建BattlePlayer记录
                battle_player = BattlePlayer(
                    battle_id=battle.id,
                    user_id=user.id,
                    selected_ai_code_id=selected_ai.id,
                    position=j + 1,
                    outcome=outcome,
                    initial_elo=random.randint(1000, 1600),
                    elo_change=elo_change,
                    join_time=created_at,
                )
                db.session.add(battle_player)

            battles.append(battle)

            # 每50个对战提交一次
            if i % 50 == 49:
                db.session.commit()
                print(f"已创建 {i+1} 个对战...")

        # 提交剩余的记录
        db.session.commit()
        print(f"总共创建了 {len(battles)} 个对战")
    return battles


def main(user_count=100, battle_count=500):
    """主函数，控制数据生成过程"""
    app = create_app_for_testing()

    print(f"开始创建 {user_count} 个用户...")
    user_ids = create_users(user_count, app)

    print(f"为用户创建AI代码...")
    ai_code_ids = create_ai_codes(user_ids, app)  # 现在返回ID

    print(f"开始创建 {battle_count} 个对战...")
    battles = create_battles(user_ids, ai_code_ids, battle_count, app)  # 传递ID

    print("数据生成完成！")
    print(f"- 用户数量: {len(user_ids)}")
    print(f"- AI代码数量: {len(ai_code_ids)}")
    print(f"- 对战数量: {len(battles)}")

    # 检查数据库中的实际数量
    with app.app_context():
        print("\n数据库统计:")
        print(f"- 用户数量: {User.query.count()}")
        print(f"- AI代码数量: {AICode.query.count()}")
        print(f"- 对战数量: {Battle.query.count()}")
        print(f"- 对战参与者数量: {BattlePlayer.query.count()}")
        print(f"- 游戏统计数量: {GameStats.query.count()}")

        # 统计不同状态的对战数量
        status_counts = {}
        for status in ["completed", "playing", "waiting", "error", "cancelled"]:
            count = Battle.query.filter_by(status=status).count()
            status_counts[status] = count

        print("\n对战状态统计:")
        for status, count in status_counts.items():
            print(f"- {status}: {count}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="生成测试用户和对战数据")
    parser.add_argument("--users", type=int, default=100, help="要创建的用户数量")
    parser.add_argument("--battles", type=int, default=500, help="要创建的对战数量")
    args = parser.parse_args()

    main(user_count=args.users, battle_count=args.battles)
