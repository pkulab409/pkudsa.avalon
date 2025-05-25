import pstats
from pstats import SortKey

# 替换为您想分析的文件路径
p = pstats.Stats("profiler/GET.game.lobby.1748152748ms.78ms.prof")
p.strip_dirs().sort_stats(SortKey.CUMULATIVE).print_stats(30)
