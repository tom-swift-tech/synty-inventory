---
name: synty-inventory
description: >
  Search and place Synty Unity/Unreal pack assets using rich catalogs (what a
  sign depicts, mount, floors, constraints, semantic role) instead of filenames.
  Use when building or dressing a Unity/Unreal scene with Synty POLYGON kits,
  choosing signs/props/modular pieces, or when the user runs /synty-inventory.
---

# Synty Pack Inventory

Do not place Synty assets from the filename alone. Query `synty-inventory` and
obey `placement` + `ai_notes`.

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

prints the resolved `unity_root`, `extracted_root`, `catalogs`, and
`viewer_data`. If the command is missing, `pip install -r requirements.txt`
from the synty-inventory checkout.

If catalogs are missing, scan first (uses `unity_root` from config):

```
synty-inventory scan
```

Prefab paths in the catalog are relative to that pack's extracted tree.

## Tools

| Skill tool | CLI |
|---|---|
| `list_packs()` | `list-packs` |
| `search_assets(query, pack=, tags=, category=, constraints=)` | `search QUERY [--pack P] [--tags a,b] [--category sign] [--constraints exterior_only]` |
| `get_asset_details(id_or_name)` | `details ID` |
| `suggest_assets_for(context)` | `suggest "police station facade"` |
| `get_placement_guidance(id)` | `placement ID` |

## How to pick and place

1. `suggest` or `search` for the building/context (e.g. `police station facade`, `first-floor barber pole`, `roadside billboard without windows`).
2. `details` on the chosen id. Read `semantic_role`, `description`, `dimensions.approx` (metres).
3. `placement` before instantiating:
   - `mount` `wall` → attach `attachment` (`back_side` or `side_bracket`) to the street facade.
   - `preferred_floors` — do not put a first-floor-only pole on storey 3.
   - `constraints` — `exterior_only`, `do_not_cover_windows`, `civic_facade_only`, `roadway_view` are hard rules.
   - `preferred_contexts` — civic plaques stay on civic buildings; barber poles stay on shop fronts.
4. Instantiate the Unity prefab at `paths.prefab` (or mesh at `paths.mesh`) at authored scale. Synty snap is 0.25 m; street face is +Z.
5. One identity sign per frontage.

## Quality checks

- Police identity → `SM_Prop_Sign_Police_01` (wall plaque, above the door, floors 1–2).
- Barber identity → `SM_Prop_Sign_Barber_01` (side-bracket pole, floor 1, beside the door).
- Do not use `PolygonGeneric` trees/roads as building heroes.
- Do not treat `*_Convex` / `Collisions/` as renderables (the scanner already drops them).
