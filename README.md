# Synty Pack Inventory

**`synty-inventory`** — offline scanner and query CLI. It turns **your** Synty
packs into per-pack JSON catalogs so you or an agent can search by meaning —
what a sign depicts, how it mounts, which floor it belongs on, which kit
family a wall module belongs to, which socket a ship engine mates to,
which skeleton bone a mech weapon parents to — instead of guessing from
filenames like `SM_Prop_Sign_Police_01`.

**One catalog, every engine.** A Synty pack is the same set of meshes in
Unity, Unreal, Godot and as converted GLBs for three.js. The catalog records
each asset once (semantics, measured bounds, assembly data) and lists the
per-engine file under `files.{unity_prefab,unity_mesh,glb,unreal_uasset,
godot_scene}`. `--engine` only chooses which file path to print; it never
changes what the asset *is*.

Does **not** need the Unity Editor. This repo is **not** affiliated with
Synty Studios. It does **not** include Synty assets or generated catalogs.

Requires Python 3.11+, numpy, and Synty packs you already license.

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
```

Copy the example config and set the three required roots to **your** disks:

```bash
# Windows cmd
copy config.example.yaml config.yaml

# Windows PowerShell
Copy-Item config.example.yaml config.yaml

# macOS/Linux
cp config.example.yaml config.yaml
```

Edit `config.yaml`:

| Key | What it points at |
|---|---|
| `unity_root` | Folder of original `*.unitypackage` files (not extracted assets) |
| `extracted_root` | Extracted pack trees, one folder per `pack_id` (`POLYGON_City`, …) |
| `catalogs` | Where this tool writes JSON catalogs (keep this **outside** git) |

Optional keys: `viewer_data` (asset-viewer `generate/data` — measured AABBs,
sign overlays and building-type grammars, if you have them; not in this
repo), `threejs_v2` (converted GLB tree with per-pack `manifest.json` /
`catalog.json`; used for `files.glb`, offline mesh measurement and the
VLM-reviewed descriptions), `godot_root` / `unreal_root` (engine-native
export trees, one folder per pack; fill `files.godot_scene` /
`files.unreal_uasset` — see [Godot / Unreal file paths](#godot--unreal-file-paths)
below), `synty_glb_root` (a checkout of the `synty-glb` renderer, needed only
for `review` — see [Local VLM review](#local-vlm-review) below). Any key can
also be set with `SYNTI_UNITY_ROOT`, `SYNTI_EXTRACTED_ROOT`, `SYNTI_CATALOGS`,
`SYNTI_VIEWER_DATA`, `SYNTI_THREEJS_V2`, `SYNTI_GODOT_ROOT`, `SYNTI_UNREAL_ROOT`,
`SYNTI_SYNTY_GLB_ROOT`, or `--config PATH`. Two further settings —
`vlm_local_url` / `vlm_local_model` (`SYNTI_VLM_LOCAL_URL` /
`SYNTI_VLM_LOCAL_MODEL`) — configure `review`'s local Ollama call and default
sensibly (`http://localhost:11434`, `gemma4:26b`) when unset. `gemma4:e4b`
is opt-in for smoke tests only.

```bash
synty-inventory config
synty-inventory scan
synty-inventory search "police"
```

After install, the CLI is `synty-inventory` (same as `python -m synty_inventory`).
`config` prints each resolved path, whether it exists, and whether it came
from the file or the environment. A wheel/sdist also ships
`config.example.yaml` and `skill.md` inside the package (`example_file` in
the `config` output).

## Why

A filename does not tell an agent that a police plaque sits above the door
on floors 1–2, or that a barber pole is a side-projecting first-floor
identity piece. The catalog does.

That is what the inventory is for: query by meaning, then instantiate the
prefab. Here an agent uses the catalog while generating a building from
pack pieces in Unity:

![Agent querying synty-inventory and assembling a building from pack pieces in Unity](assets/synty-tools.gif)

## Layout

```
src/synty_inventory/   scan, enrich, query
skill/SKILL.md         skill (copy into ~/.grok/skills/synty-inventory/)
assets/synty-tools.gif demo: catalog-driven building assembly in Unity
config.example.yaml    template — copy to config.yaml
config.yaml            local paths (gitignored; do not commit)
LICENSE / NOTICE       Apache-2.0 + third-party asset notice
tests/
```

