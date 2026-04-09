from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps


@dataclass(slots=True)
class DepictionArtifact:
    image_bytes: bytes
    image_hash: str
    formula: str
    descriptors: dict


class DepictionService:
    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.depictions_dir = storage_dir / "depictions"
        self.depictions_dir.mkdir(parents=True, exist_ok=True)

    def _build_molecule(self, smiles: str):
        from rdkit import Chem
        from rdkit.Chem import AllChem

        molecule = Chem.MolFromSmiles(smiles)
        if molecule is None:
            raise ValueError(f"Invalid SMILES: {smiles}")
        AllChem.Compute2DCoords(molecule)
        return molecule

    def compute_descriptor_snapshot(self, smiles: str) -> tuple[str, dict]:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors
        from rdkit.Chem.rdmolops import GetDistanceMatrix

        molecule = self._build_molecule(smiles)
        formula = rdMolDescriptors.CalcMolFormula(molecule)
        hetero_atoms = sum(1 for atom in molecule.GetAtoms() if atom.GetAtomicNum() not in (1, 6))
        ring_count = rdMolDescriptors.CalcNumRings(molecule)
        aromatic_ring_count = rdMolDescriptors.CalcNumAromaticRings(molecule)
        substituent_count = sum(1 for atom in molecule.GetAtoms() if atom.GetDegree() > 2)
        matrix = GetDistanceMatrix(molecule)
        longest_path = int(max(matrix.flatten())) + 1 if matrix.size else molecule.GetNumAtoms()

        functional_groups = []
        patterns = {
            "спирт": "[OX2H]",
            "амин": "[NX3;H2,H1;!$(NC=O)]",
            "карбоновая кислота": "C(=O)[OX2H1]",
            "эфир": "[OD2]([#6])[#6]",
            "галогенпроизводное": "[F,Cl,Br,I]",
        }
        for label, smarts in patterns.items():
            pattern = Chem.MolFromSmarts(smarts)
            if pattern and molecule.HasSubstructMatch(pattern):
                functional_groups.append(label)

        topic_tags = []
        if aromatic_ring_count:
            topic_tags.append("aromatic")
        if ring_count and not aromatic_ring_count:
            topic_tags.append("cyclo")
        if molecule.GetNumBonds() > 0 and any(bond.GetBondTypeAsDouble() == 2 for bond in molecule.GetBonds()):
            topic_tags.append("alkene")
        if any(atom.GetAtomicNum() == 7 for atom in molecule.GetAtoms()):
            topic_tags.append("nitrogen")
        if any(atom.GetAtomicNum() == 8 for atom in molecule.GetAtoms()):
            topic_tags.append("oxygen")
        if any(atom.GetAtomicNum() in {9, 17, 35, 53} for atom in molecule.GetAtoms()):
            topic_tags.append("halogen")

        difficulty_score = 1
        difficulty_score += min(2, substituent_count)
        difficulty_score += min(1, ring_count)
        difficulty_score += min(1, aromatic_ring_count)
        difficulty_score += min(1, len(functional_groups))
        difficulty = max(1, min(5, difficulty_score))

        descriptors = {
            "formula_weight": round(Descriptors.MolWt(molecule), 3),
            "heavy_atom_count": molecule.GetNumHeavyAtoms(),
            "hetero_atoms": hetero_atoms,
            "ring_count": ring_count,
            "aromatic_ring_count": aromatic_ring_count,
            "substituent_count": substituent_count,
            "longest_chain": longest_path,
            "functional_groups": functional_groups,
            "topic_tags": sorted(set(topic_tags)),
            "difficulty": difficulty,
        }
        return formula, descriptors

    def render_png(self, smiles: str, *, rotation: int = 0, flip_x: bool = False) -> bytes:
        from rdkit.Chem.Draw import rdMolDraw2D

        molecule = self._build_molecule(smiles)
        drawer = rdMolDraw2D.MolDraw2DCairo(900, 600)
        options = drawer.drawOptions()
        options.addStereoAnnotation = False
        options.bondLineWidth = 2
        options.clearBackground = False
        rdMolDraw2D.PrepareAndDrawMolecule(drawer, molecule)
        drawer.FinishDrawing()
        png = drawer.GetDrawingText()

        image = Image.open(BytesIO(png)).convert("RGB")
        if flip_x:
            image = ImageOps.mirror(image)
        if rotation:
            image = image.rotate(rotation, expand=True, fillcolor="white")
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    def build_artifact(self, smiles: str, *, rotation: int = 0, flip_x: bool = False) -> DepictionArtifact:
        formula, descriptors = self.compute_descriptor_snapshot(smiles)
        image_bytes = self.render_png(smiles, rotation=rotation, flip_x=flip_x)
        return DepictionArtifact(
            image_bytes=image_bytes,
            image_hash=hashlib.sha256(image_bytes).hexdigest(),
            formula=formula,
            descriptors=descriptors,
        )

    def persist_artifact(self, molecule_id: str, artifact: DepictionArtifact, variant_label: str) -> Path:
        path = self.depictions_dir / molecule_id / f"{variant_label}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(artifact.image_bytes)
        return path
