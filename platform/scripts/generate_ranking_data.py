"""
排行榜测试数据生成脚本
用于生成测试用户和游戏统计数据以填充排行榜
"""

import sys
import os
import random
import uuid
from datetime import datetime, timedelta

# 将项目根目录添加到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import db, User, GameStats
from app import create_app


def generate_test_data(num_users=20):
    """生成测试数据"""
    print(f"开始生成{num_users}个用户的排行榜测试数据...")

    # 创建测试用户
    test_users = []
    for i in range(1, num_users + 1):
        # 使用UUID作为用户名
        username = str(uuid.uuid4())[:8]  # 使用UUID前8位作为用户名
        email = f"test{i}@example.com"

        # 检查用户是否已存在
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            print(f"邮箱 {email} 已存在，使用现有用户")
            test_users.append(existing_user)
        else:
            # 创建新用户 - 不直接传入password参数
            user = User(username=username, email=email, created_at=datetime.now())
            # 使用set_password方法设置密码
            user.set_password("password123")

            db.session.add(user)
            db.session.flush()  # 获取数据库分配的ID
            test_users.append(user)
            print(f"创建用户 {username}, ID: {user.id}")

    # 确保更改保存到数据库
    db.session.commit()

    # 为用户生成游戏统计数据
    for user in test_users:
        # 检查是否已有游戏统计数据
        existing_stats = GameStats.query.filter_by(user_id=user.id).first()

        if existing_stats:
            print(f"用户 {user.username} 已有游戏统计数据，更新现有数据")
            stats = existing_stats
        else:
            stats = GameStats(user_id=user.id)
            db.session.add(stats)
            print(f"为用户 {user.username} 创建新游戏统计数据")

        # 随机生成游戏数据
        games_played = random.randint(10, 100)
        wins = random.randint(0, games_played)
        losses = random.randint(0, games_played - wins)
        draws = games_played - wins - losses

        # 计算胜率
        win_rate = (wins / games_played * 100) if games_played > 0 else 0

        # 设置ELO分数 (基础1000分 + 根据胜率加成)
        elo_score = 1000 + int(win_rate * 10) + random.randint(-100, 100)

        # 更新统计数据
        stats.games_played = games_played
        stats.wins = wins
        stats.losses = losses
        stats.draws = draws
        stats.elo_score = elo_score

        print(
            f"用户 {user.username}: 游戏{games_played}局, 胜{wins}局, 负{losses}局, 平{draws}局, ELO分数: {elo_score}"
        )

    # 保存所有更改
    db.session.commit()
    print("测试数据生成完成!")


if __name__ == "__main__":
    # 创建Flask应用上下文
    app = create_app()

    with app.app_context():
        # 获取命令行参数
        num_users = int(sys.argv[1]) if len(sys.argv) > 1 else 20

        # 生成测试数据
        generate_test_data(num_users)
