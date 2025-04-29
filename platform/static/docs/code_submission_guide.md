🧭大作业对战平台 用户文档

---

# 提交代码要求

Version 1.0  Date: 25/4/24

## 提交的代码和服务器之间的互动规则简述

用户（也就是大家）在对战平台上提交游戏代码。在游戏对局进行过程中，需要注意的是：

**服务器始终握有主动权**：它负责加载玩家代码、分发编号、循环调用玩家写的函数来与玩家代码进行互动。整个对战流程都由服务器发起和掌控，玩家代码仅被动响应这些调用。

**以“石头剪刀布”游戏为例**，整个游戏进程如下：
- 首先，服务器加载并初始化每位玩家的 `Player` 实例，给他们分配编号。
- 然后，在一轮游戏中，服务器依次调用每个玩家的 `make_move()`方法收集他们的出拳（石头、剪刀或布），即时计算胜负或平局。
- 接着，服务器再调用每位玩家的 `pass_round_result(my_move, opp_move, result)` 方法，把本轮自己和对手的出拳以及结果（赢/输/平）反馈给他们。这里，函数的所有参数（`my_move`, `opp_move`, `result`）都由服务器给出。

可以看到，上述操作中的**所有主语都是服务器**，也就是说，玩家的代码**本身从不主动“跑”流程**——它只是被动地等着服务器来调用各个接口方法，真正的流程控制和结果判定都在服务器端完成。

```python
import random

class Player:
    def __init__(self):
        self.index = None  # 保存服务器分配的玩家编号
        self.record = []  # 保存游戏记录

    def set_player_index(self, index):
        # 告诉玩家自己的编号
        self.index = index

    def make_move(self):
        # 随机出拳：rock、paper 或 scissors
        return random.choice(['rock', 'paper', 'scissors'])

    def pass_round_result(self, my_move, opp_move, result):
        # 接收本轮信息并保存
        self.record.append(
            f"Player {self.index}: {my_move} vs {opp_move} -> {result}")

```

一般而言，用户除了定义 `Player` 类之外，代码里面可以不包含任何其他内容。因为**只有  `Player` 类中的函数才在这个游戏中奏效**。

以上，我们用“石头剪刀布”游戏为例，解释了游戏运行的进程和用户需要如何写代码。《图灵阿瓦隆》游戏也是一样。下面**正式开始**介绍《图灵阿瓦隆》游戏中，玩家的代码应该怎么写👇:

---

## 提交代码文件结构

- 玩家需提交一段包含 `Player` 类的 Python 代码。
- 注意： `Player` 类是核心入口，所有回合信息均通过其方法传递，所有玩家决策均由其方法返回。

## Player 类接口说明

平台服务端会在不同阶段调用您在 `Player` 类中定义的如下方法：

### 0. `__init__(self)`
**功能**：初始化玩家内部状态，搭建决策所需的数据结构。

- **被调用时机**：服务端创建 `Player` 对象实例时自动调用。
- **使用建议**：
  - 将以下成员属性设为初始值：
    - `self.index = None`：玩家编号（待服务器调用 `set_player_index` 以填充）；
    - `self.role = None`：角色类型（待服务器调用 `set_role_type` 以填充）；
    - `self.map = None`：后续 `pass_map` 中接收的地图数据；
    - `self.memory = {"speech": {}, "teams": [], "votes": [], "mission_results": []}`：记录发言、队伍历史、投票结果及任务结果；
    - `self.suspects = set()`：可疑玩家编号集合；
    - 视具体实现可额外初始化其它缓冲或配置项（见下）。
  - **当然，这些成员属性是由大家自定的，我们这里的示例仅供参考，大家可以在其中自由发挥。**

- **示例**：
  ```python
  class Player:
      def __init__(self):
          # 基本状态
          self.index = None  # 玩家编号
          self.role = None  # 角色类型
          # 地图
          self.map = None
          self.player_positions = {}
          # 历史记录
          self.memory = {
              "speech": {},  # {player_index: [messages]}
              "teams": [],  # 每轮队伍信息
              "votes": [],  # 每轮投票详情
              "mission_results": [],  # 任务成功/失败
          }
          # 推理辅助
          self.suspects = set()  # 可疑玩家编号集合
          self.trusted = set()  # 信任玩家编号集合
          self.role_sight = {}  # 角色视野信息
          self.round = 0  # 当前回合数
          self.last_leader = None  # 上一轮队长
          self.last_team = []  # 上一轮队伍成员
          self.player_count = 7  # 总玩家数
          self.is_evil = False  # 是否为邪恶方
          self.location = None  # 当前位置
  ```

