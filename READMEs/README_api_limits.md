# API 调用限制

（此文档既面向用户，也面向开发者）

---

## **API调用限制**

#### **1. LLM调用 (`askLLM`)**

- 玩家通过从avalon_game_helper.py中调用`askLLM`函数进行AI辅助对战

- **【调用次数】**

  - 每轮最多调用三次（**请注意：含【刺杀】的轮次，在调用 `assass()` 函数时算作同一轮内的多次调用！**）

- **【输入/输出限制】**

  - 输入提示（`prompt`）长度最多 **500 tokens** 
  - llm输出响应自动截断至 **500 tokens** 

- **【示例代码】**

  ```python
  # 调用LLM
  llm_reply = helper.askLLM(f"根据以下对话和任务结果，你觉得谁最可能是梅林？只返回数字编号。")
  supposed_merlin = int(re.findall(r'\d+', llm_reply)[0]) #从回答中匹配数字
  ```

------

#### 2.公有库读取

- 玩家通过从avalon_game_helper.py中调用`read_public_lib`函数**调用公有库**

  - 在尝试无游戏ID上下文的情况下读取游戏历史，报错，返回error提醒

  - 如果成功读取文件，返回解析后的 JSON 字典，包含游戏事件列表（键为 `"events"`）

- **【读取身份限制】**
  - 公有日志文件由裁判自动写入，**无需也不能由玩家修改！**

- **【示例代码】**

  ```
  #读取公有库
  public_lib_content = helper.read_public_lib()
  ```

------

#### 3.私有库读取/写入

- 玩家通过从avalon_game_helper.py中调用`read_private_lib`函数**读写私有库**

- **【读取私有库】**

  - 尝试在无玩家ID或游戏ID上下文的情况下读取私有日志，报错，返回error提醒

  - 如果成功读取文件，返回解析后的 JSON 字典，包含游戏事件列表（键为 `"events"`）

  - 示例代码

    ```
    #读取私有库
    private_lib_content = helper.read_private_lib()
    ```

- **【写入私有库】**

  - 玩家通过从avalon_game_helper.py中调用`write_into_private()`函数，向私有库中传入一个字符串，以时间戳+内容的形式写入JSON文件，形式如下

    ```
    {
    	"timestamp": time.time(),
    	"content": content
    }
    ```
