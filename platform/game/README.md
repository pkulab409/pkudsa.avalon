# Game 包项目文档：Avalon 游戏裁判与辅助模块

此文档介绍 `game` 包的功能、使用方式和接口。

---

## 1. 环境配置

- **Python 版本**：3.8+
- **依赖库**：
  - `openai`：与大语言模型交互
  - `python-dotenv`：加载 `.env` 配置
  - `logging`：日志管理
  - `typing`：类型注解
  - `pathlib`、`os`、`sys`、`json`、`time`、`random` 等标准库

目录中需包含一个 `.env` 文件，内含使用的大模型 API 信息（被 ignore 了，自己跑之前需要配置好）：
```dotenv
OPENAI_API_KEY=sk-<YOUR_SECRET_KEY>
OPENAI_BASE_URL=https://chat.noc.pku.edu.cn/v1
OPENAI_MODEL_NAME=deepseek-v3-250324-64k-local
```

---

## 2. `avalon_game_helper.py` 模块

该模块提供对私有/公有日志的读写，以及与 LLM（大语言模型）的交互封装，**供玩家代码调用**。

### 2.1 主要功能

1. **加载环境变量与初始化 LLM 客户端**
   - 自动从 `.env` 读取 LLM API 接口的 URL 和登录口令。
   - 创建 `OpenAI` 客户端，列出可用模型。
2. **上下文管理**
   - `set_current_context(player_id: int, game_id: str) -> None`
     - 设置当前玩家 ID 与游戏会话 ID。
3. **LLM 调用封装**
   - `askLLM(prompt: str) -> str`
     - 从私有日志中加载上下文历史，与当前提示一起发送给 LLM。
     - 保存对话历史到私有日志文件。
4. **私有日志（private）**
   - 存储位置：`{AVALON_DATA_DIR}/game_<game_id>_player_<player_id>_private.json`
   - 初始模板：`INIT_PRIVA_LOG_DICT = {logs: [], llm_history: [...]}`
   - `read_private_lib() -> List[str]`：读取日志列表。
   - `write_into_private(content: str) -> None`：追加日志内容。
5. **公有日志（public）**
   - 存储位置：`{AVALON_DATA_DIR}/game_<game_id>_public.json`
   - 不在辅助模块中写入，该操作在用户代码中完成。

### 2.2 接口清单

| 函数                           | 参数                                    | 返回值           | 功能描述               |
| ------------------------------ | --------------------------------------- | ---------------- | ---------------------- |
| `askLLM`                       | `prompt: str`                          | `str`            | 向 LLM 发送对话并保存历史 |
| `read_public_lib`              | 无                                      | `List[dict]`     | 获取公有库内容           |
| `read_private_lib`             | 无                                      | `List[str]`      | 获取私有库内容           |
| `write_into_private`           | `content: str`                          | `None`           | 追加日志到私有库         |

---

## 3. `referee.py` 模块

该模块实现了 `AvalonReferee` 类，负责主持阿瓦隆（Avalon）游戏的完整流程，包括角色分配、回合执行、日志记录与胜负判定。

### 3.1 核心类：`AvalonReferee`

```python
class AvalonReferee:
    def __init__(self, game_id: str, battle_observer: Observer, data_dir: str = "./data")
    def init_logs(self) -> None
    def load_player_codes(self, player_modules: Dict[int, Any]) -> None
    def init_game(self) -> None
    def init_map(self) -> None
    def night_phase(self) -> None
    def run_mission_round(self) -> None
    def conduct_global_speech(self) -> None
    def conduct_movement(self) -> None
    def conduct_limited_speech(self) -> None
    def get_players_in_hearing_range(self, speaker_id: int) -> List[int]
    def conduct_public_vote(self, mission_members: List[int]) -> int
    def execute_mission(self, mission_members: List[int]) -> bool
    def assassinate_phase(self) -> bool
    def run_game(self) -> Dict[str, Any]
    def safe_execute(self, player_id: int, method_name: str, *args, **kwargs): ...
    def log_public_event(self, event: Dict[str, Any]) -> None
```

#### 3.1.1 玩家代码实例化流程

玩家代码的实例化分为两个阶段：模块加载与类实例化。