Catalogs are written to the `catalogs:` path. Each pack is
`<pack_id>.json` (schema `version: 2`; v1 files are migrated on read).

### What a v2 asset record carries

| Field | Meaning |
|---|---|
| `placeable`, `kind` | `false` / `animation`, `ui`, `skeleton`, `material`, … for things an assembler must never drop into a scene (clips, HUD, skyboxes). `search`/`suggest` hide them unless `--include-nonplaceable`. |
| `type` | enumerated: `building/shell`, `building/interior_module`, `vehicle/spacecraft`, `vehicle/part`, `sign`, `prop`, … |
| `semantic_role` + `semantic_detail` | enumerated role (`building_identity`, `advertisement`, `vehicle_part`, …) plus free detail (`police_station`, `displays_burger`, `engine`). |
| `placement` | `mount`, `attachment`, `preferred_floors`, `constraints`, `preferred_contexts` — all enumerated. |
| `bounds` | `{min,max,size,pivot,source}` in metres, **measured** from the GLB (or asset-viewer AABB); `null` until measured — never a guess. `dimensions.approx` mirrors `bounds.size`; `size_hint` is the rule-based remnant for unmeasured pieces. |
| `module` | kit data for modular building pieces: `family` (`Apartment`, `Shop`, …), `role` (`hero`, `shell`, `corner`, `door`, `roof`, `stairs`, `floor`, `base`), `footprint_class`, `stackable_on`, `street_side`. |
| `part` | ship-kit data: `class` (`body`, `cockpit`, `engine`, `wing`, `gear`, `greeble`), `mates_axis`, `symmetric`, `size_class`, plus mesh-analysed mating faces: `mount` (the face this part attaches with: `axis`, `position`, `normal`, `area`, `extent`, `fit`, `source`, `parent_role` = the hull socket it fits unrotated) and, for `body` hulls, `sockets[]` (`front`/`rear`/`left`/`right`/`top`/`bottom`, same shape). Positions are in `bounds` space (local, metres); `source: measured` = a flat cap found in the decoded GLB triangles, `aabb` = AABB face-centre fallback (no flat cap — rounded hull end). The mount is not always on the class axis: a part whose pivot sits on a face mounts by that face (pylon engines `Engine_08/09` → `+x`, `parent_role: left`; mirror for the right), and wings mount by their dominant ±X root cap, which may be tilted by the dihedral (`normal` is the real normal, `axis` the nearest axis — place by position, do not rotate the root flush). Attach child to parent as `parent_pos + socket.position - child.mount.position`. `null` until the GLB is analysed. Mech attachments (`SM_Mech_*`) instead carry `slot` (`{region, side l\|r\|c}` — `arm`, `leg`, `chest`, `head`, `cockpit`, …) and `attach_bone`: parent the piece to that skeleton bone with an identity local transform (pieces are authored in bone space). |
| `mech` | on `SM_Veh_Mech_*` bodies: `skeleton` (bone names), `slots[]` (`region`, `side`, `bone`, `geo_nodes`), `variants` (factory loadouts → the `geo_*` nodes each activates). The master body GLB contains every armor/weapon option as named `geo_*` nodes — assemble by toggling geo-node visibility to a `variants` set, or by parenting standalone `SM_Mech_*` attachment GLBs to their `attach_bone`. |
| `files` | `unity_prefab`, `unity_mesh`, `unity_materials`, `glb` (+ `glb_node` for meshes packed in bundle GLBs), `unreal_uasset`, `godot_scene`. `paths` is the v1 alias. |
| `provenance` | per-field source, see precedence below. |
| `footprint` | ground plan measured from the GLB — `polygon_m` (CCW ring, XZ local metres), `area_m2`, `grade_area_m2`, `overhang_ratio`, `fill_ratio`, `class`, `radius_m`, `tile_cells`, `components`, `snap_m`, `grade_band_m`. See below. |


### `footprint` — the ground plan

`bounds` says how big an asset's box is; `footprint` says what shape its
ground plan actually is. An L-plan office, a landing pad with an overhanging
lip and a solid cube all share a box — they do not share a footprint, and a
packer that only sees the box spaces everything conservatively.

