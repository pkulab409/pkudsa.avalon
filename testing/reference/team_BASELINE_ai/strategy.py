"""
平台将通过如下方式导入并调用你的策略：

from ai_submissions.team_rationalwolf.strategy import MyStrategy

ai = MyStrategy()
ai.propose_team(game_info)

你提交的 `strategy.py` 文件中，必须定义一个名为 `MyStrategy` 的类，并实现以下方法：
"""


class MyStrategy:
    def propose_team(self, game_info): ...

    def vote_team(self, game_info): ...

    def perform_mission(self, game_info): ...

    def guess_merlin(self, game_info): ...
