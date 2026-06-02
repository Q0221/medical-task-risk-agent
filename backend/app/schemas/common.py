"""通用 Pydantic 模型：统一响应结构。"""

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一接口响应结构。

    - code == 0 表示成功，其它为业务/系统错误码。
    - trace_id 由 TraceIdMiddleware 注入，便于链路排查。
    """

    code: int = Field(default=0, description="业务码，0 表示成功")
    message: str = Field(default="ok", description="结果描述")
    data: Optional[T] = Field(default=None, description="响应数据")
    trace_id: Optional[str] = Field(default=None, description="链路追踪 ID")
