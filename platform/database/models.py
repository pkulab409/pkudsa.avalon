from sqlalchemy.sql import func
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import select
from .base import db, login_manager
from sqlalchemy import update, text
from datetime import datetime


# 添加用户模型
class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username}>"

    def get_active_ai(self, game_type="default"):
        """获取用户在指定游戏类型中当前激活的AI代码"""
        return AICode.query.filter_by(
            user_id=self.id, game_type=game_type, is_active=True
        ).first()


# 游戏对战记录
class Battle(db.Model):
    __tablename__ = "battles"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.String(36), nullable=False)
    game_type = db.Column(db.String(50), nullable=False)
    player_ids = db.Column(db.Text, nullable=False)  # 存储为JSON字符串: [1, 2, 3]
    winner_ids = db.Column(db.Text, nullable=True)  # 存储为JSON字符串: [1, 3]
    loser_ids = db.Column(db.Text, nullable=True)  # 存储为JSON字符串: [2]
    is_draw = db.Column(db.Boolean, default=False)
    started_at = db.Column(db.DateTime, default=datetime.now)
    ended_at = db.Column(db.DateTime, nullable=True)
    game_data_uuid = db.Column(db.String(36), nullable=True)  # 关联到JSON文件的UUID

    # 转换方法
    @property
    def players(self):
        import json

        player_ids = json.loads(self.player_ids)
        return User.query.filter(User.id.in_(player_ids)).all()

    @property
    def winners(self):
        import json

        if not self.winner_ids:
            return []
        winner_ids = json.loads(self.winner_ids)
        return User.query.filter(User.id.in_(winner_ids)).all()

    @property
    def losers(self):
        import json

        if not self.loser_ids:
            return []
        loser_ids = json.loads(self.loser_ids)
        return User.query.filter(User.id.in_(loser_ids)).all()

    # 设置方法
    def set_players(self, player_list):
        import json

        self.player_ids = json.dumps(
            [player.id if hasattr(player, "id") else player for player in player_list]
        )

    def set_winners(self, winner_list):
        import json

        self.winner_ids = json.dumps(
            [winner.id if hasattr(winner, "id") else winner for winner in winner_list]
        )

    def set_losers(self, loser_list):
        import json

        self.loser_ids = json.dumps(
            [loser.id if hasattr(loser, "id") else loser for loser in loser_list]
        )

    def __repr__(self):
        import json

        player_count = len(json.loads(self.player_ids)) if self.player_ids else 0
        return f"<Battle {self.id}: {self.game_type} with {player_count} players>"


# 玩家游戏统计
class GameStats(db.Model):
    __tablename__ = "game_stats"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    game_type = db.Column(db.String(50), nullable=False)
    games_played = db.Column(db.Integer, default=0)
    games_won = db.Column(db.Integer, default=0)
    games_lost = db.Column(db.Integer, default=0)
    games_draw = db.Column(db.Integer, default=0)
    score = db.Column(db.Integer, default=1000)  # ELO或其他评分系统
    last_played = db.Column(db.DateTime, nullable=True)

    # 关系
    user = db.relationship("User", backref=db.backref("game_stats", lazy="dynamic"))

    __table_args__ = (
        db.UniqueConstraint("user_id", "game_type", name="unique_user_game_stats"),
    )

    def __repr__(self):
        return f"<GameStats {self.user_id}: {self.game_type} score={self.score}>"


class AICode(db.Model):
    __tablename__ = "ai_codes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    game_type = db.Column(db.String(50), nullable=False)
    code_path = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=False)  # 用户当前激活的AI代码
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    version = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default="pending")  # pending, approved, rejected

    # 关系
    user = db.relationship("User", backref=db.backref("ai_codes", lazy="dynamic"))

    def __repr__(self):
        return f"<AICode {self.name} by {self.user.username}>"
