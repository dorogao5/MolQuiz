from __future__ import annotations

from pathlib import Path

import pytest_asyncio

from molquiz.db.session import create_engine, create_schema, create_session_factory


@pytest_asyncio.fixture()
async def session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path}/molquiz.db")
    await create_schema(engine)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()
