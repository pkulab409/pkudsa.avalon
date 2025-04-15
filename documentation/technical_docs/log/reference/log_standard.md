# 日志结构规定
## 1. 公有日志结构

公有日志用于记录所有玩家的公开行为，如发言内容和投票内容等。游戏中的每轮任务或关键环节都会产生相应的日志记录。它们是所有玩家都能看到的内容，并且供 AI 或其他玩家在游戏过程中进行分析。
### 示例结构

```JSON
{
  "round": 1,  // 当前轮次
  "event": "speech",  // 当前事件类型，发言或投票等
  "timestamp": "2025-04-15T12:30:00Z",  // 事件发生的时间戳
  "players": [
    {
      "player_id": 1,  // 玩家ID
      "player_name": "player1",  // 玩家姓名
      "role": "Merlin",  // 玩家角色
      "content": "I think we should send players 2 and 3 on this mission.",  // 发言内容
      "type": "mission_proposal",  // 发言类型（如任务提议）
      "reasoning": "Player 2 and 3 are trustworthy."  // 发言理由
    },
    {
      "player_id": 2,
      "player_name": "player2",
      "role": "Knight",
      "content": "I agree with player 1's proposal, but we need to keep an eye on player 7.",
      "type": "mission_proposal",
      "reasoning": "Player 7 has been acting suspiciously."
    }
  ]
}
```

##### 说明

- **round**: 当前轮次
    
- **event**: 当前事件类型（例如发言、投票等）
    
- **timestamp**: 事件发生的时间戳
    
- **players**: 包含多个玩家的发言或投票内容。每个玩家的记录包含：
    
    - **player_id**: 玩家唯一标识符
        
    - **player_name**: 玩家姓名
        
    - **role**: 玩家角色（如梅林、骑士等）
        
    - **content**: 发言或投票内容
        
    - **type**: 发言或行为类型
        
    - **reasoning**: 发言的理由或解释
        
    

## 2. 私有日志结构

私有日志用于记录每个玩家的私人数据，例如他们的身份猜测、对其他玩家的信任程度等。该数据对其他玩家不可见。私有日志的内容用于评估算法的表现。
### 示例结构

```JSON
{
  "round": 1,  // 当前轮次
  "player_id": 1,  // 玩家ID
  "timestamp": "2025-04-15T12:30:00Z",  // 事件发生的时间戳
  "private_data": {
    "suspected_player_ids": [2, 7],  // 被怀疑的玩家ID列表
    "trust_level": {
      "2": 0.8,  // 玩家2的信任度为0.8
      "3": 0.6,  // 玩家3的信任度为0.6
      "7": 0.2   // 玩家7的信任度为0.2
    },
    "comments": "Player 2 and 3 seem to be good candidates for the mission, but player 7 is suspicious."  // 玩家对当前局势的私人评论
  }
}
```

##### 说明

- **round**: 当前轮次
    
- **player_id**: 当前记录的玩家ID
    
- **timestamp**: 事件发生的时间戳
    
- **private_data**: 包含该玩家的私人数据，内容包括：
    
    - **suspected_player_ids**: 玩家怀疑的其他玩家ID列表
        
    - **trust_level**: 对其他玩家的信任度评分（例如0到1之间）
        
    - **comments**: 玩家对当前局势的私人评论或其他分析
        
    

## 3. 日志存储与提交

- 公有日志和私有日志都应提交到服务器或平台，用于后续的数据分析。
    
- 公有日志存储在公共数据库中，供所有玩家查看并进行互动。
    
- 私有日志只能由主持人或系统管理员访问，用于后续的分析、展示分数等用途。
    

## 4. 示例日志流

- **回合1**：游戏任务按流程进行。公有日志记录每个玩家的发言和投票，私有日志记录每个玩家对其他玩家的信任度和身份猜测。

- **回合2**：新一轮游戏任务按流程进行。公有日志更新发言和投票内容，私有日志记录玩家们的身份猜测变化。
