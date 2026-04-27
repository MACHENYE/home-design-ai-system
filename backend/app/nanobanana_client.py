from __future__ import annotations

from typing import Any

import httpx


class NanoBananaClient:
    def __init__(self, *, base_url: str, api_key: str, timeout_s: float = 60.0):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_s = timeout_s

    def _headers(self) -> dict[str, str]:
        # Per NanoBanana docs: use `Authorization: Bearer <API_KEY>`
        return {"Authorization": f"Bearer {self._api_key}"}

    async def generate_or_edit(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.post(
                f"{self._base_url}/generate",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def generate_pro(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.post(
                f"{self._base_url}/generate-pro",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_task_details(self, task_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.get(
                f"{self._base_url}/record-info",
                params={"taskId": task_id},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

