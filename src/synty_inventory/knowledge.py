"""Rule-based Synty semantics: names -> type, tags, placement, notes.

This is the offline enrichment quality bar. Special-cased high-value
assets (signs, attachments, civic identity) match the Police Sign /
Barber Pole richness in the inventory spec.

``infer()`` has no pack context -- it only ever sees a stem -- so every
rule below is a name-pattern rule. Dispatch order (see ``infer``):

1. ``CURATED`` exact-id overrides (hand-authored quality bar).
2. Non-placeable data (``_infer_nonplaceable``): animation clips,
   character rig parts/whole skeletons, UI textures, skyboxes, FX.
3. Sci-fi ship/station kit vocabulary (vehicle parts, spacecraft,
   ``SM_Bld_*`` interior modules, space environment dressing, specific
   ``SM_Prop_*`` families, character attach points, HUD/icon/signage).
4. City-style exterior building kits (``SM_Bld_<Family>_<Role>``).
5. The original token/keyword legacy rules (signs, generic buildings,
   vehicles, environment, everything else) -- unchanged behaviour for
   every stem the newer, more specific rules don't claim.

``CURATED``, ``TOKEN_TAGS`` and ``PACK_STYLES`` load from ``data/*.json``.
Dispatch functions stay in this module.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import replace
from importlib.resources import files as pkg_files

from .naming import ParsedName, parse_name, title_from_tokens
from .schema import TYPE_MIGRATION, empty_gear, empty_module, empty_part

WALL_PLAQUE = {
    "mount": "wall",
    "height": "eye_level_to_above_door",
    "orientation": "outward_facing",
    "attachment": "back_side",
    "preferred_floors": [1, 2],
    "constraints": ["exterior_only", "attach_to_building", "do_not_cover_windows"],
    "preferred_contexts": [],
}

SIDE_POLE = {
    "mount": "wall",
    "height": "eye_level",
    "orientation": "outward_facing",
    "attachment": "side_bracket",
    "preferred_floors": [1],
    "constraints": [
        "exterior_only",
        "attach_to_building",
        "first_floor_commercial",
        "leave_sidewalk_clearance",
        "do_not_cover_windows",
    ],
    "preferred_contexts": [],
}

TRAFFIC_POLE = {
    "mount": "ground",
    "height": "driver_eye_level",
    "orientation": "roadway_facing",
    "attachment": "base_to_ground",
    "preferred_floors": [1],
    "constraints": ["exterior_only", "roadside", "do_not_block_sidewalk"],
    "preferred_contexts": ["street", "intersection"],
}

ROOFTOP_ICON = {
    "mount": "roof",
    "height": "roofline",
    "orientation": "street_facing",
    "attachment": "base_to_roof",
    "preferred_floors": [],
    "constraints": ["exterior_only", "sit_on_flat_roof", "readable_from_street"],
    "preferred_contexts": [],
}

BILLBOARD = {
    "mount": "pole_or_wall",
    "height": "elevated_roadway_view",
    "orientation": "roadway_facing",
    "attachment": "back_or_pole",
    "preferred_floors": [2, 3],
    "constraints": ["exterior_only", "roadway_view", "do_not_cover_windows"],
    "preferred_contexts": ["roadside", "commercial_strip"],
}

GROUND_PROP = {
    "mount": "ground",
    "height": "grade",
    "orientation": "upright",
    "attachment": "base_to_ground",
    "preferred_floors": [1],
    "constraints": ["sit_on_ground"],
    "preferred_contexts": [],
}

WALL_PROP = {
    "mount": "wall",
    "height": "mid_facade",
    "orientation": "outward_facing",
    "attachment": "back_side",
    "preferred_floors": [1, 2],
    "constraints": ["attach_to_building"],
    "preferred_contexts": [],
}

MODULAR_BUILDING = {
    "mount": "ground",
    "height": "grade",
    "orientation": "street_face_plus_z",
    "attachment": "base_to_ground",
    "preferred_floors": [1],
    "constraints": ["snap_to_grid", "align_to_street"],
    "preferred_contexts": [],
}

# Tables live in package data (data/*.json). Edit those files, not literals
# here. CURATED is the quality bar for a handful of POI pieces; TOKEN_TAGS
# enriches the legacy fallback path; PACK_STYLES maps pack_id -> style.


def _load_table(name: str):
    resource = pkg_files("synty_inventory").joinpath("data", name)
    try:
        return json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # missing or corrupt package data
        raise RuntimeError(
            f"synty_inventory package data {name!r} is missing or invalid ({exc}); "
            "reinstall the package"
        ) from exc


TOKEN_TAGS: dict[str, dict] = _load_table("token_tags.json")
CURATED: dict[str, dict] = _load_table("curated.json")
PACK_STYLES: dict[str, str] = _load_table("pack_styles.json")

TYPE_BY_KIND = {
    "sign": "prop/signage",
    "building": "building/module",
    "prop": "prop",
    "environment": "environment",
    "vehicle": "vehicle",
    "weapon": "weapon",
    "character": "character",
    "effect": "fx",
    "icon": "ui/icon",
    "skeleton": "character/skeleton",
    "generic": "environment",
}

DIM_HINTS = {
    "prop/signage": [1.2, 0.6, 0.12],
    "building/module": [5.0, 3.0, 5.0],
    "vehicle": [4.5, 1.6, 2.0],
    "character": [0.5, 1.8, 0.5],
    "prop": [0.6, 0.6, 0.6],
    "environment": [5.0, 0.2, 5.0],
    "weapon": [0.4, 0.15, 0.8],
    "fx": [1.0, 1.0, 1.0],
    "ui/icon": [0.3, 0.3, 0.05],
}


def pack_style(pack_id: str) -> str:
    if pack_id in PACK_STYLES:
        return PACK_STYLES[pack_id]
    low = pack_id.lower()
    if "scifi" in low and "city" in low:
        return "lowpoly_scifi_city"
    if "scifi" in low:
        return "lowpoly_scifi"
    if "city" in low:
        return "lowpoly_modern_city"
    if "prototype" in low:
        return "lowpoly_prototype"
    return "lowpoly_synty"


def _norm_token(tok: str) -> str:
    return tok.lower().replace(" ", "")


def _merge_token_knowledge(subject: list[str]) -> dict:
    tags: list[str] = []
    contexts: list[str] = []
    category: list[str] = []
    joined = "".join(_norm_token(t) for t in subject)
    keys = [_norm_token(t) for t in subject]
    # also consider bigrams (Chinese_Noodles, FireDepartment, DeliPizza)
    for i in range(len(keys) - 1):
        keys.append(keys[i] + keys[i + 1])
    keys.append(joined)
    seen: set[str] = set()
    for key in keys:
        info = TOKEN_TAGS.get(key)
        if not info:
            continue
        for t in info.get("tags", []):
            if t not in seen:
                tags.append(t)
                seen.add(t)
        for c in info.get("contexts", []):
            if c not in contexts:
                contexts.append(c)
        for cat in info.get("category", []):
            if cat not in category:
                category.append(cat)
    return {"tags": tags, "contexts": contexts, "category": category}


def _is_traffic_sign(tokens: set[str]) -> bool:
    return bool(tokens & {"giveway", "stop", "parking", "warning", "arrow", "street", "bustop", "busstop"})


def _is_large_icon(parsed: ParsedName) -> bool:
    up = {t.upper() for t in parsed.tokens}
    return "LARGESIGN" in up or (
        "LARGE" in up and "SIGN" in up
    )


def _is_billboard(tokens: set[str]) -> bool:
    return "billboard" in tokens


def _is_neon(tokens: set[str]) -> bool:
    return "neon" in tokens


def _is_attachment(tokens: set[str]) -> bool:
    return "attachment" in tokens


def _placement_for(parsed: ParsedName, extra: dict) -> dict:
    tokens = {_norm_token(t) for t in parsed.tokens}
    if _is_attachment(tokens):
        p = deepcopy(WALL_PROP)
        p["constraints"] = ["attach_to_building", "pair_with_sign_or_light"]
        p["preferred_contexts"] = ["facade_hardware"]
        return p
    if parsed.kind == "sign" or "sign" in tokens:
        if _is_large_icon(parsed):
            p = deepcopy(ROOFTOP_ICON)
        elif _is_billboard(tokens):
            p = deepcopy(BILLBOARD)
        elif _is_neon(tokens):
            p = deepcopy(WALL_PLAQUE)
            p["height"] = "upper_storey_or_over_awning"
            p["preferred_floors"] = [1, 2, 3]
        elif "barber" in tokens:
            p = deepcopy(SIDE_POLE)
        elif _is_traffic_sign(tokens):
            p = deepcopy(TRAFFIC_POLE)
        else:
            p = deepcopy(WALL_PLAQUE)
        p["preferred_contexts"] = list(extra.get("contexts") or p["preferred_contexts"])
        return p
    if parsed.kind == "building":
        p = deepcopy(MODULAR_BUILDING)
        p["preferred_contexts"] = list(extra.get("contexts") or [])
        return p
    if parsed.kind == "vehicle":
        p = deepcopy(GROUND_PROP)
        p["preferred_contexts"] = ["street", "parking"]
        p["constraints"] = ["sit_on_ground", "align_to_road"]
        return p
    if parsed.kind == "environment":
        p = deepcopy(GROUND_PROP)
        p["preferred_contexts"] = list(extra.get("contexts") or ["exterior"])
        return p
    if any(t in tokens for t in ("aircon", "satdish", "vent", "antenna")):
        p = deepcopy(ROOFTOP_ICON)
        p["preferred_contexts"] = ["roof"]
        return p
    if any(t in tokens for t in ("camera", "securitycamera", "poster", "neon")):
        return deepcopy(WALL_PROP)
    return deepcopy(GROUND_PROP)


def _semantic_role(parsed: ParsedName, extra: dict) -> str:
    tokens = {_norm_token(t) for t in parsed.tokens}
    if "sign" in tokens or parsed.kind == "sign":
        if "police" in tokens:
            return "identifies_building_as_police_station"
        if "barber" in tokens:
            return "identifies_building_as_barber_shop"
        if "hospital" in tokens:
            return "identifies_building_as_hospital"
        if "firedepartment" in tokens or ("fire" in tokens and "department" in tokens):
            return "identifies_building_as_fire_station"
        if "hotel" in tokens:
            return "identifies_building_as_hotel"
        if "cafe" in tokens:
            return "identifies_building_as_cafe"
        if "pizza" in tokens or "delipizza" in tokens:
            return "identifies_building_as_pizzeria"
        if "bar" in tokens:
            return "identifies_building_as_bar"
        if "pub" in tokens:
            return "identifies_building_as_pub"
        if "xxx" in tokens:
            return "identifies_building_as_adult_venue"
        if "noodles" in tokens or "chinese" in tokens:
            return "identifies_building_as_noodle_shop"
        if "bustop" in tokens or "busstop" in tokens:
            return "marks_bus_stop"
        if _is_traffic_sign(tokens):
            return "regulates_traffic"
        if _is_billboard(tokens) or "ad" in tokens:
            return "advertises_on_facade_or_roadside"
        if "neon" in tokens:
            return "nighttime_facade_identity"
        if _is_attachment(tokens):
            return "mounting_hardware_for_sign_or_light"
        if extra.get("contexts"):
            return f"identifies_building_as_{extra['contexts'][0]}"
        return "identifies_or_decorates_facade"
    if parsed.kind == "building":
        if extra.get("contexts"):
            return f"forms_{extra['contexts'][0]}_shell"
        return "forms_building_volume"
    if parsed.kind == "vehicle":
        return "populates_street_or_lot"
    if parsed.kind == "character":
        if parsed.family in {"ANIMAL", "ANIMALS"}:
            return "populates_scene_as_animal"
        return "populates_scene_as_person"
    if parsed.kind == "environment":
        if "road" in tokens:
            return "forms_drivable_surface"
        if "sidewalk" in tokens:
            return "forms_pedestrian_surface"
        return "dresses_exterior_ground"
    return "dresses_scene"


def _description(parsed: ParsedName, name: str, extra: dict, ptype: str) -> str:
    tokens = {_norm_token(t) for t in parsed.tokens}
    bits: list[str] = []
    if ptype == "prop/signage":
        if _is_large_icon(parsed):
            bits.append(f"Large sculpted {name.lower()} meant to sit on a roof or tall facade as a 3D shop identity.")
        elif _is_billboard(tokens):
            bits.append(f"{name} -- large roadside or wall advertisement panel. Face the readable side to the roadway.")
        elif _is_neon(tokens):
            bits.append(f"{name} -- neon letterform or icon for night facades. Mount on the street face.")
        elif "barber" in tokens:
            bits.append("Cylindrical barber pole that projects from a first-floor shop wall beside the door.")
        elif _is_traffic_sign(tokens):
            bits.append(f"{name} -- traffic / wayfinding sign. Place at grade on a pole facing traffic.")
        elif _is_attachment(tokens):
            bits.append("Mounting bracket / attachment hardware for hanging a sign or light off a facade.")
        else:
            bits.append(f"{name} -- wall-mounted identity plaque for a building facade.")
        if extra.get("contexts"):
            bits.append("Best on: " + ", ".join(extra["contexts"]) + ".")
        bits.append("Keep off windows; readable from the street.")
    elif ptype == "building/module":
        bits.append(
            f"{name} -- modular Synty building piece. Snap to the pack grid "
            "(typically 2.5-5 m on XZ, ~3 m storey height). Street face is +Z in official kits."
        )
        if extra.get("contexts"):
            bits.append("Role: " + ", ".join(extra["contexts"]) + ".")
    elif ptype == "vehicle":
        bits.append(f"{name} -- vehicle. Sit on the road or a parking stall; do not scale; yaw to the lane.")
    elif ptype == "character" and parsed.family in {"ANIMAL", "ANIMALS"}:
        bits.append(f"{name} -- animal mesh or prefab. Place in fields, pens or yards at 1:1 scale.")
    elif ptype == "character":
        bits.append(f"{name} -- character mesh or prefab. Place on sidewalks or interiors at 1:1 scale.")
    elif ptype == "environment":
        bits.append(f"{name} -- environment / ground piece. Use in the city-layout pass, not as a building shell.")
    else:
        bits.append(f"{name} -- Synty {ptype.replace('/', ' ')}.")
        if extra.get("contexts"):
            bits.append("Typical context: " + ", ".join(extra["contexts"]) + ".")
    return " ".join(bits)


def _ai_notes(parsed: ParsedName, extra: dict, ptype: str) -> str:
    tokens = {_norm_token(t) for t in parsed.tokens}
    if ptype == "prop/signage":
        if extra.get("contexts"):
            ctx = extra["contexts"][0].replace("_", " ")
            article = "an" if ctx[:1] in "aeiou" else "a"
            return (
                f"Use to mark {article} {ctx}. One identity sign per frontage. "
                "Do not mix civic plaques onto nightlife or vice buildings."
            )
        if _is_billboard(tokens):
            return "Roadway-facing ads. Keep clear of windows and official civic facades unless the copy is civic-only."
        if _is_attachment(tokens):
            return "Hardware only -- pair with a matching sign or light; do not use as the identity piece."
        return "Facade dressing. Prefer the street face; keep a clear read from the sidewalk."
    if ptype == "building/module":
        return (
            "Assemble on the 0.25 m snap grid. Do not scale. "
            "Do not use sidewalk/road pieces as part of the building shell."
        )
    if "city-layout" in extra.get("tags", []) or parsed.kind == "environment":
        return "City-layout only. The building generator must not emit this as a hero or annex."
    return "Place at authored scale. Prefer official Synty snap (0.25 m) and street axis +Z."


def _record(
    parsed: ParsedName,
    *,
    type_: str,
    role: str,
    detail: str,
    category: list[str],
    tags: list[str],
    description: str,
    ai_notes: str,
    placement: dict,
    module: dict | None = None,
    part: dict | None = None,
    gear: dict | None = None,
    name: str | None = None,
    dims: list[float] | None = None,
    placeable: bool | None = None,
) -> dict:
    """Build one ``infer()`` return dict. Centralises the shape so every
    v2 routing rule below only has to supply the fields it actually knows.

    ``placeable`` is only included when a rule needs to *override* the
    schema default (``default_placeable``) -- e.g. a whole SK_ skeleton,
    which schema.kind_for_type would otherwise mark non-placeable because
    its kind is "skeleton". Leaving it out lets enrich.py compute the
    correct default from ``type_`` for everything else.
    """
    rec = {
        "id": parsed.id,
        "name": name or title_from_tokens(parsed.subject_tokens or parsed.tokens) or parsed.id,
        "type": type_,
        "category": category,
        "tags": tags,
        "description": description,
        "semantic_role": role,
        "semantic_detail": detail,
        "placement": placement,
        "dimensions_hint": dims,
        "ai_notes": ai_notes,
        "module": module,
        "part": part,
        "gear": gear,
        "parsed": parsed,
    }
    if placeable is not None:
        rec["placeable"] = placeable
    return rec


def _infer_curated(parsed: ParsedName) -> dict:
    c = CURATED[parsed.id]
    return _record(
        parsed,
        type_=c["type"],
        role=c["semantic_role"],
        detail=c.get("semantic_detail", ""),
        category=list(c["category"]),
        tags=list(c["tags"]),
        description=c["description"],
        ai_notes=c["ai_notes"],
        placement=deepcopy(c["placement"]),
        dims=list(c["dimensions_hint"]) if c.get("dimensions_hint") else None,
        name=c["name"],
    )



_SAFE_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9_\-+.]*$")

# Sidekick modular part codes embedded as _NNCODE_SPECIESNN (e.g. _01HEAD_HU01).
_SIDEKICK_SLOT_RE = re.compile(r"_(\d{2})([A-Za-z]{3,6})_([A-Za-z]{2}\d+)$")
_SIDEKICK_SLOT_MAP = {
    # code -> (attach_bone, tags, gear_slot)
    "HEAD": ("HEAD", ["slot_head", "head"], "head"),
    "HAIR": ("HAIR", ["slot_head", "hair", "head"], "head"),
    "EBRL": ("EBRL", ["slot_face", "face", "brow"], "face"),
    "EBRR": ("EBRR", ["slot_face", "face", "brow"], "face"),
    "EYEL": ("EYEL", ["slot_face", "face", "eye"], "face"),
    "EYER": ("EYER", ["slot_face", "face", "eye"], "face"),
    "EARL": ("EARL", ["slot_face", "face", "ear"], "face"),
    "EARR": ("EARR", ["slot_face", "face", "ear"], "face"),
    "FCHR": ("FCHR", ["slot_face", "face"], "face"),
    "TORS": ("TORS", ["slot_torso", "torso", "clothing"], "torso"),
    "AUPL": ("AUPL", ["slot_shoulder", "arm", "shoulder"], "shoulder"),
    "AUPR": ("AUPR", ["slot_shoulder", "arm", "shoulder"], "shoulder"),
    "ALWL": ("ALWL", ["slot_wrist", "arm", "wrist"], "wrist"),
    "ALWR": ("ALWR", ["slot_wrist", "arm", "wrist"], "wrist"),
    "HNDL": ("HNDL", ["slot_hand_l", "hand", "hand_l"], "hand_l"),
    "HNDR": ("HNDR", ["slot_hand_r", "hand", "hand_r"], "hand_r"),
    "HIPS": ("HIPS", ["slot_belt", "hips", "belt"], "belt"),
    "LEGL": ("LEGL", ["slot_legs", "legs"], "legs"),
    "LEGR": ("LEGR", ["slot_legs", "legs"], "legs"),
    "FOTL": ("FOTL", ["slot_feet", "feet"], "feet"),
    "FOTR": ("FOTR", ["slot_feet", "feet"], "feet"),
    "NOSE": ("NOSE", ["slot_face", "face", "nose"], "face"),
    "TETH": ("TETH", ["slot_face", "face", "teeth"], "face"),
    "TONG": ("TONG", ["slot_face", "face"], "face"),
    "WRAP": ("WRAP", ["slot_torso", "torso", "clothing", "wrap"], "torso"),
    # Sidekick attach sockets (Axxx codes) seen on Soldiers/Civilians packs
    "AHED": ("AHED", ["slot_head", "head", "attach"], "head"),
    "AFAC": ("AFAC", ["slot_face", "face", "attach"], "face"),
    "ABAC": ("ABAC", ["slot_back", "back", "attach"], "back"),
    "AHPF": ("AHPF", ["slot_belt", "hips", "belt", "attach"], "belt"),
    "AHPB": ("AHPB", ["slot_belt", "hips", "belt", "attach"], "belt"),
    "AHPL": ("AHPL", ["slot_belt", "hips", "belt", "attach"], "belt"),
    "AHPR": ("AHPR", ["slot_belt", "hips", "belt", "attach"], "belt"),
    "ASHL": ("ASHL", ["slot_shoulder", "shoulder", "attach"], "shoulder"),
    "ASHR": ("ASHR", ["slot_shoulder", "shoulder", "attach"], "shoulder"),
    "AEBL": ("AEBL", ["slot_wrist", "arm", "elbow", "attach"], "wrist"),
    "AEBR": ("AEBR", ["slot_wrist", "arm", "elbow", "attach"], "wrist"),
    "AKNL": ("AKNL", ["slot_legs", "legs", "knee", "attach"], "legs"),
    "AKNR": ("AKNR", ["slot_legs", "legs", "knee", "attach"], "legs"),
}

_PAINT_FAMILY_TOKENS = {
    "red", "blue", "green", "black", "white", "yellow", "orange", "pink",
    "purple", "brown", "grey", "gray", "camo", "desert", "urban", "snow",
    "tan", "olive", "chrome", "gold", "silver", "cyan", "teal", "navy",
}
_TWO_HANDED_TOKENS = {
    "rifle", "shotgun", "sniper", "lmg", "minigun", "launcher", "bazooka",
    "rocket", "mg", "carbine", "bow", "crossbow", "staff", "spear", "twohand", "2h",
}
_ONE_HANDED_TOKENS = {
    "pistol", "handgun", "revolver", "knife", "dagger", "baton", "crowbar",
    "hatchet", "axe", "sword", "machete", "smg", "uzi",
}


def _unique_tags(tags: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for t in tags:
        tl = t.lower().strip()
        if not tl or tl in seen or not _SAFE_TAG_RE.fullmatch(tl):
            continue
        seen.add(tl)
        out.append(tl)
    return out


def _fits_from_stem(stem: str) -> str | None:
    up = stem.upper()
    if "ROBO" in up or re.search(r"_RO\d*$", up):
        return "robot"
    if "HUMN" in up or re.search(r"_HU\d*$", up):
        return "human"
    if "ALIEN" in up or re.search(r"_AL\d*$", up):
        return "alien"
    return None


def _sidekick_part_meta(stem: str) -> tuple[str | None, list[str], str | None, str | None]:
    """Return (attach_bone, tags, fits, gear_slot)."""
    m = _SIDEKICK_SLOT_RE.search(stem)
    fits = _fits_from_stem(stem)
    if not m:
        return None, [], fits, None
    code = m.group(2).upper()
    mapped = _SIDEKICK_SLOT_MAP.get(code)
    if mapped:
        bone, tags, gear_slot = mapped
        return bone, list(tags), fits, gear_slot
    return code, [f"slot_{code.lower()}"], fits, None


def _paint_family_from_tokens(tokens: list[str]) -> str | None:
    for t in tokens:
        tl = t.lower()
        if tl in _PAINT_FAMILY_TOKENS:
            return tl
    return None


def _two_handed_from_tokens(tokens: list[str]) -> bool | None:
    joined = " ".join(t.lower() for t in tokens)
    if any(t in joined for t in _TWO_HANDED_TOKENS):
        return True
    if any(t in joined for t in _ONE_HANDED_TOKENS):
        return False
    return None


def _coverage_from_hints(
    *,
    tags: list[str] | None = None,
    tokens: list[str] | None = None,
    sealed: bool = False,
    armorish: bool = False,
    clothingish: bool = False,
) -> str | None:
    tagset = {t.lower() for t in (tags or [])}
    toks = [t.lower() for t in (tokens or [])]
    joined = " ".join(toks)
    if sealed or "coverage_sealed" in tagset or any(x in tagset for x in ("eva", "vacuum", "space")):
        return "sealed"
    if "suit" in joined or "sealed" in joined:
        return "sealed"
    if armorish or "armor" in tagset or "plate" in joined or "heavy" in joined:
        return "heavy"
    if "vest" in joined or "tactical" in joined or "medium" in joined:
        return "medium"
    if clothingish or "clothing" in tagset or any(x in joined for x in ("shirt", "pants", "jacket", "coat", "dress")):
        return "light"
    if any(x in tagset for x in ("face", "hair", "eye", "ear", "brow", "nose", "teeth")):
        return "none"
    return None


def _make_gear(
    *,
    kind: str | None = None,
    slot: str | None = None,
    fits: str | None = None,
    coverage: str | None = None,
    role: str | None = None,
    attach: bool | None = None,
    two_handed: bool | None = None,
    paint_family: str | None = None,
) -> dict:
    g = empty_gear()
    g["kind"] = kind
    g["slot"] = slot
    g["fits"] = fits
    g["coverage"] = coverage
    g["role"] = role
    g["attach"] = attach
    g["twoHanded"] = two_handed
    g["paintFamily"] = paint_family
    return g


# --- Part 3: non-placeable data (animation / character rig / UI / skybox / fx) ---

_CLIP_PREFIX_RE = re.compile(r"^(A|Anim|ANIM)_", re.I)
# Animations(_IK|_Static).fbx in SIMPLE_Farm are multi-clip containers, not meshes.
_CLIP_WORD_RE = re.compile(
    r"^(?:(Idle|Walk|Run|Jump|Crouch|Strafe|Turn|Sprint|Fall|Land|Death|Hit|Aim|Fire|Reload)\b"
    r"|Animations?(?:_|$))",
    re.I,
)
_SK_PART_SUFFIX_RE = re.compile(r"_\d{2}[A-Za-z]{3,6}_[A-Z]{2}\d+$", re.I)
_BODY_PART_WORDS = (
    "head", "hair", "torso", "arm", "leg", "hand", "foot", "eye", "ear", "hip",
    "face", "brow", "tooth", "teeth", "knee", "elbow", "nose", "chest", "attach",
)
_UI_PREFIX_RE = re.compile(r"^(T|UI|Icon|HUD)_", re.I)
_SKY_PREFIX_RE = re.compile(r"^(Sky|Skybox|M_Sky)", re.I)

_CLIP_PLACEMENT = {
    "mount": "none", "height": "n/a", "orientation": "n/a", "attachment": "none",
    "preferred_floors": [], "constraints": [], "preferred_contexts": [],
}
_SOCKET_PLACEMENT = {
    "mount": "socket", "height": "n/a", "orientation": "align_to_parent", "attachment": "socket",
    "preferred_floors": [], "constraints": ["attach_to_character_bone"],
    "preferred_contexts": ["character_rig"],
}
_UI_PLACEMENT = {
    "mount": "none", "height": "n/a", "orientation": "screen_space", "attachment": "none",
    "preferred_floors": [], "constraints": [], "preferred_contexts": [],
}
_FX_PLACEMENT = {
    "mount": "free", "height": "n/a", "orientation": "upright", "attachment": "origin",
    "preferred_floors": [], "constraints": [], "preferred_contexts": [],
}


def _is_animation_clip(parsed: ParsedName) -> bool:
    """True for animation clip stems: ``A_``/``Anim_``/``ANIM_`` prefixed,
    or a bare clip-verb stem (Idle/Walk/Run/...) that isn't an ``SM_``/
    ``SK_`` mesh."""
    if _CLIP_PREFIX_RE.match(parsed.id):
        return True
    if parsed.id.upper().startswith(("SM_", "SK_")):
        return False
    return bool(_CLIP_WORD_RE.match(parsed.id))


def _animation_clip_record(parsed: ParsedName) -> dict:
    name = title_from_tokens(parsed.subject_tokens or parsed.tokens) or parsed.id
    return _record(
        parsed, type_="animation", role="animation_clip", detail="",
        category=["animation"], tags=["animation", "clip"],
        description=f"{name} -- animation clip, not a scene mesh.",
        ai_notes="Animation data only; apply to a rigged character, never place in a scene.",
        placement=deepcopy(_CLIP_PLACEMENT), name=name,
    )


def animation_clip(asset_id: str) -> dict:
    """The clip record for a stem the caller knows is a clip from context
    the stem lacks (e.g. its FBX sits in an ``Animations/`` folder)."""
    return _animation_clip_record(parse_name(asset_id))


def _infer_nonplaceable(parsed: ParsedName) -> dict | None:
    up = parsed.id.upper()
    name = title_from_tokens(parsed.subject_tokens or parsed.tokens) or parsed.id

    if _is_animation_clip(parsed):
        return _animation_clip_record(parsed)

    if up.startswith(("SK_", "CHR_", "CH_")):
        body = "".join(t.lower() for t in parsed.tokens)
        is_part = bool(_SK_PART_SUFFIX_RE.search(parsed.id)) or any(w in body for w in _BODY_PART_WORDS)
        if is_part:
            slot_code, slot_tags, fits, gear_slot = _sidekick_part_meta(parsed.id)
            tags = ["character_part", "rig", "wardrobe"] + slot_tags
            if fits:
                tags.append(f"fits_{fits}")
            part = empty_part()
            if slot_code:
                part["attach_bone"] = slot_code
            gear_kind = "other"
            armorish = False
            clothingish = "clothing" in tags or "wrap" in body
            # Clothing/armor-ish torso wrap etc.
            if any(t in tags for t in ("torso", "legs", "feet", "head")) and "hair" not in tags and "face" not in tags:
                if "wrap" in body or "suit" in body or "armor" in body:
                    part["class"] = "armor"
                    tags.append("armor")
                    gear_kind = "armor"
                    armorish = True
                elif clothingish:
                    gear_kind = "clothing"
            paint = _paint_family_from_tokens(parsed.tokens)
            if paint:
                tags.append(f"paint_{paint}")
            coverage = _coverage_from_hints(
                tags=tags, tokens=parsed.tokens, armorish=armorish, clothingish=clothingish,
            )
            detail = slot_tags[0] if slot_tags else "body_part"
            gear = _make_gear(
                kind=gear_kind,
                slot=gear_slot or "none",
                fits=fits,
                coverage=coverage,
                role="wardrobe",
                attach=True,
                paint_family=paint,
            )
            return _record(
                parsed, type_="character/part", role="character_part", detail=detail,
                category=["character", "part", "wardrobe"], tags=_unique_tags(tags),
                description=f"{name} -- modular character body part ({detail}). Assembles onto a skeleton rig; not placed standalone.",
                ai_notes="Rig-attached wardrobe/body part. Combine with matching parts to build a full character.",
                placement=deepcopy(_SOCKET_PLACEMENT), part=part, gear=gear, name=name,
            )
        fits = _fits_from_stem(parsed.id)
        tags = ["character", "skeleton", "preset"]
        if fits:
            tags.append(f"fits_{fits}")
        gear = _make_gear(kind="other", slot="none", fits=fits, role="preset", attach=False)
        return _record(
            parsed, type_="character/skeleton", role="character", detail="preset",
            category=["character", "preset"], tags=_unique_tags(tags),
            description=f"{name} -- whole character skeleton/rig preset.",
            ai_notes="Whole character preset. Place directly in the scene at 1:1 scale; not a wardrobe item.",
            placement=deepcopy(GROUND_PROP), name=name, placeable=True, gear=gear,
        )

    if _UI_PREFIX_RE.match(parsed.id):
        return _record(
            parsed, type_="ui/icon", role="ui_element", detail="",
            category=["ui"], tags=["ui"],
            description=f"{name} -- UI texture/icon, not a 3D scene object.",
            ai_notes="UI element. Never place in a 3D scene.",
            placement=deepcopy(_UI_PLACEMENT), name=name,
        )

    # "skydome" recurs mid-stem (not as a prefix) in both POLYGON_Military's
    # SM_Skydome_01 and PolygonGeneric's SM_Gen_Env_Skydome_01 -- catch it
    # anywhere in the token list, not just via _SKY_PREFIX_RE's stem-start match.
    if _SKY_PREFIX_RE.match(parsed.id) or "skydome" in {t.lower() for t in parsed.tokens}:
        return _record(
            parsed, type_="skybox", role="skybox", detail="",
            category=["environment", "skybox"], tags=["skybox", "sky"],
            description=f"{name} -- skybox material, applied to the scene sky dome, not placed as a mesh.",
            ai_notes="Sky material only.",
            placement=deepcopy(_UI_PLACEMENT), name=name,
        )

    if up.startswith(("FX_", "PS_")):
        return _record(
            parsed, type_="fx", role="visual_effect", detail="",
            category=["fx"], tags=["fx", "particle"],
            description=f"{name} -- particle/visual effect prefab.",
            ai_notes="Effect prefab. Trigger at runtime or place at the source point.",
            placement=deepcopy(_FX_PLACEMENT), name=name,
        )
    return None


# --- Part 1: sci-fi ship-kit vocabulary (SM_Veh_Part_* / SM_Ship_*) ------------

_PART_CLASS_SPEC = {
    "body": {
        "class": "body", "mates_axis": "any", "symmetric": True, "dims": [2.0, 2.0, 4.0],
        "note": (
            "Central hull segment. Other parts (cockpit, engine, wings, landing gear) mate to "
            "its sockets; symmetric enough to anchor either end of a hull run."
        ),
    },
    "cockpit": {
        "class": "cockpit", "mates_axis": "+z", "symmetric": False, "dims": [1.5, 1.5, 2.0],
        "note": "Forward crew module. Mates to the +Z (front) socket of a Body part; do not place at the rear.",
    },
    "engine": {
        "class": "engine", "mates_axis": "-z", "symmetric": False, "dims": [1.5, 1.5, 3.0],
        "note": (
            "Rear engine/thruster module. Mates to the -Z (rear) socket of a Body part, "
            "nozzle facing away from the hull."
        ),
    },
    "wing": {
        "class": "wing", "mates_axis": "±x", "symmetric": True, "dims": [3.0, 0.3, 2.0],
        "note": (
            "Wing panel. Mates along ±X; place a mirrored pair for left/right symmetry -- "
            "do not use a single wing alone."
        ),
    },
    "landinggear": {
        "class": "landing_gear", "mates_axis": "-y", "symmetric": False, "dims": [0.6, 0.8, 0.6],
        "note": "Landing gear/strut. Mates to the -Y (underside) socket; deploy only when the ship is landed or docked.",
    },
    "misc": {
        "class": "greeble", "mates_axis": "any", "symmetric": False, "dims": None,
        "note": (
            "Small hull detail/greeble. Mates anywhere on the hull for visual variety -- "
            "purely decorative, no structural role."
        ),
    },
}

_VEH_PART_PLACEMENT = {
    "mount": "socket", "height": "n/a", "orientation": "align_to_parent", "attachment": "socket",
    "preferred_floors": [], "constraints": ["attach_to_ship_body", "do_not_scale"],
    "preferred_contexts": ["ship_kit"],
}


def _infer_vehicle_part(parsed: ParsedName) -> dict | None:
    if not parsed.id.upper().startswith("SM_VEH_PART_"):
        return None
    joined = "".join(t.lower() for t in parsed.subject_tokens)
    key = next((k for k in _PART_CLASS_SPEC if k in joined), "misc")
    spec = _PART_CLASS_SPEC[key]
    part = empty_part()
    part["class"] = spec["class"]
    part["mates_axis"] = spec["mates_axis"]
    part["symmetric"] = spec["symmetric"]
    name_tokens = [t for t in parsed.subject_tokens if t.lower() != "part"]
    name = title_from_tokens(name_tokens) or parsed.id
    return _record(
        parsed,
        type_="vehicle/part",
        role="vehicle_part",
        detail=spec["class"],
        category=["vehicle", "ship_part"],
        tags=["vehicle_part", spec["class"], "ship_kit"],
        description=f"{name} -- {spec['note']}",
        ai_notes=spec["note"],
        placement=deepcopy(_VEH_PART_PLACEMENT),
        part=part,
        dims=spec["dims"],
        name=name,
    )


_SHIP_SIZE_DIMS = {
    "fighter": [8.0, 3.0, 10.0],
    "bomber": [12.0, 4.0, 14.0],
    "transport": [18.0, 6.0, 22.0],
    "cruiser": [30.0, 9.0, 40.0],
    "capital": [60.0, 20.0, 120.0],
    "station": [50.0, 20.0, 50.0],
}
_SHIP_PLACEMENT = {
    "mount": "free", "height": "n/a", "orientation": "nose_plus_z", "attachment": "origin",
    "preferred_floors": [], "constraints": ["do_not_scale"],
    "preferred_contexts": ["space", "hangar", "orbit"],
}


def _ship_size_class(joined: str) -> str:
    if "fighter" in joined or "stealth" in joined:
        return "fighter"
    if "bomber" in joined:
        return "bomber"
    if "transport" in joined:
        return "transport"
    if "cruiser" in joined:
        return "cruiser"
    if "galactic" in joined or "colossal" in joined:
        return "capital"
    if "station" in joined:
        return "station"
    return "fighter"


def _infer_spacecraft(parsed: ParsedName) -> dict | None:
    if not parsed.id.upper().startswith("SM_SHIP_"):
        return None
    subject = [t for t in parsed.subject_tokens if t.lower() != "ship"]
    joined = "".join(t.lower() for t in subject)
    size_class = _ship_size_class(joined)
    part = empty_part()
    part["size_class"] = size_class
    name = title_from_tokens(subject) or parsed.id
    return _record(
        parsed,
        type_="vehicle/spacecraft",
        role="spacecraft",
        detail=size_class,
        category=["vehicle", "spacecraft"],
        tags=["spacecraft", size_class],
        description=(
            f"{name} -- complete spacecraft prefab ({size_class} class), not a hull part. "
            "Fly or park freely in space, hangar or orbit; do not attach as a ship-kit module."
        ),
        ai_notes=f"Whole ship, {size_class} class. Place with nose along +Z; scale is authored, do not rescale.",
        placement=deepcopy(_SHIP_PLACEMENT),
        part=part,
        dims=_SHIP_SIZE_DIMS.get(size_class),
        name=name,
    )


# --- SM_Wep_* weapon vocabulary (military/war/crime packs) --------------------
#
# naming.py's FAMILY_KIND already maps WEP -> kind="weapon", so a bare
# ``SM_Wep_<Name>_*`` already gets type="weapon" via the legacy fallback --
# but the legacy `_semantic_role` has no "weapon" branch (it falls to the
# generic "dresses_scene" default), which is why weapons still need an
# explicit rule here to land on the schema's "weapon" semantic role.

_WEAPON_SOCKET_PLACEMENT = {
    "mount": "socket", "height": "n/a", "orientation": "align_to_parent", "attachment": "socket",
    "preferred_floors": [], "constraints": ["attach_to_character_hand_or_holster"],
    "preferred_contexts": ["character_rig", "loadout"],
}
_WEAPON_MOD_PLACEMENT = {
    "mount": "socket", "height": "n/a", "orientation": "align_to_parent", "attachment": "socket",
    "preferred_floors": [], "constraints": ["attach_to_weapon_body", "do_not_scale"],
    "preferred_contexts": ["weapon_builder"],
}
# SM_Wep_Mod_<Slot>_* -> nearest PART_CLASSES value. No "weapon/part" type
# and no "weapon_part" semantic role exist in schema.TYPES/SEMANTIC_ROLES
# (gap -- see brief report); modelled as type="weapon" + `part.class` instead,
# the same shape POLYGON_Mech's attachments use below.
_WEAPON_MOD_SLOTS = {
    "barrel", "body", "grip", "handguard", "handle", "ironsight", "magazine",
    "mag", "scope", "stock", "suppressor", "muzzle", "sight", "rail", "trigger",
}
_WEAPON_NATIONALITY_TOKENS = {"american", "german", "russian", "british", "bandit", "swat"}



def _optic_gear() -> dict:
    """Weapon optic / scope attachment: sockets onto a weapon, not a hand."""
    return _make_gear(kind="attachment", slot="none", fits="any", role="optic", attach=True)


def _is_optic_weapon_part(subject_lower: list[str], joined: str) -> bool:
    """True when the asset is clearly an optic/scope attachment, not a full gun.

    Rules (all require SM_Wep_* already):
    a) SM_Wep_Mod_* with mod slot in {scope, sight, ironsight} OR tokens contain
       reddot/holo/optic
    b) tokens contain attachment AND (scope|sight|optic|reddot|holo)
    c) primary noun is scope: first non-nationality token is ``scope``, OR id
       pattern like SM_Wep_*_Scope_* / SM_Wep_Scope_*
    d) nationality + Scope (American_Scope, German_Scope, Russian_Scope)
    e) Sniper_Scope (both tokens) = optic piece; bare Sniper / Rifle / Pistol /
       Preset = still weapon
    f) NEVER crosshair / UI (handled before this); NEVER microscope/satellite
    """
    if "crosshair" in joined or "crosshair" in subject_lower:
        return False
    if "microscope" in joined or "satellite" in joined:
        return False

    optic_tokens = {"scope", "sight", "optic", "reddot", "holo", "ironsight"}
    nationality = _WEAPON_NATIONALITY_TOKENS

    # a) Mod_* with optic slot or optic tokens
    if subject_lower[:1] == ["mod"]:
        rest = subject_lower[1:]
        slot = next((t for t in rest if t in _WEAPON_MOD_SLOTS), None)
        if slot in {"scope", "sight", "ironsight"}:
            return True
        if any(t in optic_tokens for t in rest) or any(
            k in joined for k in ("reddot", "holo", "optic")
        ):
            return True

    # b) attachment + (scope|sight|optic|reddot|holo) — also compound tokens
    #    like SniperScope / RedDot in a single subject token (joined check)
    if "attachment" in subject_lower and (
        any(t in optic_tokens for t in subject_lower)
        or any(k in joined for k in ("scope", "sight", "optic", "reddot", "holo"))
    ):
        return True

    # e) Sniper_Scope (both tokens) OR compound SniperScope in joined;
    #    bare Sniper / Rifle / Pistol / Preset alone stays a weapon
    if ("sniper" in subject_lower and "scope" in subject_lower) or (
        "sniper" in joined and "scope" in joined
    ):
        return True

    # Strip nationality for primary-noun checks
    non_nat = [t for t in subject_lower if t not in nationality]

    # c) first non-nationality token is scope, or Scope appears as a structural token
    if non_nat[:1] == ["scope"]:
        return True
    # SM_Wep_Scope_* / SM_Wep_*_Scope_* — subject contains scope not as gun name alone
    if "scope" in subject_lower:
        # bare "..._Scope_..." attachment-style ids (not a full weapon name like
        # hypothetical future guns that include scope in a compound — those still
        # need another optic cue; nationality+Scope handled in d)
        if subject_lower[:1] == ["scope"]:
            return True
        # middle Scope token: e.g. American_Scope_Long, Attachment_SniperScope
        if any(t == "scope" for t in subject_lower[1:]):
            return True

    # d) nationality + Scope
    if any(t in nationality for t in subject_lower) and "scope" in subject_lower:
        return True

    return False


def _infer_weapon(parsed: ParsedName) -> dict | None:
    if not parsed.id.upper().startswith("SM_WEP_"):
        return None
    subject = parsed.subject_tokens
    subject_lower = [t.lower() for t in subject]
    joined = "".join(subject_lower)
    name = title_from_tokens(subject) or parsed.id

    if "crosshair" in joined:
        return _record(
            parsed, type_="ui/icon", role="ui_element", detail="crosshair",
            category=["ui", "icon"], tags=["ui", "crosshair", "reticle"],
            description=f"{name} -- weapon crosshair/reticle icon. Not a scene object; screen-space HUD only.",
            ai_notes="UI element. Never place in a 3D scene.",
            placement=deepcopy(_UI_PLACEMENT), name=name,
        )

    if subject_lower[:1] == ["mod"]:
        slot = next((t for t in subject_lower[1:] if t in _WEAPON_MOD_SLOTS), None)
        part = empty_part()
        part["class"] = "weapon_mount"
        mod_name = title_from_tokens(subject[1:]) or name
        is_optic = _is_optic_weapon_part(subject_lower, joined)
        if is_optic:
            tags = ["weapon_part", "weapon_mod", "attachment", "optic"]
            if slot:
                tags.append(slot)
            elif "scope" in subject_lower or "scope" in joined:
                tags.append("scope")
            for extra in ("sight", "reddot", "holo"):
                if extra in subject_lower or extra in joined:
                    tags.append(extra)
            return _record(
                parsed, type_="weapon", role="weapon", detail="optic_attachment",
                category=["weapon", "weapon_part"], tags=tags,
                description=(
                    f"{mod_name} -- weapon optic/scope attachment. Sockets onto a weapon "
                    "rail/receiver; not a standalone weapon."
                ),
                ai_notes="Optic attachment. Mount on a weapon optic rail; never place standalone or in a character hand.",
                placement=deepcopy(_WEAPON_MOD_PLACEMENT), part=part, name=mod_name,
                gear=_optic_gear(),
            )
        return _record(
            parsed, type_="weapon", role="weapon", detail="weapon_mod",
            category=["weapon", "weapon_part"], tags=["weapon_part", "weapon_mod", "attachment"] + ([slot] if slot else []),
            description=(
                f"{mod_name} -- modular weapon component. Sockets onto a weapon body/rail; "
                "not a standalone weapon."
            ),
            ai_notes="Weapon builder part. Attach to the matching socket on a weapon body; never place standalone.",
            placement=deepcopy(_WEAPON_MOD_PLACEMENT), part=part, name=mod_name,
            gear=_make_gear(kind="attachment", slot="none", fits="any", role=None, attach=True),
        )

    if subject_lower[:1] == ["preset"]:
        preset_name = title_from_tokens(subject[1:]) or name
        th = _two_handed_from_tokens(subject)
        paint = _paint_family_from_tokens(subject)
        wtags = ["weapon", "preset", "assembled"]
        if paint:
            wtags.append(f"paint_{paint}")
        if th is True:
            wtags.append("two_handed")
        elif th is False:
            wtags.append("one_handed")
        return _record(
            parsed, type_="weapon", role="weapon", detail="assembled_weapon",
            category=["weapon"], tags=wtags,
            description=(
                f"{preset_name} -- pre-assembled weapon loadout (Wep_Mod parts combined into one "
                "weapon). Equip whole; do not disassemble by default."
            ),
            ai_notes="Ready-to-use weapon assembly. Equip to a character hand socket.",
            placement=deepcopy(_WEAPON_SOCKET_PLACEMENT), name=preset_name,
            gear=_make_gear(
                kind="weapon", slot="hand_r", fits="any", role=None, attach=True,
                two_handed=th, paint_family=paint,
            ),
        )

    # Non-Mod optic attachments: SM_Wep_Scope_*, SM_Wep_Attachment_*Scope*,
    # SM_Wep_American_Scope_*, SM_Wep_Sniper_Scope_*, etc.
    if _is_optic_weapon_part(subject_lower, joined):
        part = empty_part()
        part["class"] = "weapon_mount"
        tags = ["weapon_part", "attachment", "optic"]
        if "scope" in subject_lower or "scope" in joined:
            tags.append("scope")
        for extra in ("sight", "reddot", "holo", "ironsight"):
            if extra in subject_lower or extra in joined:
                tags.append(extra)
        return _record(
            parsed, type_="weapon", role="weapon", detail="optic_attachment",
            category=["weapon", "weapon_part"], tags=tags,
            description=(
                f"{name} -- weapon optic/scope attachment. Sockets onto a weapon "
                "rail/receiver; not a standalone weapon."
            ),
            ai_notes="Optic attachment. Mount on a weapon optic rail; never place standalone or in a character hand.",
            placement=deepcopy(_WEAPON_MOD_PLACEMENT), part=part, name=name,
            gear=_optic_gear(),
        )

    detail_tokens = [t for t in subject_lower if t not in _WEAPON_NATIONALITY_TOKENS]
    detail = detail_tokens[0] if detail_tokens else (subject_lower[0] if subject_lower else "weapon")
    tags = ["weapon", detail] + [t for t in subject_lower if t in _WEAPON_NATIONALITY_TOKENS]
    th = _two_handed_from_tokens(subject)
    paint = _paint_family_from_tokens(subject)
    if paint:
        tags.append(f"paint_{paint}")
    if th is True:
        tags.append("two_handed")
    elif th is False:
        tags.append("one_handed")
    return _record(
        parsed, type_="weapon", role="weapon", detail=detail,
        category=["weapon"], tags=tags,
        description=f"{name} -- handheld weapon. Equip to a character hand socket or place in a weapon rack/loadout.",
        ai_notes="Weapon prop. Socket to a character hand bone when equipped; ground-place only in armories/loadout scenes.",
        placement=deepcopy(_WEAPON_SOCKET_PLACEMENT), name=name,
        gear=_make_gear(
            kind="weapon", slot="hand_r", fits="any", role=None, attach=True,
            two_handed=th, paint_family=paint,
        ),
    )


# --- SM_Veh_* military vehicle vocabulary --------------------------------------

_VEHICLE_GROUND_PLACEMENT = {
    "mount": "ground", "height": "grade", "orientation": "forward_plus_z", "attachment": "base_to_ground",
    "preferred_floors": [1], "constraints": ["sit_on_ground", "align_to_road_or_field"],
    "preferred_contexts": ["street", "battlefield", "motor_pool"],
}


def _infer_veh_military(parsed: ParsedName) -> dict | None:
    if not parsed.id.upper().startswith("SM_VEH_") or parsed.id.upper().startswith("SM_VEH_PART_"):
        return None
    subject = parsed.subject_tokens
    subject_lower = [t.lower() for t in subject]
    name = title_from_tokens(subject) or parsed.id
    joined = "".join(subject_lower)

    if subject_lower[:1] == ["attach"]:
        part = empty_part()
        part["class"] = "greeble"
        attach_name = title_from_tokens(subject[1:]) or name
        return _record(
            parsed, type_="vehicle/part", role="vehicle_part", detail="cargo_attachment",
            category=["vehicle", "vehicle_part"], tags=["vehicle_part", "cargo", "greeble"],
            description=(
                f"{attach_name} -- vehicle cargo/greeble attachment. Sockets onto a vehicle "
                "hardpoint (roof rack, truck bed, hood); purely decorative."
            ),
            ai_notes="Attach to the matching vehicle hardpoint. Not a standalone vehicle.",
            placement=deepcopy(_VEH_PART_PLACEMENT), part=part, name=attach_name,
        )

    is_wreck = "destroyed" in joined
    tags = ["vehicle", "military_vehicle"]
    if is_wreck:
        tags += ["destroyed", "wreck"]
    return _record(
        parsed, type_="vehicle", role="vehicle", detail="destroyed_vehicle" if is_wreck else "military_vehicle",
        category=["vehicle", "military"], tags=tags,
        description=f"{name} -- military vehicle. Sit on the road, field or motor pool; do not scale; yaw to travel direction.",
        ai_notes=(
            'Ground/air military vehicle. Wreck variants ("Destroyed") dress battle-damaged scenes; '
            "do not mix with intact motor pools."
        ),
        placement=deepcopy(_VEHICLE_GROUND_PLACEMENT), name=name,
    )


# --- POLYGON_Mech vocabulary ----------------------------------------------------
#
# No listing was provided for this pack -- the lead described it as a
# rigged ``SM_Veh_Mech_01`` body plus a ``MechAttachments/`` folder of
# slot-keyed armor/weapon meshes (Arm/Leg/Chest/Head/Hips/Foot/Back/Hand/
# Cockpit/Neck). ASSUMPTION (report to lead, validate at scan time): the
# attachments follow the pack's existing ``SM_Veh_Attach_*`` cargo-
# attachment naming convention, i.e. ``SM_Veh_MechAttach_<Slot>_##`` /
# ``SM_Veh_Mech_Attach_<Slot>_##``; the matcher below only requires the
# "Mech" and "Attach" tokens to both be present (in either order/spacing),
# so it survives minor real-naming differences.
_MECH_SLOT_PART_CLASS = {
    "arm": "armor", "leg": "armor", "chest": "armor", "head": "armor",
    "hips": "armor", "foot": "armor", "back": "armor", "hand": "armor", "neck": "armor",
    "cockpit": "cockpit", "weapon": "weapon_mount", "wep": "weapon_mount",
}


def _infer_mech(parsed: ParsedName) -> dict | None:
    # Two real spellings in POLYGON_Mech (validated against the extracted pack,
    # 2026-08-19): bodies are SM_Veh_Mech_01..06; attachments are
    # SM_Mech_<Region>_01_<Kind>_<Detail> (MechAttachments/) plus a couple of
    # SM_Mech_01_Attach_* saddlebags. SM_Mech_* is ALWAYS an attachment --
    # the standalone bolt-on meshes for the slot/bone system.
    pid = parsed.id.upper()
    is_veh = pid.startswith("SM_VEH_")
    is_mech_part = pid.startswith("SM_MECH_")
    if not (is_veh or is_mech_part):
        return None
    tokens_lower = [t.lower() for t in parsed.tokens]
    # substring, not exact-token, match: the assumed real stem may glue
    # "Mech"/"Attach" into one camelCase token (SM_Veh_MechAttach_Arm_01)
    # instead of splitting them (SM_Veh_Mech_Attach_Arm_01) -- both must resolve.
    if "mech" not in "".join(tokens_lower):
        return None
    subject = parsed.subject_tokens
    subject_lower = [t.lower() for t in subject]

    if is_mech_part or "attach" in "".join(subject_lower):
        name = title_from_tokens(subject) or parsed.id
        slot = next((t for t in subject_lower if t in _MECH_SLOT_PART_CLASS), None)
        part_class = _MECH_SLOT_PART_CLASS.get(slot, "armor")
        remaining = [t for t in subject if "mech" not in t.lower() and "attach" not in t.lower()]
        part = empty_part()
        part["class"] = part_class
        attach_name = title_from_tokens(remaining) or name
        return _record(
            parsed, type_="vehicle/part", role="vehicle_part", detail=f"mech_{part_class}",
            category=["vehicle", "mech_part"], tags=["mech", "mech_attachment", part_class],
            description=(
                f"{attach_name} -- Mech slot-keyed {part_class} attachment. Sockets onto the "
                f"{slot or 'matching'} hardpoint of the Mech body."
            ),
            ai_notes="Attach to the matching Mech body slot. Not a standalone vehicle.",
            placement=deepcopy(_VEH_PART_PLACEMENT), part=part, name=attach_name,
        )

    name = title_from_tokens(subject) or parsed.id
    return _record(
        parsed, type_="vehicle", role="vehicle", detail="mech",
        category=["vehicle", "mech"], tags=["mech", "vehicle", "walker"],
        description=f"{name} -- rigged Mech walker body. Equip MechAttachments slot pieces onto it; place at authored scale.",
        ai_notes="Whole Mech chassis. Combine with MechAttachments/ slot parts for the assembled loadout.",
        placement=deepcopy(_VEHICLE_GROUND_PLACEMENT), name=name,
    )


# --- Bld_* dispatch: City-style exterior kits vs sci-fi interior kits ----------

_CITY_TWO_TOKEN_FAMILIES = {
    ("officeold", "large"): "OfficeOld_Large", ("officeold", "small"): "OfficeOld_Small",
    # War/Military-pack two-word building families ("SM_Bld_Guard_Tower_*",
    # "SM_Bld_State_Building_*") -- same family as the single-word spellings
    # below ("GuardTower" in POLYGON_Military), normalised to one label.
    ("guard", "tower"): "GuardTower", ("state", "building"): "StateBuilding",
}
_CITY_SINGLE_FAMILIES = {
    "apartment": "Apartment", "officeoctagon": "OfficeOctagon", "officeround": "OfficeRound",
    "officesquare": "OfficeSquare", "shop": "Shop", "station": "Station", "cityhall": "CityHall",
    "fireescape": "FireEscape", "spire": "Spire", "cover": "Cover",
    # War/military/crime-pack hero building families (POLYGON_Military,
    # POLYGON_War, POLYGON_Gang_Warfare, POLYGON_BattleRoyale). None of
    # these collide with _INTERIOR_TRIGGER_TOKENS, so bld_exterior_family
    # keeps taking precedence over is_interior_bld for them as designed.
    "village": "Village", "tent": "Tent", "camonet": "CamoNet", "camonetting": "CamoNet",
    "guardtower": "GuardTower", "plywood": "Plywood", "ruins": "Ruins", "ruin": "Ruins",
    "decorative": "Decorative", "gastower": "GasTower", "archway": "Archway",
    "hangar": "Hangar", "hanger": "Hangar", "city": "City", "bunker": "Bunker",
    "townhouse": "TownHouse", "barracks": "Barracks", "warehouse": "Warehouse",
    "house": "House", "smallbuilding": "SmallBuilding", "woodenshack": "WoodenShack",
    "shack": "Shack", "walkway": "Walkway", "skylight": "Skylight",
    "loadingdock": "LoadingDock", "barn": "Barn", "farmhouse": "FarmHouse",
    "farm": "Farm", "outhose": "Outhouse", "shed": "Shed",
    # NOTE: deliberately no "roof": "Roof" entry here. A bare Roof head
    # token (SM_Bld_Roof_Cap_01 in Military, SM_Bld_Roof_Beam_01 /
    # SM_Bld_Roof_Flat_*_01 in Gang_Warfare) is common enough in the new
    # war/crime packs, but SM_Bld_Roof_* also exists as head token in
    # POLYGON_SciFi_City (Roof_Pagoda) and POLYGON_SciFi_Space
    # (Roof_Exterior) -- packs this lane does not own. Adding "roof" here
    # would change those two lanes' existing classification (family/role
    # go from null/None to "Roof"/"misc") as a side effect of vocab added
    # for unrelated packs. Bare Roof stems in the new packs fall through
    # to _infer_legacy instead, which (after the TYPE_MIGRATION fix above)
    # still resolves to a valid "building/module" type -- just without the
    # more specific family/role. "SM_Bld_Roof_Access_01" and two-token
    # "<Family>_Roof_01" suffixes (e.g. State_Building_Roof_01) are
    # unaffected -- those are handled by the explicit branch and by
    # _EXTERIOR_ROLE_PRECEDENCE's "roof" role-suffix respectively, not by
    # this table.
}


def bld_exterior_family(subject_tokens: list[str]) -> tuple[str, list[str]] | None:
    """Return ``(family_label, remaining_role_tokens)`` if *subject_tokens*
    (the tokens after ``SM_Bld_``, variant already stripped) name a known
    City-style exterior building-kit family (Apartment, Office*, Shop,
    Station, CityHall, FireEscape, Spire, Cover, RoofAccess), else
    ``None``. Two-word families (``OfficeOld_Large``/``OfficeOld_Small``)
    are matched before the single-word table.
    """
    if not subject_tokens:
        return None
    toks = [t.lower() for t in subject_tokens]
    if len(toks) > 1 and (toks[0], toks[1]) in _CITY_TWO_TOKEN_FAMILIES:
        return _CITY_TWO_TOKEN_FAMILIES[(toks[0], toks[1])], subject_tokens[2:]
    if toks[0] == "roof" and len(toks) > 1 and toks[1] == "access":
        return "RoofAccess", subject_tokens[2:]
    if toks[0] in _CITY_SINGLE_FAMILIES:
        return _CITY_SINGLE_FAMILIES[toks[0]], subject_tokens[1:]
    return None


_INTERIOR_TRIGGER_TOKENS = ("wall", "floor", "ceiling", "corridor", "bridge", "crew", "hydroponics", "base", "door")


def is_interior_bld(subject_tokens: list[str]) -> bool:
    """True if a ``SM_Bld_*`` stem names a sci-fi station/ship *interior*
    kit piece rather than a City-style exterior module.

    A stem is interior when it mentions a structural interior token
    (wall/floor/ceiling/corridor/bridge/crew/hydroponics/base/door) AND is
    NOT a recognised City exterior family -- City's own
    ``SM_Bld_Apartment_Door_01`` is an exterior module, not an interior
    one, even though it contains "Door".
    """
    if bld_exterior_family(subject_tokens) is not None:
        return False
    joined = "".join(t.lower() for t in subject_tokens)
    return any(tok in joined for tok in _INTERIOR_TRIGGER_TOKENS)


_EXTERIOR_ROLE_PRECEDENCE = ("door", "stairs", "roof", "floor", "base", "cover")
_EXTERIOR_STACKABLE = {"floor": ["base", "floor"], "roof": ["floor", "base"], "base": []}
_FAMILY_CONTEXT = {
    "Apartment": "residential_block", "Shop": "shop", "Station": "transit_station",
    "CityHall": "civic", "OfficeOctagon": "office", "OfficeRound": "office",
    "OfficeSquare": "office", "OfficeOld_Large": "office", "OfficeOld_Small": "office",
    "Village": "settlement", "Tent": "encampment", "CamoNet": "military_base",
    "GuardTower": "checkpoint", "Bunker": "military_base", "Hangar": "airfield",
    "Barracks": "military_base", "Warehouse": "industrial", "TownHouse": "residential_block",
    "House": "residential_block", "SmallBuilding": "residential_block",
    "WoodenShack": "settlement", "Shack": "settlement", "StateBuilding": "civic",
    "City": "urban", "Farm": "farmland", "FarmHouse": "farmland", "Barn": "farmland",
}
_ONEOFF_EXTERIOR_MODULES = {
    "FireEscape": {"role": "misc", "mount": "wall"},
    "Spire": {"role": "spire", "mount": "roof"},
    "RoofAccess": {"role": "roof", "mount": "roof"},
    "Cover": {"role": "cover", "mount": "wall"},
}
_INTERIOR_MODULE_PLACEMENT = {
    "mount": "module", "height": "n/a", "orientation": "kit_grid", "attachment": "origin",
    "preferred_floors": [], "constraints": ["snap_to_grid", "do_not_scale"],
    "preferred_contexts": ["station_interior", "ship_interior"],
}
_INTERIOR_FAMILY_STARTERS = {"base", "bridge", "crew", "corridor", "hydroponics"}
_INTERIOR_ROLE_PRECEDENCE = ("door", "window", "stairs", "pillar", "corridor", "bridge", "ceiling", "floor", "wall")


def _infer_exterior_bld(parsed: ParsedName, family: str, remaining: list[str]) -> dict:
    if family in _ONEOFF_EXTERIOR_MODULES:
        spec = _ONEOFF_EXTERIOR_MODULES[family]
        placement = deepcopy(MODULAR_BUILDING)
        placement["mount"] = spec["mount"]
        placement["attachment"] = "base_to_roof" if spec["mount"] == "roof" else "back_side"
        placement["constraints"] = ["snap_to_grid", "do_not_scale"]
        placement["preferred_contexts"] = ["building_exterior"]
        module = empty_module()
        module["family"] = family
        module["role"] = spec["role"]
        module["street_side"] = "+z"
        name = title_from_tokens(parsed.subject_tokens) or parsed.id
        return _record(
            parsed, type_="building/module", role="building_module", detail=f"{family.lower()}_{spec['role']}",
            category=["building", "exterior_dressing"], tags=[family.lower()],
            description=(
                f"{family} -- one-off exterior building attachment ({spec['role']}). Mount on the "
                f"{spec['mount']} of a hero shell; do not use as a standalone structure."
            ),
            ai_notes=f"Attach to an existing building shell's {spec['mount']}. Not a stackable kit module.",
            placement=placement, module=module, name=name,
        )

    context = _FAMILY_CONTEXT.get(family, family.lower())
    family_words = family.replace("_", " ")
    name = title_from_tokens(parsed.subject_tokens) or parsed.id
    if not remaining:
        module = empty_module()
        module["family"] = family
        module["role"] = "hero"
        module["street_side"] = "+z"
        placement = deepcopy(MODULAR_BUILDING)
        placement["constraints"] = ["snap_to_grid", "do_not_scale"]
        placement["preferred_contexts"] = [context]
        return _record(
            parsed, type_="building/shell", role="building_shell", detail=context,
            category=["building", context],
            tags=[family.lower().replace("_", "-")],
            description=(
                f"{family_words} -- a complete hero building shell for the {context.replace('_', ' ')} kit. "
                "This is a whole building, not a stackable module; place at grade on the city block "
                "grid, street face +Z."
            ),
            ai_notes=(
                "Whole hero shell. One per lot. Only stack with Base/Floor/Roof pieces from the "
                "same family if the kit provides them."
            ),
            placement=placement, module=module, name=name,
        )

    rem_lower = [t.lower() for t in remaining]
    footprint_class = None
    if "corner" in rem_lower:
        others = [r for r in _EXTERIOR_ROLE_PRECEDENCE if r in rem_lower]
        if others:
            role = others[0]
            footprint_class = "corner"
        else:
            role = "corner"
    else:
        others = [r for r in _EXTERIOR_ROLE_PRECEDENCE if r in rem_lower]
        role = others[0] if others else ("shell" if "stack" in rem_lower else "misc")
    stackable_on = _EXTERIOR_STACKABLE.get(role, [])
    module = empty_module()
    module["family"] = family
    module["role"] = role
    module["footprint_class"] = footprint_class
    module["stackable_on"] = stackable_on
    module["street_side"] = "+z"
    placement = deepcopy(MODULAR_BUILDING)
    placement["constraints"] = ["snap_to_grid", "do_not_scale"]
    placement["preferred_contexts"] = [context]
    detail = f"{family.lower()}_{role}"
    corner_note = " Corner footprint -- use at building corners only." if footprint_class == "corner" else ""
    return _record(
        parsed, type_="building/module", role="building_module", detail=detail,
        category=["building", context],
        tags=[family.lower().replace("_", "-"), role],
        description=(
            f"{family_words} {role} module -- stackable Synty city kit piece. Snap to the "
            f"{family_words} kit grid; role: {role}.{corner_note}"
        ),
        ai_notes=(
            f"Assemble as part of a {family_words} building -- stack {role} pieces on "
            f"{', '.join(stackable_on) if stackable_on else 'the ground'}. Do not mix with other kit families."
        ),
        placement=placement, module=module, name=name,
    )


def _interior_family_and_role(subject_tokens: list[str]) -> tuple[str, str]:
    if not subject_tokens:
        return "Interior", "misc"
    head = subject_tokens[0].lower()
    if head in _INTERIOR_FAMILY_STARTERS:
        family = subject_tokens[0]
        remaining = subject_tokens[1:]
    else:
        family = "Interior"
        remaining = subject_tokens
    scan_tokens = remaining or subject_tokens[:1]
    joined = "".join(t.lower() for t in scan_tokens)
    role = next((r for r in _INTERIOR_ROLE_PRECEDENCE if r in joined), "misc")
    return family, role


def _infer_interior_bld(parsed: ParsedName, subject_tokens: list[str]) -> dict:
    family, role = _interior_family_and_role(subject_tokens)
    module = empty_module()
    module["family"] = family
    module["role"] = role
    detail = f"{family.lower()}_{role}"
    fam_words = family.replace("_", " ")
    name = title_from_tokens(subject_tokens) or parsed.id
    return _record(
        parsed, type_="building/interior_module", role="interior_module", detail=detail,
        category=["building", "interior"],
        tags=[family.lower(), role],
        description=(
            f"{fam_words} {role} -- sci-fi station/ship interior kit piece. Snap to the interior "
            "kit grid; assembles with other Bld_ pieces to build station or ship interiors."
        ),
        ai_notes=(
            f"Interior kit module ({role}). Use inside station/ship interiors only, not on exterior "
            "building facades. Snap to the kit grid; do not scale."
        ),
        placement=deepcopy(_INTERIOR_MODULE_PLACEMENT), module=module, name=name,
    )


def _infer_bld(parsed: ParsedName) -> dict | None:
    if not parsed.id.upper().startswith("SM_BLD_"):
        return None
    subject = parsed.subject_tokens
    result = bld_exterior_family(subject)
    if result is not None:
        family, remaining = result
        return _infer_exterior_bld(parsed, family, remaining)
    if is_interior_bld(subject):
        return _infer_interior_bld(parsed, subject)
    return None


# --- SM_Env_* (space environment dressing) -------------------------------------

_ENV_SCIFI_PLACEMENT = {
    "mount": "free", "height": "n/a", "orientation": "random", "attachment": "origin",
    "preferred_floors": [], "constraints": ["do_not_scale"],
    "preferred_contexts": ["space"],
}


def _infer_env_scifi(parsed: ParsedName) -> dict | None:
    if not parsed.id.upper().startswith("SM_ENV_"):
        return None
    joined = "".join(t.lower() for t in parsed.subject_tokens)
    if "asteroid" in joined or "astroid" in joined:
        role, detail = "celestial", "asteroid"
    elif "planet" in joined:
        role, detail = "celestial", "planet"
    elif "debris" in joined:
        role, detail = "debris", "debris"
    elif "rubble" in joined:
        role, detail = "debris", "rubble"
    else:
        return None
    name = title_from_tokens(parsed.subject_tokens) or parsed.id
    return _record(
        parsed, type_="environment", role=role, detail=detail,
        category=["environment", "space"], tags=[detail, "space"],
        description=f"{name} -- deep-space {detail} dressing. Scatter freely; no grid or footprint constraints.",
        ai_notes=f"Space environment {detail}. Place at any scale/orientation to fill the backdrop.",
        placement=deepcopy(_ENV_SCIFI_PLACEMENT), name=name,
    )


# --- specific SM_Prop_* families (turret / greeble / interior props) ----------

_TURRET_PLACEMENT = {
    "mount": "socket", "height": "n/a", "orientation": "align_to_parent", "attachment": "socket",
    "preferred_floors": [], "constraints": ["mount_on_hull_or_roof"],
    "preferred_contexts": ["ship_hull", "station", "defense"],
}
_GREEBLE_PLACEMENT = {
    "mount": "wall", "height": "n/a", "orientation": "align_to_parent", "attachment": "back_side",
    "preferred_floors": [], "constraints": ["surface_detail", "do_not_use_as_structure"],
    "preferred_contexts": ["hull_surface", "station_interior"],
}
# token -> (mount, attachment, detail, role)
_INTERIOR_PROP_SPEC = {
    "screen": ("wall", "back_side", "screen", "interior_prop"),
    "controlpanel": ("wall", "back_side", "control_panel", "interior_prop"),
    "buttons": ("wall", "back_side", "buttons", "interior_prop"),
    "light": ("ceiling", "bottom", "light", "interior_prop"),
    "wires": ("wall", "back_side", "wires", "interior_prop"),
    "hose": ("wall", "back_side", "hose", "interior_prop"),
    "bed": ("ground", "base_to_ground", "bed", "interior_prop"),
    "crate": ("ground", "base_to_ground", "crate", "container"),
    "medical": ("ground", "base_to_ground", "medical_equipment", "interior_prop"),
    "foodpacket": ("ground", "base_to_ground", "food_packet", "interior_prop"),
}


def _infer_prop_scifi(parsed: ParsedName) -> dict | None:
    if not parsed.id.upper().startswith("SM_PROP_"):
        return None
    subject = parsed.subject_tokens
    name = title_from_tokens(subject) or parsed.id
    # Exact-token / adjacent-bigram keys only -- NOT a naive substring check
    # against the fully concatenated stem. A plain `"bed" in joined` false-
    # positives on e.g. "SM_Prop_Barbed_Wire_01" ("bar-BED-wire") because
    # "bed" happens to appear mid-word once every token is glued together.
    # Bigrams keep multi-token keys like "controlpanel"/"foodpacket" working.
    token_keys = [t.lower() for t in subject]
    token_keys += ["".join(token_keys[i : i + 2]) for i in range(len(token_keys) - 1)]

    if "sign" in token_keys:
        # "SM_Prop_Sign_Medical_01" / "SM_Prop_Sign_Light_01" etc. would
        # otherwise match the "medical"/"light" interior-prop keys below and
        # lose their prop/signage typing entirely. Signage always belongs to
        # the legacy sign path (or a CURATED entry), never this vocabulary.
        return None
    if "turret" in token_keys:
        return _record(
            parsed, type_="weapon", role="weapon", detail="turret",
            category=["weapon", "turret"], tags=["turret", "weapon", "defense"],
            description=f"{name} -- mounted defense turret. Socket onto a ship hull or station roof hardpoint.",
            ai_notes="Mount at a hull or roof hardpoint. Orient to cover the expected threat arc.",
            placement=deepcopy(_TURRET_PLACEMENT), name=name,
        )
    if "greeble" in token_keys or "detail" in token_keys:
        return _record(
            parsed, type_="prop", role="facade_dressing", detail="greeble",
            category=["prop", "greeble"], tags=["greeble", "hull_detail"],
            description=f"{name} -- small hull/interior surface greeble. Scatter on flat panels for visual detail; do not use as structure.",
            ai_notes="Surface dressing only -- scatter on hull or interior wall panels, never load-bearing.",
            placement=deepcopy(_GREEBLE_PLACEMENT), name=name,
        )
    for key, (mount, attach, detail, role) in _INTERIOR_PROP_SPEC.items():
        if key in token_keys:
            placement = {
                "mount": mount, "height": "n/a",
                "orientation": "upright" if mount == "ground" else "align_to_parent",
                "attachment": attach, "preferred_floors": [1] if mount == "ground" else [],
                "constraints": [], "preferred_contexts": ["station_interior", "ship_interior"],
            }
            return _record(
                parsed, type_="prop", role=role, detail=detail,
                category=["prop", "interior"], tags=[detail, "interior"],
                description=f"{name} -- interior station/ship {detail.replace('_', ' ')} prop.",
                ai_notes=f"Interior dressing ({detail.replace('_', ' ')}). Use inside station/ship interiors.",
                placement=placement, name=name,
            )
    return None


def _infer_chr_attach(parsed: ParsedName) -> dict | None:
    if not parsed.id.upper().startswith("SM_CHR_ATTACH_"):
        return None
    name = title_from_tokens(parsed.subject_tokens) or parsed.id
    subject_l = [t.lower() for t in parsed.subject_tokens]
    joined = "_".join(subject_l)
    tags = ["character_attach", "rig", "wardrobe"]
    detail = "attach_point"
    part = empty_part()
    gear_kind: str | None = "other"
    gear_slot: str | None = "none"
    part_class_hint = None
    slot_map = (
        (("helmet",), "helmet", "head", "armor", "helmet"),
        (("hat", "beanie", "cap"), "hat", "head", "clothing", "clothing"),
        (("visor",), "visor", "head", "armor", "armor"),
        (("headset", "comm", "radio"), "headset", "head", "gadget", "gadget"),
        (("hair", "beard", "brow"), "hair", "head", None, "other"),
        (("mask",), "mask", "face", "armor", "armor"),
        (("head", "face"), "head", "head", None, "other"),
        (("backpack", "pack", "bag", "cage"), "backpack", "back", "pack", "pack"),
        (("shoulder", "pad"), "shoulder", "shoulder", "armor", "armor"),
        (("belt", "hip", "holster"), "belt", "belt", None, "other"),
        (("boot", "shoe", "foot"), "boots", "feet", "clothing", "clothing"),
        (("glove", "hand"), "gloves", "hand", "clothing", "clothing"),
        (("armor", "chest", "vest", "plate"), "armor", "torso", "armor", "armor"),
        (("suit",), "suit", "torso", "armor", "armor"),
        (("tool", "wrench", "scanner"), "tool", "hand_r", None, "tool"),
        (("implant", "cyber"), "implant", "implant", None, "implant"),
    )
    for keys, kind_tag, slot_tag, part_class, gkind in slot_map:
        if any(k in joined for k in keys):
            tags.extend([kind_tag, f"slot_{slot_tag}"])
            detail = kind_tag
            gear_slot = "none" if slot_tag == "hand" else slot_tag
            part["attach_bone"] = slot_tag
            gear_kind = gkind
            part_class_hint = part_class
            if part_class == "armor":
                part["class"] = "armor"
                tags.append("armor")
            elif part_class == "pack":
                tags.append("pack")
            elif part_class == "clothing":
                tags.append("clothing")
            elif part_class == "gadget":
                tags.extend(["gadget", "comms"])
            elif gkind == "tool":
                tags.append("tool")
            elif gkind == "implant":
                tags.append("implant")
            break
    else:
        tags.append("slot_none")
    for hint in ("miner", "mining", "civilian", "crew", "merc", "soldier", "medic", "scav", "eva", "space", "vacuum"):
        if hint in joined or hint in subject_l:
            tags.append("miner" if hint == "mining" else hint)
    sealed = "space" in tags or "eva" in tags or "vacuum" in tags or "suit" in joined
    if sealed:
        tags.append("coverage_sealed")
    paint = _paint_family_from_tokens(list(parsed.subject_tokens) + list(parsed.tokens))
    if paint:
        tags.append(f"paint_{paint}")
    coverage = _coverage_from_hints(
        tags=tags,
        tokens=parsed.subject_tokens,
        sealed=sealed,
        armorish=gear_kind in {"armor", "helmet"} or part_class_hint == "armor",
        clothingish=gear_kind == "clothing",
    )
    gear = _make_gear(
        kind=gear_kind or "other",
        slot=gear_slot,
        fits="any",
        coverage=coverage,
        role="wardrobe",
        attach=True,
        paint_family=paint,
    )
    return _record(
        parsed, type_="character/part", role="character_part", detail=detail,
        category=["character", "attachment", "wardrobe"], tags=_unique_tags(tags),
        description=f"{name} -- character attachment ({detail}). Parents to a character rig bone; not placed directly in a scene.",
        ai_notes="Attach to the matching character rig socket. Wardrobe item, not a whole-character preset.",
        placement=deepcopy(_SOCKET_PLACEMENT), part=part, gear=gear, name=name,
    )


def _infer_chr_preset(parsed: ParsedName) -> dict | None:
    """POLYGON whole-character prefabs (SM_Chr_* excluding Attach) = presets, not wardrobe."""
    up = parsed.id.upper()
    if not up.startswith("SM_CHR_") or up.startswith("SM_CHR_ATTACH_"):
        return None
    subject_l = [t.lower() for t in parsed.subject_tokens]
    joined = "_".join(subject_l)
    name = title_from_tokens(parsed.subject_tokens) or parsed.id
    tags = ["character", "preset"]
    fits = "any"
    if "alien" in joined:
        fits = "alien"
        tags.append("alien")
    elif "android" in joined or "robot" in joined or "robo" in joined:
        fits = "robot"
        tags.append("robot")
    else:
        fits = "human"
    tags.append(f"fits_{fits}")
    for hint in ("crew", "miner", "mining", "civilian", "merc", "soldier", "medic", "scav", "space", "suit", "dead"):
        if hint in joined or hint in subject_l:
            tags.append("miner" if hint == "mining" else hint)
    sealed = "suit" in joined or "space" in joined
    if sealed:
        tags.append("coverage_sealed")
    paint = _paint_family_from_tokens(list(parsed.subject_tokens) + list(parsed.tokens))
    if paint:
        tags.append(f"paint_{paint}")
    coverage = _coverage_from_hints(tags=tags, tokens=parsed.subject_tokens, sealed=sealed)
    gear = _make_gear(
        kind="other",
        slot="none",
        fits=fits,
        coverage=coverage,
        role="preset",
        attach=False,
        paint_family=paint,
    )
    return _record(
        parsed, type_="character", role="character", detail="preset",
        category=["character", "preset"], tags=_unique_tags(tags),
        description=f"{name} -- whole-character preset prefab. Place as a complete NPC/actor; not a modular wardrobe piece.",
        ai_notes="Character preset (full body). Do not treat as attachable clothing/armor; use Chr_Attach_* for wardrobe.",
        placement=deepcopy(GROUND_PROP), name=name, placeable=True, gear=gear,
    )


_SIGNBORDER_PLACEMENT = {
    "mount": "wall", "height": "eye_level", "orientation": "outward_facing", "attachment": "back_side",
    "preferred_floors": [1], "constraints": ["attach_to_wall_near_door"],
    "preferred_contexts": ["station_interior", "ship_interior"],
}


def _infer_hud_icon_signborder(parsed: ParsedName) -> dict | None:
    up = parsed.id.upper()
    if up.startswith("SM_HUD_") or up.startswith("SM_ICON_"):
        subject = [t for t in parsed.subject_tokens if t.lower() != "hud"]
        name = title_from_tokens(subject) or parsed.id
        return _record(
            parsed, type_="ui/icon", role="ui_element", detail="hud_icon",
            category=["ui", "icon"], tags=["ui", "icon", "hud"],
            description=f"{name} -- HUD/UI icon texture or mesh. Not a scene object; used in screen-space UI only.",
            ai_notes="UI element. Never place in a 3D scene.",
            placement=deepcopy(_UI_PLACEMENT), name=name,
        )
    if up.startswith("SM_SIGNBORDER_"):
        subject = [t for t in parsed.subject_tokens if t.lower() != "signborder"]
        detail = "_".join(t.lower() for t in subject) or "icon"
        name = f"{title_from_tokens(subject) or detail.title()} Sign"
        return _record(
            parsed, type_="prop/signage", role="wayfinding", detail=detail,
            category=["sign", "wayfinding"], tags=["wayfinding", "station_signage", detail],
            description=f"{name} -- bordered wayfinding/functional signage icon for station interiors.",
            ai_notes="Interior wayfinding sign. Mount on a wall near the relevant door/room.",
            placement=deepcopy(_SIGNBORDER_PLACEMENT), name=name,
        )
    return None


# --- SM_Gen_<Family>_* wrapper (PolygonGeneric's shared kit) -------------------

_GEN_INNER_FAMILY_TOKENS = {"ENV", "PROP", "BLD", "VEH", "WEP", "CHR", "CHARACTER", "CHAR", "ITEM"}


def _infer_gen_wrapper(parsed: ParsedName) -> dict | None:
    """PolygonGeneric ships its whole shared kit re-prefixed one level
    deeper than every other pack: ``SM_Gen_Env_*``, ``SM_Gen_Prop_*``,
    ``SM_Gen_Bld_*``, ``SM_Gen_Chr_Attach_*``, ``SM_Gen_Wep_*`` ...
    ``parse_name`` only ever consumes the *first* family token, so a raw
    ``SM_Gen_*`` stem gets stuck at family=GEN / kind="generic" and never
    reaches the Env/Prop/Bld/Chr/Wep vocabulary below (which every other
    pack's stems hit directly). Strip the "Gen" token, re-parse and
    re-dispatch on the resulting synthetic stem (e.g.
    ``SM_Gen_Chr_Attach_Beanie_01`` -> ``SM_Chr_Attach_Beanie_01``), then
    stamp the real id/tokens back onto the result so callers still see the
    asset's actual filename-derived identity.

    Known gap (see brief report): this makes ``SM_Gen_Env_Rubble_*``
    resolve through ``_infer_env_scifi`` as deep-space debris even inside a
    ground-war pack -- ``infer()`` has no pack context to disambiguate, and
    narrowing that rule risks the SciFi_Space vocabulary it exists for.
    """
    if parsed.family != "GEN" or not parsed.subject_tokens:
        return None
    inner = parsed.subject_tokens[0].upper()
    if inner not in _GEN_INNER_FAMILY_TOKENS:
        return None
    gen_index = next(i for i, t in enumerate(parsed.tokens) if t.upper() == "GEN")
    synthetic_tokens = parsed.tokens[:gen_index] + parsed.tokens[gen_index + 1 :]
    synthetic_id = "_".join(synthetic_tokens)
    synthetic_parsed = parse_name(synthetic_id)
    if synthetic_parsed.family == "GEN":
        return None  # malformed input; guards against re-entering this rule
    rec = _dispatch(synthetic_parsed)
    rec["id"] = parsed.id
    rec["parsed"] = replace(synthetic_parsed, id=parsed.id)
    return rec


_SCIFI_SPACE_RULES = (
    _infer_gen_wrapper,
    _infer_vehicle_part,
    _infer_spacecraft,
    _infer_weapon,
    _infer_mech,
    _infer_veh_military,
    _infer_bld,
    _infer_env_scifi,
    _infer_prop_scifi,
    _infer_chr_preset,
    _infer_chr_attach,
    _infer_hud_icon_signborder,
)


def _infer_legacy(parsed: ParsedName) -> dict:
    extra = _merge_token_knowledge(parsed.subject_tokens + parsed.tokens)
    ptype = TYPE_BY_KIND.get(parsed.kind, "prop")
    if "sign" in {_norm_token(t) for t in parsed.tokens} and not _is_attachment(
        {_norm_token(t) for t in parsed.tokens}
    ):
        ptype = "prop/signage"

    name_tokens = parsed.subject_tokens or parsed.tokens
    name = title_from_tokens(name_tokens) or parsed.id
    if ptype == "prop/signage" and "sign" not in name.lower() and "pole" not in name.lower():
        name = f"{name} Sign"
    category = list(extra["category"])
    if ptype == "prop/signage" and "sign" not in category:
        category.insert(0, "sign")
    if parsed.kind == "building" and "building" not in category:
        category.insert(0, "building")
    tags = list(extra["tags"])
    if parsed.family in {"ANIMAL", "ANIMALS"}:
        # The family token is consumed by parse_name; keep it searchable.
        tags.insert(0, "animal")
        if "animal" not in category:
            category.insert(0, "animal")
    for t in parsed.subject_tokens:
        tl = t.lower()
        if tl not in tags and not tl.isdigit() and _SAFE_TAG_RE.fullmatch(tl):
            tags.append(tl)

    placement = _placement_for(parsed, extra)
    if placement.get("mount") == "wall" and "wall-mounted" not in category:
        category.append("wall-mounted")

    if _is_large_icon(parsed):
        dims = [2.5, 2.5, 1.2]
    elif _is_billboard({_norm_token(t) for t in parsed.tokens}):
        dims = [6.0, 3.0, 0.4]
    elif parsed.kind == "sign":
        dims = [1.2, 0.6, 0.12]
    else:
        dims = list(DIM_HINTS.get(ptype, [1.0, 1.0, 1.0]))

    return {
        "id": parsed.id,
        "name": name,
        # TYPE_BY_KIND already emits v2 "building/module". TYPE_MIGRATION
        # remains for any leftover v1 alias (on-disk catalogs, or a rule
        # that still speaks "building/modular").
        "type": TYPE_MIGRATION.get(ptype, ptype),
        "category": category,
        "tags": tags,
        "description": _description(parsed, name, extra, ptype),
        "semantic_role": _semantic_role(parsed, extra),
        "placement": placement,
        "dimensions_hint": dims,
        "ai_notes": _ai_notes(parsed, extra, ptype),
        "parsed": parsed,
    }


def _dispatch(parsed: ParsedName) -> dict:
    """Run the full rule chain against an already-parsed name. Split out
    from ``infer()`` so ``_infer_gen_wrapper`` can re-dispatch on a
    synthetic ``ParsedName`` (the Gen-token-stripped stem) without a
    round-trip through ``parse_name`` twice or duplicating the chain.
    """
    if parsed.id in CURATED:
        return _infer_curated(parsed)
    rec = _infer_nonplaceable(parsed)
    if rec is not None:
        return rec
    for fn in _SCIFI_SPACE_RULES:
        rec = fn(parsed)
        if rec is not None:
            return rec
    return _infer_legacy(parsed)


def infer(asset_id: str) -> dict:
    return _dispatch(parse_name(asset_id))
