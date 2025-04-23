# 公有库/私有库数据存储结构

*dmcnczy 25/4/20*

该文档统一一局游戏中，公/私有库数据存储结构，并方便后续可视化网页的编写和用户调用公/私有库的指南编写。

*(应该是符合 [技术组这一次commit](https://github.com/pkulab409/pkudsa.avalon/commit/51612c215d896c82e2ef49ea5fabf979daae04fd) 所写的代码的，如有错误之处敬请改正！)*

---

**JSON**格式是公有库/私有库的数据存储格式。具体如下：

## 公有库

### 1. 游戏开始

- **游戏开始时**， `referee` 将创建该局游戏的公有库 JSON 文档，路径为 `./data/game_{GAME_ID}_public.json` 。例如一局游戏的编号是 12345，那么路径为 `./data/game_12345_public.json` 。

  - 经过初始化后，这个 JSON 文档初始的内容是一个“空列表”：

  ```json
  []
  ```

- **分配角色时**， `referee` 将对局的初始信息加入到公有库 JSON 文档中。**分配角色的结果是不能被放到公有库的，否则用户对游戏一切的一切都了如指掌。**

  - 例如，这局游戏的 game_id 是 12345，七人局，9x9 地图，那么分配角色后，规定的格式使得这个 JSON 文档将会变成这样：

  ```json
  [
    {
      "type": "game_start",
      "game_id": 12345,
      "player_count": 7,
      "map_size": 9
    }
  ]
  ```

### 2. 夜晚阶段

- 夜晚阶段非常私密，没有实质性的信息会被放到公有库中来。只有在夜晚阶段结束后，公有库会加上一句冷冰冰的记录如下：

```json
[
  {
    "type": "game_start",
    "game_id": 12345,
    "player_count": 7,
    "map_size": 9
  },
  {  // --- 以下信息将被追加 ---
    "type": "night_phase_complete"
  }
]
```

### 3. 【任务】轮次开始

- 【任务】轮次的开始，是指定该轮队长和该轮任务人数。这些信息会被放到公有库中：

```json
[
  {
    "type": "game_start",
    "game_id": 12345,
    "player_count": 7,
    "map_size": 9
  },
  {
    "type": "night_phase_complete"
  },
  {  // --- 以下信息将被追加 ---
    "type": "mission_start",
    "round": 1,  // 假定是第1轮
    "leader": 2,  // 假定是第2人当队长
    "member_count": 2  // 第一轮，任务执行需要2人
  }
]
```

### 4. 队长选人

- 假如第1轮第一次队长选人的队长是1号，并且选择了1,2号玩家作为次轮任务的执行者，那么公有库将会加入一条格式如下的记录：

```json
{
  "type": "team_proposed",
  "round": 1,
  "vote_round": 1,
  "leader": 1,
  "members": [1, 2, 3]
}
```

### 5. 第一轮发言（全图广播）

- 例如第二轮，当前队长是3号，执行完所有玩家的 `say()` 函数后，公有库添加如下记录：

```json
{
  "type": "global_speech",
  "round": 2,
  "speeches": [
    ["3", "You're lying!"],
    ["4", "You're lying!"],
    ["5", "You're lying!"],
    ["6", "You're lying!"],
    ["7", "You're lying!"],
    ["1", "You're lying!"],
    ["2", "You're lying!"]
  ]
}
```

### 6. 玩家移动

- 例如在第1轮，所有玩家完成一轮移动之后，公有库添加：

```json
{
  "type": "movement",
  "round": 1,
  "movements": [
    {
      "player_id": 1,
      "requested_moves": ["Left", "Left", "Left"],
      "executed_moves": ["Left", "Left"],  // 有效的移动
      "final_position": [1, 1]
    },
    {
      "player_id": 2,
      // ...
    },
    // ...
  ]}
```

### 7. 第二轮发言（有限听力范围）

- 游戏结束前，发言具体内容不能被加到公有库中。例如在第1轮，所有玩家完成第二轮发言之后，公有库添加：

```json
{
  "type": "limited_speech",
  "round": 1
}
```

### 8. 第一轮公投表决（是否认同队伍执行任务）

- 假如第1轮中的一次公投表决被通过（1-6号玩家投赞成，7号投出反对），那么公有库将会加入一条格式如下的记录：

```json
{
  "type": "public_vote",
  "round": 1,
  "votes": {
    "1": true,
    "2": true,
    "3": true,
    "4": true,
    "5": true,
    "6": true,
    "7": false
  },
  "approve_count": 6,
  "result": "approved"
}
```

- 假如第1轮中的第一次公投表决**未**被通过（1-2号玩家投赞成，3-7号投出反对），那么公有库将会加入一条格式如下的记录和一条轮换队长记录：

```json
{
  "type": "public_vote",
  "round": 1,
  "votes": {
    "1": true,
    "2": true,
    "3": false,
    "4": false,
    "5": false,
    "6": false,
    "7": false
  },
  "approve_count": 2,
  "result": "approved"
}
```

```json
{
  "type": "team_rejected",
  "round": 1,
  "vote_round": 1,
  "approve_count": 2,
  "next_leader": 4,
}
```

- 如第1轮中，公投遭到连续5轮否决，即将触发强制组队执行任务，公有库会在任务执行前添加一条记录：

```json
{"type": "consecutive_rejections", "round": 1}
```

### 9. 第二轮投票表决（任务是否成功）

- 假如第4轮中的投票表决**未**被通过，有3人投出失败票，那么公有库将会加入一条格式如下的记录和一条回合结果的记录：

```json
{  // 任务执行记录
  "type": "mission_execution",
  "round": 4,
  "fail_votes": 3,
  "success": false
}
```

```json
{  // 回合结果记录
  "type": "mission_result",
  "round": 4,
  "result": "fail",  // 成功："success"
  "blue_wins": 2,
  "red_wins": 2
}
```

### 10. 蓝方即将胜利、刺杀、蓝/红方胜利、游戏结束

- 假如第三轮结束后，蓝方即将胜利（红方一轮也没赢），刺客玩家（5号）选择刺杀对象为1号且刺杀成功，那么公有库将会加入一条刺杀记录和一条游戏结束记录（**此时公布玩家身份**）：

```json
{  // 刺杀记录
  "type": "assassination",
  "assassin": 5,
  "target": 1,
  "target_role": "Merlin",
  "success": true
}
```

```json
{  // 游戏结束记录
  "type": "game_end",
  "result": {
    "blue_wins": 3,
    "red_wins": 0,
    "rounds_played": 3,
    "roles": {
      "1": "Merlin",
      // ...
    },
    "public_log_file": "...",  // 文件位置
    "winner": "red",
    "win_reason": "assassination_success"
  }
}
```

- 假如第三轮结束后，蓝方即将胜利（红方一轮也没赢），刺客玩家（5号）选择刺杀对象为1号但刺杀失败，那么公有库将会加入一条刺杀记录和一条游戏结束记录（**此时公布玩家身份**）：

```json
{  // 刺杀记录
  "type": "assassination",
  "assassin": 5,
  "target": 1,
  "target_role": "Oberon",
  "success": false
}
```

```json
{  // 游戏结束记录
  "type": "game_end",
  "result": {
    "blue_wins": 3,
    "red_wins": 0,
    "rounds_played": 3,
    "roles": {
      "1": "Merlin",
      // ...
    },
    "public_log_file": "...",  // 文件位置
    "winner": "blue",
    "win_reason": "missions_complete_and_assassination_failed"
  }
}
```

- 假如第三轮结束后，红方胜利（蓝方一轮也没赢），那么公有库将会加入一条游戏结束记录（**此时公布玩家身份**）：

```json
{
  "type": "game_end",
  "result": {
    "blue_wins": 0,
    "red_wins": 3,
    "rounds_played": 3,
    "roles": {
      "1": "Merlin",
      // ...
    },
    "public_log_file": "...",  // 文件位置
    "winner": "red",
    "win_reason": "missions_failed"
  }
}
```

### \*11. 程序意外终止

- 遇到程序意外终止，**公有库的记录随即终止**，服务器程序抛出 Critical Error。

---

## 私有库

- **私有库初始化**：初始化的私有库 JSON 如下：

```json
{
  "logs": [],
  "llm_history": [{"role": "system", "content": "你是一个专家。"}]
}
```

- **给予用户的发挥空间**：用户可以将任意字符串添加到私有库 JSON 的 `logs` 字段下。

  - 例如，用户使用了如下代码向私有库中存储信息：

  ```python
  from game.avalon_game_helper import write_into_private

  write_into_private("1号玩家动机不纯。")
  write_into_private("2号玩家这轮的说话只有我能听到。他说他是梅林，坏人是5,6,7号。")
  ```

  - 此时，服务器将**在这些字符串前面贴上时间戳**，并让私有库追加这些记录：

  ```json
  {
    "logs": [
      {
        "timestamp": 1745396437.1877804,
        "content": "\u6211\u662f\u90aa\u6076\u9635\u8425\u3002"
      }
    ]
  }
  ```

- **LLM 聊天记录保留**：用户和LLM的聊天记录在私有库 JSON 的 `llm_history` 字段下。例如：

```json
{
  "logs": [
    {
      "timestamp": 1745396437.1877804,
      "content": "\u6211\u662f\u90aa\u6076\u9635\u8425\u3002"
    }
  ],
  "llm_history": [
    {
      "role": "system",
      "content": "\n\u4f60\u662f\u4e00\u4e2a\u4e13\u4e1a\u52a9\u7406\u3002\n"
    },
    {
      "role": "user",
      "content": "\u968f\u4fbf\u751f\u6210\u4e00\u53e530\u5b57\u4ee5\u5185\u7684\u73a97\u4eba\u300a\u963f\u74e6\u9686\u300b\u6e38\u620f\u65f6\u53ef\u80fd\u8bf4\u7684\u8bdd\u3002\u53ea\u7ed9\u51fa\u8bdd\uff0c\u4e0d\u8981\u522b\u7684\u4fe1\u606f\u3002"
    },
    {
      "role": "assistant",
      "content": "\"\u6d3e\u897f\u7ef4\u5c14\uff0c\u4f60\u5230\u5e95\u770b\u5230\u6885\u6797\u8fd8\u662f\u83ab\u5fb7\u96f7\u5fb7\u4e86\uff1f\u5feb\u51b3\u5b9a\u554a\uff01\""
    }
  ]
}
```

这样，用户在下一次调用LLM时，先前的聊天记录 (`context`) 会被自动导入。
