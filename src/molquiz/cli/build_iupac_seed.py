from __future__ import annotations

import gzip
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import typer
import yaml
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from molquiz.services.translator_ru import looks_like_supported_ru_iupac, translate_iupac_en_to_ru

app = typer.Typer(add_completion=False, help="Build a curated IUPAC seed from PubChem bulk extras.")

CID_IUPAC_URL = "https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/Extras/CID-IUPAC.gz"
CID_SMILES_URL = "https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/Extras/CID-SMILES.gz"
ALLOWED_ATOMS = {6, 7, 8, 9, 17, 35, 53}
BLACKLIST_FRAGMENTS = {
    "azanium",
    "phosphate",
    "phosph",
    "sulf",
    "purin",
    "pyrid",
    "piper",
    "imid",
    "indol",
    "quin",
    "diaza",
    "triaza",
    "tetraaza",
    "oxa",
    "thia",
    "spiro",
    "ylidene",
    "ylidyn",
    "cyclopenta[",
    "phenanthren",
    "naphth",
    "acen",
    "anthrac",
    "bor",
    "sil",
    "sel",
    "tell",
}


@dataclass(slots=True)
class CandidateEntry:
    cid: int
    canonical_smiles: str
    iupac_en: str
    iupac_ru: str


def _iter_tsv(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "MolQuiz/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        with gzip.GzipFile(fileobj=response) as gz:
            for raw_line in gz:
                line = raw_line.decode("utf-8").rstrip("\n")
                if not line:
                    continue
                cid_text, value = line.split("\t", 1)
                yield int(cid_text), value


def _iter_bulk_rows():
    iupac_iter = _iter_tsv(CID_IUPAC_URL)
    smiles_iter = _iter_tsv(CID_SMILES_URL)

    current_iupac = next(iupac_iter, None)
    current_smiles = next(smiles_iter, None)

    while current_iupac is not None and current_smiles is not None:
        iupac_cid, iupac_name = current_iupac
        smiles_cid, smiles = current_smiles

        if iupac_cid == smiles_cid:
            yield iupac_cid, iupac_name, smiles
            current_iupac = next(iupac_iter, None)
            current_smiles = next(smiles_iter, None)
        elif iupac_cid < smiles_cid:
            current_iupac = next(iupac_iter, None)
        else:
            current_smiles = next(smiles_iter, None)


def _is_supported_name(name: str) -> bool:
    lowered = name.lower().strip()
    if any(fragment in lowered for fragment in BLACKLIST_FRAGMENTS):
        return False
    if any(char in lowered for char in "[]{};"):
        return False
    return looks_like_supported_ru_iupac(lowered)


def _is_supported_structure(smiles: str) -> bool:
    if "." in smiles or any(marker in smiles for marker in ("@", "/", "\\")):
        return False
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return False
    if molecule.GetNumHeavyAtoms() < 2 or molecule.GetNumHeavyAtoms() > 24:
        return False
    if any(atom.GetAtomicNum() not in ALLOWED_ATOMS for atom in molecule.GetAtoms()):
        return False
    if any(atom.GetFormalCharge() != 0 for atom in molecule.GetAtoms()):
        return False
    if rdMolDescriptors.CalcNumRings(molecule) > 2:
        return False
    if rdMolDescriptors.CalcNumAromaticRings(molecule) > 1:
        return False
    hetero_atoms = sum(1 for atom in molecule.GetAtoms() if atom.GetAtomicNum() not in (1, 6))
    if hetero_atoms > 4:
        return False
    return True


def _build_entry(cid: int, name: str, smiles: str) -> CandidateEntry | None:
    if not _is_supported_structure(smiles):
        return None

    lowered_name = name.lower().strip()
    if not _is_supported_name(lowered_name):
        return None

    ru_name = translate_iupac_en_to_ru(lowered_name)
    if any("a" <= character <= "z" for character in ru_name):
        return None

    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return None

    canonical_smiles = Chem.MolToSmiles(molecule, canonical=True)
    return CandidateEntry(
        cid=cid,
        canonical_smiles=canonical_smiles,
        iupac_en=lowered_name,
        iupac_ru=ru_name,
    )


def _write_yaml(entries: list[CandidateEntry], output: Path) -> None:
    payload = {
        "entries": [
            {
                "canonical_smiles": entry.canonical_smiles,
                "source_ref": f"pubchem:cid:{entry.cid}",
                "names": {
                    "iupac": {
                        "en": [entry.iupac_en],
                        "ru": [entry.iupac_ru],
                    }
                },
            }
            for entry in entries
        ]
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


@app.command()
def build(
    output: Path = Path("data/iupac_curated.yaml"),
    target_count: int = 2200,
    max_scanned: int = 250000,
) -> None:
    accepted: list[CandidateEntry] = []
    seen_inchikeys: set[str] = set()

    scanned = 0
    for cid, name, smiles in _iter_bulk_rows():
        scanned += 1
        if scanned > max_scanned:
            break

        entry = _build_entry(cid, name, smiles)
        if entry is None:
            continue

        molecule = Chem.MolFromSmiles(entry.canonical_smiles)
        if molecule is None:
            continue
        inchikey = Chem.MolToInchiKey(molecule)
        if inchikey in seen_inchikeys:
            continue
        seen_inchikeys.add(inchikey)
        accepted.append(entry)

        if len(accepted) >= target_count:
            break

    if len(accepted) < target_count:
        raise typer.Exit(
            code=1,
        )

    _write_yaml(accepted, output)
    typer.echo(f"Built IUPAC seed: {len(accepted)} entries -> {output}")


def main() -> None:
    app()
