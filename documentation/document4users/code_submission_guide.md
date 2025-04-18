🧭大作业对战平台 用户文档

---

# 提交代码要求

Version 0.1  Date: 25/4/18

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
    - 视具体实现可额外初始化其它缓冲或配置项。

- **示例**：
  ```python
  class Player:
      def __init__(self):
          # 基本状态
          self.index = None
          self.role = None
          # 地图
          self.map = None
          # 历史记录
          self.memory = {
              "speech": {},         # {player_index: [messages]}
              "teams": [],          # 每轮队伍信息
              "votes": [],          # 每轮投票详情
              "mission_results": [] # 任务成功/失败
          }
          # 推理辅助
          self.suspects = set()
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
**功能**：向具有视野能力的角色（如梅林、派西维尔）传递夜晚视野信息。

- **参数**：
  - `role_sight`：字典类型，键为对方角色名（如 "Morgana"），值为玩家编号。
- **返回值**：无。
- **被调用时机**：夜晚阶段，服务端向特定角色调用。
- **使用建议**：
  - 将视野信息保存在 `self.sight` 或合并到可疑玩家集合 `self.suspects`，用于后续推理。

### 4. `pass_map(self, map_data: list[list[str]])`
**功能**：传递当前游戏地图数据的深拷贝给玩家。

- **参数**：
  - `map_data`：二维列表，包含地图格子信息的字符串。
- **返回值**：无。
- **被调用时机**：每次地图更新时调用。
- **使用建议**：
  - 存储在 `self.map`，用于导航、路径规划等逻辑。

### 5. `pass_message(self, content: tuple[int, str])`
**功能**：接收其他玩家的发言内容。

- **参数**：
  - `content`：二元组 `(speaker_index, message_text)`。
- **返回值**：无。
- **被调用时机**：每当任意玩家发言后，服务端广播时调用。
- **使用建议**：
  - 将发言记录到 `self.memory["speech"]` 中；
  - 针对关键词（如“破坏”、“成功”）进行简单文本分析，标记嫌疑对象。

### 6. `pass_mission_members(self, leader: int, members: list[int])`
**功能**：告知本轮任务队长及选中队员列表。

- **参数**：
  - `leader`：整数，当前轮次队长编号；
  - `members`：整数列表，包含本轮执行任务的队员编号。
- **返回值**：无。
- **被调用时机**：队长选择队员完成后调用。
- **使用建议**：
  - 保存 `self.last_leader`、`self.last_team` 并记录到历史队伍信息 `self.memory["teams"]`；
  - 检查自身是否在队伍中，以便在 `mission_vote2` 中区分投票逻辑。

### 7. `decide_mission_member(self, member_number: int) -> list[int]`
**功能**：由队长角色调用，选择本轮任务的执行成员。

- **参数**：
  - `member_number`：整数，所需队员人数。
- **返回值**：整数列表，长度等于 `member_number`。
- **被调用时机**：轮到自己担任队长时。
- **使用建议**：
  - 必须包含 `self.index`；
  - 优先排除在可疑集合中的玩家或根据信任度排序后取前 `member_number` 人。

### 8. `walk(self) -> tuple[str, ...]`
**功能**：执行移动行为，返回一组方向指令。

- **参数**：无。
- **返回值**：字符串元组，最多包含 3 个方向（"Up"、"Down"、"Left"、"Right"）。长度小于 3 则视为放弃剩余步数。
- **被调用时机**：需要移动时，服务端依次通过内核调用。
- **使用建议**：
  - 根据当前 `self.map` 与目标位置路径规划；
  - 返回尽可能有效的路径指令序列。

### 9. `say(self) -> str`
**功能**：发言行为，返回文本内容供其他玩家接收。

- **参数**：无。
- **返回值**：字符串，玩家发言内容。
- **被调用时机**：发言轮次，服务端按顺序调用。
- **使用建议**：
  - 可结合 `helper.read_public_lib()` 获取全局对局记录，构造 `askLLM` 的提示词生成发言；
  - 将重要推理写入私有存储，如 `helper.write_into_private()`，便于后续阅读。

### 10. `mission_vote1(self) -> bool`
**功能**：对队长提案进行公投，决定是否通过队伍。

- **参数**：无。
- **返回值**：布尔值，`True` 表示同意，`False` 表示否决。
- **被调用时机**：每轮队长提案完成后。
- **使用建议**：
  - 若队伍完全由信任玩家组成，返回 `True`；
  - 否则可按照风险度或概率方式投出 `True` 或 `False`。

### 11. `mission_vote2(self) -> bool`
**功能**：在任务执行阶段决定任务结果。

- **参数**：无。
- **返回值**：布尔值，`True` 表示任务成功（蓝方），`False` 表示破坏（红方）。
- **被调用时机**：任务成员确定后。
- **使用建议**：
  - 红方角色（"Assassin","Morgana","Oberon"）应返回 `False`；
  - 蓝方角色必须返回 `True`；
  - 或可结合混淆策略，增加不可预测性。

### 12. `assass(self) -> int`
**功能**：红方失败时刺杀操作，选择目标玩家编号。

- **参数**：无。
- **返回值**：整数，被刺杀玩家编号。
- **被调用时机**：所有任务完成且红方未获胜时。只有身份是刺客的玩家才会被调用。
- **使用建议**：
  - 按照前期推理结果（`self.suspects` 或私有存储记录）选择最可能为梅林的玩家；
  - 写入私有日志，便于赛后复盘。


## 可调用的辅助 API

服务器为大家提供了辅助 API 工具包，用户可以通过下面语句导入：

```python
import avalon_game_helper as helper
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
  response = helper.askLLM("推测当前玩家的阵营是？")
  ```

---

### 2. `read_public_lib() -> list[dict]`
**功能**：读取所有玩家可见的公共对局记录库，包含全局对战信息。

- **返回值**：
  - `list[dict]`: 返回一个字典列表，每个字典表示一条对局记录。  

- **调用示例**：
  ```python
  history = helper.read_public_lib()
  ```

### 3. `read_private_lib() -> dict`
**功能**：读取仅对当前玩家可见的私有存储数据。

- **返回值**：
  - `dict`: 返回私有存储的完整内容。

- **调用示例**：
  ```python
  private_data = helper.read_private_lib()
  ```

### 4. `write_into_private(content: str) -> None`
**功能**：向当前玩家的私有存储中追加写入内容。

- **参数**：
  - `content` (str): 需要保存的文本内容（建议使用 JSON 格式以确保可解析性）。

- **调用示例**：
  ```python
  helper.write_into_private('{"suspects": ["player3", "player5"]}')
  ```

请根据需要在策略中调用，记录、分析对局数据。


## 服务器调用流程概览

1. **模块导入**：服务端 import 玩家代码模块，并实例化 1~7 号玩家 `Player` 对象。
2. **分配角色**：随机分配角色并调用 `set_role_type`。
3. **夜晚阶段**：根据角色不同，调用 `pass_role_sight` 等方法传递身份信息。
4. **队伍选择**：每轮随机或按规则确定队长，调用 `decide_mission_member` 获取队员。
5. **发言/移动轮次**：按顺序调用 `say`，广播每段发言并通过 `pass_message` 通知能收听到发言的其他玩家；按顺序调用 `walk` 实现玩家移动。
6. **投票与任务**：分别调用 `mission_vote1`、`mission_vote2`，记录投票结果。
7. **刺杀阶段**：游戏结束后，若红方失败触发刺杀，调用 `assass` 选择目标。


## 示例代码

以下为简化样例，供初次接入参考：

```python
import random
import re
from avalon_game_helper import askLLM, read_public_lib, read_private_lib, write_into_private

