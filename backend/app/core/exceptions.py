"""业务异常基类：业务层抛出 BizException 由全局处理器统一封装。"""

from typing import Any, Optional


class BizException(Exception):
    """业务异常基类。

    属性:
        code: 业务错误码（非 0）。
        message: 错误说明。
        data: 额外上下文数据，可选。
    """

    def __init__(
        self,
        message: str = "business error",
        code: int = 1000,
        data: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
