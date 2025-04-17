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
llm_reply = helper.askLLM("根据上述信息，你觉得几号玩家最有可能是梅林？直接给出结论，不要在回答中有任何其他分析过程。")
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