### 1. `set_player_index(self, index: int)`
**功能**：设置当前玩家的唯一编号。

- **参数**：
  - `index`：整数，范围为 1~7，表示玩家在本局中的编号。
- **返回值**：无。
- **被调用时机**：游戏开始时，由服务端分配玩家实例编号时调用。
- **使用建议**：
  - 将编号保存在实例属性，如 `self.index`，用于后续决策过程中的自身识别。

### 2. `set_role_type(self, role_type: str)`
**功能**：告知玩家其在本局中的角色身份。

- **参数**：
  - `role_type`：字符串，如 "Merlin"、"Assassin"、"Percival" 等。
- **返回值**：无。
- **被调用时机**：分配角色后立即调用。
- **使用建议**：
  - 存储为 `self.role`，以便在决策逻辑中区分红蓝方及特殊能力。

### 3. `pass_role_sight(self, role_sight: dict[str, int])`
**功能**：向具有视野能力的角色（如梅林、派西维尔）传递夜晚视野信息。服务器**不会调用**没有夜晚视野的玩家的 `pass_role_sight` 函数。

- **参数**：
  - `role_sight`：字典类型。
    - **梅林**会得到红方玩家的信息：`{"Morgana": 4, "Assassin": 5, "Oberon": 7}`
    - **莫甘娜**得到刺客信息：`{"Assassin"： 5}`
    - **刺客**得到莫甘娜信息：`{"Morgana": 4}`
    - **派西维尔**得到梅林和莫甘娜的编号，但无法区分：`{"Special1": 1, "Special2", 4}`
- **返回值**：无。
- **被调用时机**：夜晚阶段，服务端向特定角色调用。
- **使用建议**：
  - 将视野信息保存在 `self.role_sight` 或合并到可疑玩家集合 `self.suspects`，用于后续推理。

### 4. `pass_map(self, map_data: list[list[str]])`
**功能**：传递当前游戏地图数据的深拷贝给玩家。

- **参数**：
  - `map_data`：二维列表，包含地图格子信息的字符串。
- **返回值**：无。
- **被调用时机**：每次地图更新时调用。
- **使用建议**：
  - 存储在 `self.map`，用于导航、路径规划等逻辑。

### 5. `pass_position_data(self, player_positions: dict[int,tuple])`
**功能**：获取其他玩家的位置信息。

- **参数**：
  - `player_positions`：字典，键为玩家编号，值为包含玩家位置信息的二元组`(x, y)`。
- **返回值**：无。
- **被调用时机**：每次地图更新时调用。
- **使用建议**：
  - 存储在 `self.player_positions`，用于导航、路径规划等逻辑。

### 6. `pass_message(self, content: tuple[int, str])`
**功能**：接收其他玩家的发言内容。

- **参数**：
  - `content`：二元组 `(speaker_index, message_text)`。
- **返回值**：无。
- **被调用时机**：每当任意玩家发言后，服务端广播时调用。
- **使用建议**：
  - 将发言记录到 `self.memory["speech"]` 中；
  - 针对关键词（如“破坏”、“成功”）进行简单文本分析，标记嫌疑对象。

### 7. `pass_mission_members(self, leader: int, members: list[int])`
**功能**：告知本轮任务队长及选中队员列表。

- **参数**：
  - `leader`：整数，当前轮次队长编号；
  - `members`：整数列表，包含本轮执行任务的队员编号。
- **返回值**：无。
- **被调用时机**：队长选择队员完成后调用。
- **使用建议**：
  - 保存 `self.last_leader`、`self.last_team` 并记录到历史队伍信息 `self.memory["teams"]`；
  - 检查自身是否在队伍中，以便在 `mission_vote2` 中区分投票逻辑。

### 8. `decide_mission_member(self, team_size: int) -> list[int]`
**功能**：由队长角色调用，选择本轮任务的执行成员。

- **参数**：
  - `team_size`：整数，所需队员人数。
- **返回值**：整数列表，长度等于 `team_size`。
- **被调用时机**：轮到自己担任队长时。
- **使用建议**：
  - 根据游戏策略，选择合适人选。

### 9. `walk(self) -> tuple[str, ...]`
**功能**：执行移动行为，返回一组方向指令。

