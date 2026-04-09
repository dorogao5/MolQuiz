from __future__ import annotations

from fastapi import FastAPI, HTTPException
from py2opsin import OPSIN

app = FastAPI(title="MolQuiz OPSIN sidecar")
opsin = OPSIN()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/parse/{chemical_name:path}")
async def parse_name(chemical_name: str) -> dict:
    try:
        result = opsin.parse(chemical_name)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not result:
        raise HTTPException(status_code=404, detail="Name was not parsed")

    return {
        "status": "SUCCESS",
        "smiles": getattr(result, "smiles", None),
        "stdinchikey": getattr(result, "stdinchikey", None),
        "inchi": getattr(result, "inchi", None),
    }

