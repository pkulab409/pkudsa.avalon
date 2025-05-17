# 前端模板结构说明
这个文档主要介绍了前端的一些html布局，方便大家后续的更改和维护
## 后端关联
- 对应后端模块：`database/` 和 `blueprint/` 文件夹

## 目录结构树
```text
# templates/
├── admin/              # 管理员功能模块
│   └── dashboard.html  # 管理员控制面板前端界面
├── ai/                 # AI管理模块
│   ├── edit.html       # AI配置编辑界面
│   ├── list.html       # AI列表展示界面
│   └── upload.html     # AI文件上传界面（核心功能）
├── auth/               # 用户认证模块
│   ├── login.html      # 用户登录界面
│   └── register.html   # 用户注册界面
├── docs/               # 文档模块
│   └── docs.html       # 项目文档展示界面
├── errors/             # 错误处理模块
│   ├── 404.html        # 404页面不存在错误界面
│   └── 500.html        # 500服务器错误界面
├── profile/            # 个人资料模块（通过右上角导航栏访问）
│   ├── battle_history.html   # 用户对战历史记录界面
│   └── profile.html          # 个人资料主界面（关联 battle_history.html 和 admin/dashboard.html）
└── visualizer/         # 对战可视化核心模块
    ├── base.html       # 基础模板文件（被大部分html继承）
    ├── battle_completed.html    # 对战结束展示界面
    ├── battle_ongoing.html      # 实时对战展示界面
    ├── create_battle.html       # 新对战创建界面
    ├── error.html               # 对战异常处理界面
    ├── index.html               # 程序欢迎主界面
    ├── lobby.html               # 游戏大厅主界面
    └── ranking.html             # 玩家排行榜界面