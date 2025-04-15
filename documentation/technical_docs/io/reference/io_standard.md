# 输入输出格式规范

## 1. 游戏初始化

玩家角色分配和游戏设置。这部分无直接输出，主要用于初始化游戏状态。
##### 输入

```JSON
{
  "players": [
    {"id": 1, "name": "player1", "role": "Merlin"},
    {"id": 2, "name": "player2", "role": "Knight"},
    {"id": 3, "name": "player3", "role": "Knight"},
    {"id": 4, "name": "player4", "role": "Percival"},
    {"id": 5, "name": "player5", "role": "Morgana"},
    {"id": 6, "name": "player6", "role": "Assassin"},
    {"id": 7, "name": "player7", "role": "Oberon"}
  ],
  "game_settings": {
    "rounds": 5,
    "max_players_per_mission": 3,
    "mission_attempts": 3
  }
}
```

##### 输出

```JSON
{
  "game_state": "initialized",
  "round": 1,
  "players": [
    {"id": 1, "role": "Merlin", "status": "alive"},
    {"id": 2, "role": "Knight", "status": "alive"},
    {"id": 3, "role": "Knight", "status": "alive"},
    {"id": 4, "role": "Percival", "status": "alive"},
    {"id": 5, "role": "Morgana", "status": "alive"},
    {"id": 6, "role": "Assassin", "status": "alive"},
    {"id": 7, "role": "Oberon", "status": "alive"}
  ]
}
```

## 2. 任务
### 2.1 组队环节
#### **2.1.1 一般情况**
##### 输入

```JSON
{
  "round": 1,
  "leader_id": 2,
  "team_size": 2,
  "proposed_team": [2, 3],
  "include_self": true
}
```

##### 输出

```JSON
{
  "round": 1,
  "leader_id": 2,
  "team_size": 2,
  "proposed_team": [2, 3],
  "result": "team_proposal_accepted"
}
```

#### 2.1.2 特殊情况（连续三次否决后）
##### 输入

```JSON
{
  "round": 4,
  "forced_execution": true,
  "leader_id": 2,
  "forced_team": [2, 3, 4, 5]
}
```
##### 输出

```JSON
{
  "round": 4,
  "forced_execution": true,
  "leader_id": 2,
  "forced_team": [2, 3, 4, 5],
  "result": "forced_team_accepted"
}
```

### 2.2 发言环节

每轮任务公投前，按顺时针顺序进行发言。
##### 输入

```JSON
{
  "round": 2,
  "pre_vote_speech": [
    {
      "player_id": 1,
      "speech_type": "mission_proposal",
      "speech_content": "I think we should send players 2, 3, and 4 on this mission. They're trustworthy.",
      "reasoning": "These players have shown consistent behavior and seem to be good candidates."
    },
    {
      "player_id": 2,
      "speech_type": "mission_proposal",
      "speech_content": "I agree with player 1, but I want to keep an eye on player 7. They’ve been acting suspicious.",
      "reasoning": "Player 7 has been avoiding some key decisions. Not sure if they're evil or good."
    },
    // 其他玩家发言...
  ]
}
```

##### 输出

```JSON
{
  "round": 2,
  "pre_vote_speech_result": [
    {
      "player_id": 1,
      "speech_type": "mission_proposal",
      "speech_content": "I think we should send players 2, 3, and 4 on this mission. They're trustworthy.",
      "reasoning": "These players have shown consistent behavior and seem to be good candidates."
    },
    {
      "player_id": 2,
      "speech_type": "mission_proposal",
      "speech_content": "I agree with player 1, but I want to keep an eye on player 7. They’ve been acting suspicious.",
      "reasoning": "Player 7 has been avoiding some key decisions. Not sure if they're evil or good."
    },
    // 其他玩家发言...
  ],
  "result": "speech_complete"
}
```

### 2.3 公投环节

所有玩家投票，决定是否批准本次任务。
##### 输入

```JSON
{
  "round": 1,
  "mission_proposal": [
    {"player_id": 1, "vote": "approve"},
    {"player_id": 2, "vote": "approve"},
    {"player_id": 3, "vote": "reject"},
    {"player_id": 4, "vote": "approve"},
    {"player_id": 5, "vote": "reject"},
    {"player_id": 6, "vote": "approve"},
    {"player_id": 7, "vote": "approve"}
  ]
}
```

##### 输出

```JSON
{
  "round": 1,
  "mission_proposal": [
    {"player_id": 1, "vote": "approve"},
    {"player_id": 2, "vote": "approve"},
    {"player_id": 3, "vote": "reject"},
    {"player_id": 4, "vote": "approve"},
    {"player_id": 5, "vote": "reject"},
    {"player_id": 6, "vote": "approve"},
    {"player_id": 7, "vote": "approve"}
  ],
  "approval_count": 4,
  "rejection_count": 3,
  "result": "approved"
}
```

### 2.4 匿名投票环节

任务执行后，所有队员匿名投票，决定任务是否成功。蓝方只能投“成功票”，红方可以选择“失败票”来破坏任务。
##### 输入

```JSON
{
  "round": 1,
  "mission_result": {
    "success_votes": [2, 3],
    "failure_votes": [4],
    "result": "success"
  }
}
```

#### **输出：**

```JSON
{
  "round": 1,
  "mission_result": {
    "success_votes": [2, 3],
    "failure_votes": [4],
    "result": "success"
  }
}
```

## 3. 刺杀环节

##### 输入

```JSON
{
  "round": 5,
  "assassin_attempt": {
    "assassin_id": 6,
    "target_id": 1,
    "success": true
  }
}
```

##### 输出

```JSON
{
  "round": 5,
  "assassin_attempt": {
    "assassin_id": 6,
    "target_id": 1,
    "success": true
  }
}
```

## 4. 游戏结果

游戏结束后输出最终胜利阵营和每个玩家的状态。
##### 输入

```JSON
{
  "game_result": {
    "winning_faction": "evil",
    "final_players_status": [
      {"player_id": 1, "role": "Merlin", "status": "dead"},
      {"player_id": 2, "role": "Knight", "status": "alive"},
      {"player_id": 3, "role": "Knight", "status": "alive"},
      {"player_id": 4, "role": "Percival", "status": "alive"},
      {"player_id": 5, "role": "Morgana", "status": "alive"},
      {"player_id": 6, "role": "Assassin", "status": "alive"},
      {"player_id": 7, "role": "Oberon", "status": "alive"}
    ]
  }
}
```

##### 输出

```JSON
{
  "game_result": {
    "winning_faction": "evil",
    "final_players_status": [
      {"player_id": 1, "role": "Merlin", "status": "dead"},
      {"player_id": 2, "role": "Knight", "status": "alive"},
      {"player_id": 3, "role": "Knight", "status": "alive"},
      {"player_id": 4, "role": "Percival", "status": "alive"},
      {"player_id": 5, "role": "Morgana", "status": "alive"},
      {"player_id": 6, "role": "Assassin", "status": "alive"},
      {"player_id": 7, "role": "Oberon", "status": "alive"}
    ]
  }
}
```
