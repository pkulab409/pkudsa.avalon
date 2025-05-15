# 关于 avalon 数据库架构的解读

# app.py：Flask 应用创建与配置

## 1.数据库初始化架构

### 1.1 导入必要的库和模块

在 app.py 中，导入了 flask_sqlalchemy 库，用于集成 SQLAlchemy 到 Flask 应用中，同时从 database.base 导入 db 和 login_manager，并从 database 模块导入 initialize_database 函数。

### 1.2 初始化数据库的连接

在 create_app 函数中，调用 initialize_database(app) 函数来初始化数据库连接。这个函数应该包含了设置数据库 URI 等操作，将数据库与 Flask 应用绑定。

#### 关于数据库 URI 设置的解读：

### 1.3 创建数据库表

在应用上下文环境中，调用 db.create_all() 来创建所有定义好的数据库表.

## 2.数据库模型架构

主要位于 model.py 文件中。

### 2.1 用户模型（User）

用于存储用户的基本信息，如用户名、邮箱、密码等。在 app.py 中，使用了 get_user_by_email、create_user 等函数来操作这个模型。

- get_user_by_email：根据用户邮箱查询用户信息。
- create_user：创建新用户记录。(位于 action.py 中，关注创建新用户的代码实现)
  1. 参数调整：在 create_user 函数中加入新参数
  2. 用户对象创建：创建 User 对象时，加入对应的参数
  3. 日志信息更新：更新日志信息，记录用户创建的动作

### 2.2 AI 代码模型（AICode）

用于存储用户上传的 AI 代码信息，包括所属用户 ID、AI 代码名称、代码存储路径、描述等。在 app.py 中，使用了 create_ai_code 函数来创建这个模型的记录。

- create_ai_code：创建新的 AI 代码记录。
- set_active_ai_code：设置某个用户的活跃 AI 代码

## 数据库储存架构

### 3.1 文件储存

AI 代码文件以文件形式存储在服务器上，通过配置 AI_CODE_UPLOAD_FOLDER 来指定存储路径。每个用户有自己的子目录，AI 代码文件存储在该子目录下。

### 3.2 数据库储存

用户信息和 AI 代码信息以记录的形式存储在数据库中，通过关联关系（如 user_id 外键）来建立用户和 AI 代码之间的联系。

# action.py:实现了数据库的增删改查(CRUD)操作

## 1. 导入模块与配置

- 数据库连接：从 .base 导入 db，这应该是 SQLAlchemy 的数据库实例，用于与数据库进行交互。
- 日志记录：使用 logging 模块记录数据库操作中的错误和信息。
- SQLAlchemy 工具：导入 select、update 等 SQLAlchemy 工具，用于构建数据库查询。
- 模型导入：从 .models 导入多个数据库模型，包括 User、Battle 等，这些模型定义了数据库表的结构。
  - User：存储用户的基本信息，如用户名、邮箱、密码等，可能还包含是否为管理员等标识。
  - Battle：记录对战的相关信息，例如对战的时间、对战的结果等。
  - GameStats：存储用户的游戏统计信息，像胜场数、负场数、Elo 分数等。
  - AICode：存储用户上传的 AI 代码的信息，包括代码名称、文件路径、版本号、是否激活等。
  - BattlePlayer：关联用户和对战，记录用户在对战中的表现。

## 基础数据库工具函数

- 安全提交：safe_commit 函数用于安全地提交数据库事务，若出现异常则回滚并记录错误。
- 安全添加：safe_add 函数将模型实例添加到数据库会话中，并调用 safe_commit 进行提交。
- 安全删除：safe_delete 函数从数据库会话中删除模型实例，并调用 safe_commit 进行提交。

## 用户(User)CRUD 操作

- 查询用户：提供了根据用户 ID、用户名和邮箱查询用户记录的函数。
  - get_user_by_id：根据用户 ID 查询用户记录。
  - get_user_by_username：根据用户名查询用户记录。
  - get_user_by_email：根据邮箱查询用户记录。
- 创建用户：创建新用户时会检查用户名和邮箱是否已存在，同时为新用户创建游戏统计记录。(create_user)
- 更新用户：可以更新用户的多个字段，特殊处理密码更新，并更新时间戳。(update_user)
- 删除用户：删除用户记录时，相关的 AICode、BattlePlayer 和 GameStats 记录会根据级联规则或外键约束进行处理。(delete_user)

## AI 代码(AICode)CRUD 操作

- 查询 AI 代码：提供了根据 AI 代码 ID、用户 ID 查询 AI 代码记录的函数，还可以获取用户当前激活的 AI 代码。
- 创建 AI 代码：创建新的 AI 代码记录时会自动生成版本号，默认不激活。
- 更新 AI 代码：可以更新 AI 代码的部分字段，不允许修改 ID、创建日期、用户 ID 和版本号。
- 删除 AI 代码：删除 AI 代码记录时会检查是否有相关的 BattlePlayer 记录。
- 设置激活 AI 代码：为用户设置激活的 AI 代码时，会取消该用户当前所有 AI 的激活状态。
- 获取 AI 代码完整路径：根据 AI 代码 ID 获取 AI 代码文件在文件系统中的完整路径。

