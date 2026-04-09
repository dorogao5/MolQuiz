from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(slots=True)
class QwenSuggestion:
    title: str
    suggestions: list[str]
    raw_payload: dict


class QwenHeadlessClient:
    def __init__(self, base_url: str | None, oauth_token: str | None, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.oauth_token = oauth_token
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.oauth_token)

    async def suggest_ru_aliases(self, en_name: str, canonical_smiles: str) -> QwenSuggestion | None:
        if not self.enabled:
            return None

        response = await self._client.post(
            f"{self.base_url}/v1/suggest",
            headers={"Authorization": f"Bearer {self.oauth_token}"},
            json={
                "task": "ru_iupac_alias_review",
                "input": {"en_name": en_name, "canonical_smiles": canonical_smiles},
            },
        )
        response.raise_for_status()
        payload = response.json()
        suggestions = payload.get("suggestions") or []
        return QwenSuggestion(title=payload.get("title", "qwen_aliases"), suggestions=suggestions, raw_payload=payload)

    async def aclose(self) -> None:
        await self._client.aclose()
