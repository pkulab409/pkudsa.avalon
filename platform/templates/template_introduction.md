# 前端模板结构说明
这个文档主要介绍了平台前端的一些html布局，方便大家后续的更改和维护
## 后端关联
- 对应后端模块：`database/` 和 `blueprint/` 文件夹

## 目录结构树
```text
# templates/
├── admin/              # 管理员功能模块
│   └── dashboard.html           # 管理员面板界面      后端admin.py,admin_dashboard函数
├── ai/                 # AI管理模块                   后端ai.py
│   ├── edit.html                # AI配置编辑界面
│   ├── list.html                # 我的AI展示界面
│   └── upload.html              # AI文件上传界面
├── auth/               # 用户认证模块                  后端auth.py
│   ├── login.html               # 用户登录界面
│   └── register.html            # 用户注册界面   
├── docs/               # 文档模块                      后端docs.py
│   ├── docs.html                # 文档展示界面
│   └── elo.html                 # elo机制文档显示界面
├── errors/             # 错误处理模块
│   ├── 404.html                 # 404页面不存在界面
│   └── 500.html                 # 500服务器错误界面
├── profile/            # 个人资料模块
│   ├── battle_history.html      # 用户对战历史记录界面
│   └── profile.html             # 个人资料主界面（关联 battle_history.html 和 admin/dashboard.html）
├── visualizer/         # 对战可视化核心模块
│   ├── game_replay.html         # 对局重放界面        后端visualizer.py,game.replay函数return部分
│   └── upload.html              # 上传对局文件界面    后端visualizer.py,upload_game_json函数
│
├── base.html                    # 基础模板文件（被大部分html继承）
├── battle_completed.html        # 对战结束展示界面    后端game.py,view_battle函数末尾条件判断处
├── battle_ongoing.html          # 对战进行中界面      后端game.py,view_battle函数末尾条件判断处
├── create_battle.html           # 新对战创建界面      后端game.py,create_battle_page函数
├── error.html                   # 异常界面           后端main.py,home函数
├── index.html                   # 程序欢迎主界面
├── lobby.html                   # 游戏大厅主界面      后端game.py,lobby函数
└── ranking.html                 # 玩家排行榜界面      后端ranking.py,show_ranking函数