class Player:
    def __init__(self, player_index: int):
        self.index = player_index
        self.role = None
        self.role_info = {}
        self.map = None
        self.memory = {
            "speech": {},         # {player_index: [utterance1, utterance2, ...]}
            "votes": [],          # [(operators, {pid: vote})]
            "mission_results": [] # [True, False, ...]
        }
        self.teammates = set()   # 推测的可信玩家编号
        self.suspects = set()    # 推测的红方编号

    def set_role_type(self, role_type: str):
        self.role = role_type

    def set_role_info(self, role_sight: dict[str, int]):
        '''
        该函数是系统在夜晚阶段传入的“我方可识别敌方信息”，
        例如：梅林会得到“红方玩家编号”的列表或字典。
        注意：
        1.红方角色根本不会获得任何此类信息，不要误用。
        2.对于派西维尔，看到应该是梅林和莫甘娜的混合视图，
        不应该加入`suspect`
        '''
        self.sight = role_sight
        self.suspects.update(role_sight.values())

    def pass_map(self, map_data: list[list[str]]):
        self.map = map_data

    def pass_message(self, content: tuple[int, str]):
        player_id, speech = content:
        self.memory["speech"].setdefault(player_id, []).append(speech)
        if "任务失败" in speech or "破坏" in speech:
            self.suspects.add(player_id)  # 简化的推理：谁喊破坏谁可疑

    def decide_mission_member(self, member_number: int) -> list[int]:
        """
        选择任务队员：
        - 自己一定上
        - 优先选择不在嫌疑列表的人
        """
        candidates = [i for i in range(1, 8) if i != self.index and i not in self.suspects]
        random.shuffle(candidates)
        chosen = [self.index] + candidates[:member_number - 1]
        return chosen[:member_number]

    def pass_mission_members(self, leader: int, members: list[int]):
        self.last_leader = leader # 储存本轮的队长编号
        self.last_team = members # 储存本轮将执行任务的队员编号列表
        self.is_chosen = self.index in self.last_team # 是否被选为任务执行者
        self.memory.setdefault("team_history", []).append({
            "round": len(self.memory.get("team_history", [])) + 1,
            "leader": self.last_leader,
            "team": self.last_team.copy(),
            "included_me": self.is_chosen
        })
        # 记录历史队伍和队长，用于后续的推理

    def walk(self) -> tuple:
        """
        TODO 现在就是随便走
        """
        return "Left", "Up", "Right"

    def say(self) -> str:
        # 使用大模型来判断谁最可能是梅林，演示自然语言+正则+推理
        try:
            full_history = read_public_lib() # 读取公有库：每轮队伍、队长信息+玩家发言记录+投票和任务执行结果等
            prompt = f"根据以下对话和任务结果，你觉得谁最可能是梅林？只返回数字编号。\n{full_history}"
            reply = askLLM(prompt)
            match = re.findall(r'\b[1-7]\b', reply) # 使用正则表达式提取LLM回复中的第一个数字编号（可以优化）
            if not match:
                return "我还在观察。"
            merlin_id = int(match[0])  
            write_into_private(f"round_say: suspect_merlin={merlin_id}") # 写入私有库，记录这轮判断

            if merlin_id == self.index:
                return f"我觉得我知道谁是梅林，但我不方便多说。"
            else:
                return f"我怀疑{merlin_id}号是梅林，理由稍后详谈。"
        except Exception as e:
            write_into_private(f"round_say_error: {str(e)}")
            return "这轮信息太混乱，我还在观察。"

    def mission_vote1(self) -> bool:
        """
        投票策略：
        - 如果队伍中全是可信玩家则通过
        - 否则按概率通过
        """
        if all(pid not in self.suspects for pid in self.last_team):
            return True
        return random.random() > 0.3

    def mission_vote2(self) -> bool:
        """
        执行任务投票：
        - 红方一定投False（破坏）
        - 蓝方一定True（成功）
        """
        return self.role not in ["Morgana", "Assassin", "Oberon"]

```  

- **注意事项**：所有方法名、参数及返回类型务必与规范一致。
