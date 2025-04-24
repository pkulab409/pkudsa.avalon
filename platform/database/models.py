from sqlalchemy.sql import func
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import select
from .base import db, login_manager
from sqlalchemy import update, text
from datetime import datetime
import time


# 用户模型
class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

    # 移除游戏统计相关字段，这些已经在GameStats模型中
    # 将它们放在相应的游戏类型的统计中更有意义

    # 时间戳
    created_at = db.Column(db.DateTime, default=datetime.now)

    # 关系
    ai_codes = db.relationship("AICode", backref="user", lazy="dynamic")
    hosted_rooms = db.relationship(
        "Room", backref="host", lazy="dynamic", foreign_keys="Room.host_id"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username}>"

    def get_active_ai(self):
        """获取用户当前激活的AI代码"""
        return AICode.query.filter_by(user_id=self.id, is_active=True).first()

    def get_elo_score(self):
        """获取用户的ELO分数"""
        stats = GameStats.query.filter_by(user_id=self.id).first()
        return stats.elo_score if stats else 1200  # 默认分数


# 游戏对战记录
class Battle(db.Model):
    __tablename__ = "battles"

    id = db.Column(db.String(36), primary_key=True)  # UUID
    status = db.Column(
        db.String(20), default="waiting"
    )  # waiting, playing, completed, error

    # 房间关联
    room_id = db.Column(db.String(36), db.ForeignKey("rooms.id"), nullable=True)

    # 参与玩家，以JSON格式存储
    player_ids = db.Column(db.Text, nullable=False)  # JSON格式：[1, 2, 3, ...]
    winner_id = db.Column(db.Integer, nullable=True)  # 胜利者ID

    # 游戏日志UUID
    game_log_uuid = db.Column(db.String(36), nullable=True)

    # 时间戳
    started_at = db.Column(db.DateTime, default=datetime.now)
    ended_at = db.Column(db.DateTime, nullable=True)

    # 游戏结果数据
    results = db.Column(db.Text, nullable=True)  # JSON存储结果数据

    # 关系
    # 明确指定与Room的关系使用room_id外键
    room = db.relationship("Room", foreign_keys=[room_id], back_populates="battles")

    def __repr__(self):
        return f"<Battle {self.id}>"


# 玩家游戏统计
class GameStats(db.Model):
    __tablename__ = "game_stats"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True
    )

    # 游戏统计
    elo_score = db.Column(db.Integer, default=1200)
    games_played = db.Column(db.Integer, default=0)
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)
    draws = db.Column(db.Integer, default=0)

    # 关系
    user = db.relationship("User", backref=db.backref("game_stats", uselist=False))

    def __repr__(self):
        return f"<GameStats {self.user_id}>"


# AI代码
class AICode(db.Model):
    __tablename__ = "ai_codes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    code_path = db.Column(db.String(255), nullable=False)  # 文件系统中的路径
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=False)  # 用户当前激活的AI代码

    # 时间戳
    created_at = db.Column(db.DateTime, default=datetime.now)

    version = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default="pending")  # pending, approved, rejected

    def __repr__(self):
        return f"<AICode {self.id} {self.name}>"