```
synty-inventory footprint [--pack CSV] [--ids CSV] [--rebuild] [--dry-run]
                          [--report PATH] [--min-coverage F]
```

Deterministic mesh math — no VLM, no render, no network. Cached in
`<catalogs>/_footprint_cache.json` by mtime+size+`FOOTPRINT_VERSION`, so the
first run per pack is the expensive one (~6 min for 800 assets) and every run
after it is free. Bumping `FOOTPRINT_VERSION` invalidates every entry without
`--rebuild`.

Things a consumer must know:

- **`null` is a legitimate state.** The mesh could not be decoded, or it is a
  zero-thickness kit card (`SM_Bld_Base_Wall_Thin_*`, neon flats, billboards)
  whose AABB has no XZ depth, so any positive area would violate its own
  bounding box. ~115 of 10,185 across all packs. Check before use.
- **`area_m2` is enclosed area, not silhouette.** Synty building shells are
  hollow — no floor or roof slab — so the raw wall ribbon of a 15 × 15 m shaft
  is only 179 of 3,660 cells. Interior voids are filled, because a hollow
  shell still blocks its whole floorplate.
- **Measures are conservative by up to one cell and never under.** A 6.00 m
  tower reads 6.12 m. Deliberate: over-reporting occupancy fails safe.
- **`radius_m` is set iff `class == "radial"`.** A round tower has no face to
  name, so its traced outline is replaced by a regular 16-gon and the radius
  is recorded — that is the number that compares across a kit family.
- **`overhang_ratio` of 1.0** means nothing at all sits within the grade band
  (a pole-mounted sign). Legitimate, not an error.
- **Never in slim rows.** `details <id>` for the full block, or widen a list
  query with `--fields footprint`.

`class` is one of `point`, `thin`, `radial`, `compact`, `l_plan`, `u_plan`,
`irregular`, first match wins in that order. It is a convenience — `fill_ratio`
is the number to filter on if you want "box-like enough to pack as a box".

Verify a pass before trusting it:

```
python -m synty_inventory.tools.diff_catalog --before <backup>.zip --after <catalogs>
python -m synty_inventory.tools.footprint_sheet --pack P --type buildable --out DIR
```

`diff_catalog` proves the pass was additive — it permits only *additions* at
`footprint`, `provenance.footprint` and `_auto.footprint`, and fails on any
other added, changed or removed key path, or any gained or dropped record.
`footprint_sheet` renders a contact-sheet SVG (AABB in grey, polygon in cyan)
so a systematic error shows up as a block of wrong cells.
Catalog-level `grid` (`snap 0.25`, module/tile/story sizes) and
`conventions` (street axis `+z`, rotate step, scale `1.0`) are written once
per pack.

### Precedence (who wins on re-scan)

Lowest to highest; a higher rank overwrites a lower one, equal rank refreshes:

| Rank | Source | Examples |
|---|---|---|
| 1 | `rules` | stem-based inference (`knowledge.py`) |
| 2 | `viewer` | asset-viewer roles / sign overlays |
| 3 | `measured` / `vlm` | GLB bounds, unreviewed VLM |
| 4 | `vlm_reviewed` | threejs-v2 `catalog.json` entries with `reviewed: true` |
| 5 | `curated` | hand-written overrides in the package |
| 6 | `human` | anything you edit in the catalog or list in `locked_fields` |

`bounds` never regress (measured is never replaced by a hint). `files.*`,
`placeable`, `kind` and `size_hint` always refresh from disk/rules unless
`human`. `scan --rebuild` discards every non-human field so a precedence or
rule change takes effect everywhere.

## CLI

Paths default from `config.yaml`. Pass a root only to override.

```bash
synty-inventory discover
synty-inventory scan
synty-inventory scan --pack POLYGON_City
synty-inventory list-packs
synty-inventory search "police" --pack POLYGON_City
synty-inventory search "engine" --type vehicle/part --part-class engine --engine threejs
synty-inventory details SM_Prop_Sign_Police_01
synty-inventory suggest "police station facade"
synty-inventory suggest "fighter space ship"        # -> {"recipes":[ship_kit, ...], "assets":[...]}
synty-inventory placement SM_Prop_Sign_Police_01
synty-inventory recipes [--pack POLYGON_City]
synty-inventory recipe ship_kit --engine unity
synty-inventory recipe building_shop --pack POLYGON_City
synty-inventory kit Apartment                      # modules grouped by role
synty-inventory kit "*"                            # every family
synty-inventory validate
synty-inventory gauntlet
synty-inventory vision --calibrate
synty-inventory vision --pack POLYGON_City --ids SM_Bld_Apartment_01 --dry-run
synty-inventory review --pack POLYGON_SciFi_Space --limit 20
```

