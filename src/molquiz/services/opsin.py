from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import httpx


@dataclass(slots=True)
class OpsinResult:
    status: str
    smiles: str | None = None
    stdinchikey: str | None = None
    inchi: str | None = None
    message: str | None = None


class OpsinClient:
    def __init__(self, base_url: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def healthcheck(self) -> bool:
        response = await self._client.get(f"{self.base_url}/health")
        return response.status_code == 200

    async def parse_name(self, name: str) -> OpsinResult | None:
        encoded = quote(name, safe="")
        response = await self._client.get(f"{self.base_url}/parse/{encoded}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        return OpsinResult(
            status=payload.get("status", "FAILURE"),
            smiles=payload.get("smiles"),
            stdinchikey=payload.get("stdinchikey"),
            inchi=payload.get("inchi"),
            message=payload.get("message"),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
