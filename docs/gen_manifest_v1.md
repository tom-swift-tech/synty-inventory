# Generator manifest — spec v1 (`gen-manifest/1`)

The contract between the AI generation pipeline and the catalog. One sidecar JSON per
generated GLB. The manifest **declares intent** (structure); the scanner **measures
geometry**; the VLM review **verifies prose** (Phase 4 `review --verify`). That split is
the whole design:

> Everything structural the catalog needs is declared here; everything geometric is
> measured; everything prose is verified.

## Pack layout

```
<threejs_v2>/GEN_<Theme>/
  manifest.json                 # pack-level GLB listing, same as every threejs-v2 pack:
                                #   {"models": ["models/Models/<Stem>.glb", ...]}
  models/Models/<Stem>.glb
  models/Models/<Stem>.gen.json # THIS spec — one sidecar per GLB, same directory
```

- Pack ids start with `GEN_` — disjoint by prefix from every `POLYGON_*`/`SIMPLE_*` Synty
  pack (`scan --pack` matches by substring; the prefix keeps them separable).
- The sidecar is named `<Stem>.gen.json`, **not** `<Stem>.manifest.json` — the word
  "manifest" at pack level already means the GLB listing in threejs-v2.
- The catalog of record is `synty_catalogs/GEN_<Theme>.json`, built by `scan` exactly like
  Synty packs. Viewer / godot export / review / gauntlet see a normal pack.

## Sidecar schema

```jsonc
{
  "schema": "gen-manifest/1",           // required, exactly this string
  "id": "<Stem>",                       // required, == GLB filename stem; stable across
                                        // regenerations (a new render of the same stem is a
                                        // VERSION of one asset, not a new asset)
  "pack": "GEN_<Theme>",                // required, == pack dir name
  "type": "prop",                       // required, existing catalog TYPES enum
  "semantic_role": "exterior_prop",     // required, existing SEMANTIC_ROLES enum
  "name": "",                           // optional display name; else derived from stem
  "tags": [],                           // optional, lowercase tokens
  "intended_size_m": [2.0, 3.0, 2.0],   // required, what was ASKED for; Phase 4
                                        // scale_agreement gate compares measured vs this
  "pivot": "base",                      // required, "base" | "center" — expectation, checked
                                        // against measured pivot (Phase 4 pivot gate)
  "up_axis": "Y",                       // required, always "Y" in v1
  "placement": {},                      // optional, same shape as catalog placement
  "sockets": [],                        // optional, same shape as catalog part.sockets;
                                        // only if deliberately modular
  "kit": null,                          // optional module family name; only if modular
  "generation": {                       // required block
    "model": "",                        //   generator model tag or vendor id (required)
    "pipeline_version": "",             //   required
    "prompt": "",                       //   required; doubles as description until verified
    "negative_prompt": "",
    "seed": 0,
    "created": "2026-08-22T00:00:00Z",  //   ISO-8601, required
    "supersedes": null,                 //   previous generation's created/seed marker, or
                                        //   null for first generation of this stem
    "source_images": []
  },
  "license": "own",                     // required
  "description": ""                     // optional; defaults to generation.prompt
}
```

## Ingestion semantics (`sources/manifest.py`)

- **Declared provenance.** Manifest-sourced fields land with provenance `declared`,
  rank **2**: above `rules` (1), below `measured` (3), `vlm_reviewed` (4), `curated` (5),
  `human` (6). Structure comes from intent; a human or a grounded review still outranks it.
- **Geometry is never declared.** Bounds, dimensions and pivot always come from GLB
  measurement (`measured`). `intended_size_m` / `pivot` / `up_axis` are stored inside the
  asset's `generation` block as *expectations* for the Phase 4 QA gates
  (`scale_agreement`, `pivot_at_base`, `up_axis`) — they never populate `bounds`.
- **Prose.** `description` (or `prompt` as fallback) is declared prose. Phase 4's
  `review --verify` renders stills and scores prompt-vs-mesh agreement instead of writing
  new prose; until then the prompt IS the description.
- **Stored on the asset**: `source: "generated"`, `license`, and
  `generation{model, pipeline_version, prompt, negative_prompt, seed, created, supersedes,
  source_images, intended_size_m, pivot, up_axis}` — scanner-owned, refreshed every scan.
  Synty assets carry no `source` key (absent ⇒ synty).
- **Regeneration.** Same stem ⇒ same asset id ⇒ merge, not churn. The measure cache keys on
  `mtime:size`, so a regenerated GLB re-measures automatically; `generation.supersedes`
  chains versions.
- **Missing / invalid sidecar (Phase 3).** The GLB still ingests as a rules-only skeleton
  and the error is reported in the scan summary + `validate`. Phase 4's `manifest_present`
  gate turns this into a hard reject ("no manifest, no entry").

## Validation

`validate_manifest(doc)` (called at ingest; surfaced via `scan` errors) checks: `schema`
string, `id` == GLB stem, `pack` == pack dir, `type` ∈ TYPES, `semantic_role` ∈
SEMANTIC_ROLES, `intended_size_m` a positive [x,y,z], `pivot` ∈ {base, center},
`up_axis` == "Y", required `generation` keys (`model`, `pipeline_version`, `prompt`,
`created`), `license` non-empty, tags/token hygiene.
