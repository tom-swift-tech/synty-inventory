"""Parse Synty filenames (SM_, SK_, Prop_, Sign_, Bld_, …)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PREFIX_KIND = {
    "SM": "static_mesh",
    # SIMPLE-line packs (SIMPLE_Farm_Animals) prefix meshes SA_ instead of SM_.
    "SA": "static_mesh",
    "SK": "skeleton",
    "CH": "character",
    "CHR": "character",
    "FX": "effect",
    "PF": "prefab",
    "MI": "material_instance",
    "M": "material",
    "T": "texture",
}

FAMILY_KIND = {
    "BLD": "building",
    "BUILDING": "building",
    "BUILDINGS": "building",
    "PROP": "prop",
    "ENV": "environment",
    "ENVIRONMENT": "environment",
    "VEH": "vehicle",
    "VEHICLE": "vehicle",
    "WEP": "weapon",
    "WEAPON": "weapon",
    "SIGN": "sign",
    "SIGNS": "sign",
    "CHR": "character",
    "CHARACTER": "character",
    "CHAR": "character",
    # No creature type in the v2 schema; animals are placeable characters,
    # told apart by the family (semantic detail populates_scene_as_animal).
    "ANIMAL": "character",
    "ANIMALS": "character",
    # Unprefixed rigged masters: POLYGON_Kaiju's Kaiju_0x.fbx and
    # POLYGON_Modular_Fantasy_Hero's ModularCharacter_0x prefabs.
    "KAIJU": "character",
    "MODULARCHARACTER": "character",
    "ICON": "icon",
    "GEN": "generic",
    "GENERIC": "generic",
    "FX": "effect",
}

SKIP_STEM_RE = re.compile(
    r"(?:_Convex|_Col(?:lider)?|_Collision|_LOD[1-9]|_ColMesh)$",
    re.IGNORECASE,
)
SKIP_PATH_PARTS = (
    "/collisions/",
    "/collision/",
    "/syntypackagehelper/",
    "/editor/",
    "/demosettings",
    # Pose rigs for demo scenes (Modular_Fantasy_Hero Scenes/DemoFiles/CharacterPose.fbx).
    "/demofiles/",
)
BULK_STEMS = {
    "CHARACTERS",
    # Same bulk multi-character FBX under pack-specific names.
    "ZOMBIES",
    "MODULARCHARACTERS",
    "GENERIC_CHARACTERS",
    "DEMONSTRATION",
    "POLYGON_PROTOTYPE_DEMO_STATICMESHES",
}

_VARIANT_RE = re.compile(r"_(\d{2,3}|0\d)$")
_TOKEN_SPLIT = re.compile(r"[_\-\s]+")


@dataclass
class ParsedName:
    id: str
    tokens: list[str]
    prefix: str | None
    family: str | None
    variant: str | None
    subject_tokens: list[str] = field(default_factory=list)
    kind: str = "unknown"

    @property
    def token_set(self) -> set[str]:
        return {t.lower() for t in self.tokens}


def normalize_stem(name: str) -> str:
    stem = Pathish(name)
    for ext in (".prefab", ".fbx", ".obj", ".glb", ".gltf", ".uasset", ".mesh"):
        if stem.lower().endswith(ext):
            stem = stem[: -len(ext)]
    return stem


def Pathish(name: str) -> str:
    return name.replace("\\", "/").rsplit("/", 1)[-1]


def should_skip(rel_path: str, stem: str) -> bool:
    low = rel_path.replace("\\", "/").lower()
    if any(part in low for part in SKIP_PATH_PARTS):
        return True
    if SKIP_STEM_RE.search(stem):
        return True
    if stem.upper() in BULK_STEMS:
        return True
    return False


_UNITY_DUP_TOKEN_RE = re.compile(r"^\(\d+\)$")


def parse_name(raw: str) -> ParsedName:
    stem = normalize_stem(raw)
    # Drop Unity duplicate-name suffixes like '(1)' so tags stay snake_case.
    parts = [p for p in _TOKEN_SPLIT.split(stem) if p and not _UNITY_DUP_TOKEN_RE.fullmatch(p)]
    prefix = None
    family = None
    kind = "unknown"
    rest = list(parts)

    if rest and rest[0].upper() in PREFIX_KIND:
        prefix = rest[0].upper()
        kind = PREFIX_KIND[prefix]
        rest = rest[1:]

    if rest and rest[0].upper() in FAMILY_KIND:
        family = rest[0].upper()
        fam_kind = FAMILY_KIND[family]
        if kind in {"unknown", "static_mesh", "prefab"}:
            kind = fam_kind
        rest = rest[1:]
    elif rest and rest[0].upper() == "POLYGONPROTOTYPE" and len(rest) > 1:
        family = rest[1].upper()
        kind = FAMILY_KIND.get(family, "prototype")
        rest = rest[2:]

    variant = None
    subject = list(rest)
    if subject and _VARIANT_RE.fullmatch("_" + subject[-1]):
        variant = subject[-1]
        subject = subject[:-1]
    elif subject and subject[-1].isdigit() and len(subject[-1]) <= 3:
        variant = subject[-1]
        subject = subject[:-1]

    # SM_Sign_* has family already consumed; SM_Prop_Sign_* keeps Sign in subject
    if "SIGN" in {t.upper() for t in subject} or family == "SIGN":
        if kind in {"unknown", "static_mesh", "prop"}:
            kind = "sign"

    return ParsedName(
        id=stem,
        tokens=parts,
        prefix=prefix,
        family=family,
        variant=variant,
        subject_tokens=subject,
        kind=kind,
    )


def title_from_tokens(tokens: list[str]) -> str:
    special = {
        "XXX": "XXX",
        "ATM": "ATM",
        "FX": "FX",
        "UV": "UV",
        "LOD": "LOD",
        "SM": None,
        "SK": None,
        "CH": None,
        "PF": None,
    }
    words: list[str] = []
    for tok in tokens:
        key = tok.upper()
        if key in special:
            if special[key]:
                words.append(special[key])
            continue
        if tok.isdigit():
            continue
        words.append(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", tok).title())
    return " ".join(words).strip()
