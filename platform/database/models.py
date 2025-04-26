# author: shihuaidexianyu
# date: 2025-04-24
# status: developing
# description: Database models

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from .base import db, login_manager
from datetime import datetime
import uuid


# 工具函数
def generate_uuid():
    return str(uuid.uuid4())


# 用户模型
class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

    # 时间戳
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系:
    # ai_codes: 用户撰写的AI代码 (一对多 User -> AICode)
    ai_codes = db.relationship("AICode", backref="user", lazy="dynamic")
    # battle_participations: 用户参与过的对战 (一对多 User -> BattlePlayer)
    # BattlePlayer 记录包含了用户在每次对战中的详情，包括结果 (outcome) (一对多 User -> BattlePlayer)
    battle_participations = db.relationship(
        "BattlePlayer", backref="user", lazy="dynamic"
    )
    # game_stats: 用户的游戏统计 (一对一 User <-> GameStats)
    # 使用 db.backref 并指定 uselist=False 表示这是一对一关系
    game_stats = db.relationship(
        "GameStats", backref=db.backref("user", uselist=False), uselist=False
    )
    # battles_won: 获取用户赢得的对战列表 (通过查询 BattlePlayer 实现，关系定义在 BattlePlayer 中)
    # 无需在这里明确定义 `relationship` 如果是通过 BattlePlayer 筛选

    def set_password(self, password):
        """设置用户的密码哈希"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """检查输入的密码是否与哈希匹配"""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        # 添加用户ID到 repr，方便调试
        return f"<User {self.id}: {self.username}>"

    def get_active_ai(self):
        """获取用户当前激活的AI代码"""
        # 使用 .first() 获取单个激活的AI，一个用户只有一个激活的AI
        return AICode.query.filter_by(user_id=self.id, is_active=True).first()

    def get_elo_score(self):
        """获取用户的ELO分数"""
        # 通过 User.game_stats 关系访问
        # 如果用户还没有统计记录，返回默认分数 1200
        return self.game_stats.elo_score if self.game_stats else 1200

    def get_battles_won(self):
        """获取用户赢得的所有对战的 Battle 对象列表"""
        # 查询该用户参与的 BattlePlayer 记录中 outcome 为 'win' 的对战
        # return Battle.query.join(BattlePlayer).filter(
        #     BattlePlayer.user_id == self.id,
        #     BattlePlayer.outcome == 'win'
        # ).all()
        # 或者通过 battle_participations 关系更直接
        # return [bp.battle for bp in self.battle_participations.filter_by(outcome='win').all() if bp.battle]
        # 使用 dynamic relationship 执行查询
        return (
            db.session.query(Battle)
            .join(BattlePlayer)
            .filter(BattlePlayer.user_id == self.id, BattlePlayer.outcome == "win")
        )  # 返回一个查询对象，可以继续筛选或使用 .all()/.first()


# AI代码
class AICode(db.Model):
    __tablename__ = "ai_codes"
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    code_path = db.Column(db.String(255), nullable=False)  # 文件系统中的路径
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=False)  # 用户当前激活的AI代码标记
    created_at = db.Column(db.DateTime, default=datetime.now)
    version = db.Column(db.Integer, default=1)

    # 关系:
    # user: 哪个用户拥有这个AI (backref="user" 在 User 模型中定义)
    # battle_players: 哪些 BattlePlayer 记录使用了这个AI (一对多 AICode -> BattlePlayer)
    battle_players = db.relationship(
        "BattlePlayer", backref="selected_ai_code", lazy="dynamic"
    )

    def __repr__(self):
        # 添加AI ID到 repr
        return f"<AICode {self.id}: {self.name} by User {self.user_id}>"

    def to_dict(self):
        """将 AI 代码信息转换为字典"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "code_path": self.code_path,
            "description": self.description,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "version": self.version,
        }