# 房间模型
class Room(db.Model):
    __tablename__ = "rooms"

    id = db.Column(db.String(36), primary_key=True)  # UUID
    name = db.Column(db.String(100), nullable=False)
    host_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    max_players = db.Column(db.Integer, default=7)

    # 房间状态
    status = db.Column(
        db.String(20), default="waiting"
    )  # waiting, ready, playing, completed, closed
    is_public = db.Column(db.Boolean, default=True)

    # 当前关联的对战
    current_battle_id = db.Column(
        db.String(36), db.ForeignKey("battles.id"), nullable=True
    )

    # 时间戳
    created_at = db.Column(db.Integer, default=lambda: int(time.time()))

    # 关系
    participants = db.relationship(
        "RoomParticipant", back_populates="room", cascade="all, delete-orphan"
    )
    current_battle = db.relationship(
        "Battle", foreign_keys=[current_battle_id], uselist=False
    )
    # 与Battle表的room_id关联的battles关系
    battles = db.relationship(
        "Battle",
        foreign_keys="Battle.room_id",
        back_populates="room",
        overlaps="current_battle",
    )

    def get_current_players_count(self):
        """获取当前房间的玩家数量"""
        return RoomParticipant.query.filter_by(room_id=self.id).count()

    def to_dict(self):
        """将房间信息转换为字典"""
        participants = RoomParticipant.query.filter_by(room_id=self.id).all()

        return {
            "id": self.id,
            "room_name": self.name,
            "host_id": self.host_id,
            "max_players": self.max_players,
            "status": self.status,
            "is_public": self.is_public,
            "created_at": self.created_at,
            "current_battle_id": self.current_battle_id,
            "participants": [p.to_dict() for p in participants],
            "current_players": self.get_current_players_count(),
        }

    def __repr__(self):
        return f"<Room {self.id} {self.name}>"


# 房间参与者模型
class RoomParticipant(db.Model):
    __tablename__ = "room_participants"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.String(36), db.ForeignKey("rooms.id"), nullable=False)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )  # 如果是AI，可以为空

    # AI相关信息
    ai_type = db.Column(
        db.String(50), nullable=True
    )  # AI类型：basic_player, smart_player
    ai_id = db.Column(db.String(36), nullable=True)  # AI唯一ID
    ai_name = db.Column(db.String(100), nullable=True)  # AI名称

    # 玩家选择的AI代码
    selected_ai_code_id = db.Column(
        db.Integer, db.ForeignKey("ai_codes.id"), nullable=True
    )

    # 新增：存储序列化的AI实例
    ai_instance_data = db.Column(db.LargeBinary, nullable=True)  # 序列化的AI实例数据
    ai_instance_id = db.Column(db.String(100), nullable=True)  # 实例ID，替代内存中的key
    ai_instance_created_at = db.Column(db.DateTime, nullable=True)  # 实例创建时间

    # 参与者类型标记
    is_ai = db.Column(db.Boolean, default=False)
    is_host = db.Column(db.Boolean, default=False)
    is_ready = db.Column(db.Boolean, default=False)

    # 加入时间
    join_time = db.Column(db.Integer, default=lambda: int(time.time()))

    # 关系
    room = db.relationship("Room", back_populates="participants")
    user = db.relationship("User", backref="room_participations")
    selected_ai_code = db.relationship("AICode")

    def to_dict(self):
        """将参与者信息转换为字典"""
        if self.is_ai:
            return {"id": self.ai_id, "type": "ai", "name": self.ai_name}
        else:
            return {
                "id": self.user_id,
                "type": "human",
                "username": self.user.username if self.user else "未知用户",
            }

    def store_ai_instance(self, instance, instance_id=None):
        """存储AI实例到数据库

        参数:
            instance: AI实例对象
            instance_id: 实例ID，如果不提供则自动生成

        返回:
            instance_id: 实例ID
        """
        import pickle
        import uuid
        from datetime import datetime

        if instance_id is None:
            instance_id = f"ai_instance:{uuid.uuid4().hex}"

        self.ai_instance_id = instance_id
        self.ai_instance_data = pickle.dumps(instance)
        self.ai_instance_created_at = datetime.now()
        db.session.commit()

        return instance_id

    def get_ai_instance(self):
        """从数据库获取AI实例

        返回:
            AI实例对象，如果没有则返回None
        """
        import pickle

        if not self.ai_instance_data:
            return None

        try:
            return pickle.loads(self.ai_instance_data)
        except Exception as e:
            print(f"获取AI实例失败: {e}")
            return None

    def __repr__(self):
        if self.is_ai:
            return f"<RoomParticipant AI {self.ai_id} in Room {self.room_id}>"
        else:
            return f"<RoomParticipant User {self.user_id} in Room {self.room_id}>"


# 用户加载函数
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
