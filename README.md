## Tuvalon

### 一、项目概述

《图灵阿瓦隆-Tuvalon》是一个基于经典桌游《阿瓦隆》的AI对战平台。项目核心目标是让用户编写自己的AI程序，通过平台进行对战，并利用大语言模型（LLM）辅助AI进行决策和交流。平台提供用户认证、AI代码管理、在线匹配、实时对战、历史回放、天梯排行等功能。

### 二、技术文档

#### 1. 游戏规则与核心逻辑

游戏的详细规则、背景故事、角色设定、胜负条件等在项目的 `README.md` 及 `static/docs/README.md` 中有详细阐述。核心玩法围绕两大阵营（骑士方和反抗军方）在至多五轮任务中的博弈，融合了身份隐藏、推理、投票、执行任务以及最终的刺杀环节。

* **阵营与角色**：包含梅林、派西维尔、骑士（蓝方）和莫甘娜、刺客、奥伯伦（红方），每个角色拥有独特能力和信息视角。
* **游戏流程**：夜晚阶段（角色互认、梅林/派西维尔获取信息）-> 任务阶段（队长组队 -> 全图发言 -> 玩家移动 -> 有限范围发言 -> 公投表决 -> 任务执行）-> （可能发生的）刺杀阶段。
* **地图与移动**：游戏在9x9地图上进行，玩家每轮可移动3步，位置公开。
* **发言机制**：分为全图广播的公开讨论和基于角色听力范围（3x3或5x5）的有限讨论。
* **胜负判定**：
    * 蓝方：3轮任务成功且梅林未被刺杀。
    * 红方：3轮任务失败，或蓝方3轮任务成功后刺客成功刺杀梅林。
    * 异常结束：玩家算法bug或超时/超token等犯规行为导致该玩家判负。

#### 2. 平台架构

项目采用Flask框架构建Web应用，前后端交互。

* **后端核心**：
    * **应用入口 (`app.py`)**：Flask应用初始化，配置加载，蓝图注册，数据库和登录管理器初始化，预设数据（用户、AI）的初始化。
    * **蓝图 (`blueprints`目录)**：
        * `main.py`：处理主页等基本路由。
        * `auth.py`：负责用户认证（登录、注册、登出），使用Flask-Login和Flask-WTF进行表单处理和会话管理。
        * `ai.py`：AI代码管理（上传、编辑、删除、激活）。
        * `game.py`：游戏大厅、创建对战、查看对战详情、下载日志、取消对战等。
        * `profile.py`：用户个人资料及对战历史。
        * `ranking.py`：显示排行榜。
        * `visualizer.py`：游戏对局回放和JSON上传。
        * `admin.py`：管理员后台功能（用户管理、ELO修改、对局管理、自动对战控制等）。
        * `docs.py`：提供Markdown文档的在线渲染。
    * **数据库 (`database`目录)**：
        * `models.py`：定义了User, AICode, GameStats, Battle, BattlePlayer等SQLAlchemy数据模型。
        * `action.py`：封装了CRUD数据库操作函数。
        * `base.py`：创建SQLAlchemy (`db`) 和LoginManager (`login_manager`) 实例。
        * `__init__.py`：包初始化，导出模型和操作函数，配置Flask-Login的`user_loader`。
        * `关于avalon数据库架构的解读.md`：对数据库设计的解释。
    * **游戏核心逻辑 (`game`目录)**：
        * `referee.py`：核心裁判逻辑，负责主持游戏流程、加载玩家代码、执行玩家动作、判定胜负、记录日志等。包含`AvalonReferee`类，通过`safe_execute`安全调用玩家代码。
        * `avalon_game_helper.py`：为玩家AI提供辅助API，如调用LLM (`askLLM`)、读写公私有日志库等。近期重构为面向对象并引入线程本地存储以保证多线程环境下的状态一致性。 [cite: 2]
        * `battle_manager.py`：单例模式的对战管理器，负责创建、管理和监控所有对战线程。
        * `observer.py`：记录游戏快照，用于前端可视化回放。
        * `automatch.py`：自动对战匹配和执行逻辑。
        * `restrictor.py`：限制玩家代码中`__builtins__`的访问，提供安全的模块导入器。
        * `basic_player.py`, `smart_player.py`, `idiot_player.py`, `smart_player_new.py`: 不同策略的示例AI玩家代码。
    * **服务层 (`services`目录)**：
        * `battle_service.py`：处理与对战相关的数据库交互和服务，如更新对战状态、处理结果、获取AI代码路径。
    * **工具类 (`utils`目录)**：
        * `automatch_utils.py`：提供获取`AutoMatch`单例的工具函数。
        * `battle_manager_utils.py`：提供获取`BattleManager`单例的工具函数。
        * `db_utils.py`：数据库相关工具函数，如构建日志路径、获取AI代码路径等。
    * **配置 (`config`目录)**：
        * `config.py`：Flask应用配置类，从`config.yaml`加载配置。
        * `config.yaml`：YAML格式的配置文件，包含数据库URI、密钥、AI代码上传目录、初始用户等。
