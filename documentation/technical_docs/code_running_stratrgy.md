# 调用用户提交代码的策略

*dmcnczy 25/4/15*

- 用户提交一个python文件代码，必须包含以下函数：

```python
# 用户提交的代码必须包含以下函数

def get_role_type(role_type: str):  # 拿到角色
    pass

def get_role_info(role_info: dict):  # 拿到信息
    pass

def get_map(map: list):  # 获取地图
    pass

def listen(content: dict):  # 收听信息
	pass

def choose_mission_operators(number: int) -> list:  # 选择队员
    pass

def walk() -> int:  # 走步
    pass

def say() -> str:  # 发言
    pass

def mission_vote1() -> bool:  # 第一轮投票
    pass

def mission_vote2() -> bool:  # 第二轮投票
    pass

```

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
    elif ...  # 奇特角色略去


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