"""Rule-based Synty semantics: names → type, tags, placement, notes.

This is the offline enrichment quality bar. Special-cased high-value
assets (signs, attachments, civic identity) match the Police Sign /
Barber Pole richness in the inventory spec.
"""

from __future__ import annotations

from copy import deepcopy

from .naming import ParsedName, parse_name, title_from_tokens

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

# token → extra tags / contexts (lowercase)
TOKEN_TAGS: dict[str, dict] = {
    "police": {
        "tags": ["police", "facade", "station", "law_enforcement", "civic"],
        "contexts": ["police_station", "civic_building"],
        "category": ["civic"],
    },
    "barber": {
        "tags": ["barber", "salon", "pole", "commercial", "facade"],
        "contexts": ["barber_shop", "salon"],
        "category": ["commercial"],
    },
    "hospital": {
        "tags": ["hospital", "medical", "civic", "facade"],
        "contexts": ["hospital", "clinic", "civic_building"],
        "category": ["civic"],
    },
    "firedepartment": {
        "tags": ["fire", "fire_department", "civic", "facade"],
        "contexts": ["fire_station", "civic_building"],
        "category": ["civic"],
    },
    "fire": {
        "tags": ["fire", "civic"],
        "contexts": ["fire_station"],
        "category": ["civic"],
    },
    "cafe": {
        "tags": ["cafe", "coffee", "food", "commercial"],
        "contexts": ["cafe", "coffee_shop"],
        "category": ["commercial", "food"],
    },
    "hotel": {
        "tags": ["hotel", "lodging", "commercial"],
        "contexts": ["hotel"],
        "category": ["commercial"],
    },
    "bar": {
        "tags": ["bar", "nightlife", "alcohol"],
        "contexts": ["bar", "pub", "nightlife"],
        "category": ["commercial", "nightlife"],
    },
    "pub": {
        "tags": ["pub", "bar", "nightlife", "alcohol"],
        "contexts": ["pub", "bar"],
        "category": ["commercial", "nightlife"],
    },
    "pizza": {
        "tags": ["pizza", "food", "restaurant"],
        "contexts": ["pizzeria", "restaurant"],
        "category": ["commercial", "food"],
    },
    "delipizza": {
        "tags": ["deli", "pizza", "food"],
        "contexts": ["deli", "pizzeria"],
        "category": ["commercial", "food"],
    },
    "noodles": {
        "tags": ["noodles", "food", "chinese"],
        "contexts": ["noodle_shop", "restaurant"],
        "category": ["commercial", "food"],
    },
    "chinese": {
        "tags": ["chinese", "food"],
        "contexts": ["restaurant"],
        "category": ["food"],
    },
    "xxx": {
        "tags": ["adult", "vice", "nightlife"],
        "contexts": ["adult_venue", "nightlife"],
        "category": ["nightlife"],
    },
    "beer": {"tags": ["beer", "alcohol", "bar"], "contexts": ["bar"], "category": ["nightlife"]},
    "bottle": {"tags": ["bottle", "alcohol"], "contexts": ["bar"], "category": ["nightlife"]},
    "burger": {"tags": ["burger", "food"], "contexts": ["fast_food"], "category": ["food"]},
    "hotdog": {"tags": ["hotdog", "food"], "contexts": ["fast_food", "street_food"], "category": ["food"]},
    "coffee": {"tags": ["coffee", "cafe"], "contexts": ["cafe"], "category": ["food"]},
    "donut": {"tags": ["donut", "food"], "contexts": ["bakery", "cafe"], "category": ["food"]},
    "icecream": {"tags": ["ice_cream", "food"], "contexts": ["ice_cream_shop"], "category": ["food"]},
    "milkshake": {"tags": ["milkshake", "food"], "contexts": ["diner"], "category": ["food"]},
    "soda": {"tags": ["soda", "drink"], "contexts": ["shop"], "category": ["food"]},
    "taco": {"tags": ["taco", "food"], "contexts": ["restaurant"], "category": ["food"]},
    "popcorn": {"tags": ["popcorn", "cinema"], "contexts": ["cinema"], "category": ["entertainment"]},
    "guitar": {"tags": ["guitar", "music"], "contexts": ["music_shop", "bar"], "category": ["entertainment"]},
    "bowlingball": {"tags": ["bowling"], "contexts": ["bowling_alley"], "category": ["entertainment"]},
    "bowlingpin": {"tags": ["bowling"], "contexts": ["bowling_alley"], "category": ["entertainment"]},
    "lollypop": {"tags": ["candy", "food"], "contexts": ["shop"], "category": ["food"]},
    "billboard": {
        "tags": ["billboard", "advertisement", "roadside"],
        "contexts": ["roadside", "commercial_strip"],
        "category": ["sign", "advertisement"],
    },
    "neon": {"tags": ["neon", "nightlife", "facade"], "contexts": ["nightlife", "shop"], "category": ["sign"]},
    "ad": {"tags": ["advertisement", "poster"], "contexts": ["facade"], "category": ["sign", "advertisement"]},
    "poster": {"tags": ["poster", "advertisement"], "contexts": ["facade", "interior"], "category": ["sign"]},
    "apartment": {
        "tags": ["apartment", "residential", "modular"],
        "contexts": ["residential_block"],
        "category": ["building", "residential"],
    },
    "shop": {
        "tags": ["shop", "storefront", "commercial"],
        "contexts": ["shop", "retail"],
        "category": ["building", "commercial"],
    },
    "office": {
        "tags": ["office", "commercial"],
        "contexts": ["office"],
        "category": ["building", "commercial"],
    },
    "bank": {"tags": ["bank", "civic", "commercial"], "contexts": ["bank"], "category": ["building", "civic"]},
    "warehouse": {"tags": ["warehouse", "industrial"], "contexts": ["industrial"], "category": ["building", "industrial"]},
    "hangar": {"tags": ["hangar", "industrial", "aircraft"], "contexts": ["airfield"], "category": ["building"]},
    "station": {"tags": ["station", "transit", "civic"], "contexts": ["transit_station"], "category": ["building"]},
    "cityhall": {"tags": ["city_hall", "civic"], "contexts": ["civic_building"], "category": ["building", "civic"]},
    "road": {"tags": ["road", "street", "city-layout"], "contexts": ["street"], "category": ["environment", "road"]},
    "sidewalk": {"tags": ["sidewalk", "city-layout"], "contexts": ["street"], "category": ["environment"]},
    "curb": {"tags": ["curb", "city-layout"], "contexts": ["street"], "category": ["environment"]},
    "tree": {"tags": ["tree", "foliage"], "contexts": ["park", "street"], "category": ["environment"]},
    "vehicle": {"tags": ["vehicle"], "contexts": ["street"], "category": ["vehicle"]},
    "car": {"tags": ["car", "vehicle"], "contexts": ["street", "parking"], "category": ["vehicle"]},
    "barrier": {"tags": ["barrier", "security"], "contexts": ["checkpoint", "construction"], "category": ["prop"]},
    "door": {"tags": ["door", "opening"], "contexts": ["building"], "category": ["building", "opening"]},
    "window": {"tags": ["window", "opening"], "contexts": ["building"], "category": ["building", "opening"]},
    "aircon": {"tags": ["hvac", "roof", "utility"], "contexts": ["roof"], "category": ["prop"]},
    "satdish": {"tags": ["satellite", "roof", "loose-roof"], "contexts": ["roof"], "category": ["prop"]},
    "securitycamera": {"tags": ["camera", "security", "facade"], "contexts": ["facade"], "category": ["prop"]},
    "streetlight": {"tags": ["streetlight", "lighting", "city-layout"], "contexts": ["street"], "category": ["prop"]},
    "bench": {"tags": ["bench", "street-furniture"], "contexts": ["street", "park"], "category": ["prop"]},
    "dumpster": {"tags": ["dumpster", "street-furniture"], "contexts": ["alley"], "category": ["prop"]},
    "hydrant": {"tags": ["hydrant", "civic"], "contexts": ["street"], "category": ["prop"]},
    "mailbox": {"tags": ["mailbox"], "contexts": ["street"], "category": ["prop"]},
    "parkingmeter": {"tags": ["parking_meter"], "contexts": ["street"], "category": ["prop"]},
    "busstop": {"tags": ["bus_stop", "transit"], "contexts": ["street", "transit"], "category": ["prop"]},
    "bustop": {"tags": ["bus_stop", "transit"], "contexts": ["street", "transit"], "category": ["prop"]},
    "giveway": {"tags": ["give_way", "traffic"], "contexts": ["intersection"], "category": ["sign", "traffic"]},
    "stop": {"tags": ["stop", "traffic"], "contexts": ["intersection"], "category": ["sign", "traffic"]},
    "parking": {"tags": ["parking", "traffic"], "contexts": ["parking"], "category": ["sign", "traffic"]},
    "warning": {"tags": ["warning", "traffic", "safety"], "contexts": ["street", "civic"], "category": ["sign"]},
    "arrow": {"tags": ["arrow", "wayfinding"], "contexts": ["street"], "category": ["sign"]},
    "entrance": {"tags": ["entrance", "wayfinding"], "contexts": ["building"], "category": ["sign"]},
    "street": {"tags": ["street", "wayfinding"], "contexts": ["street"], "category": ["sign"]},
    "attachment": {"tags": ["attachment", "hardware", "mount"], "contexts": ["facade"], "category": ["hardware"]},
    "chopshop": {"tags": ["chopshop", "industrial", "garage"], "contexts": ["chopshop"], "category": ["building"]},
    "stripclub": {"tags": ["stripclub", "nightlife", "vice"], "contexts": ["nightlife"], "category": ["building"]},
}

