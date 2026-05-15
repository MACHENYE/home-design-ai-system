from __future__ import annotations

from typing import Any

import httpx


class NanoBananaClient:  # 封装 NanoBanana 图像生成接口的异步 HTTP 调用
    def __init__(self, *, base_url: str, api_key: str, timeout_s: float = 60.0):  # 初始化对象并保存必要的连接或配置状态
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_s = timeout_s

    def _headers(self) -> dict[str, str]:  # 构造鉴权请求头，按接口要求使用 Bearer Token
        return {"Authorization": f"Bearer {self._api_key}"}

    async def generate_or_edit(self, payload: dict[str, Any]) -> dict[str, Any]:  # 调用 NanoBanana 普通生成或编辑接口
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.post(
                f"{self._base_url}/generate",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def generate_pro(self, payload: dict[str, Any]) -> dict[str, Any]:  # 调用 NanoBanana 专业生成接口
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.post(
                f"{self._base_url}/generate-pro",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_task_details(self, task_id: str) -> dict[str, Any]:  # 查询 NanoBanana 远程任务详情
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.get(
                f"{self._base_url}/record-info",
                params={"taskId": task_id},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

