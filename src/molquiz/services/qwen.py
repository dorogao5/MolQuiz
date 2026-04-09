from __future__ import annotations

import asyncio
import json
import re
import shutil
from dataclasses import dataclass

from structlog import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class QwenSuggestion:
    title: str
    suggestions: list[str]
    raw_payload: dict


class QwenHeadlessClient:
    def __init__(self, command: str | None, timeout: float = 30.0) -> None:
        self.command = command
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.command and shutil.which(self.command))

    async def suggest_ru_aliases(self, en_name: str, canonical_smiles: str) -> QwenSuggestion | None:
        if not self.enabled or not self.command:
            return None

        prompt = self._build_prompt(en_name=en_name, canonical_smiles=canonical_smiles)

        try:
            process = await asyncio.create_subprocess_exec(
                self.command,
                "-p",
                prompt,
                "--output-format",
                "json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
        except TimeoutError:
            logger.warning("qwen_prompt_timeout", command=self.command, timeout=self.timeout)
            return None
        except OSError as exc:
            logger.warning("qwen_prompt_unavailable", command=self.command, error=str(exc))
            return None

        if process.returncode != 0:
            logger.warning(
                "qwen_prompt_failed",
                command=self.command,
                returncode=process.returncode,
                stderr=stderr.decode("utf-8", errors="replace").strip(),
            )
            return None

        raw_text = stdout.decode("utf-8", errors="replace").strip()
        if not raw_text:
            return None

        return self._parse_output(raw_text)

    async def aclose(self) -> None:
        return None

    def _build_prompt(self, *, en_name: str, canonical_smiles: str) -> str:
        return (
            "You are helping with offline review of Russian organic nomenclature aliases.\n"
            "Input compound:\n"
            f"- English IUPAC name: {en_name}\n"
            f"- Canonical SMILES: {canonical_smiles}\n\n"
            "Task:\n"
            "- Suggest up to 5 Russian aliases or alternative spellings that a human reviewer may want to approve.\n"
            "- Do not invent unsupported names.\n"
            "- If unsure, return an empty list.\n\n"
            'Return only compact JSON in this exact shape: {"title":"...","suggestions":["..."]}'
        )

    def _parse_output(self, raw_text: str) -> QwenSuggestion | None:
        payload = self._extract_payload(raw_text)
        if payload is None:
            suggestions = self._extract_suggestions_from_text(raw_text)
            if not suggestions:
                return None
            return QwenSuggestion(
                title="qwen_aliases",
                suggestions=suggestions,
                raw_payload={"raw_text": raw_text},
            )

        suggestions = [
            item.strip()
            for item in payload.get("suggestions", [])
            if isinstance(item, str) and item.strip()
        ]
        title = payload.get("title")
        if not isinstance(title, str) or not title.strip():
            title = "qwen_aliases"
        return QwenSuggestion(title=title, suggestions=suggestions, raw_payload=payload)

    def _extract_payload(self, raw_text: str) -> dict | None:
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            return self._extract_json_object(raw_text)

        if isinstance(parsed, dict):
            return parsed

        if isinstance(parsed, list):
            for item in reversed(parsed):
                if not isinstance(item, dict):
                    continue
                result = item.get("result")
                if isinstance(result, str):
                    extracted = self._extract_json_object(result)
                    if extracted is not None:
                        return extracted
        return None

    def _extract_json_object(self, raw_text: str) -> dict | None:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        try:
            payload = json.loads(raw_text[start : end + 1])
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _extract_suggestions_from_text(self, raw_text: str) -> list[str]:
        suggestions: list[str] = []
        for line in raw_text.splitlines():
            candidate = re.sub(r"^(?:[-*]\s+|\d+\.\s+)", "", line.strip()).strip()
            if candidate:
                suggestions.append(candidate)
        return suggestions[:5]
