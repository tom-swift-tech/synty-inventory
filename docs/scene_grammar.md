# Scene grammar (`scene-mine`)

`synty-inventory scene-mine --pack <PACK_ID>` mines a Synty pack's own demo
`.unity` scenes into `<out>/<PACK_ID>.scene_grammar.json`, a
`scene-grammar/1`-schema document
(`src/synty_inventory/data/scene_grammar.v1.json`): every placement a Synty
artist actually made, world-composed and resolved against the pack's
catalog, plus derived look/camera/layout data a generator can condition on.

This tool never edits a catalog and never writes into the licensed
`extracted` tree — it only reads `.unity`/`.asset`/`.meta` files under
`catalog["source"]["extracted"]` and the catalog itself, and writes one new
JSON file under `--out` (default: the catalogs directory).

## CLI

```bash
synty-inventory scene-mine --pack POLYGON_SciFi_City
synty-inventory scene-mine --pack POLYGON_City \
    --scene Assets/Synty/PolygonCity/Scenes/Demo.unity \
    --out scratchpad/sg --report scratchpad/sg/POLYGON_City.report.json
```

| flag | default | meaning |
| --- | --- | --- |
| `--pack` (required) | — | `pack_id`, e.g. `POLYGON_SciFi_City` |
| `--scene` (repeatable) | every `*.unity` under the pack's `Scenes/` dir, minus `--exclude` | mine exactly these scenes, in the given order |
| `--exclude` (repeatable) | `Overview*` | glob(s) applied to scene filenames during default discovery only — ignored when `--scene` is given |
| `--catalogs` | `catalogs` from `config.yaml` / env | catalogs directory to read `<PACK_ID>.json` from |
| `--out` | the catalogs directory | directory the grammar JSON is written into |
| `--adjacency-radius-m` | `6.0` | XZ radius for the `adjacency` co-occurrence stat |
| `--cell-m` | `20.0` | grid cell size for the `density` stat |
| `--report` | — | also write the `scene-mine-report/1` JSON (summary + `unresolved`) to this path |

### Exit codes

| code | meaning |
| --- | --- |
| `0` | grammar written; the `scene-mine-report/1` JSON printed on stdout |
| `2` | bad input: catalogs dir / catalog / `source.extracted` / named scene not found |
| `3` | a scene was refused: it looks like Synty's own `Overview.unity` catalogue grid (even when named explicitly with `--scene`), or its resolved/placements ratio fell below the 0.95 floor |
| `6` | malformed scene YAML (`SceneParseError`), a duplicate GUID across two `.meta` files (`GuidIndexError`), or the assembled document failed `scene_grammar.v1.json` validation |

Nothing is written on any non-zero exit.

## How a placement is resolved

Every `PrefabInstance` (`!u!1001`) in a scene carries its own local
position/rotation/scale as override entries under
`m_Modification.m_Modifications`, parented to a scene `Transform` via
`m_Modification.m_TransformParent.fileID`. That parent can itself be a
*stripped* `Transform` (`!u!4 ... stripped`, no fields beyond
`m_PrefabInstance.fileID`) belonging to another `PrefabInstance` — composing
world transforms is therefore a memoized mutual recursion between "the world
of a Transform fileID" and "the world of a PrefabInstance fileID"
(`unity_yaml._resolve_transform_world` / `_resolve_instance_world`), so
parent-before-child file order is never assumed and a cycle raises
`SceneParseError` instead of recursing forever.

The join to the catalog is **GUID only**, never `m_Name`:
`PrefabInstance.m_SourcePrefab.guid` → the pack's `.meta` files (built once
per pack by `GuidIndex.build`, keyed by the 32-hex GUID inside each
`*.meta`) → asset path → the catalog row whose `files.unity_prefab` equals
that path. A catalog row's own `guid` field, when present, is cross-checked
against the scene's GUID and any mismatch is recorded as a `warnings` entry
only — it never blocks resolution.

An instance that fails to resolve is recorded once in `unresolved[]` with a
`reason`, never fabricated as a placement:

| `reason` | meaning |
| --- | --- |
| `no_meta` | the GUID has no `.meta` file anywhere under `source.extracted` |
| `not_in_catalog` | the GUID resolves to a real asset path, but no catalog row's `files.unity_prefab` matches it |
| `not_placeable` | the catalog row exists but `placeable: false` |

`unresolved[].hint` is the instance's own name with a trailing `" (N)"` Unity
copy-suffix stripped (`"Wall (3)"` → `"Wall"`) — a hint for a human, never
used to resolve anything.

A pack's overall `scenes[].resolved / scenes[].placements` ratio must be
`>= 0.95` per scene or the run is refused (exit 3, `ResolveRateError`) —
this is a floor on parse correctness, not a quality target.

## Duplicate-scene detection