# 玩家游戏统计
class GameStats(db.Model):
    __tablename__ = "game_stats"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, unique=True
    )  # unique=True 强制一对一关系

    # 游戏统计
    elo_score = db.Column(db.Integer, default=1200)
    games_played = db.Column(db.Integer, default=0)
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)
    draws = db.Column(db.Integer, default=0)

    # 关系:
    # user: 哪个用户的统计数据 (backref="user" 在 User 模型中定义)

    def __repr__(self):
        return f"<GameStats for User {self.user_id} - Elo: {self.elo_score}>"

    def to_dict(self):
        """将游戏统计信息转换为字典"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "elo_score": self.elo_score,
            "games_played": self.games_played,
            "wins": self.wins,
            "losses": self.losses,
            "draws": self.draws,
        }


# 游戏对战记录 (现在承担了游戏的整体记录和状态)
class Battle(db.Model):
    __tablename__ = "battles"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)  # UUID
    status = db.Column(
        db.String(20), default="waiting"
    )  # waiting, playing, completed, error, cancelled
    # 分区类型：0=普通对局，1=预选赛，2=决赛，等
    section = db.Column(db.Integer, default=0)  # 默认为普通对局
    # 游戏日志UUID (关联到存储游戏过程的日志文件或对象)
    game_log_uuid = db.Column(db.String(36), nullable=True)

    # 时间戳
    created_at = db.Column(db.DateTime, default=datetime.now)  # 记录对战创建时间
    started_at = db.Column(db.DateTime, nullable=True)  # 记录对战开始时间
    ended_at = db.Column(db.DateTime, nullable=True)  # 记录对战结束时间

    # 游戏结果数据 (JSON格式，根据游戏类型不同)
    # 存储更详细的对战全局结果，而非单个玩家的结果
    results = db.Column(db.Text, nullable=True)  # JSON存储全局结果数据

    # 关系:
    # players: 参与这场对战的所有 BattlePlayer 记录 (一对多 Battle -> BattlePlayer)
    # cascade="all, delete-orphan": 当删除一个 Battle 时，相关的 BattlePlayer 记录也会被删除
    players = db.relationship(
        "BattlePlayer", backref="battle", lazy="dynamic", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Battle {self.id} - Status: {self.status}>"

    def get_players(self):
        """获取参与此对战的所有用户的 User 对象"""
        # 通过 BattlePlayer 关系获取用户对象
        # 注意：lazy='dynamic' 意味着这个返回的是一个查询对象
        # .all() 会执行查询并返回一个列表
        return [bp.user for bp in self.players.all() if bp.user]

    def get_battle_players(self):
        """获取此对战所有 BattlePlayer 记录"""
        # lazy='dynamic' 返回查询对象，可以继续筛选
        return self.players

    def get_winners(self):
        """获取此对战所有胜利者的 User 对象列表"""
        # 查询关联的 BattlePlayer 记录中 outcome 为 'win' 的用户
        return [
            bp.user for bp in self.players.filter_by(outcome="win").all() if bp.user
        ]

    def get_winner_battle_players(self):
        """获取此对战所有胜利者的 BattlePlayer 记录列表"""
        return self.players.filter_by(outcome="win")  # 返回一个查询对象

    def get_player_battlestats(self, user_id):
        """获取指定用户在此对战中的 BattlePlayer 记录"""
        return self.players.filter_by(user_id=user_id).first()


# 对战参与者模型 (直接挂载在 Battle 下)
class BattlePlayer(db.Model):
    __tablename__ = "battle_players"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    # 与 Battle 的关联 (多对一 BattlePlayer -> Battle)
    # nullable=False 强制每个 BattlePlayer 必须属于一个 Battle
    battle_id = db.Column(db.String(36), db.ForeignKey("battles.id"), nullable=False)
    # battle: 在 Battle 模型中通过 backref="players" 定义了

    # 与 User 的关联 (多对一 BattlePlayer -> User)
    # nullable=False 强制参与者必须是系统中的注册用户
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    # user: 在 User 模型中通过 backref="battle_participations" 定义了

    # 与用户选择的 AI 代码的关联 (多对一 BattlePlayer -> AICode)
    # 如果用户手动玩或者游戏类型不需要AI，可以为 nullable=True
    # 当前您设置为 nullable=False，表示每个参与者都必须使用一个 AI 代码进行对战
    # 如果需要支持人类玩家，请改为 nullable=True
    selected_ai_code_id = db.Column(
        db.String(36),
        db.ForeignKey("ai_codes.id"),
        nullable=False,  # 建议根据需求改为 True 或保持 False
    )
    # selected_ai_code: 在 AICode 模型中通过 backref="battle_players" 定义了

    # 参与者在此对战中的具体信息/状态
    # 例如，玩家在此对战中的位置/编号 (Player 1, Player 2 等)
    position = db.Column(db.Integer, nullable=True)

    # 玩家在此对战中的结果 (win, loss, draw, error, quit 等)
    # 使用这个字段来表示每个玩家在该对战中的胜负平状态
    outcome = db.Column(db.String(20), nullable=True)

    # 玩家在此对战开始前的 Elo 分数快照
    initial_elo = db.Column(db.Integer, nullable=True)

    # 玩家在此对战结束后 Elo 分数的变化值
    elo_change = db.Column(db.Integer, nullable=True)

    # 记录加入对战的时间 (如果需要区分何时“加入”对战列表 vs 对战实际开始)
    join_time = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        """将参与者信息转换为字典"""
        data = {
            "id": self.id,  # BattlePlayer 的 ID
            "battle_id": self.battle_id,
            "user_id": self.user_id,
            "username": (
                self.user.username if self.user else "未知用户"
            ),  # user_id nullable=False，所以 user 应该是 Non-None
            "selected_ai_code_id": self.selected_ai_code_id,
            "position": self.position,
            "outcome": self.outcome,
            "initial_elo": self.initial_elo,
            "elo_change": self.elo_change,
            "join_time": (
                self.join_time.isoformat() if self.join_time else None
            ),  # 格式化日期
        }
        # 如果 selected_ai_code_id 不为 None，则添加 AI 名称
        if self.selected_ai_code:
            data["selected_ai_code_name"] = self.selected_ai_code.name
        elif self.selected_ai_code_id is not None:
            # 如果 selected_ai_code_id 有值但对象为空 (比如 AI 记录被删了)，可以给一个提示
            data["selected_ai_code_name"] = "AI Not Found"

        return data

    def __repr__(self):
        user_info = self.user.username if self.user else "Unknown User"
        battle_info = self.battle_id or "Unknown Battle"
        return f"<BattlePlayer {self.id} for User {user_info} in Battle {battle_info} Outcome: {self.outcome}>"


# 用户加载函数 (用于 Flask-Login)
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)
