# Gunicorn生产环境配置

# 基础设置
workers = 4
worker_class = 'gevent'
bind = '0.0.0.0:5050'
timeout = 120
keepalive = 5

# 安全限制
max_requests = 1000
max_requests_jitter = 50
limit_request_line = 4094
limit_request_fields = 100

# 日志设置
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# 环境变量
raw_env = [
    'FLASK_ENV=production',
    'PYTHONDONTWRITEBYTECODE=1'
]