# Exact-id curated entries — quality bar for autonomous placement.
CURATED: dict[str, dict] = {
    "SM_Prop_Sign_Police_01": {
        "name": "Police Sign",
        "type": "prop/signage",
        "category": ["sign", "wall-mounted", "civic"],
        "tags": ["police", "facade", "station", "law_enforcement"],
        "description": (
            "Rectangular wall-mounted sign suitable for identifying a police station facade. "
            "Typically shows a police badge or POLICE lettering. Wide, shallow plaque — "
            "seat the back face on the wall above the main entrance, not over windows."
        ),
        "semantic_role": "identifies_building_as_police_station",
        "placement": {
            "mount": "wall",
            "height": "eye_level_to_above_door",
            "orientation": "outward_facing",
            "attachment": "back_side",
            "preferred_floors": [1, 2],
            "constraints": ["exterior_only", "attach_to_building", "do_not_cover_windows"],
            "preferred_contexts": ["police_station", "civic_building"],
        },
        "dimensions_hint": [1.94, 0.55, 0.13],
        "ai_notes": (
            "Use on police station facades. Center above the public entrance on floor 1. "
            "Pairs with barriers, official doors, and a police vehicle at the curb. "
            "Do not put on shops, bars, or apartments."
        ),
    },
    "SM_Prop_Sign_Barber_01": {
        "name": "Barber Pole",
        "type": "prop/signage",
        "category": ["sign", "wall-mounted", "commercial", "pole"],
        "tags": ["barber", "salon", "pole", "facade", "side_mount"],
        "description": (
            "Classic cylindrical barber pole that projects from the facade on a short arm. "
            "Identifies a barber shop or salon. Slim vertical volume — attach the flat back "
            "of the bracket to the wall beside the door, first floor only, leaving sidewalk clearance."
        ),
        "semantic_role": "identifies_building_as_barber_shop",
        "placement": {
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
                "beside_entrance_not_above",
            ],
            "preferred_contexts": ["barber_shop", "salon"],
        },
        "dimensions_hint": [0.32, 0.95, 0.47],
        "ai_notes": (
            "First-floor commercial only. Mount beside the shop door on the street face, "
            "not above windows and not on upper storeys. One pole per frontage. "
            "Pairs with SM_Bld_Shop_* storefronts, not civic buildings."
        ),
    },
}