- **参数**：无。
- **返回值**：字符串元组，最多包含 3 个方向（"Up"、"Down"、"Left"、"Right"）。长度小于 3 则视为放弃剩余步数。
- **被调用时机**：需要移动时，服务端依次通过内核调用。
- **使用建议**：
  - 根据当前 `self.map` 与目标位置路径规划；
  - 返回尽可能有效的路径指令序列。

### 10. `say(self) -> str`
**功能**：发言行为，返回文本内容供其他玩家接收。

- **参数**：无。
- **返回值**：字符串，玩家发言内容。
- **被调用时机**：发言轮次，服务端按顺序调用。
- **使用建议**：
  - 可结合 `helper.read_public_lib()` 获取全局对局记录，构造 `askLLM` 的提示词生成发言；
  - 将重要推理写入私有存储，如 `helper.write_into_private()`，便于后续阅读。

### 11. `mission_vote1(self) -> bool`
**功能**：对队长提案进行公投，决定是否通过队伍。

- **参数**：无。
- **返回值**：布尔值，`True` 表示同意，`False` 表示否决。
- **被调用时机**：每轮队长提案完成后。
- **使用建议**：
  - 若队伍完全由信任玩家组成，返回 `True`；
  - 否则可按照风险度或概率方式投出 `True` 或 `False`。

### 12. `mission_vote2(self) -> bool`
**功能**：在任务执行阶段决定任务结果。

- **参数**：无。
- **返回值**：布尔值，`True` 表示任务成功（蓝方），`False` 表示破坏（红方）。
- **被调用时机**：任务成员确定后。
- **使用建议**：
  - 红方角色（"Assassin","Morgana","Oberon"）可以返回 `False`，或可结合混淆策略，增加不可预测性。
  - 蓝方角色必须返回 `True` （如果不返回 `True` 将造成不可预料的后果）。

### 13. `assass(self) -> int`
**功能**：红方失败时刺杀操作，选择目标玩家编号。

- **参数**：无。
- **返回值**：整数，被刺杀玩家编号。
- **被调用时机**：所有任务完成且红方未获胜时。只有身份是刺客的玩家才会被调用。
- **使用建议**：
  - 按照前期推理结果（`self.suspects` 或私有存储记录）选择最可能为梅林的玩家；
  - 写入私有日志，便于赛后复盘。

---

## 可调用的辅助API

服务器为大家提供了辅助 API 工具包，用户可以通过下面语句导入：

```python
from game.avalon_game_helper import (
    askLLM, read_public_lib,
    read_private_lib, write_into_private
)
```

工具包中有以下工具函数可供使用：

### 1. `askLLM(prompt: str) -> str`
**功能**：调用大语言模型（LLM）进行推理，生成文本回复。

- **参数**：
  - `prompt` (str): 输入给模型的提示文本，用于引导模型生成回复。
- **返回值**：
  - `str`: 大语言模型生成的文本回复。

- **调用示例**:
  ```python
  response = askLLM("推测当前玩家的阵营是？")
  ```

### 2. `read_public_lib() -> list[dict]`
**功能**：读取所有玩家可见的公共对局记录库，包含全局对战信息。

- **返回值**：
  - `list[dict]`: 返回一个字典列表，每个字典表示一条对局记录。  

- **调用示例**：
  ```python
  history = read_public_lib()
  ```

### 3. `read_private_lib() -> list[dict]`
**功能**：读取仅对当前玩家可见的私有存储数据。

- **返回值**：
  - `list[dict]`: 返回一个字典列表，每个字典表示一条记录。 字典中，键 `"content"` 对应的值是先前写入的文本内容。

- **调用示例**：
  ```python
  private_data = read_private_lib()
  ```

### 4. `write_into_private(content: str) -> None`
**功能**：向当前玩家的私有存储中追加写入内容。

- **参数**：
  - `content` (str): 需要保存的文本内容。

- **调用示例**：
  ```python
  write_into_private('suspects: 3,5')
  ```

请根据需要在策略中调用，记录、分析对局数据。

- 关于公有库、私有库的 [更多说明](./server_func)

---

## 服务器调用流程概览

1. **模块导入**：服务端 import 玩家代码模块，并实例化 1~7 号玩家 `Player` 对象。
2. **分配角色**：随机分配角色并调用 `set_role_type`。
3. **夜晚阶段**：根据角色不同，调用 `pass_role_sight` 等方法传递身份信息。
4. **队伍选择**：每轮随机或按规则确定队长，调用 `decide_mission_member` 获取队员。
5. **发言/移动轮次**：按顺序调用 `say`，广播每段发言并通过 `pass_message` 通知能收听到发言的其他玩家；按顺序调用 `walk` 实现玩家移动。
6. **投票与任务**：分别调用 `mission_vote1`、`mission_vote2`，记录投票结果。
7. **刺杀阶段**：游戏结束后，若红方失败触发刺杀，调用 `assass` 选择目标。

