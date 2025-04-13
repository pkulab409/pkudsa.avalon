from fastapi import FastAPI, Request, Response, HTTPException, status, Depends
from fastapi.responses import JSONResponse, RedirectResponse
import gradio as gr
import uvicorn
from starlette.middleware.sessions import SessionMiddleware
import os
import logging

# 仅导入主应用
from ui.main_app import create_main_app

# 移除 Pydantic 模型导入，因为 /api/login 被移除

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# 创建FastAPI应用
app = FastAPI(title="代码对战平台")

# 创建Gradio应用实例
main_app_instance = create_main_app()


@app.get("/")
async def root():
    # 重定向到 Gradio 应用
    return RedirectResponse(url="/app")


@app.get("/health")
def health_check():
    return {"status": "ok"}


# --- 中间件配置 ---
# SessionMiddleware 必须在挂载 Gradio 之前添加
SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "AREHAQERTGWESHTRH54322345GWEG")
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="code_platform_session",
    max_age=86400,  # 1 day
    same_site="lax",
    https_only=False,  # 开发环境设为 False，生产环境建议 True
)

# --- 挂载 Gradio 应用 ---
# 确保在添加中间件之后挂载
app = gr.mount_gradio_app(
    app,
    main_app_instance,
    path="/app",  # 主应用路径
)


# --- 启动 ---
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8022,
        reload=True,
        workers=1,  # 开发时建议使用 workers=1 以避免重载问题
    )