* **前端 (`templates`目录)**：使用Jinja2模板引擎渲染HTML页面，涵盖认证、AI管理、游戏大厅、对战视图、排行榜、文档、个人资料、管理员面板等。
* **静态文件 (`static/docs`目录)**：存放Markdown格式的文档，通过`docs.py`蓝图进行渲染。

#### 3. AI玩家代码提交流程与接口

玩家需要提交包含特定接口的Python类 (`Player`或`MyStrategy`)。

* **核心接口 (`Player`类 - 参考 `README_code_submission_guide.md` 及 `static/docs/code_submission_guide.md`)**：
    * `__init__(self)`: 初始化玩家状态。
    * `set_player_index(self, index: int)`: 设置玩家编号。
    * `set_role_type(self, role_type: str)`: 设置玩家角色。
    * `pass_role_sight(self, role_sight: dict[str, int])`: 传递夜晚视野信息。
    * `pass_map(self, map_data: list[list[str]])`: 传递地图数据。
    * `pass_position_data(self, player_positions: dict[int,tuple])`: 传递玩家位置信息。
    * `pass_message(self, content: tuple[int, str])`: 接收其他玩家发言。
    * `pass_mission_members(self, leader: int, members: list[int])`: 告知本轮队长及队员。
    * `decide_mission_member(self, team_size: int) -> list[int]`: （队长）选择任务成员。
    * `walk(self) -> tuple[str, ...]`: 返回移动指令。
    * `say(self) -> str`: 发言。
    * `mission_vote1(self) -> bool`: 对队伍提案进行公投。
    * `mission_vote2(self) -> bool`: 任务执行投票（决定成功/失败）。
    * `assass(self) -> int`: （刺客）选择刺杀目标。
* **辅助API (由 `avalon_game_helper.py` 提供)**：
    * `askLLM(prompt: str) -> str`: 调用大语言模型。
    * `read_public_lib() -> list[dict]`: 读取公共对局记录。
    * `read_private_lib() -> list[str]`: 读取私有存储。
    * `write_into_private(content: str) -> None`: 写入私有存储。
* **代码限制**：通过`restrictor.py`限制导入的库和内建函数，保证安全性。允许 `random`, `re`, `collections`, `math`, 以及 `game.avalon_game_helper`。
* **代码执行**：`referee.py` 中的 `_load_codes` 和 `load_player_codes` 方法负责动态加载、实例化和执行玩家代码。

#### 4. 数据存储与格式

* **数据库**：使用SQLite (默认 `platform.db`)，通过SQLAlchemy进行ORM。模型定义见 `database/models.py`。
* **AI代码文件**：存储在服务器文件系统中，路径由`config.yaml`中的`AI_CODE_UPLOAD_FOLDER`指定。
* **游戏日志**：
    * **公共日志 (`game_{GAME_ID}_public.json`)**: 记录游戏流程中的公开事件，如游戏开始、夜晚结束、任务开始、队伍提名、发言、移动、投票结果、任务结果、刺杀、游戏结束等。详细格式见 `documentation/technical_docs/lib_data_format.md` 及 `documentation/document4users/server_func.md`。
    * **私有日志 (`game_{GAME_ID}_player_{PLAYER_ID}_private.json`)**: 存储每个玩家的私有笔记和LLM交互历史。格式包含`logs` (玩家自定义内容) 和 `llm_history` (对话记录)，`llm_call_counts` (LLM调用计数)。
    * **快照日志 (`game_{GAME_ID}_archive.json`)**: 由`Observer`类 生成，记录详细的游戏事件快照，用于可视化回放。事件类型包括阶段（Phase）、事件（Event）、动作（Action）、标识（Sign）、信息（Information）、大事件（Big_Event）、地图（Map）、Bug。格式说明见 `game/README_snapshot.md`。 示例见 `example/example_game_replay.json`。

### 三、项目架构

#### 1. 宏观架构

本项目是一个典型的Model-View-Controller (MVC) 模式的Web应用，结合了游戏服务逻辑：

* **Model**: 由 `database/models.py` 定义，通过SQLAlchemy与数据库交互，`database/action.py` 封装了数据操作逻辑。
* **View**: 由 `templates` 目录下的HTML文件构成，通过Jinja2模板引擎渲染。
* **Controller**: 由 `blueprints` 目录下的各个Python模块实现，处理HTTP请求，与服务层、模型层交互，并返回视图或JSON数据。
* **Game Services**: 位于 `game` 和 `services` 目录，处理核心游戏逻辑、AI执行、对战管理等。

#### 2. 目录结构（核心部分）

