# 调用用户提交代码的策略

*dmcnczy 25/4/17*

- 用户提交一个python文件代码，必须包含`Player`类，其必须包含以下方法：

**务必注意**：以下所有的方法均由服务器调用：当每回合的所需信息已经向你的玩家类(的实例)传递完毕后，你的玩家类就可以开始进行分析计算。当然，你也可以等到服务器调用请求相关数据（如：发言，投票，选人等）的方法时再计算。

```python
# 以下为服务器主动行为

def set_player_index(index: int):  # 为玩家设置编号
    pass

def set_role_type(role_type: str):  # 为玩家设置角色
    pass

def pass_role_sight(role_info: dict[str, int]):  # 向玩家传递角色特有的信息（即，某些其他玩家的身份）以键值对{身份: 编号}形式给出
    pass

def pass_map(map: list[list[str]]):  # 向玩家传递当前地图的拷贝
    pass

def pass_message(content: tuple[int, str]):  # 向玩家传递其他玩家的发言，以元组(发言人编号, 发言内容)形式给出
    pass

def pass_mission_members(leader: int, members: list[int]):  # 向玩家传递当前轮次队长和队员信息
    pass

# 以下为玩家主动行为（仍为服务器端主动调用）

def mission_member(number: int) -> list[int]:  # 选择队员
    pass

def walk() -> tuple:  # 走步，若内核调用后玩家返回('Up', 'Right', 'Down')，即为玩家试图向上、向右再向下行进。传递长度小于3的元组视为放弃步数。
    pass

def say() -> str:  # 发言
    pass

def mission_vote1() -> bool:  # 第一轮投票（公投表决）
    pass

def mission_vote2() -> bool:  # 第二轮投票（任务执行）
    pass

```

- 此外，用户还可以自行调用LLM、公有库以及私有库的API（此处仅提供函数名称，供用户使用）：

```python
import avalon_game_helper as helper
import re

# 调用LLM
llm_reply = helper.askLLM(f"根据以下对话和任务结果，你觉得谁最可能是梅林？只返回数字编号。")
supposed_merlin = int(re.findall(r'\d+', llm_reply)[0])  # 从回答中匹配数字

# 读取公有库
public_lib_content = helper.read_public_lib()

# 读取私有库
private_lib_content = helper.read_private_lib()

# 写入私有库
helper.write_into_private("123 321 1234567")

```

---

- 按照游戏规则，服务器端可以先后调用以下代码（仅做示例，错误之处直接改正即可）：

```python
# 导入用户封装好的代码
from ??? import player1, player2, ..., player7
players = (None, player1, player2, ..., player7)


# 随机分配角色
roles = random.shuffle(["Merlin", "Percival", "Knight", "Knight", "Morgana", "Assassin", "Oberon"])
roles_distributed = {}
for i in range(7):
    players[i + 1].get_role_type(roles[i])  # 玩家获知自己角色
    roles_distributed[i + 1] = roles[i]  # 服务器记录角色信息


# 夜晚阶段，角色互认，以梅林知道所有红方玩家为例
for player_index in range(1, 8):
    if roles_distributed[i] == "Merlin":
        merlin_info = {}
        for j in range(1, 8):
            if j != player_index and roles_distributed[j] in ["Morgana", "Assassin", "Oberon"]:
                merlin_info[j] = "red"
        players[player_index].get_role_info(merlin_info)
    elif ...  # 其他角色略去


# 第一次队长选择队员
captain_index = random.randint(1, 7)
operators = players[captain_index].choose_mission_operators(2)


# 轮流发言
speaker_index = captain_index
for _ in range(7):
    speech_content = players[speaker_index].say()  # 调用说话函数
    save_speech_content_to_library(speech_content)  # 保存到公共库
    for i in [j for j in range(1, 8) if j != i]:  # 别的玩家听到他说话
        players[i].listen({speaker_index: speech_content})
    speaker_index = 1 if speaker_index == 7 else speaker_index + 1

# 其他步骤略去…

```

- 相应地，服务器也需要定义好上述`avalon_game_helper`中的函数，并且**指定好公有库、私有库中数据存放格式（例如 [格式规范](./io/reference/io_standard.md) ）**。 （这件事情也需要大家统一确定好~）

```python
def askLLM(prompt: str) -> str:
    pass

def read_public_lib():
    pass


# 关于private lib还需要做的事情是在服务器端判断是哪位玩家发起的read和write

def read_private_lib():
    pass

def write_into_private(content):
    pass

```
---
## 样例代码的编写：
*Yimisda 25/04/18*
### 说明
1. 样例代码只是对于用户提交代码要求的简单实现和细化，给出角色的通用模型和基本需求。
2. 不同角色的代码应加入经典算法和推理策略来满足角色的个性定位。
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

    def get_role_type(self, role_type: str):
        self.role = role_type

    def get_role_info(self, role_info: dict):
      '''
      该函数是系统在夜晚阶段传入的“我方可识别敌方信息”，
      例如：梅林会得到“红方玩家编号”的列表或字典。
      注意：
      1.红方角色根本不会获得任何此类信息，不要误用。
      2.对于派西维尔，看到应该是梅林和莫甘娜的混合试图，
      不应该加入`suspect`
      '''
        self.role_info = role_info
        self.suspects.update(role_info.keys())

    def get_map(self, map_data: list):
        self.map = map_data

    def listen(self, content: dict):
        for pid, speech in content.items():
            self.memory["speech"].setdefault(pid, []).append(speech)
            if "任务失败" in speech or "破坏" in speech:
                self.suspects.add(pid)  # 简化的推理：谁喊破坏谁可疑

    def choose_mission_operators(self, number: int) -> list[int]:
        """
        选择任务队员：
        - 自己一定上
        - 优先选择不在嫌疑列表的人
        """
        candidates = [i for i in range(1, 8) if i != self.index and i not in self.suspects]
        random.shuffle(candidates)
        chosen = [self.index] + candidates[:number - 1]
        return chosen[:number]

    def get_mission_operators_info(self, content: dict):
        self.last_captain = content.get("captain") # 储存本轮将执行任务的队员编号列表
        self.last_team = content.get("operators", []) # 储存本轮的队长编号
        self.is_chosen = self.index in self.last_team # 是否被选为任务执行者
        self.memory.setdefault("team_history", []).append({
        "round": len(self.memory.get("team_history", [])) + 1,
        "captain": self.last_captain,
        "team": self.last_team.copy(),
        "included_me": self.is_chosen
        }) # 记录历史队伍和队长，用于后续的推理

    def walk(self) -> list[str]:
        return [f"Player {self.index} walked."]

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
            return "这轮信息太混乱，我还在观察。""

    def mission_vote1(self, operators: list[int]) -> bool:
        """
        投票策略：
        - 如果队伍中全是可信玩家则通过
        - 否则按概率通过
        """
        if all(pid not in self.suspects for pid in operators):
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

