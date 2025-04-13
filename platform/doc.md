## 代码对战平台 - 技术文档

### 1. 概述

本项目是一个基于 Web 的代码对战平台，允许用户注册、登录、管理自己的代码（策略），并与其他用户或预设的 Baseline AI 进行对战。平台还提供天梯排名系统。

### 2. 技术栈

*   **后端框架:** FastAPI (`main.py`) - 用于处理 API 请求、认证和挂载 Gradio 应用。
*   **UI 框架:** Gradio (`ui/main_app.py`, `ui/auth_app.py`) - 用于快速构建交互式 Web 用户界面。
*   **数据库:** TinyDB (`db/database.py`) - 一个轻量级的文档型数据库，用于存储用户信息、代码和对战记录。数据文件存储在 data 目录下。
*   **编程语言:** Python 3
*   **依赖管理:** 通过 requirements.txt 文件管理。
*   **可视化:** Matplotlib (`game/visualizer.py`) - 用于生成对战过程和统计数据的图表。
*   **Web 服务器:** Uvicorn (`main.py`) - 用于运行 FastAPI 应用。

### 3. 项目结构

```
.
├── main.py             # FastAPI 应用入口，挂载 Gradio 应用
├── requirements.txt    # 项目依赖
├── TODO                # 待办事项列表
├── data/               # 存储 TinyDB 数据库文件 (users.json, codes.json, duels.json)
├── db/
│   └── database.py     # 提供数据库连接获取函数
├── dependencies/
│   └── auth.py         # 认证相关的依赖和中间件
├── game/               # 游戏核心逻辑
│   ├── __init__.py
│   ├── baselines.py    # 预设的 AI 对手代码
│   ├── referee.py      # 执行玩家代码和单回合对战逻辑
│   ├── rules.py        # 定义游戏规则 (石头剪刀布)
│   └── visualizer.py   # 生成对战可视化图表
├── services/           # 业务逻辑层
│   ├── code_service.py # 代码管理相关服务
│   ├── duel_service.py # 对战相关服务 (匹配、执行、记录)
│   └── user_service.py # 用户管理相关服务 (注册、登录、资料)
└── ui/                 # Gradio UI 组件
    ├── auth_app.py     # 认证 (登录/注册) 界面
    ├── main_app.py     # 主应用界面 (包含多个 Tab)
    └── components/     # 主应用各 Tab 的具体实现
        ├── __init__.py
        ├── code_tab.py
        ├── duel_tab.py
        ├── ladder_tab.py
        └── user_tab.py
```

### 4. 核心模块与流程

#### 4.1 认证流程

1.  用户访问根路径 `/` 或 `/gradio` 时，如果未登录，会被重定向到 `/auth` (`dependencies/auth.py` 中的 `AuthMiddleware`)。
2.  `/auth` 路径挂载了 auth_app.py 定义的 Gradio 应用，提供登录和注册界面。
3.  **注册:** 用户在注册 Tab 输入信息，点击注册按钮调用 `services.user_service.register_user` 函数。
4.  **登录:**
    *   用户在登录 Tab 输入凭据。
    *   前端 JavaScript (`ui/auth_app.py` 中的 HTML) 捕获登录按钮点击事件，向 FastAPI 后端 `/api/login` (`main.py`) 发送 POST 请求。
    *   `/api/login` 接口调用 `services.user_service.verify_user` 验证凭据。
    *   验证成功后，在服务器端设置 Session (`main.py`)，包含用户名。
    *   前端 JavaScript 根据 API 响应结果，显示成功或失败信息，并在成功时延迟跳转到 `/gradio`。
5.  访问 `/gradio` 路径时，`auth_dependency` (`dependencies.auth.verify_session`) 会检查 Session 是否有效，无效则拒绝访问。

#### 4.2 主应用界面 (`ui/main_app.py`)

*   使用 Gradio 的 `Blocks` 和 `Tabs` 构建。
*   包含四个主要 Tab：用户中心、代码管理、对战中心、天梯排名。
*   每个 Tab 的内容由 components 下对应的模块创建函数生成 (e.g., `create_user_tab`)。
*   页面加载和 Tab 切换时会调用 `get_username` 函数更新右下角的状态指示器。