`search`/`suggest` filters: `--type`, `--role`, `--module-role`,
`--part-class`, `--include-nonplaceable`, `--engine unity|unreal|godot|threejs`.
`suggest` prints `{"recipes": [...], "assets": [...]}` — `--assets-only` gives
the v1 bare list.

### Recipes — how the pieces are meant to be used

A recipe is a grammar: ordered steps, each with a `select` filter over the
catalog, a count range, a layout and constraints. `select` keys: `ids`,
`pack`, `type`, `semantic_role`, `semantic_detail`, `module_role`,
`module_family`, `part_class`, `size_class`, `part_slot_region` (matches
`part.slot.region` on mech attachments — `arm`, `hand`, `cockpit`, …),
`tags_any`, `tags_all`, `contexts_any`, `placeable`, `id_prefix`,
`id_regex`. `recipe <id>` resolves it against your catalogs and
returns the eligible pieces per step **with bounds and files**, and
`complete: false` (exit 4) if a required step has no candidates. Sources:

- package recipes in `src/synty_inventory/recipes/` — `ship_kit`,
  `station_interior`, `main_street_row`, `apartment_block`, `mech_kit`;
- asset-viewer building types (`generate/data/types/*.json`) exposed as
  `building_<type>@<pack>` when `viewer_data` is set;
- your own `<catalogs>/recipes/*.json` (same shape; `triggers` drive `suggest`).

Optional scan flags:

- `--include-shared` — also catalog `PolygonGeneric` inside each pack
- `--from-package` — index the `.unitypackage` even when an extracted tree exists
- `--extract-previews` — write Synty `preview.png` files under
  `catalogs/previews/` (do **not** commit or share)
- `--vlm` — optional vision pass (`XAI_API_KEY` / `OPENAI_API_KEY` /
  `SYNTI_VLM_API_KEY`). May upload previews; can conflict with the Synty
  or Unity EULA. Off by default.

Re-scan merges by the precedence table above. Human / `locked_fields` /
`provenance: human` values are kept. Paths always refresh from disk. `scan
--pack` updates that pack and rebuilds `index.json` from **all** catalogs on
disk. `scan --rebuild` keeps only human fields.

Unreal trees are discovered when present; that path is implemented, not
proven against live packs. Overlays apply only when the folder name equals
`pack_id` (or an explicit override table).

### Godot / Unreal file paths

`godot_root` / `unreal_root` are separate, optional reference trees — not
part of the Unity scan itself — that `enrich` overlays onto each cataloged
asset by stem match: `sources/godot.py` and `sources/unreal.py` map a
top-level folder name under the root to a `pack_id` (Godot: `SLUG_PACK_OVERRIDES`
only — unmapped folders are skipped and warned; Unreal: the folder name must
equal `pack_id`, or an explicit override), index every `.tscn` / `.uasset`
under that pack's tree, and wire `files.godot_scene` / `files.unreal_uasset`
to a path relative to the root (forward slashes).
Neither field carries a provenance stamp — like `files.glb`, `files` is
scanner-owned and refreshed wholesale on every rescan. A reference
`unreal_root` never overwrites `files.unreal_uasset` already set by a
natively-Unreal-sourced pack (`scan --pack` on an Unreal root). Both roots
default to unset (`null`) and are a no-op when missing — no Unreal export
tree exists on any known machine today.

### Hosted Grok vision (assembler fields)

