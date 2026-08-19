---
name: synty-inventory
description: >
  Search, select and assemble Synty POLYGON pack assets for Unity, Unreal,
  Godot or three.js from one engine-neutral catalog: what a sign depicts, how
  it mounts, measured bounds, kit family/role for modular buildings, ship-part
  class/mating axis, and recipes (building grammars, ship kits, street rows).
  Use when dressing a scene with Synty pieces, procedurally assembling
  buildings / city blocks / spaceships from modules, or when the user runs
  /synty-inventory.
---

# Synty Pack Inventory

Do not place Synty assets from the filename alone. Query `synty-inventory`,
obey `placement`, `bounds`, `module` / `part` and the recipe constraints.
One catalog serves every engine: `--engine unity|unreal|godot|threejs` only
selects which `files.*` path is printed; semantics never change.

## Command

```
synty-inventory <tool> [args]
```

(`python -m synty_inventory` is the same.) Every command prints JSON. Roots
come from `config.yaml` (copied from `config.example.yaml`) or `SYNTI_*` env
vars — never hardcode drive paths and never pass `--out` / a scan root unless
the user asked to override.

```
synty-inventory config
```

prints the resolved `unity_root`, `extracted_root`, `catalogs`, `viewer_data`,
`threejs_v2`. If the command is missing, `pip install -r requirements.txt`
from the synty-inventory checkout. If catalogs are missing, `synty-inventory
scan` first (`scan --rebuild` after rule/precedence changes).

## Tools

| Purpose | CLI |
|---|---|
| packs on disk | `list-packs` |
| find pieces | `search QUERY [--pack P] [--type T] [--role R] [--module-role M] [--part-class C] [--tags a,b] [--category sign] [--constraints exterior_only] [--engine E] [--include-nonplaceable]` |
| one record | `details ID` |
| context → recipe pointer + ranked pieces | `suggest "fighter space ship" [--pack P] [--engine E]` → `{"recipes":[…],"assets":[…]}` (`--assets-only` for a bare list) |
| how to mount it | `placement ID` |
| all grammars | `recipes [--pack P]` |
| resolve a grammar to pieces with bounds + files | `recipe ID [--pack P] [--engine E] [--limit N]` (exit 4 when a required step has no candidates) |
| modular family grouped by role | `kit Apartment` / `kit "*"` |

## Record fields that matter

- `placeable` / `kind` — `false` means clip / HUD / skeleton / skybox: never place. Default queries hide them.
- `type` — `building/shell`, `building/interior_module`, `vehicle/spacecraft`, `vehicle/part`, `sign`, `prop`, …
- `semantic_role` + `semantic_detail` — `building_identity` / `police_station`, `advertisement` / `displays_burger`, `vehicle_part` / `engine`.
- `bounds` — `{min,max,size,pivot,source}` metres, measured from the mesh. `null` = unmeasured (fall back to `size_hint`, and say so). `pivot` tells you whether the origin is `bottom_center`, `center`, `corner`, …
- `module` — `family`, `role` (`hero|shell|corner|door|roof|stairs|floor|base`), `footprint_class`, `stackable_on`, `street_side`.
- `part` — `class` (`body|cockpit|engine|wing|gear|greeble`), `mates_axis` (`-z` engine → rear socket of the body), `symmetric`, `size_class`, `mount` (this part's own attachment face: `axis`, `position`, `normal`, `fit`, `source`) and, on `body` hulls, `sockets[]` (`role` front/rear/left/right/top/bottom + the same fields). `source: measured` is a flat cap found in the mesh; `aabb` is the face-centre fallback — trust it less. Positions are local metres, same space as `bounds`.
- `files` — `unity_prefab`, `unity_mesh`, `glb` (+ `glb_node` inside bundle GLBs), `unreal_uasset`, `godot_scene`. `paths` is the v1 alias.
- Catalog `grid.snap` is 0.25 m; `conventions.street_axis` is `+z`; scale is always 1.0.

## How to assemble (buildings, blocks, ships)

1. `suggest "<what the user wants>"`. If `recipes` is non-empty, take the first id.
2. `recipe <id> --pack <pack> --engine <engine>`. Each `resolved_steps[]` entry has `role`, `count`, `layout`, `required`, `note` and `eligible[]` pieces with `bounds` and `files`. Stop and report if `complete` is false.
3. Place step by step using `bounds.size` to stack / tile, `grid.snap` for positions, the recipe `constraints` (`do_not_scale`, `engines_at_rear`, `mirror_wings_in_pairs`, `one_identity_sign_per_frontage`, …) as hard rules.
4. Modular buildings: `kit <family>` gives the family grouped by role — base → floors × n → roof, corners on corners, doors at street level, stairs/fire escapes on the blank side. Only `hero` shells stand alone.
5. Ship kits: one `body`, `cockpit` at +Z, engines at -Z, wings in mirrored ± X pairs, gear under -Y. Place each child at `body_pos + body.part.sockets[role].position - child.part.mount.position`, child unrotated (its `mount.normal` already opposes the socket normal); overlap the hull by 0.1–0.3 m when `mount.fit` is low or `source` is `aabb`. If `sockets`/`mount` are null, fall back to `bounds` faces. Whole `SM_Ship_*` are references, not parts.
6. Instantiate the file for the target engine at authored scale.

## How to pick and place a single piece

1. `search` / `suggest` for the context (`police station facade`, `first-floor barber pole`).
2. `details` on the chosen id — read `semantic_role`, `description`, `bounds`.
3. `placement` before instantiating: `mount` `wall` → attach via `attachment` (`back_side` / `side_bracket`) to the street facade; honour `preferred_floors`, `constraints` (`exterior_only`, `do_not_cover_windows`, `civic_facade_only`, `roadway_view`) and `preferred_contexts`.
4. One identity sign per frontage.

## Quality checks

- Police identity → `SM_Prop_Sign_Police_01` (white channel letters, wall, above the door, floors 1–2).
- Barber identity → `SM_Prop_Sign_Barber_01` (side-bracket pole, floor 1, beside the door).
- `recipe ship_kit` must be `complete`; every part has `part.class`, measured `bounds`, and a `part.mount` (hulls: six `part.sockets`).
- Do not use `PolygonGeneric` trees/roads as building heroes; do not place `placeable: false` records.
- Do not treat `*_Convex` / `Collisions/` as renderables (the scanner already drops them).
- `synty-inventory gauntlet` must stay all-green after any catalog change.
