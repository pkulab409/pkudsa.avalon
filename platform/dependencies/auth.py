from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from fastapi.responses import RedirectResponse
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def verify_session(request: Request) -> str:
    """
    验证会话并返回用户名
    作为auth_dependency传递给gr.mount_gradio_app
    """
    if "session" not in request.scope:
        logging.error(
            f"verify_session: SessionMiddleware在路径 {request.url.path} 上未激活!"
        )
        return None

    username = request.session.get("username")
    if not username:
        logging.warning(f"verify_session: 路径 {request.url.path} 无有效会话")
        return None

    return username


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        if request.url.path.startswith("/gradio"):
            if "session" not in request.scope:
                logging.error(
                    f"AuthMiddleware: 路径 {request.url.path} 的SessionMiddleware未激活!"
                )
                return RedirectResponse(
                    url="/auth?error=session_config", status_code=status.HTTP_302_FOUND
                )

            username = request.session.get("username")
            if not username:
                logging.warning(
                    f"AuthMiddleware: 路径 {request.url.path} 无会话用户名，重定向到/auth"
                )
                return RedirectResponse(url="/auth", status_code=status.HTTP_302_FOUND)

        response = await call_next(request)
        return response
