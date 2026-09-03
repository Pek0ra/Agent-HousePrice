from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api.routes import router
from app.config import settings


async def add_json_utf8_charset(request: Request, call_next) -> Response:
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if (
        content_type.lower().startswith("application/json")
        and "charset=" not in content_type.lower()
    ):
        response.headers["content-type"] = f"{content_type}; charset=utf-8"
    return response


def create_app() -> FastAPI:
    application = FastAPI(
        title="House Price Agent Service",
        version="0.1.0",
        description="一线城市房价智能问数 Agent 服务",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.middleware("http")(add_json_utf8_charset)
    application.include_router(router)
    return application


app = create_app()
