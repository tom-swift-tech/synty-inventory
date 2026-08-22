---
name: synty-inventory
description: >
  Search, select and assemble Synty POLYGON pack assets for Unity, Unreal,
  Godot or three.js from one engine-neutral catalog: what a sign depicts, how
  it mounts, measured bounds, kit family/role for modular buildings, ship-part
  class/mating axis, mech slot/bone attachments, and recipes (building
  grammars, ship kits, mech kits, street rows). Covers the city, sci-fi,
  military/war and crime packs. Use when dressing a scene with Synty pieces,
  procedurally assembling buildings / city blocks / spaceships / mechs from
  modules, or when the user runs /synty-inventory.
---

# Synty Pack Inventory

Do not place Synty assets from the filename alone. Query `synty-inventory`,
obey `placement`, `bounds`, `module` / `part` and the recipe constraints.
One catalog serves every engine: `--engine unity|unreal|godot|threejs` only
selects which `files.*` path is printed; semantics never change.

## Slim rows first, `details` second

Read `<catalogs>/index.json` before anything else: per-pack asset / placeable
/ measured / reviewed counts, kit family names and recipe ids — it answers
"what is here" without a query. Every list verb (`search`, `suggest`,
`recipe`, `kit`) then returns **slim rows** (~200 B):

```
{"id", "pack", "type", "role", "size": [x,y,z] m | null, "file", "score"?}
```

plus, only when the asset has them: `sockets` (ship-hull socket count),
`slots` (mech slot count), `kit` + `kit_role` (module family/role),
`part_class`, `glb_node` (node inside a bundle GLB). `file` is the one path
for the target `--engine` (GLB fallback). Everything else — `description`,
`placement`, `bounds` with pivot, `part` sockets/mount, `mech`
skeleton/slots/variants — lives in the full record: get it with
`details <id>` for the pieces you actually picked, or widen list rows with
`--fields description,placement,part,mech,bounds,files` when you need a
field across many rows. `recipe` caps eligible pieces per step at 16 by
default (`eligible_count` reports the full pool; `--limit N` widens).

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
| find pieces (slim rows) | `search QUERY [--pack P] [--type T] [--role R] [--module-role M] [--part-class C] [--tags a,b] [--category sign] [--constraints exterior_only] [--engine E] [--fields a,b,c] [--include-nonplaceable]` |
| one full record | `details ID` |
| context → recipe pointer + ranked slim rows | `suggest "fighter space ship" [--pack P] [--engine E] [--fields a,b,c]` → `{"recipes":[…],"assets":[…]}` (`--assets-only` for a bare list) |
| how to mount it | `placement ID` |
| all grammars | `recipes [--pack P]` |
| resolve a grammar to slim candidate rows | `recipe ID [--pack P] [--engine E] [--fields a,b,c] [--limit N]` (exit 4 when a required step has no candidates) |
| modular family grouped by role (slim rows) | `kit Apartment` / `kit "*"` `[--pack P] [--engine E] [--fields a,b,c]` |

## Record fields that matter

