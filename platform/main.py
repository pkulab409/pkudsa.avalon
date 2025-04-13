from fastapi import FastAPI, Request, Response, HTTPException, status, Depends
from fastapi.responses import JSONResponse, RedirectResponse
import gradio as gr
import uvicorn
from starlette.middleware.sessions import SessionMiddleware
import os
import logging

# 导入依赖
from dependencies.auth import verify_session, AuthMiddleware

# 导入UI应用
from ui.main_app import create_main_app
from ui.auth_app import create_auth_app

# 导入Pydantic模型
from pydantic import BaseModel

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# 创建FastAPI应用
app = FastAPI(title="代码对战平台")

# 创建Gradio应用实例
main_app = create_main_app()
auth_app = create_auth_app()


# Pydantic模型
class LoginRequest(BaseModel):
    username: str
    password: str


# API路由


@app.get("/")
async def root():
    return RedirectResponse(url="/auth")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/login")
async def api_login(login_data: LoginRequest, request: Request):
    """处理API登录请求并设置会话"""
    from services.user_service import verify_user

    logging.info(f"接收到API登录请求: {login_data.username}")

    # 检查会话中间件是否生效
    if "session" not in request.scope:
        logging.error("/api/login: SessionMiddleware未激活!")
        raise HTTPException(status_code=500, detail="会话中间件配置错误。")

    try:
        success, message = verify_user(login_data.username, login_data.password)
        if success:
            request.session["username"] = login_data.username
            logging.info(
                f"API登录成功: {login_data.username}. 会话已设置: {dict(request.session)}"
            )
            return JSONResponse(content={"success": True, "message": message})
        else:
            logging.warning(f"API登录失败: {login_data.username}. 原因: {message}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=message,
                headers={"WWW-Authenticate": "Bearer"},
            )
    except Exception as e:
        logging.error(f"API登录处理错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登录过程中发生内部服务器错误。",
        )


@app.get("/logout")
async def logout(request: Request):
    if "session" not in request.scope:
        logging.error("/logout: SessionMiddleware未激活!")
        return RedirectResponse(url="/auth", status_code=status.HTTP_302_FOUND)

    request.session.clear()
    logging.info("用户已登出，会话已清除。")
    return RedirectResponse(url="/auth", status_code=status.HTTP_302_FOUND)


# 挂载Gradio应用
app = gr.mount_gradio_app(app, auth_app, path="/auth")
app = gr.mount_gradio_app(
    app, main_app, path="/gradio", auth_dependency=verify_session  # 使用认证依赖
)

# 添加中间件
SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "AREHAQERTGWESHTRH54322345GWEG")
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="code_platform_session",
    max_age=86400,  # 1天
    same_site="lax",
    https_only=False,  # 开发环境设为False
)
app.add_middleware(AuthMiddleware)

# 启动
if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8022, reload=True, workers=4)