`vision` is the stills-grounded pass that may write **structure**. It calls
Grok 4.6 (`XAI_API_KEY`, `https://api.x.ai/v1`) on contact sheets
(LEFT=front, RIGHT=quarter) or front+quarter renders (`gizmo=0`), enum-locks
the JSON, and **merge-not-replace**s into the pack's threejs-v2
`catalog.json`. Allowed: name, description, tags, `semantic_role`,
`module.role` on buildings, mount / attachment / orientation / floors /
contexts / constraints, and `type` except on `part.class` rows. Forbidden:
`placement.contact`, ship/mech sockets, `SM_Veh_Part_*` / `SM_Mech_*` (prose
only). Do **not** use `scan --vlm` (free-form placement, stale contract) or
`review` (Ollama/Gemma4) on POLYGON_City / SciFi_City / Starter.

```bash
synty-inventory vision --calibrate          # 20 City gold stills; never writes
synty-inventory vision --pack POLYGON_City --match SM_Sign_ --limit 20
synty-inventory vision --pack POLYGON_City --ids SM_Bld_Apartment_01 --dry-run
```

After a pack is labelled: `scan --rebuild --pack POLYGON_City` then `gauntlet`.
Stills default to `tools/viewer/tasks/vision_qa/stills/<pack>/<id>.png`
(`--stills-root` / `SYNTI_VISION_STILLS` to override). Missing stills render
`front,quarter` via synty-glb with `--no-gizmo`.

### Local VLM review