- `placeable` / `kind` — `false` means clip / HUD / skeleton / skybox: never place. Default queries hide them.
- `type` — `building/shell`, `building/interior_module`, `vehicle/spacecraft`, `vehicle/part`, `sign`, `prop`, …
- `semantic_role` + `semantic_detail` — `building_identity` / `police_station`, `advertisement` / `displays_burger`, `vehicle_part` / `engine`.
- `bounds` — `{min,max,size,pivot,source}` metres, measured from the mesh. `null` = unmeasured (fall back to `size_hint`, and say so). `pivot` tells you whether the origin is `bottom_center`, `center`, `corner`, …
- `module` — `family`, `role` (`hero|shell|corner|door|roof|stairs|floor|base`), `footprint_class`, `stackable_on`, `street_side`.
- `part` — `class` (`body|cockpit|engine|wing|gear|greeble`), `mates_axis` (`-z` engine → rear socket of the body), `symmetric`, `size_class`, `mount` (this part's own attachment face: `axis`, `position`, `normal`, `fit`, `source`, `parent_role` = the hull socket it fits unrotated) and, on `body` hulls, `sockets[]` (`role` front/rear/left/right/top/bottom + the same fields). `source: measured` is a flat cap found in the mesh; `aabb` is the face-centre fallback — trust it less. Positions are local metres, same space as `bounds`. Read `mount.parent_role` rather than assuming the class axis: `Engine_08/09` are pylon pods that mount by their `+x` plate on the `left` socket (mirror for `right`), and wings mount by their root cap on the `right`/`left` socket (`normal` may be tilted — that is the dihedral; place by position, do not rotate it flush).
- `part.slot` + `part.attach_bone` (mech attachments, `SM_Mech_*`) — `slot` is `{region, side l|r|c}` (arm/leg/chest/head/hips/foot/back/hand/cockpit/neck/…); `attach_bone` is the skeleton bone to parent the piece to.
- `mech` (on `SM_Veh_Mech_*` bodies) — `skeleton` (bone names), `slots[]` (`region`, `side`, `bone`, `geo_nodes`), `variants` (factory loadouts → the geo nodes each activates). The master body GLB contains EVERY armor/weapon option as named `geo_*` nodes: assemble either by toggling geo-node visibility to match a `variants` set, or by parenting standalone `SM_Mech_*` attachment GLBs to their `attach_bone`.
- `files` — `unity_prefab`, `unity_mesh`, `glb` (+ `glb_node` inside bundle GLBs), `unreal_uasset`, `godot_scene`. `paths` is the v1 alias.
- Catalog `grid.snap` is 0.25 m; `conventions.street_axis` is `+z`; scale is always 1.0.

## How to assemble (buildings, blocks, ships)

1. `suggest "<what the user wants>"`. If `recipes` is non-empty, take the first id.
2. `recipe <id> --pack <pack> --engine <engine>`. Each `resolved_steps[]` entry has `role`, `count`, `layout`, `required`, `note` and `eligible[]` slim rows (id, size, file). Stop and report if `complete` is false. Pick pieces from the slim rows, then `details <id>` (or re-run with `--fields part,mech,bounds`) for the sockets/mounts/pivots of the pieces you chose.
3. Place step by step using `bounds.size` to stack / tile, `grid.snap` for positions, the recipe `constraints` (`do_not_scale`, `engines_at_rear`, `mirror_wings_in_pairs`, `one_identity_sign_per_frontage`, …) as hard rules.
4. Modular buildings: `kit <family>` gives the family grouped by role — base → floors × n → roof, corners on corners, doors at street level, stairs/fire escapes on the blank side. Only `hero` shells stand alone.
5. Ship kits: one `body`, `cockpit` at +Z, engines at -Z, wings in mirrored ± X pairs, gear under -Y. Slim rows carry only the socket count — `details` on the hull and each chosen child gives `part.sockets` / `part.mount`. Put each child on the socket named by its `mount.parent_role` (mirror the copy for the opposite side): `body_pos + body.part.sockets[role].position - child.part.mount.position`, child unrotated (its `mount.normal` already opposes the socket normal; greebles may instead be rotated so `mount.normal == -socket.normal` onto any face); overlap the hull by 0.1–0.3 m when `mount.fit` is low or `source` is `aabb`. If `sockets`/`mount` are null, fall back to `bounds` faces. Whole `SM_Ship_*` are references, not parts.
6. Mech kits (`recipe mech_kit`): pick ONE `SM_Veh_Mech_*` body (`details` it for `mech.skeleton/slots/variants`), then either (a) load the master body GLB and set geo-node visibility to one of `mech.variants` (mix regions across variants freely — every combination is factory-compatible per slot), or (b) parent standalone attachment GLBs to `part.attach_bone` with identity local transform (pieces are authored in bone space). `l`/`r` slots come in mirrored pairs — fill both. One cockpit, one head; weapons go on `hand`/`chest` slots.
7. Instantiate the file for the target engine at authored scale.

## How to pick and place a single piece

1. `search` / `suggest` for the context (`police station facade`, `first-floor barber pole`).
2. `details` on the chosen id — the full record: `description`, `bounds` with pivot, `placement`, `part`, `mech`.
3. `placement` before instantiating: `mount` `wall` → attach via `attachment` (`back_side` / `side_bracket`) to the street facade; honour `preferred_floors`, `constraints` (`exterior_only`, `do_not_cover_windows`, `civic_facade_only`, `roadway_view`) and `preferred_contexts`.
4. One identity sign per frontage.

## Quality checks

- Police identity → `SM_Prop_Sign_Police_01` (white channel letters, wall, above the door, floors 1–2).
- Barber identity → `SM_Prop_Sign_Barber_01` (side-bracket pole, floor 1, beside the door).
- `recipe ship_kit` must be `complete`; every part has `part.class`, measured `bounds`, and a `part.mount` (hulls: six `part.sockets`).
- `recipe mech_kit` must be `complete`; every `SM_Mech_*` attachment has `part.slot` + `part.attach_bone`; bodies carry `mech.skeleton/slots/variants`.
- Do not use `PolygonGeneric` trees/roads as building heroes; do not place `placeable: false` records.
- Do not treat `*_Convex` / `Collisions/` as renderables (the scanner already drops them).
- `synty-inventory gauntlet` must stay all-green after any catalog change.
