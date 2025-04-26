#  Tuvalon 阿瓦隆游戏系统 - 接口说明文档

## `POST /start_game`

启动一组阿瓦隆游戏并返回游戏运行的统计信息与详细结果。

### 请求体（JSON）

#### 以下是对局所需参数：

| **参数名**      | **类型** | **必填** | **说明**                                               |
| ------------ | ------ | ------ | ---------------------------------------------------- |
| mode         | string | 是      | 游戏模式，可选值：basic_test、smart_test、mixed_test、qualifying |
| games        | int    | 是      | 需要运行的游戏场数                                            |
| player_codes | object | 否      | 玩家策略代码，键为玩家编号（1~7），值为 Python 脚本代码字符串。未提供者将用默认 AI 补全。 |          

#### 请求体示例：

```json
{
  "mode": "mixed_test",
  "games": 3,
  "player_codes": {
    "1": "def decide_mission_member(...): ...",
    "2": "def decide_mission_member(...): ..."
  }
}
```

#### 注意事项:

- player_codes 是可选字段，若缺失或不完整，当`mode`为`basic_test`, `mixed_test`, `smart_test`时将由系统自动补全剩余 AI； `mode`为`qualifying`时则会导致游戏错误。
- 所有玩家编号应为字符串（例如 "1" 至 "7"），不得重复或超出范围。
- 每段代码必须为完整有效的 Python 脚本，系统将以字符串形式读取与执行。