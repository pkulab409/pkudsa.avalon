# 或者在您的Flask应用初始化文件中
from blueprints.game import game_bp

# 注册蓝图时确保没有添加URL前缀
app.register_blueprint(game_bp)  # 正确
# app.register_blueprint(game_bp, url_prefix='/api')  # 如果是这样会导致问题