Two scenes whose sorted `(asset_id, pos_m, yaw_deg)` multiset of resolved
placements is identical are the same authored layout — an exact-equality
check, not a fuzzy or partial match (confirmed against real data: on
`POLYGON_SciFi_City`, `Demo_TriplanarDirt.unity` looked like an
alternate-ground-material variant of `Demo.unity` by name alone, but its
placement multiset is genuinely different and smaller, so it is correctly
*not* flagged a duplicate). The second and any later such scene get
`scenes[i].duplicate_of` set to the index of the first; a duplicate
contributes its row to `scenes[]` (so its `sha256`/`placements`/`resolved`
counts are visible) but **nothing** to `placements[]`, the stats blocks, or
`cameras[]` — only the look/render-settings of the *first* non-duplicate
scene are kept as the pack's `look`.

## Overview-scene heuristic

Synty ships a `Overview.unity` (or similarly named) scene in most packs that
is a one-of-each catalogue grid, not an authored layout — mining it would
poison every layout statistic with an artificial uniform grid. A scene is
refused as an Overview grid, even when named explicitly with `--scene`,
when **both**:

- at least 80% of its resolved placements share one modal nearest-*any*-id
  XZ distance, binned to 0.1 m, within ±5% of that mode; **and**
- the number of distinct asset ids is at least 90% of the placement count
  (i.e. almost every placement is a different asset — a grid of one-of-each,
  not a repeated layout).

## `look`

Extracted from the first non-duplicate scene's `!u!104 RenderSettings`,
its one `!u!108` directional Light, and its one global `!u!114 Volume`
(`m_IsGlobal: 1`):

- **`fog`**: `mode` (`none`/`linear`/`exp`/`exp2`, forced to `none` when
  `m_Fog: 0` regardless of `m_FogMode`), `color_rgb`, `density`, `start_m`,
  `end_m` straight off `RenderSettings`.
- **`ambient`**: `mode` (`skybox`/`trilight`/`flat`/`custom` from
  `m_AmbientMode`), the three ambient colours, `intensity`.
- **`sky`**: `kind`/`material_path`. Unity's built-in
  `Default-Skybox` material (GUID `0000000000000000f000000000000000`, no
  `.meta` file of its own to resolve) reports
  `material_path: "builtin:Default-Skybox"`; any other GUID resolves through
  the pack's GUID index. `zenith_rgb`/`horizon_rgb` are always `null` in v1
  — a procedural-skybox material's own shader parameters are not parsed.
- **`sun`**: `null` (plus a `warnings` entry) unless the scene has *exactly
  one* directional Light. Otherwise: `azimuth_deg`/`elevation_deg` from the
  light's world rotation — `forward = rotate(q, (0,0,1))`,
  `direction = -forward`, `elevation = asin(direction.y)`,
  `azimuth = atan2(direction.x, direction.z) mod 360` — plus `intensity`,
  `color_rgb`, and `shadows` (`none`/`hard`/`soft` from `m_Shadows.m_Type`).
- **`post`**: the global Volume's `sharedProfile` asset, resolved by GUID
  and parsed for every component whose fields carry `m_OverrideState: 1`.
  `overrides.<Component>.<field>` holds the parsed value (colours as
  `[r,g,b,a]`, vectors as `[x,y,...]`, scalars as-is); a `Tonemapping.mode`
  override is mapped `0/1/2` → `none`/`neutral`/`aces`. A field whose
  override value is a `{fileID}` object reference (a texture, a curve
  asset, …) is **never** fabricated as a value — its `"Component.field"`
  name is listed in `unparsed` instead. A field with `m_OverrideState: 0`
  (present in the asset but not actually overridden) appears in neither
  `overrides` nor `unparsed`.
- **`lighting_settings_path`**: the pack's baked-lighting `.lighting` asset
  path, resolved from the scene's one `!u!157 LightmapSettings` doc (parsed
  even though class `157` sits outside the miner's normal streaming
  allowlist — see "Deviations" below).

## `cameras`

One row per `!u!20 Camera` in the **first non-duplicate scene** — the same
scene `look` comes from, because a camera is a vantage in one particular
layout and the capture consumer opens exactly that scene (pooling every
scene's cameras put `Demo_TriplanarDirt.unity`'s `Main Camera` into the
Sci-Fi City grammar under the same id): `id` (its GameObject's name), world
`position_m`/`yaw_deg`, `pitch_deg` (`= -(Unity Euler x)`, so a camera
looking *up* reports a **positive** pitch), `fov_deg`, `enabled`.

## Stats

Adjacency/spacing/ground/density/streets all need nearest-neighbour queries
on XZ position, and two different demo scenes are two different coordinate
spaces — a "nearest neighbour" never crosses a scene boundary. Those five
are therefore computed **within each non-duplicate scene independently**,
then pooled (counts summed; percentiles taken over the pooled per-instance
or per-cell values). `histogram`/`roles`/`rotation`/`scale` only ever look
at one placement at a time, so they operate on the flat pooled placement
list directly. This per-scene-then-merge split is this tool's own design
decision (not spelled out verbatim in the spec) — it is the only way these
five numbers mean anything across multiple demo scenes with unrelated
origins.

- **`histogram`**: count of each `asset_id` across every resolved,
  non-duplicate placement.
- **`roles`**: `asset_id` → one of `building`/`road`/`prop`/`vehicle`/
  `character`/`fx`/`unknown`, derived from the catalog's `type` field (D1:
  `building*` → building; `environment/city_layout` → road; `prop`,
  `prop/*`, `environment`, `weapon` → prop; `character`, `character/*` →
  character; `vehicle` → vehicle; `fx` → fx; everything else → unknown).
  Never guessed from the asset name.
