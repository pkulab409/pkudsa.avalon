# Interface Optimizing - 中世纪风格对局回放 - 说明

> dmcnczy 25/5/26

### 📚中世纪风格对局回放

- **HTML 文件**：在 `templates/visualizer/medieval_style_replay_page.html`

- **CSS 样式文件**：在 `static/css/medieval.css`

- **一些图片补充**：在 `static/images`

### 🖥沉浸式对局回放

先不揭示玩家身份，通过不断点按“下一步”按钮，对局信息逐步出现，最后揭晓玩家身份

- **HTML 文件**: 在 `templates/visualizer/game_reveal.html`

### 🪙对局重放的新增 & 修复

**\[NOTE\] 改动了 `game/visualizer.py`**

- 实现了地图同步聊天容器滚动位置更新

- 实现了对局重放页面用户名显示

- 修复对局重放中提议队伍被拒绝、重新选择队长无法显示的问题

- 实现聊天框中显示玩家移动

- 实现监听聊天滚动，联动地图

（`medieval_style_replay_page.html` 、 `game_reveal.html` 、 和 `game_replay.html` 均实现）

### ✅待上传的角色卡片

- **梅林**： `static/images/merlin.jpg`

- **派西维尔**： `static/images/percival.jpg`

- **莫甘娜**： `static/images/morgana.jpg`

- **刺客**： `static/images/assassin.jpg`

- **奥伯伦**： `static/images/oberon.jpg`

- **骑士1**： `static/images/knight1.jpg`

- **骑士2**： `static/images/knight2.jpg`