PACK_STYLES = {
    "POLYGON_City": "lowpoly_modern_city",
    "POLYGON_SciFi_City": "lowpoly_scifi_city",
    "POLYGON_SciFi_Space": "lowpoly_scifi_space",
    "POLYGON_Prototype": "lowpoly_prototype",
    "POLYGON_Starter": "lowpoly_starter",
    "POLYGON_Particle_FX": "lowpoly_vfx",
    "POLYGON_QuadBike": "lowpoly_vehicle",
    "POLYGON_AdultFacePlates": "lowpoly_character",
    "POLYGON_Generic": "lowpoly_generic_kit",
    "POLYGON_Coffee_Shop": "lowpoly_interior",
    "SIDEKICK_SciFi_Soldiers": "lowpoly_character",
    "SIDEKICK_Starter": "lowpoly_character",
    "ANIMATION_Base_Locomotion": "animation",
    "INTERFACE_SciFi_Soldier_HUD": "ui",
    "SIMPLE_Sky": "skybox",
}

TYPE_BY_KIND = {
    "sign": "prop/signage",
    "building": "building/modular",
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
    "building/modular": [5.0, 3.0, 5.0],
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
    if parsed.id in CURATED:
        return deepcopy(CURATED[parsed.id]["placement"])
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
    if parsed.id in CURATED:
        return CURATED[parsed.id]["semantic_role"]
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
        return "populates_scene_as_person"
    if parsed.kind == "environment":
        if "road" in tokens:
            return "forms_drivable_surface"
        if "sidewalk" in tokens:
            return "forms_pedestrian_surface"
        return "dresses_exterior_ground"
    return "dresses_scene"


def _description(parsed: ParsedName, name: str, extra: dict, ptype: str) -> str:
    if parsed.id in CURATED:
        return CURATED[parsed.id]["description"]
    tokens = {_norm_token(t) for t in parsed.tokens}
    bits: list[str] = []
    if ptype == "prop/signage":
        if _is_large_icon(parsed):
            bits.append(f"Large sculpted {name.lower()} meant to sit on a roof or tall facade as a 3D shop identity.")
        elif _is_billboard(tokens):
            bits.append(f"{name} — large roadside or wall advertisement panel. Face the readable side to the roadway.")
        elif _is_neon(tokens):
            bits.append(f"{name} — neon letterform or icon for night facades. Mount on the street face.")
        elif "barber" in tokens:
            bits.append("Cylindrical barber pole that projects from a first-floor shop wall beside the door.")
        elif _is_traffic_sign(tokens):
            bits.append(f"{name} — traffic / wayfinding sign. Place at grade on a pole facing traffic.")
        elif _is_attachment(tokens):
            bits.append("Mounting bracket / attachment hardware for hanging a sign or light off a facade.")
        else:
            bits.append(f"{name} — wall-mounted identity plaque for a building facade.")
        if extra.get("contexts"):
            bits.append("Best on: " + ", ".join(extra["contexts"]) + ".")
        bits.append("Keep off windows; readable from the street.")
    elif ptype == "building/modular":
        bits.append(
            f"{name} — modular Synty building piece. Snap to the pack grid "
            "(typically 2.5–5 m on XZ, ~3 m storey height). Street face is +Z in official kits."
        )
        if extra.get("contexts"):
            bits.append("Role: " + ", ".join(extra["contexts"]) + ".")
    elif ptype == "vehicle":
        bits.append(f"{name} — vehicle. Sit on the road or a parking stall; do not scale; yaw to the lane.")
    elif ptype == "character":
        bits.append(f"{name} — character mesh or prefab. Place on sidewalks or interiors at 1:1 scale.")
    elif ptype == "environment":
        bits.append(f"{name} — environment / ground piece. Use in the city-layout pass, not as a building shell.")
    else:
        bits.append(f"{name} — Synty {ptype.replace('/', ' ')}.")
        if extra.get("contexts"):
            bits.append("Typical context: " + ", ".join(extra["contexts"]) + ".")
    return " ".join(bits)


def _ai_notes(parsed: ParsedName, extra: dict, ptype: str) -> str:
    if parsed.id in CURATED:
        return CURATED[parsed.id]["ai_notes"]
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
            return "Hardware only — pair with a matching sign or light; do not use as the identity piece."
        return "Facade dressing. Prefer the street face; keep a clear read from the sidewalk."
    if ptype == "building/modular":
        return (
            "Assemble on the 0.25 m snap grid. Do not scale. "
            "Do not use sidewalk/road pieces as part of the building shell."
        )
    if "city-layout" in extra.get("tags", []) or parsed.kind == "environment":
        return "City-layout only. The building generator must not emit this as a hero or annex."
    return "Place at authored scale. Prefer official Synty snap (0.25 m) and street axis +Z."


def infer(asset_id: str) -> dict:
    parsed = parse_name(asset_id)
    extra = _merge_token_knowledge(parsed.subject_tokens + parsed.tokens)
    ptype = TYPE_BY_KIND.get(parsed.kind, "prop")
    if parsed.id in CURATED:
        ptype = CURATED[parsed.id]["type"]
    elif "sign" in {_norm_token(t) for t in parsed.tokens} and not _is_attachment(
        {_norm_token(t) for t in parsed.tokens}
    ):
        ptype = "prop/signage"

    if parsed.id in CURATED:
        name = CURATED[parsed.id]["name"]
        category = list(CURATED[parsed.id]["category"])
        tags = list(CURATED[parsed.id]["tags"])
    else:
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
        for t in parsed.subject_tokens:
            tl = t.lower()
            if tl not in tags and not tl.isdigit():
                tags.append(tl)

    placement = _placement_for(parsed, extra)
    if placement.get("mount") == "wall" and "wall-mounted" not in category:
        category.append("wall-mounted")

    dims = None
    if parsed.id in CURATED:
        dims = list(CURATED[parsed.id]["dimensions_hint"])
    elif _is_large_icon(parsed):
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
        "type": ptype,
        "category": category,
        "tags": tags,
        "description": _description(parsed, name, extra, ptype),
        "semantic_role": _semantic_role(parsed, extra),
        "placement": placement,
        "dimensions_hint": dims,
        "ai_notes": _ai_notes(parsed, extra, ptype),
        "parsed": parsed,
    }