#### 4.3 代码管理 (`ui/components/code_tab.py`, `services/code_service.py`)

*   允许用户新建、查看、编辑和调试自己的 Python 代码策略。
*   提供代码模板 (`services.code_service.get_code_templates`)。
*   代码保存/加载通过 `services.code_service` 中的函数与 `data/codes.json` 交互。
*   代码调试使用 `services.code_service.execute_code_safely` 在受限环境中执行代码，并捕获输出。

#### 4.4 对战中心 (`ui/components/duel_tab.py`, `services/duel_service.py`)

*   **测试对战:** 用户选择自己的代码和 Baseline 对手，调用 `services.duel_service.start_test_duel`。该函数获取代码内容，调用 `game.referee.run_single_round` 执行对战，保存记录，并返回结果和可视化图表 (`game.visualizer.create_moves_visualization`)。
*   **天梯对战:** 用户选择自己的代码，调用 `services.duel_service.join_ladder_duel`。
    *   请求被添加到全局队列 `duel_queue` (受 `queue_lock` 保护)。
    *   如果队列中有两个不同用户的请求，则将它们匹配并移出队列。
    *   调用 `services.duel_service.conduct_ladder_duel` 执行对战。
    *   `conduct_ladder_duel` 获取双方代码，调用 `game.referee.run_single_round` 执行，根据结果调用 `services.user_service.update_user_points` 更新双方积分，保存对战记录，并返回结果。
*   **对战记录:** 用户可以查看历史对战记录列表 (`services.duel_service.get_duel_records`)，选择某条记录后，调用 `services.duel_service.get_duel_details` 获取详细信息和对战可视化。

#### 4.5 用户中心与天梯排名 (`ui/components/user_tab.py`, `ui/components/ladder_tab.py`)

*   **用户中心:** 显示当前登录用户的个人资料（用户名、积分、分区），通过调用 `services.user_service.get_user_profile` 获取数据，并使用 Matplotlib 生成积分可视化图表。
*   **天梯排名:** 从 `data/users.json` 加载所有用户数据，按积分排序后以 Markdown 表格显示。同时使用 Matplotlib 生成各分区用户数量的统计图表。

#### 4.6 游戏逻辑 (game 目录)

*   `game.rules.determine_winner`: 根据双方出招（"rock", "paper", "scissors"）判断单回合胜负。
*   `game.referee.execute_player_code`: 在受限环境中执行单份玩家代码，获取其 `play_game()` 函数的返回值。**注意：当前的 `exec` 实现存在安全风险。**
*   `game.referee.run_single_round`: 协调单回合对战，调用 `execute_player_code` 获取双方出招，然后调用 `determine_winner` 判定结果。
*   `game.baselines.get_all_baseline_codes`: 提供预设的 AI 对手代码。
*   `game.visualizer.create_moves_visualization`: 使用 Matplotlib 生成展示双方出招和结果的简单图表。

### 5. 数据存储 (`db/database.py`)

*   使用 TinyDB 将数据存储在 data 目录下的 JSON 文件中：
    *   `users.json`: 存储用户信息（用户名、密码（明文存储，**不安全**）、积分、分区）。
    *   `codes.json`: 存储用户代码（用户名、代码名称、代码内容）。
    *   `duels.json`: 存储对战记录（对战类型、双方信息、出招、结果、时间戳、过程）。
*   提供 `get_user_db()`, `get_code_db()`, `get_duel_db()` 函数来获取相应的 TinyDB 实例。

### 6. 待办事项与改进点 (`TODO`)

*   修复登录后无法自动跳转的问题。
*   优化 UI 交互，减少冗余控件。
*   数据库方案过于简单，生产环境应考虑更健壮的数据库（如 PostgreSQL, MySQL）并对密码进行哈希存储。
*   完善游戏可视化和裁判逻辑，增强代码执行的安全性（使用沙箱）。