1. **模块加载 (`_load_codes` 函数)**
   1. 为每个玩家 ID 构建唯一模块名，格式为 `player_<id>_module_<timestamp>`。
   2. 使用 `importlib.util.spec_from_loader` 创建模块规范，并通过 `module_from_spec` 生成模块对象。
   3. 将模块注册到 `sys.modules`，然后 `exec(code_content, module.__dict__)` 执行玩家提供的代码。
   4. 校验模块中是否定义了 `Player` 类，若缺失则记录错误并跳过；否则保存该模块以供后续使用（**此时玩家的代码字符串成功被转化成一个模块**）。

2. **类实例化、游戏开始 (`load_player_codes` 函数)**
   1. 遍历已加载的玩家模块字典 `{player_id: module}`。
   2. 调用模块中的 `Player()` 构造函数，创建对应的玩家实例并存入 `self.players`。
   3. 通过 `safe_execute(player_id, "set_player_index", player_id)` 方法，通知实例其玩家编号。
   4. 同样使用 `safe_execute` 将分配好的角色类型通过 `set_role_type` 传递给对应实例。
   5. 任何实例化或调用过程中的异常均由 `safe_execute` 捕获并记录，保证游戏流程不中断。

此流程确保玩家自定义策略在隔离的动态模块中执行，并与裁判逻辑解耦，便于安全管理与错误容忍。

#### 3.1.2 游戏流程

1. **初始化日志**：创建公有与各玩家私有 JSON 日志文件。
2. **加载玩家代码**：动态导入并执行玩家定义的 `Player` 类（见上）。
3. **角色分配**：随机分配蓝方（Merlin、Percival、Knight×2）与红方角色。
4. **夜晚阶段**：根据角色向玩家分发视觉信息。
5. **任务回合**：最多 5 轮，每轮包含提名、讨论、投票、任务执行。
6. **胜负判定**：蓝方或红方率先获得 3 胜；蓝方获胜后刺杀阶段。
7. **日志记录**：全过程中的事件通过 `log_public_event` 写入公有日志。私有对话数据由辅助模块存储。

#### 3.1.3 主要方法说明

- `safe_execute`：包装玩家代码调用，捕获异常并提供默认行为。
- `conduct_global_speech` / `conduct_limited_speech`：分别处理全局与有限范围的发言。
- `conduct_movement`：基于玩家 `walk()` 返回的方向，更新地图坐标并避免冲突。
- `conduct_public_vote` / `execute_mission`：处理投票逻辑与任务成功判定。
- `assassinate_phase`：蓝方完成任务后，刺客尝试刺杀 Merlin。
- `run_game`：整合以上步骤，返回包含胜者、角色分配与日志文件路径的结果字典。

### 3.2 同步对局数据到 Observer

- 游戏进行全程通过调用 `Observer.make_snapshot()` 函数向 Observer 提供对局信息，用于可视化。 
- 具体传递内容格式见下。

```python
def make_snapshot(self, event_type: str, event_data) -> None:
    """
    接收一次游戏事件并生成对应快照，加入内部消息队列中。

    event_type (str): 显示类型：
        "referee" -- 显示成旁白
        "player1" ~ "player7" -- 显示成玩家对话框气泡
        "move" -- 显示成地图
    event_data: 事件数据，数据类型语具体状况如下：
        * 如果 event_type 是 "referee"： str 类型，表示旁白
        * 如果 event_type 是 "player{P}"： str 类型，表示玩家行为
        * 如果 event_type 是 "move"： dict 类型，表示不同玩家目前的位置
            例： {1: (1, 3), 2: (2, 5), 3: (4, 7), ...}
    """
```

### 3.3 ⚠️玩家代码报错时，中止游戏

目前能实现玩家代码报错时中止游戏，**但还需要经过测试debug**。

玩家代码报错中止游戏时，**公有库**添加一项：

