"""健康检查冒烟测试。"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_healthz(async_client: AsyncClient) -> None:
    resp = await async_client.get("/api/v1/healthz")
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["data"] == {"status": "ok"}
    assert resp.headers.get("X-Trace-Id")
