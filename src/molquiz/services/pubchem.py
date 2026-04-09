from __future__ import annotations

from dataclasses import dataclass

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass(slots=True)
class PubChemCompound:
    cid: int
    iupac_name: str
    canonical_smiles: str
    molecular_formula: str
    inchikey: str


class PubChemClient:
    def __init__(self, base_url: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    @retry(wait=wait_exponential(min=1, max=8), stop=stop_after_attempt(3))
    async def fetch_properties(self, cids: list[int]) -> list[PubChemCompound]:
        cid_payload = ",".join(str(cid) for cid in cids)
        url = (
            f"{self.base_url}/compound/cid/{cid_payload}/property/"
            "IUPACName,CanonicalSMILES,MolecularFormula,InChIKey/JSON"
        )
        response = await self._client.get(url)
        response.raise_for_status()
        payload = response.json()
        records = payload.get("PropertyTable", {}).get("Properties", [])
        compounds: list[PubChemCompound] = []
        for record in records:
            if not record.get("IUPACName") or not record.get("CanonicalSMILES"):
                continue
            compounds.append(
                PubChemCompound(
                    cid=int(record["CID"]),
                    iupac_name=record["IUPACName"],
                    canonical_smiles=record["CanonicalSMILES"],
                    molecular_formula=record["MolecularFormula"],
                    inchikey=record["InChIKey"],
                )
            )
        return compounds

    async def aclose(self) -> None:
        await self._client.aclose()