## 游戏统计(GameStats)CRUD 操作

- 查询：按用户 ID 查询游戏统计信息。(get_game_stats_by_user_id)
- 创建：检查记录是否存在，避免重复创建，保证数据唯一性。(create_game_stats)
- 更新：可更新部分字段，限制关键信息修改，维护数据一致性。(update_game_stats)
- 排行榜：根据游戏场次和 Elo 分数生成排行榜，方便展示用户排名。(get_leaderboard)此处可以用于后期天梯榜的具体实现。

## 对战 CRUD 操作

- 查询：按 ID 查询对战记录，支持按用户、状态、时间范围查询对战列表。(get_battle_by_id)
- 创建：检查 AI 代码是否存在，创建对战记录并关联玩家和 AI 代码，保证数据有效性。(create_battle)
- 更新：可更新对战记录的多个字段。(update_battle)
- 列表获取：支持分页查询，方便展示对战信息。(get_battle_list)

# models.py:数据库模型定义

## 1. 用户模型(User)

- ai_codes：一对多关系，一个用户可以撰写多个 AI 代码。
- battle_participations：一对多关系，一个用户可以参与多个对战。
- game_stats：一对一关系，一个用户对应一条游戏统计记录。

### 方法：

- set_password：设置用户的密码哈希。
- check_password：检查输入的密码是否与哈希匹配。
- get_active_ai：获取用户当前激活的 AI 代码。
- get_elo_score：获取用户的 ELO 分数。
- get_battles_won：获取用户赢得的所有对战的 Battle 对象列表。

## 2. AI 代码模型(AICode)

- user：多对一关系，一个 AI 代码属于一个用户。
- battle_players：一对多关系，一个 AI 代码可以被多个 BattlePlayer 使用。

### 方法：

- to_dict：将 AI 代码信息转换为字典。

## 3. 游戏统计模型(GameStats)

- user：一对一关系，一条游戏统计记录对应一个用户。

### 方法：

- to_dict：将游戏统计信息转换为字典。

## 4. 对战 j 记录模型(Battle)

- players：一对多关系，一个对战可以有多个参与者。

### 方法：

- get_players：获取参与此对战的所有用户的 User 对象。
- get_battle_players：获取此对战所有 BattlePlayer 记录。
- get_winners：获取此对战所有胜利者的 User 对象列表。
- get_winner_battle_players：获取此对战所有胜利者的 BattlePlayer 记录列表。
- get_player_battlestats：获取指定用户在此对战中的 BattlePlayer 记录。

## 5. 对战玩家模型(BattlePlayer)

- battle：多对一关系，一个 BattlePlayer 属于一个对战。
- user：多对一关系，一个 BattlePlayer 对应一个用户。
- selected_ai_code：多对一关系，一个 BattlePlayer 选择一个 AI 代码。

### 方法：

- to_dict：将参与者信息转换为字典。

## 6.用户加载函数(load_user)

用于 Flask-Login 模块加载用户信息，根据用户 ID 从数据库中查询用户信息。

# base.py 创建核心数据库和登录管理器的实例

## 1. 核心实例的创建

- SQLAlchemy 实例 (db)：SQLAlchemy 是一个强大的 SQL 工具包和对象关系映射（ORM）库，db 实例用于与数据库进行交互，包括创建、查询、更新和删除数据等操作。
- LoginManager 实例 (login_manager)：LoginManager 是 Flask-Login 扩展的核心组件，用于管理用户会话和登录状态。

# **init**.py 包入口与初始化

这个文件作为包的入口，负责导出核心实例、模型类和数据库操作函数，并提供数据库初始化的功能。

## 1. 导出核心实例

从 base.py 中导入 db 和 login_manager 实例，以便在其他模块中使用。

## 2. 导出模型类

从 models.py 中导入所有的模型类，这些模型类定义了数据库表的结构和关系。

## 3. 数据库初始化函数

initialize_database 函数用于将 db 实例与 Flask 应用关联起来，完成数据库的初始化工作。

## 4. 导出数据库操作函数

从 action.py 中导入所有需要外部使用的数据库操作函数，这些函数封装了对数据库的各种操作，如查询、创建、更新和删除等。

## 5. 配置 Flask-Login 的 user_loader

load_user 函数是 Flask-Login 用来加载用户的回调函数，它根据用户 ID 从数据库中获取用户对象。

## 6. 清理命名空间

**all** 列表定义了包的公共接口，只有在这个列表中的对象才能被 from package import \* 语句导入。
