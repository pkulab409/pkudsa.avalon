# 🤖 AI 提交规范（v0.1）

欢迎参赛者将你们的阿瓦隆 AI 上传至平台！

请按照本指南打包并提交你的代码，平台将自动验证、导入、并用于比赛对局。

---

## 📁 提交格式：zip 压缩包

请提交一个 zip 压缩包，内部目录结构如下所示：

```
team_rationalwolf_ai.zip
	└── team_rationalwolf/
		├── strategy.py
		├── __init__.py
		└── requirements.txt  （可选）

- zip 包文件名建议为：`team_xxx_ai.zip`
- 内部顶层目录名称必须与你填写的队伍名一致！
```

---
## 🧠 策略类实现要求

你提交的 `strategy.py` 文件中，必须定义一个名为 `MyStrategy` 的类，并实现以下方法：

```python
class MyStrategy:
    def propose_team(self, game_info):
        ...

    def vote_team(self, game_info):
        ...

    def perform_mission(self, game_info):
        ...

    def guess_merlin(self, game_info):
        ...
```

平台将通过如下方式导入并调用你的策略：

```
from ai_submissions.team_rationalwolf.strategy import MyStrategy

ai = MyStrategy()
ai.propose_team(game_info)
```


---
## 📤 提交方式（网页端）


**访问比赛平台主页，在「AI提交区」上传你的 zip 包：**

- 拖拽或点击上传
    
- 填写队伍名（需与 zip 包内文件夹名一致）
    
- 点击提交按钮
    

**平台将在后台自动：**

1. 解压并保存代码
    
2. 校验目录结构
    
3. 尝试导入并运行策略类（进行一局测试）
    

---

## 🛠 常见问题

- ❌ 没有 `__init__.py` 文件 → 无法导入模块
    
- ❌ 类名写错（不是 MyStrategy） → 无法识别
    
- ❌ 函数接口缺失 → 比赛运行时报错
    
- ✅ 提交后如需修改，可以重新上传（历史版本将被保存）
    

---

## 📮 联系我们

如有疑问，可联系技术组。

---