```json
{
  "type": "CRITICAL ERROR",
  "error_code_pid": 1,  // 1~7
  "error_code_method": "...",
  "error_msg": "..."
}
````

---

## 4. `battle_manager.py` 模块

该模块实现了对战管理器 `BattleManager`，采用单例模式，负责创建、管理和监控所有对战线程。

### 4.1 核心类：`BattleManager`

| 方法 | 参数 | 返回值 | 描述 |
| ---- | ---- | ------ | ---- |
| `create_battle(player_codes: Dict[int, str], config: Dict[str, Any] = None) -> str` | `player_codes`: 玩家代码字典<br>`config`: 可选对战配置 | `battle_id`: 对战唯一标识符 | 创建并启动新对战，返回其 ID |
| `get_battle_status(battle_id: str) -> Optional[str]` | `battle_id`: 对战 ID | 状态字符串 (`running`, `completed`, `error`) | 查询指定对战的当前状态 |
| `get_snapshots_queue(battle_id: str) -> List[Dict[str, Any]]` | `battle_id`: 对战 ID | 快照事件列表 | 获取并清空对应观察者的快照队列 |
| `get_battle_result(battle_id: str) -> Optional[Dict[str, Any]]` | `battle_id`: 对战 ID | 对战结果数据字典或 `None` | 查询已完成对战的最终结果 |
| `get_all_battles() -> List[Tuple[str, str]]` | 无 | 对战 ID 与状态列表 | 列出所有对战及其当前状态 |

模块通过 `__new__` 方法确保单例，使用 `threading.Thread` 启动每场对战，并在内部调用 `AvalonReferee` 执行游戏逻辑。`Observer` 实例用于收集并提供快照数据，便于前端或调试查看。数据目录由环境变量 `AVALON_DATA_DIR` 指定。

### 4.2 创建对战线程的具体实现办法（`create_battle()` 函数）

`create_battle` 方法在 `BattleManager` 中的作用是：为每场对战生成唯一 ID，创建并启动对应的线程，同时维护对战状态、结果与观察者。具体流程如下：

1. **生成唯一对战 ID**：使用 `uuid.uuid4()` 确保全局唯一性。

2. **定义线程执行函数**：

    - 1. 新建一个裁判 `AvalonReferee` 对象。
    - 2. 使用 `AvalonReferee._load_codes()` 和 `AvalonReferee.load_player_codes()` 将输入的玩家代码字典转给 `AvalonReferee` ，让它实例化这些代码，开始游戏。
    - 3. 在线程中执行裁判全过程。
    - 4. 捕获所有异常，保证主线程稳定运行。

3. **创建观察者并启动线程**：

    - 每场对战使用独立 `Observer`，用于收集裁判和玩家产生的快照。
    - 启动线程后即可并行进行游戏逻辑。

4. **返回对战 ID**。

---

## 5. `observer.py` 模块

用于记录游戏的快照，并预留接口提供给前端进行可视化。

### 5.1 核心类 `Observer`

#### 5.1.1 方法

- **`make_snapshot(event_type: str, event_data) -> None`**

  记录游戏事件并生成快照。**具体格式见上文，该方法被一局游戏的 referee 反复调用**。

- **`pop_snapshots() -> List[Dict[str, Any]]`**

  获取并清空所有快照。

- **`get_snapshots() -> List[Dict[str, Any]]`**

  获取所有快照，不删除。

- **`get_latest_snapshot() -> Dict[str, Any]`**

  获取最近的1条快照记录。

### 5.2 用法

该模块适用于需要记录和可视化游戏事件的场景。`Observer` 类提供线程安全的方法来管理游戏事件的快照。

---

## 6. `basic_player.py` / `smart_player.py` 模块

两个基准AI，**程序结构和用户需要写的代码完全相同**，并且可以跑通游戏。

- 其中，`smart_player.py` 会在每次发言时**使用 LLM**：

    ```python
    def say(self) -> str:
        what_deepseek_says = askLLM("随便生成一句30字以内的玩7人《阿瓦隆》游戏时可能说的话。只给出话，不要别的信息。")
        return what_deepseek_says
    ```

---

## 7. `main.py` 模块

### 7.1 方法

- **`parse_arguments()`**

    解析命令行参数，返回值包含所有参数的命名空间对象。

- **`setup_environment(args)`**

    设置环境变量，创建数据目录。

- **`create_player_codes(mode, player_codes)`**
    
    根据预定义的游戏模式（basic_test(基础AI), smart_test(智能AI), mixed_test(混合), qualifying(排位赛)）创建7个玩家代码字典。

- **`run_games(args)`**
    
    运行指定数量的游戏（调用`battle_manager.create_battle()`）并统计结果。

> `main.py` 还需要经过修改后，封装成面向用户进行测试的模块。

---

# 面向用户的 `main.py` 使用指南

> 🚧施工中…

---

**最后更新**：2025-04-24