- **`adjacency`**: for every pair of placements within
  `--adjacency-radius-m` of each other on XZ (within one scene), a directed
  `(a, b)` row: `count`, `p_b_given_a = count / histogram[a]`, and
  `mean_offset_m` — the mean `b - a` XZ+Y displacement, expressed in `a`'s
  own yaw-aligned local frame (so "b sits 2 m to a's right" is comparable
  across differently-rotated instances of `a`). `(a, b)` and `(b, a)` are
  separate rows.
- **`spacing`**: per `asset_id`, `n` instances total, `nn_same_m_p50/p90`
  (nearest same-id XZ distance; `null` when fewer than 2 instances of that
  id exist anywhere) and `nn_any_m_p50` (nearest any-id XZ distance).
- **`rotation`**: per `asset_id`, `cardinal_frac` (fraction of instances
  within ±1° of 0/90/180/270 — matching `POI_builder`'s own `corner_yaw`
  tolerance), the cardinal `yaw_hist_deg`, and the sorted unique
  non-cardinal yaws (1 dp).
- **`scale`**: per `asset_id`, `unit_frac` (fraction at exactly `[1,1,1]`
  within `1e-4`), per-axis `min`/`max`, `n`. This only *records* the
  non-unit-scale finding (surfaced pack-wide in `findings` too) — it never
  corrects or drops a placement.
- **`ground`**: per `asset_id`, `y_rel_p50/p90` = that instance's Y minus
  the Y of the nearest road-role instance on XZ, in the same scene. `{}`
  when the pack has no `road`-role asset at all.
- **`density`**: an XZ grid of `--cell-m`, one grid per scene (a cell key is
  scoped to its scene index, so two scenes' grids never collide even though
  both start at their own local origin). `cells` = occupied-cell count;
  `per_cell_p50/p90/max` and `by_role_per_cell_p50` over the pooled
  per-cell placement counts.
- **`streets`**: **a v1 heuristic estimate**, not a measured kerb-to-kerb
  number — `null` when the pack has no `road`-role asset. `axis_deg` is the
  modal yaw of road-role instances; `module_m` is the modal nearest-same-id
  XZ distance among them (one road tile's repeat spacing); `run_lengths_*`
  projects each scene's road instances onto `axis_deg` and chains
  consecutive tiles within ±10% of `module_m` into runs, then takes
  p50/p90 of run length pooled across scenes; `width_m_p50` and
  `building_setback_m_p50` are **the same number** in v1 — the p50 nearest
  building-role XZ distance from a road-role instance, pooled across
  scenes (a proxy for setback, not an actual street width).

## `findings` / `warnings`

`findings` (only present when non-empty) carries pack-wide
`non_unit_scale_placements`/`non_unit_scale_asset_ids` counts and
`render_settings_diffs` — a list of `"<scene>: <key> differs (first=...,
other=...)"` strings whenever a later non-duplicate scene's RenderSettings
disagree with the first scene's (the scene that supplied `look`).
`warnings` (also omitted when empty) collects GUID cross-check mismatches,
missing-sun/multiple-sun notices, and unresolved Volume-profile references.

## Determinism

Every float is rounded to 4 decimal places; `placements[]` are emitted in
`(scene index, fileID)` ascending order; the JSON is written with
`sort_keys=True`. Two mining runs of the same scenes against the same
catalog produce byte-identical output **except** `provenance.generated_at`
— the only field allowed to differ between runs (verified in
`tests/test_scene_mine_mine.py::test_write_grammar_is_deterministic_modulo_generated_at`).

## Deviations from a literal reading of the spec

- `unity_yaml.parse_scene` also parses class `157` (`LightmapSettings`) to
  populate `look.lighting_settings_path`, even though D3's streaming
  allowlist for `iter_docs` is `{1, 4, 20, 104, 108, 114, 1001}`. There is
  exactly one `LightmapSettings` doc per scene, so this does not touch the
  memory/streaming intent D3 protects (avoiding a full parse of every one
  of a scene's 2000+ `PrefabInstance` bodies).
- `mine_pack` takes an explicit `catalog_path: Path` keyword parameter
  beyond the spec's pseudocode signature, needed to populate the output's
  `catalog.path`/`catalog.sha256` fields.
- `unresolved[]` is always one row per unresolved instance; there is no
  `count`-aggregated form, even though the schema's `unresolved[].count`
  field is optional and would allow one.
