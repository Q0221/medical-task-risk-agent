"""统一响应辅助 + 全局异常处理器 + trace_id 中间件。"""

import uuid
from typing import Any, Optional

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.exceptions import BizException
from app.core.logger import get_logger

logger = get_logger(__name__)

TRACE_ID_HEADER = "X-Trace-Id"


def _envelope(
    code: int,
    message: str,
    data: Any = None,
    trace_id: Optional[str] = None,
) -> dict:
    return {
        "code": code,
        "message": message,
        "data": data,
        "trace_id": trace_id,
    }


def success(data: Any = None, message: str = "ok") -> dict:
    """构造成功响应体（业务层直接 return 即可）。"""
    return _envelope(code=0, message=message, data=data)


def fail(code: int = 1000, message: str = "error", data: Any = None) -> dict:
    """构造失败响应体。"""
    return _envelope(code=code, message=message, data=data)


class TraceIdMiddleware(BaseHTTPMiddleware):
    """为每个请求生成或透传 trace_id，写入 request.state 与响应头。"""

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get(TRACE_ID_HEADER) or uuid.uuid4().hex
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers[TRACE_ID_HEADER] = trace_id
        return response


def _get_trace_id(request: Request) -> Optional[str]:
    return getattr(request.state, "trace_id", None)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器，统一返回 ApiResponse 结构。"""

    @app.exception_handler(BizException)
    async def _biz_handler(request: Request, exc: BizException) -> JSONResponse:
        logger.warning("BizException: code=%s msg=%s", exc.code, exc.message)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=_envelope(
                code=exc.code,
                message=exc.message,
                data=exc.data,
                trace_id=_get_trace_id(request),
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope(
                code=4220,
                message="request validation failed",
                data=jsonable_encoder(exc.errors()),
                trace_id=_get_trace_id(request),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(
                code=exc.status_code,
                message=str(exc.detail),
                trace_id=_get_trace_id(request),
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope(
                code=5000,
                message="internal server error",
                trace_id=_get_trace_id(request),
            ),
        )
