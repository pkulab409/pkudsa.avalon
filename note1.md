# 代码修改详细解释

您的修改是对 Avalon 游戏辅助模块的一次重要重构，主要将全局状态和函数转变为面向对象设计，并添加了线程安全机制。下面详细解释这些修改：

## 1. avalon_game_helper.py 的主要改进

### 1.1 从全局变量到面向对象

**原代码问题**：使用全局变量（`_CURRENT_PLAYER_ID`, `_GAME_SESSION_ID`, `_DATA_DIR`等）来存储游戏状态，这在多线程/多游戏环境下会导致状态混乱。

**您的改进**：
- 创建了 `GameHelper` 类封装所有功能和状态
- 将全局变量转换为类的实例属性：
  ```python
  self.current_player_id = None
  self.game_session_id = None
  self.data_dir = data_dir or os.environ.get("AVALON_DATA_DIR", "./data")
  self.current_round = None
  self.call_count_added = 0
  ```

### 1.2 引入线程本地存储机制

**改进点**：添加了线程本地存储，使每个线程拥有自己的 `GameHelper` 实例：
```python
_thread_local = threading.local()

def get_current_helper():
    """获取当前线程的 GameHelper 实例"""
    if not hasattr(_thread_local, "helper"):
        _thread_local.helper = GameHelper()
    return _thread_local.helper

def set_thread_helper(helper):
    """设置当前线程的 GameHelper 实例"""
    _thread_local.helper = helper
```

### 1.3 保持API兼容性

**改进点**：保留了原有的全局函数接口，但内部实现改为调用线程本地的实例方法：
```python
def askLLM(prompt: str) -> str:
    return get_current_helper().askLLM(prompt)

def read_private_lib() -> List[str]:
    return get_current_helper().read_private_lib()
```

## 2. referee.py 的适配修改

### 2.1 创建专属Helper实例

**改进点**：在 `AvalonReferee` 类中为每个游戏实例创建专属的 `GameHelper`：
```python
# 为这个referee创建一个专用的GameHelper实例
self.game_helper = GameHelper(data_dir=data_dir)
self.game_helper.game_session_id = game_id  # 直接设置game_id
```

### 2.2 修改上下文设置逻辑

**改进点**：在 `safe_execute` 方法中，为每个玩家代码执行设置正确的上下文：
```python
# 1. 设置referee实例的上下文
self.game_helper.set_current_context(player_id, self.game_id)

# 2. 同时设置全局默认实例的上下文 - 确保线程安全
from .avalon_game_helper import (
    set_thread_helper, set_current_context, set_current_round
)

# 将当前线程的helper设为referee的专属实例
set_thread_helper(self.game_helper)
```

### 2.3 移除对全局函数的直接依赖

**改进点**：将直接调用全局函数的代码改为使用实例方法：
```python
# 原代码
from .avalon_game_helper import reset_llm_limit
reset_llm_limit(self.current_round)

# 修改后
self.game_helper.reset_llm_limit(self.current_round)
```

## 3. 修改的关键优势

1. **线程安全**：解决了多线程环境下的竞态条件问题，每个游戏/玩家上下文独立隔离
   
2. **状态一致性**：确保了每个玩家的操作都在正确的游戏上下文中执行

3. **提高可维护性**：代码结构更清晰，通过对象封装相关功能和状态

4. **向后兼容**：保留原有的函数接口，不破坏已有的调用代码

5. **资源隔离**：不同游戏实例的数据读写不会相互干扰

这个重构是一个典型的从面向过程到面向对象的改进，同时增加了线程安全性，使代码更加健壮，特别适合在多线程服务环境中运行多个游戏实例的场景。