```
pkudsa.avalon/
├── app.py                      # Flask应用主入口和初始化
├── requirements.txt            # Python依赖
├── config/                     # 配置文件夹
│   ├── config.py               # 配置加载逻辑
│   └── config.yaml             # 具体配置项
├── blueprints/                 # Flask蓝图，模块化应用功能
│   ├── admin.py                # 管理员功能
│   ├── ai.py                   # AI代码管理
│   ├── auth.py                 # 用户认证
│   ├── docs.py                 # 文档展示
│   ├── game.py                 # 游戏大厅与对战流程控制
│   ├── main.py                 # 主页等
│   ├── profile.py              # 用户资料
│   ├── ranking.py              # 排行榜
│   └── visualizer.py           # 游戏回放可视化
├── database/                   # 数据库相关
│   ├── __init__.py
│   ├── action.py               # CRUD操作
│   ├── base.py                 # SQLAlchemy和LoginManager实例
│   ├── models.py               # 数据模型定义
│   └── 关于avalon数据库架构的解读.md
├── game/                       # 游戏核心逻辑
│   ├── __init__.py
│   ├── avalon_game_helper.py   # 玩家AI辅助工具 (LLM, 日志)
│   ├── automatch.py            # 自动匹配逻辑
│   ├── battle_manager.py       # 对战管理器 (单例)
│   ├── basic_player.py         # 基础AI示例
│   ├── idiot_player.py         # 更简单的AI示例
│   ├── observer.py             # 游戏快照记录器
│   ├── referee.py              # 游戏裁判核心逻辑
│   ├── restrictor.py           # AI代码执行环境限制
│   ├── smart_player.py         # 智能AI示例
│   └── smart_player_new.py     # 另一个智能AI示例
├── services/                   # 业务逻辑服务
│   └── battle_service.py       # 对战相关服务
├── static/                     # 静态文件 (CSS, JS, images, docs)
│   └── docs/                   # Markdown文档
├── templates/                  # Jinja2 HTML模板
│   ├── admin/
│   ├── ai/
│   ├── auth/
│   ├── docs/
│   ├── errors/
│   ├── profile/
│   ├── visualizer/
│   ├── base.html
│   ├── battle_completed.html
│   ├── battle_ongoing.html
│   ├── create_battle.html
│   ├── index.html
│   ├── lobby.html
│   └── ranking.html
└── utils/                      # 工具函数
    ├── __init__.py
    ├── automatch_utils.py
    ├── battle_manager_utils.py
    └── db_utils.py
```

#### 3. 技术栈

* **后端**: Python, Flask, Flask-Login, Flask-SQLAlchemy, Flask-WTF, Werkzeug
* **数据库**: SQLite (可配置其他SQLAlchemy支持的数据库)
* **前端**: HTML, Bootstrap, JavaScript (用于动态更新和交互，如对战状态轮询、地图渲染等)
* **LLM**: OpenAI API (通过`avalon_game_helper.py` 接入，可配置不同模型如DeepSeek)
* **配置**: YAML
* **其他**: `python-dotenv` (环境变量管理), `PyYAML` (YAML解析), `requests` (可能用于内部API调用或未来扩展), `Pillow` (图像处理，可能用于头像等), `faker` (测试数据生成), `email_validator` (邮箱验证)。

#### 4. 关键组件交互

1.  **用户请求**: 用户通过浏览器与Flask应用交互，请求被路由到相应的蓝图处理函数。
2.  **认证与授权**: `auth.py` 和Flask-Login处理用户登录状态，`@login_required` 和 `@admin_required` (自定义装饰器) 控制访问权限。
3.  **AI代码管理**: 用户通过`ai.py` 对应的页面上传、管理AI。代码文件存储在服务器，元数据存入数据库。
4.  **对战创建与执行**:
    * 用户通过`game.py` 蓝图创建对战，选择参与者和AI。
    * `BattleManager` (`battle_manager.py`) 单例接收创建请求，启动一个新的对战线程。
    * 每个对战线程中，`AvalonReferee` (`referee.py`) 实例被创建。
    * `Referee` 加载玩家AI代码 (使用`restrictor.py` 限制环境)，初始化游戏（角色、地图），并按游戏规则驱动流程。
    * 玩家AI通过`avalon_game_helper.py` 提供的接口与LLM交互、记录私有信息。
    * `Observer` (`observer.py`) 记录游戏快照。
    * `BattleService` (`battle_service.py`) 用于裁判与数据库之间的交互，如更新对战状态。
5.  **数据持久化**: `database/action.py` 中的函数被各模块调用以操作数据库。
6.  **结果展示与回放**: 对战结束后，结果存入数据库。用户可通过`profile.py` 查看历史，`visualizer.py` 提供对局回放（读取`_archive.json`快照文件）。
7.  **排行榜**: `ranking.py` 从数据库提取统计数据生成排行榜。
8.  **自动对战**: `automatch.py` 和 `automatch_utils.py` 实现后台自动匹配和进行对战的逻辑，主要由管理员控制。
