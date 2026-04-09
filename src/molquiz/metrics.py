from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

attempts_total = Counter(
    "molquiz_attempts_total",
    "Total answer attempts processed.",
    labelnames=("mode", "verdict"),
)
cards_issued_total = Counter(
    "molquiz_cards_issued_total",
    "Total practice cards issued.",
    labelnames=("mode", "repeat_errors"),
)
webhook_updates_total = Counter(
    "molquiz_webhook_updates_total",
    "Total Telegram webhook updates received.",
)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
