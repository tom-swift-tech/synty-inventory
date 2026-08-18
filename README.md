# Synty Pack Inventory

**`synty-inventory`** — offline scanner and query CLI. It turns **your** Synty
Unity (and Unreal) packs into per-pack JSON catalogs so you or an agent can
search by meaning — what a sign depicts, how it mounts, which floor it belongs
on — instead of guessing from filenames like `SM_Prop_Sign_Police_01`.

Does **not** need the Unity Editor. This repo is **not** affiliated with
Synty Studios. It does **not** include Synty assets or generated catalogs.

Requires Python 3.11+ and Synty packs you already license.

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

Optional keys: `viewer_data` (local measured sizes / sign overlays if you
have them; not in this repo), `threejs_v2` (reserved, unused). Any key can
also be set with `SYNTI_UNITY_ROOT`, `SYNTI_EXTRACTED_ROOT`, `SYNTI_CATALOGS`,
`SYNTI_VIEWER_DATA`, `SYNTI_THREEJS_V2`, or `--config PATH`.

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
`<pack_id>.json` with `semantic_role`, structured `placement`,
`dimensions`, and Unity `paths`.

## CLI

Paths default from `config.yaml`. Pass a root only to override.

```bash
synty-inventory discover
synty-inventory scan
synty-inventory scan --pack POLYGON_City
synty-inventory list-packs
synty-inventory search "police" --pack POLYGON_City
synty-inventory details SM_Prop_Sign_Police_01
synty-inventory suggest "police station facade"
synty-inventory placement SM_Prop_Sign_Police_01
synty-inventory validate
synty-inventory gauntlet
```

Optional scan flags:

- `--include-shared` — also catalog `PolygonGeneric` inside each pack
- `--from-package` — index the `.unitypackage` even when an extracted tree exists
- `--extract-previews` — write Synty `preview.png` files under
  `catalogs/previews/` (do **not** commit or share)
- `--vlm` — optional vision pass (`XAI_API_KEY` / `OPENAI_API_KEY` /
  `SYNTI_VLM_API_KEY`). May upload previews; can conflict with the Synty
  or Unity EULA. Off by default.

Re-scan merges. Human / `locked_fields` / `provenance: human` values are
kept. Paths always refresh from disk. `scan --pack` updates that pack and
rebuilds `index.json` from **all** catalogs on disk.

Unreal trees are discovered when present; that path is implemented, not
proven against live packs.

`gauntlet` is a live acceptance suite (expects a `POLYGON_City` catalog
with police/barber richness). CI uses `pytest` and a fake fixture pack.

## Skill

See `skill/SKILL.md`. Copy it to `~/.grok/skills/synty-inventory/SKILL.md`
(or your Claude Code skills dir). Every tool is a `synty-inventory` command
that prints JSON.

## Tests

```bash
python -m pytest
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