---

## 示例代码

以下为简化样例，供初次接入参考：

```python
from game.avalon_game_helper import write_into_private, read_private_lib, askLLM
import random
from collections import defaultdict
MAP_SIZE = 9

# 这是一段用 DeepSeek-R1 增强的 Player.

class Player:
    def __init__(self):
        self.index = None
        self.role = None
        self.map = None
        self.memory = set()
        self.trusted_evil = set()
        self.team_history = []
        self.vote_history = defaultdict(list)
        self.mission_results = []
        self.trusted_good = set()
        self.assassination_target = None
        self.suspicion_level = defaultdict(int)
        self.players = [1, 2, 3, 4, 5, 6, 7]
        self.player_positions = {}

    def set_player_index(self, index: int):
        self.index = index

    def set_role_type(self, role_type: str):
        self.role = role_type
        if self.role == "Merlin":
            write_into_private(f"我是梅林。")
        elif self.role in {"Oberon", "Assassin", "Morgana"}:
            write_into_private(f"我是邪恶阵营。")

    def pass_role_sight(self, role_sight: dict[str, int]):
        self.sight = role_sight
        if self.role == "Merlin":
            self.trusted_evil.update(role_sight.values())
        elif self.role == "Morgana":
            self.trusted_evil.update(role_sight.values())

    def pass_map(self, game_map):
        self.map = game_map

    def pass_position_data(self, player_positions: dict[int,tuple]):
        self.player_positions = player_positions

    def pass_message(self, content: tuple[int, str]):
        """消息处理：动态更新信任模型"""
        speaker, msg = content
        self.memory.add(content)
        
        # 分析可疑发言模式
        if "trust" in msg.lower() and "not" in msg.lower():
            mentioned_players = [int(w[1:]) for w in msg.split() if w.startswith("P")]
            for p in mentioned_players:
                self.suspicion_level[p] += 1 if p != speaker else 0
                self.suspicion_level[speaker] += 0.5  # 标记评价他人的玩家

        # 检测矛盾陈述
        if any((msg.lower().count(keyword) > 1 for keyword in ["但", "可能", "好像"])):
            self.suspicion_level[speaker] += 2

        # 记录投票模式异常
        if "approve" in msg.lower() and self.vote_history.get(speaker, [0])[-3:].count(False) > 1:
            self.suspicion_level[speaker] += 3

    def walk(self) -> tuple:

        origin_pos = self.player_positions[self.index] # tuple
        x, y = origin_pos
        others_pos = [self.player_positions[i] for i in range(1,8) if i != self.index]
        total_step = random.randint(0,3)

        # 被包围的情况,开始前判定一次即可
        if (((x-1,y) in others_pos or x == 0) 
            and ((x+1,y) in others_pos or x == MAP_SIZE - 1)
            and ((x,y-1) in others_pos or y == 0)
            and ((x,y+1) in others_pos or y == MAP_SIZE - 1)):
            total_step = 0
        
        valid_moves = []
        step = 0
        while step < total_step:
            direction = random.choice(["Left", "Up", "Right", "Down"])

            if direction == "Up" and x > 0 and (x - 1, y) not in others_pos:
                x, y = x - 1, y
                valid_moves.append("Up")
                step += 1
            elif direction == "Down" and x < MAP_SIZE - 1 and (x + 1, y) not in others_pos:
                x, y = x + 1, y
                valid_moves.append("Down")
                step += 1
            elif direction == "Left" and y > 0 and (x, y - 1) not in others_pos:
                x, y = x, y - 1
                valid_moves.append("Left")
                step += 1
            elif direction == "Right" and y < MAP_SIZE - 1 and (x, y + 1) not in others_pos:
                x, y = x, y + 1
                valid_moves.append("Right")
                step += 1
        
        return tuple(valid_moves)

    def say(self) -> str:
        what_deepseek_says = askLLM("随便生成一句90字以内的玩7人《阿瓦隆》游戏时可能说的话。只给出话，不要别的信息。")
        return what_deepseek_says

    def _generate_smart_param(self, template: str, current_round: int) -> str:
        """根据上下文生成智能参数"""
        if "可疑成员" in template:
            evil_in_team = len([p for p in self.team_history[-1] if p in self.trusted_evil])
            return str(max(1, evil_in_team))
        if "成功任务" in template:
            success_count = sum(self.mission_results)
            return str(success_count if success_count >0 else 3)
        return str(random.randint(1, current_round))

    def pass_mission_members(self, leader: int, mission_members: list):
        self.team_history.append(mission_members)

    def decide_mission_member(self, team_size: int) -> list:
        """动态组队策略"""
        candidates = []
        current_round = len(self.team_history) + 1
        
        # 梅林策略：排除已知邪恶，优先信任好人
        if self.role == "Merlin":
            safe_players = [p for p in self.players if p not in self.trusted_evil]
            candidates = [self.index] + random.sample(safe_players, min(team_size-1, len(safe_players)))
        
        # 莫甘娜策略：混入邪恶成员，模仿好人行为
        elif self.role == "Morgana":
            evil_pool = [p for p in self.trusted_evil if p != self.index]
            if len(evil_pool) >= 1 and current_round >= 3:  # 后期增加破坏概率
                candidates = [self.index] + random.sample(evil_pool, 1)
                candidates += random.sample(self.players, team_size-len(candidates))
            else:
                candidates = random.sample(self.players, team_size)
        
        # 刺客策略：主动加入队伍伺机破坏
        elif self.role == "Assassin":
            candidates = [self.index]
            candidates += random.sample([p for p in self.players if p != self.index], team_size-1)
        
        # 默认策略：信任历史清白玩家
        else:
            clean_players = [p for p in self.players 
                           if sum(self.vote_history.get(p, [])) / max(len(self.vote_history[p]), 1) > 0.5]
            candidates = [self.index] if self.role not in ["Oberon"] else []
            candidates += random.sample(clean_players, min(team_size-len(candidates), len(clean_players)))

        candidates = list(set(candidates))
        while len(candidates) < team_size:
            r = random.randint(1, 7)
            if r not in candidates:
                candidates.append(r)
        
        return candidates[:team_size]

    def mission_vote1(self) -> bool:
        """第一阶段投票策略"""
        current_team = self.team_history[-1] if self.team_history else []
        
        # 邪恶阵营：根据破坏需要决定
        if self.role in {"Morgana", "Assassin", "Oberon"}:
            evil_count = len([p for p in current_team if p in self.trusted_evil])
            if self.index in current_team:
                return True
            return random.random() < 0.7 if evil_count > 0 else random.random() < 0.3
        
        # 好人阵营：分析可疑程度
        suspicion_score = sum(self.suspicion_level[p] for p in current_team)
        team_trust = 1 - (suspicion_score / (len(current_team) * 10))
        return random.random() < (0.6 + team_trust * 0.3)

    def mission_vote2(self) -> bool:
        """任务执行阶段策略"""
        # 好人永远成功，邪恶动态破坏
        if self.role in {"Morgana", "Assassin"}:
                return False if random.random() < 0.8 else True  # 80%概率破坏
        return True

    def assass(self) -> int:
        """刺杀策略：分析梅林特征"""
        candidate_scores = defaultdict(int)
        
        # 分析特征：1) 长期支持成功队伍 2) 组队排除可疑玩家
        for i, (team, result) in enumerate(zip(self.team_history, self.mission_results)):
            for p in team:
                if result:
                    candidate_scores[p] += 2 if p != self.index else 0
                else:
                    candidate_scores[p] -= 1
        
        # 排除已知邪恶阵营
        for evil in self.trusted_evil:
            candidate_scores.pop(evil, None)
        
        # 选择最符合梅林特征的目标
        if candidate_scores:
            max_score = max(candidate_scores.values())
            candidates = [p for p, s in candidate_scores.items() if s == max_score]
            return random.choice(candidates)
        return random.choice([p for p in self.players if p != self.index])

```  

- **注意事项**：所有方法名、参数及返回类型务必与规范一致。对战平台网页上提供了定义这些函数的模板，可以直接调用。

---

## import限制


- **重要**：目前我们只开放了以下包的 import 权限：

    - `re`
    - `random`
    - `collections`
    - `game.avalon_game_helper`

- 建议完全按照以下示例代码导入 Python 库：

```python
import random
import re
import collections
from game.avalon_game_helper import (
    askLLM, read_public_lib,
    read_private_lib, write_into_private
)
```