`review` is **prose only** (name, description, tags). It must not run on
POLYGON_City / POLYGON_SciFi_City / POLYGON_Starter — Gemma4 already
overwrote those stills catalogs once. It needs a threejs-v2 pack
(`threejs_v2` config key, a `manifest.json` GLB listing), a `synty-glb`
checkout (`synty_glb_root`) to render stills, and a local
[Ollama](https://ollama.com) server with a vision-capable model pulled
(`ollama pull gemma4:26b`).

```bash
synty-inventory review --pack POLYGON_SciFi_Space --limit 20
synty-inventory review --pack POLYGON_SciFi_Space --match SM_Prop
synty-inventory review --pack POLYGON_SciFi_Space --model gemma4:26b --vlm-timeout 300
```

For each unreviewed GLB (deterministic order, `characters` / `br_characters`
/ `generic_characters` bundles skipped — too many named nodes for a
single-asset pass): render 1-2 stills via
`python -m synty_glb.qa render <glb> <outdir> <view,...>` (subprocess, `cwd`
= `synty_glb_root`), ask the local VLM for `{name, description, tags,
category, semantic_role}`, and merge the result into the pack's
`catalog.json` with `reviewed: true`. Resumable: an asset already carrying
`reviewed: true` is skipped before it counts against `--limit`, and a still
already on disk isn't re-rendered — safe to interrupt and rerun. A per-asset
render or VLM failure is logged (`failed: [...]` in the JSON result) and
skipped; it never aborts the batch.

**Stills cache**: `<threejs_v2_root>/<pack_id>/_review_stills/<stem>/<view>.png`
— next to the GLBs, **outside** this repo and outside `catalogs`, so a rerun
reuses them and they never end up in git.

**Views**: default `left,top` (`--views` to override). Vertical planar
assets (wall signs, decals, draped ivy — thin along Z) are edge-on in BOTH
default views, so review renders those face-on (`front,top`) automatically
from GLB bounds. Renders pass `--no-gizmo`: the harness's 1.8 m human-scale
reference figure dominates the frame on small assets and the VLM describes
the gizmo instead of the asset (observed: a wall anchor reviewed as
"cotton_candy"). This needs a synty-glb checkout whose `qa render` accepts
`--no-gizmo` (`gizmo=0` harness query param); the prompt still tells the
model to ignore a small teal humanoid, which covers stills cached from
older gizmo renders.

**Model choice**: the code default is `gemma4:26b` because it grounds on
these renders (~15–20 s/asset on an otherwise-idle GPU; minutes/asset under
GPU contention). `gemma4:e4b` is opt-in for throwaway smoke tests
(`--model gemma4:e4b` or `SYNTI_VLM_LOCAL_MODEL`) — it produces plausible,
confident, wrong output (a table reviewed as a wooden crate) and must not
be trusted for batches. Exclude `FX_*` from review (`--match SM_`):
translucent light-shaft FX render as plain shapes and no vision model can
recover their function.

`gauntlet` is a live acceptance suite (expects `POLYGON_City` and, for the
assembly gates, `POLYGON_SciFi_Space`): the v1 sign gates plus bounds
coverage >= 95 %, no heuristic dimensions, GLB paths, VLM overlay applied,
ship-part typing, ship-part sockets (every hull six faces, every child part a
mount with `parent_role`, >= 95 % of mounts measured caps, pylon engines on
`+x`), mech slot wiring when `POLYGON_Mech` is on disk (`mech_slots`:
every `SM_Veh_Mech_*` body carries `mech.skeleton/slots/variants` with the
six factory variants, >= 95 % of `SM_Mech_*` attachments carry `part.slot`
+ `part.attach_bone`, and pinned bone mappings hold — chest weapon →
`Spine_01`, cockpit → `CockpitDoor`), every package recipe resolving
`complete`,
`suggest` pointing assembly prompts at the right recipe, and — when
`godot_root` is configured — `godot_paths`: the three mapped packs
(`POLYGON_City`, `POLYGON_Starter`, `POLYGON_Particle_FX`) resolve, every
non-null `files.godot_scene` exists on disk, and geometry-bearing
(`kind` prefab/mesh) resolution coverage is >= 90 % (observed 95.3 % on the
reference machine: `POLYGON_City` 333/337, `POLYGON_Starter` 52/55,
`POLYGON_Particle_FX` 0/12 — that pack's Godot export ships only ~13 demo
particle scenes, none matching its 12 mesh-kind catalog entries). CI uses
`pytest` and a fake fixture pack.

## Mesh analysis

Bounds come from accessor `min`/`max` alone. Ship-part sockets need the real
triangles, so `sources/meshopt.py` carries pure-Python decoders for the
`EXT_meshopt_compression` vertex (v0) and index (v0/v1) codecs the threejs-v2
GLBs use — no native `meshoptimizer` dependency. `sources/glb_geometry.py`
turns a GLB (or one named node of a bundle GLB) into world-space triangles;
`sources/sockets.py` clusters the coplanar triangles facing each axis (10°
cone; 30° for wing roots, which carry the dihedral) into caps and picks the
outermost sizeable one per axis. The mount is chosen in this order: a cap
whose plane passes through the pivot (Synty puts the pivot on the mating
face where it is off-centre — pylon pods, gear, base-pivoted greebles),
then the class axis (cockpit −Z, engine +Z, gear +Y), then for wings the
dominant ±X cap (two equal side faces = a fin → its top/bottom), then for
greebles the largest axis-true flat face. Results are cached in
`_measure_cache.json` under `<glb>#sockets`, keyed by file mtime/size, the
algorithm version and the part class, so rule changes re-analyse.

## Skill

See `skill/SKILL.md`. Copy it to `~/.grok/skills/synty-inventory/SKILL.md`
(or your Claude Code skills dir). Every tool is a `synty-inventory` command
that prints JSON. The skill tells an agent to start from `suggest` -> recipe
-> `recipe <id> --engine <engine>` for assemblies, and `search`/`details`/
`placement` for single pieces.

Edit `skill/SKILL.md` and `config.example.yaml` (repo root), then copy into
`src/synty_inventory/` (`skill.md` / `config.example.yaml`) so the wheel
stays in sync. The packaged copies are not the files to edit.

## Tests

```bash
python -m pytest                  # fixture suite (CI)
synty-inventory gauntlet          # live catalogs on this machine
```

## License

This software is licensed under the Apache License, Version 2.0. See
`LICENSE` and `NOTICE`.

Apache-2.0 covers this scanner, skill, and docs only. It does not grant
trademark rights in the project name, and it does not license Synty
content.

## Third-party assets

This repository does **not** include Synty Studios packs, source files,
preview images, or generated catalogs. You must own the packs you scan
and follow the [Synty EULA](https://syntystore.com/pages/one-time-purchase-licence)
(and the Unity Asset Store EULA if you bought a pack there).

Synty and POLYGON are trademarks of Synty Studios Limited. This project
is not affiliated with, endorsed by, or sponsored by Synty Studios.

Do not commit or publish `config.yaml`, extracted/original packages,
`--extract-previews` PNG output, or catalog JSON. Keep those on your
machine. `--extract-previews` and `--vlm` can write or upload Synty
artwork; both are optional and your responsibility.
