from __future__ import annotations

import os
import tempfile
import uuid

from fastapi import FastAPI, HTTPException
from py2opsin import py2opsin

app = FastAPI(title="MolQuiz OPSIN sidecar")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/parse/{chemical_name:path}")
async def parse_name(chemical_name: str) -> dict:
    tmp_fpath = os.path.join(tempfile.gettempdir(), f"py2opsin_{uuid.uuid4().hex}.txt")
    try:
        smiles = py2opsin(chemical_name, output_format="SMILES", tmp_fpath=tmp_fpath)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if smiles is False or not smiles:
        raise HTTPException(status_code=404, detail="Name was not parsed")

    inchi = py2opsin(chemical_name, output_format="InChI", tmp_fpath=tmp_fpath)
    stdinchikey = py2opsin(chemical_name, output_format="StdInChIKey", tmp_fpath=tmp_fpath)

    return {
        "status": "SUCCESS",
        "smiles": smiles,
        "stdinchikey": stdinchikey if stdinchikey is not False else None,
        "inchi": inchi if inchi is not False else None,
    }

