# Spec: weapon directory (synty-inventory `weapons` verb group)

**Written:** 2026-10-16. **Status:** APPROVED by Tom 2026-10-16 (all stated defaults; B-1 = public icon renders off, so `export --profile public`
refuses; NB-1 to NB-15 as written). Approved at commit f6bd3bf. No code exists yet; build plan in §11.
**Branch:** `spec/weapon-directory`, based on `main` at `40f7d3c`.
**Consumers:** the `sit_armory` overlay addon (sit-capabilities, specced separately), games that vendor it, an
in-game shop/trading layer, and a possible external storefront later.
**Workflow:** intent -> **spec** -> plan -> build -> validate.

> Public-repo rule. This repository is public and must never contain Synty content or pack-derived data. This
> document therefore carries id *patterns*, enum values, algorithms and *aggregate* survey figures only. Per-asset
> measured numbers, catalogs, icons, review pages and caches are written outside the repo (under `<catalogs>/` or
> `<threejs_v2>/`) and are never committed (INV-1).

## 1. Problem statement

Tom owns thousands of Synty meshes; roughly 2,300 are weapon-class (survey, 2026-10-16, §4.9) spread over 62 packs and
four genres. A game or shop that wants "a sniper rifle" or "a one-handed fantasy axe" today has to grep file names and
guess a hold pose, a muzzle point and a size. This spec adds a **weapon directory** to synty-inventory: one
engine-neutral, game-neutral profile per weapon holding only objective facts: identity and taxonomy, measured geometry,
suggested tiers (hints, never stats) and generated icon renders. Each game decides names, damage, damage types, effects
and price in its own overlay (`sit_armory`); the directory is what that overlay defaults from.

The directory must be automatic (classification from name patterns plus measurement) yet correctable cheaply: a
generated review page lets Tom flag mistakes, and the fixes land in a committed pattern/override table so the next
build is right without anyone touching individual records again.

## 2. Non-goals

- Not stats: no damage, fire rate, range, recoil, price, rarity names, damage types or effects. `hints` only suggests.
- Not the game overlay. `sit_armory` owns per-game names/stats/prices; this spec owns what it reads.
- Not a new asset scanner. The per-pack catalogs stay the source of truth for identity, `files`, bounds and `gear`.
  The directory is derived from them, never the other way round. The existing `gear` block is read as one input signal
  and never written.
- Not weapon assembly: no composing modular-gun parts or prefab presets into one weapon. Prefab-only presets (§4.9)
  get a record with `geometry: null` (phase 2 candidate, §8 NB-9).
- Not pose or animation authoring (sit_weapons / sit_melee own poses). The directory only names the pose class a
  weapon maps onto.
- Not mech weapons in v1: `SM_Mech_*_Weapon_*` attachments and `geo_*` nodes of the shared mech body are out (§8 NB-3).
  Whole `SM_Wep_*` weapons inside the Mech pack are in, flagged `mech_scale`.
- Not character attachments (`SM_Chr_Attach_*`, non-placeable holstered props): excluded by default (§8 NB-4).
- Not a storefront or any hosting. The directory exports metadata and icons; publishing is Tom's call (§8 B-1).
- Not VLM classification. Catalog fields written by a VLM (`provenance == vlm*`) are never consulted for `kind`,
  `archetype` or `role` (the survey saw a mine tagged `blade`/`melee_weapon` and a rifle tagged `sci_fi`).
- Not Unreal. `files` carries whatever the catalog has; no Unreal-specific work.
- Not a change to any existing catalog field, slim-row projection, `scan` precedence, or `gauntlet` gate (gauntlet
  gains one additive gate, §6 AC30).

## 3. Interfaces / contracts

### 3.1 Where it lives

New package `src/synty_inventory/weapons/` (precedent: `packs/`), a CLI group `weapons`, and two committed data
files beside the existing curated tables:

```
src/synty_inventory/weapons/
  __init__.py        WEAPON_VERSION, WEAPON_GEOMETRY_VERSION, public API below
  candidates.py      candidate selection + exclusion (§3.3)
  classify.py        role / kind / archetype / hold_class / genre (§3.4)
  geometry.py        axes, length, tip/butt, muzzle, grip, support (§3.5)
  hints.py           size_class / weight_class / quality_tier / ammo_family / inventory_cells (§3.6)
  variants.py        colourway discovery (§3.7)
  icons.py           icon pipeline + icon_harness/ (html + js) (§3.8)
  review.py          review page + corrections (§3.9)
  export.py          per-game snapshot + public profile (§3.10)
  guards.py          process lock for build/icons, export-target refusal (§7; PATCH W6)
src/synty_inventory/data/weapon_rules.yaml       name-pattern + threshold tables (human-edited, commented)
src/synty_inventory/data/weapon_overrides.json   corrections (machine-merged, sorted keys; §3.9)
```

Generated, never committed (all under the configured `catalogs` dir):

```
<catalogs>/weapons/directory.json              the directory (§4.1), all packs, sorted by id
<catalogs>/weapons/excluded.json               every rejected candidate with a reason
<catalogs>/weapons/_geometry_cache.json        keyed like _footprint_cache.json (mtime+size+versions)
<catalogs>/weapons/icons/<pack>/<asset_id>.png            256 px
<catalogs>/weapons/icons/<pack>/<asset_id>@64.png         64 px
<catalogs>/weapons/review/index.html           static review page (§3.9)
<catalogs>/weapons/snapshots/                  default --out dir for exports
```

Why a sidecar and not a `weapon` block inside each pack catalog (the footprint precedent)? Footprint is a pure
function of one mesh; the weapon directory needs cross-record context (family grouping, per-archetype statistics for
the tier hint, `duplicate_of`, the override table) and a public/private export profile. `scan --rebuild` also discards
non-human catalog fields, which would throw away derived data that is expensive to regenerate (geometry, icons).
`catalog.py` globs only top-level `*.json`, so a `weapons/` subdirectory is invisible to every existing loader (same
trick `pack_profiles/` uses). Veto-able: NB-1.

### 3.2 CLI

```
synty-inventory weapons build    [--pack CSV] [--rebuild] [--no-geometry] [--report PATH] [--min-coverage F]
synty-inventory weapons show     ID                      # ID = "<pack>/<asset_id>"; bare asset_id allowed iff unique
synty-inventory weapons list     [--pack CSV] [--kind K] [--role R] [--archetype A] [--genre G]
                                 [--status auto|reviewed|overridden] [--max-confidence F] [--limit N]
synty-inventory weapons icons    [--pack CSV] [--ids CSV] [--size 256] [--rebuild] [--variants] [--gpu]
synty-inventory weapons review   [--out DIR] [--pack CSV] [--only-unreviewed] [--max-confidence F]
synty-inventory weapons apply-corrections FILE [--dry-run]
synty-inventory weapons export   --game NAME (--packs CSV | --ids-file FILE) [--out FILE]
                                 [--roles whole,part,...|all] [--engine godot|unity|threejs|all]
                                 [--frame item|asset] [--icons-dir DIR] [--profile private|public]
synty-inventory weapons validate [--directory FILE] [--snapshot FILE]
```

All print JSON on stdout. Exit codes follow the repo convention: `0` ok, `2` bad input (missing catalog, unknown pack,
malformed corrections/overrides), `3` refusal (public profile not approved; override names a missing id when
`--strict`), `4` below `--min-coverage`, `5` renderer unavailable (no icons written; never a placeholder), `6` schema
violation in an input or output file.

### 3.3 Python API (module surface; CLI is a thin wrapper)

```python
# weapons/__init__.py
WEAPON_VERSION = 1             # classification + hints; bump invalidates directory.json
WEAPON_GEOMETRY_VERSION = 4    # geometry algorithm; bump invalidates _geometry_cache.json entries

def build_directory(catalogs_dir: Path, *, packs: list[str] | None = None, rules: dict | None = None,
                    overrides: dict | None = None, measure: bool = True,
                    threejs_v2_dir: Path | None = None) -> tuple[dict, dict]:
    """(directory doc, excluded doc). Pure given its inputs: no clock, no network, no randomness."""

# weapons/candidates.py
def select_candidates(asset: dict, pack_id: str, rules: dict) -> tuple[bool, str, str | None]:
    """(is_candidate, source, reject_reason). source in CANDIDATE_SOURCES; reject_reason in EXCLUDE_REASONS or None."""

# weapons/classify.py
def tokenize_id(asset_id: str) -> list[str]:
    """Split on '_' and camelCase, lower-case, drop pure-digit tokens, apply rules['token_aliases']."""
def classify(asset: dict, pack_id: str, rules: dict, overrides: dict, pack_setting: dict) -> dict:
    """{role, kind, archetype, hold_class, genre, genre_source, family, flags, confidence, matched_rule}"""
def genre_for_pack(setting: str | None, era: str | None) -> str | None:   # §3.4.3; None = undetermined
def family_of(asset_id: str, rules: dict) -> str

# weapons/geometry.py
def measure_weapon(glb: Path, glb_node, scale: float, archetype: str, kind: str, role: str,
                   rules: dict) -> dict | None:
    """The §4.1 `geometry` block, or None when the mesh cannot be decoded. All points in asset-local metres."""
def muzzle_point(verts, forward_axis: str, bounds: dict) -> tuple[list[float], str]:
    """Port of sit_weapons spec §3.6 `muzzle_local` M1-M6 along `forward_axis`; (point, 'face'|'bounds_fallback')."""

# weapons/hints.py
def derive_hints(record: dict, group_stats: dict, rules: dict) -> dict          # the §4.1 `hints` block

# weapons/variants.py
def discover_variants(asset: dict, extracted_root: Path | None) -> list[dict]   # the §4.1 `visuals.variants[]`

# weapons/icons.py
class RendererUnavailable(RuntimeError): ...
def render_icons(records: list[dict], out_dir: Path, *, size: int = 256, variants: bool = False,
                 threejs_v2_dir: Path, synty_glb_root: Path, rebuild: bool = False) -> dict[str, dict]:
    """id -> {icon, thumb, sha256}. Raises RendererUnavailable; never writes a placeholder."""

# weapons/review.py
def write_review_page(directory: dict, out_dir: Path, *, only_unreviewed: bool, max_confidence: float | None) -> Path
def apply_corrections(corrections: dict, overrides: dict) -> tuple[dict, list[str]]   # (new overrides, warnings)

# weapons/export.py
def export_snapshot(directory: dict, *, game: str, pack_ids: set[str] | None, ids: set[str] | None,
                    roles: set[str], engines: set[str], frame: str, profile: str,
                    pack_meta: dict[str, dict], rules_digest: str, overrides_digest: str) -> dict
def digest(obj) -> str:       # sha256 over canonical JSON (sort_keys, separators (',', ':'), ensure_ascii), first 16 hex
```

### 3.4 Classification

#### 3.4.1 Candidate selection (every candidate gets a record or an `excluded` row)

A catalog asset is a **candidate** when it is placeable (`placeable != false`) and ANY of:

| source | test | trust |
|---|---|---|
| `catalog` | `type == "weapon"` or `semantic_role == "weapon"` or `gear.kind == "weapon"` | high |
| `name_token` | `id` matches an `include` pattern in `weapon_rules.yaml: candidates.include` (e.g. `SM_Prop_<weapon noun>`, `SM_Item_<weapon noun>`, `SM_Veh_*Cannon*`) | low (confidence cap 0.6) |

Then `candidates.exclude` patterns reject, each with a closed `reason` (`EXCLUDE_REASONS`): `nonplaceable`, `ui`
(`SM_Wep_Crosshair*`, HUD), `fx`, `character_attachment` (`SM_Chr_Attach_*`), `mech_attachment`, `scenery` (road
arrows, `Mine_Track`/`MineTunnel`, `Club` awnings, windshield/`FaceShield`, ribbon bows, rack/sign props named
`Weapon*`), `tool_prop` (torch; pickaxe/spade props that are not `Wep`-prefixed), `override`. The survey's
false-positive families (§4.9) are the seed list; each must have a fixture trap (§6 AC8). `excluded.json` lists every
rejected candidate-by-match (a token or catalog signal matched) with its reason, so Tom can audit rejections from the
review page ("Excluded" section).

Rule order for exclusion is data (`weapon_rules.yaml`), not code; a test asserts no rule is shadowed (AC9).

> **PATCH (W7, 2026-10-22): scenery, furniture and vehicle attachments.** Tom's W7 list named the StripClub club
> match. The premise was a substring bug; it is not one. The tokenizer splits `StripClub` into `strip`, `club`, so the
> real token `club` fires the `club` rule, and the narrow `club_awning` exclude (`club_?(awning|sign|door|...)`)
> never sees a `StripClub` id. The fix is context, not a matcher change. New data, all in `weapon_rules.yaml`, every
> entry with a synthetic fixture id that first-matches it (AC9, AC50-AC53):
> - **excludes (reason `scenery` unless stated)**, appended at the END of `candidates.exclude` so every id an older entry
>   caught keeps its entry, reason and `matched` name (`strip_club` stays before `bld_env_prefix`): `strip_club` (`strip_?club`: the building and the 8 props); `bld_env_prefix`
>   (`^SM_(Bld|Env)_`: building and environment pieces that carry a weapon noun: mine towers and wheels, vents, ArrowSlit,
>   Bomb, Planetary_Cannon); `chr_prefix` (`^SM_Chr_`, reason `character_attachment`: whole character meshes such as the
>   Shieldmaidens); `sign_prop` (`^SM_(Prop|Sign|SignBorder)_` with token `sign`, none of `wep`: arrow signs, nightclub
>   signs; a `Wep`-prefixed `Sign_Shield` stays, it is an improvised shield); `container_furniture`
>   (`^SM_(Prop|Item)_` with a container or furniture token (crate, case, locker, holder, stand, hanging, hook, altar,
>   display, machine, rack, arcade, box, fence) and none of ammo, bullet, arrow, quiver, magazine, shell, rocket,
>   missile, `wep`: gun cases, knife holders, weapon hangers, claw machines, crates, pike fences); `pestle` (a mortar
>   with a pestle is kitchenware, not artillery).
> - **vehicle attachments**: a new rule `part_attach` (token `attach`, role `part`, `component.slot` misc) between
>   `part_misc` and the emplaced rules: Veh/Heli/Jet/Tug attachments and the `SM_Wep_Attach_*` set are mounting pieces of
>   a vehicle or mech, not hand-held weapons. `Heli_Attach_Missile` and `Attach_Bolt` stay `ammo` (earlier rules). A new
>   rule `emplaced_vehicle` (token `veh`, after `emplaced_cannon`) makes vehicle-mounted guns (`Veh_Extra_Gun`,
>   `Wep_Veh_*`) role `emplaced`, archetype `turret`; a vehicle cannon stays `cannon` (the rule says `tokens_none: [cannon]`
>   so the cannon rule does not count as an ambiguous second match and cost every vehicle cannon a confidence step).
> - **aliases** (unambiguous compound spellings only): `fireaxe` -> axe; `straightsword`, `zweihander`, `ninjato`,
>   `odachi`, `machette` -> sword; `pickacxe` -> pickaxe; `cannonballs` -> cannonball (the Pirate `CannonBalls`
>   were an emplaced cannon, they are loose ammo).
> - Gate: the full before -> after list of changed records (role, archetype, excluded) is printed and reviewed
>   record by record (capture a of the W7 report); no `SM_Wep_*` record may be excluded by these entries. Golf clubs
>   (`Golf_Club`, `Minigolf`) are left as `club`; they are an open question (NB-16). About 100 real weapons whose names
>   the vocabulary does not know stay `unknown` and are listed in NB-16; they are not aliased wholesale.

> **PATCH (W7b, 2026-10-22): `kind` is never null for `whole` and `emplaced`.** The rule above (required iff role is
> whole/emplaced) was not enforced when the archetype was `unknown`: `check_record` exempted those records, 229 live
> `whole` records had `kind: null` and `weapons export` wrote them, so `sit_armory` rejected the snapshot (ARM_E02).
> 1. **Enforcement.** `kind` is non-null iff `role` in {whole, emplaced} (§4.1). `check_record` (so `weapons validate`
>    and every directory write) and the export's snapshot check both reject a violation; the exemption for
>    `archetype == "unknown"` is removed.
> 2. **Inference**, in this order, only for a `whole`/`emplaced` record whose rules left `kind` null (the archetype may stay
>    `unknown`):
>    a. *Vocabulary and rules* (data): `flamethrower` and `chainsaw` alias themselves (the joined `FlameThrower`,
>       `Flame_Thrower`, `ChainSaw` reach the token); `blunderbuss` -> shotgun; `stungun` -> utilgun; `gunstock` -> stock;
>       `cleaver` -> knife; `battery` joins `part_misc`. New rules before `generic_gun`: `assault_rifle` (token `assault`
>       -> `rifle`, 0.8), `heavy_gun_worlds` (token `heavy`, not `preset`, pack `*SciFi_Worlds*` -> `heavy_gun`, 0.75),
>       `alien_gun` (token `alien`, pack `*SciFi_Worlds*` -> `rifle`, 0.7), `preset_gun` (token `preset` -> `whole`,
>       `ranged`, `unknown`, 0.5: every prefab preset in the survey lives under `Prefabs/Weapons/Guns/`).
>    b. *Kind hints* (data, new optional top-level key `kind_hints: {ranged: [...], melee: [...], thrown: [...]}`, canonical
>       post-alias tokens): the first kind whose list shares a token with the id wins, the archetype stays `unknown`,
>       provenance `kind = "rule"`.
>    c. *Measured fallback* (pass 2): when still null and the record is measured, `kind = ranged` if `geometry.long_axis`
>       is `z`, else `melee` (on the live whole set the long axis predicts kind for 75 % of `z` and 89 % of `y` records:
>       a guess), provenance `kind = "measured"`, and the review reason `kind_guessed` (new member of `REASONS`, §4.6).
>    d. *Unmeasured with no hint*: `melee`, reason `kind_guessed`. This does not fail the build: a new pack must still
>       build, and the reason puts the record on the review page.
>    The record is then measured with its final kind (the measurement depends on it, as for archetype).
> 3. A per-id override of `kind` (§4.5) clears `kind_guessed`. Hint tokens are a vocabulary table, not an asset list: one
>    entry names a family of ids (Sceptre, Shock_Stick), never one id.
> Gate: the build report lists, per `kind_guessed` record, id and kind; the lead hand-checks the BONDED subset (24 ids) and a
> sample of the rest from icons.

#### 3.4.2 Role, kind, archetype, hold_class

First-match-wins ordered rules in `weapon_rules.yaml`:

```yaml
version: 1
token_aliases: {smg: [submgun, submachinegun, machinepistol], rpg: [rocketlauncher], ...}
rules:
  - name: sniper_rifle
    match: {tokens_any: [sniper], tokens_none: [scope, crosshair, ammo], packs_none: []}
    set: {role: whole, kind: ranged, archetype: sniper}
    confidence: 0.92
  - name: optic_part
    match: {tokens_any: [scope, sight, ironsight, reddot, holo, optic]}
    set: {role: part, component: optic}
    confidence: 0.9
```

`match` keys: `tokens_any`, `tokens_all`, `tokens_none`, `id_regex`, `packs_any`, `packs_none`,
`gear_two_handed` (true/false/null), `long_m: [lo, hi]` (measured length, applied in pass 2 only). Pass 1 uses name
only; pass 2 (after geometry) may fill a still-`unknown` archetype from measurement at confidence <= 0.4 and applies
the plausibility penalty below.

**role** (closed): `whole` | `part` (gun component: optic, magazine, stock, barrel, body, grip, silencer, bayonet,
rail, trigger, handguard, misc) | `ammo` (bullets, arrows, bolts, shells, rockets as loose projectiles) | `carrier`
(quiver, sheath, scabbard, holster) | `emplaced` (turrets, cannons, siege engines, mortars, flak: not hand-held).
Prefab presets are `whole` with flag `preset`.

**kind** (closed, required iff role in whole/emplaced, else `null`): `ranged` | `melee` | `thrown` | `shield`.

**archetype** (closed; grounded in the survey vocabulary):

| kind | archetypes |
|---|---|
| ranged | `pistol` `revolver` `smg` `rifle` `shotgun` `sniper` `lmg` `heavy_gun` (minigun, gatling, chain gun, HMG) `launcher` (RPG, rocket, grenade, missile) `flamethrower` `bow` `crossbow` `utility_gun` (nail, paint, water, syringe, flare, welder) |
| melee | `knife` (knife, dagger, shiv, tanto, kukri, razor) `sword` (incl. katana, rapier, cutlass, machete, greatsword) `axe` `mace` (mace, flail, morningstar) `hammer` `club` (bat, cudgel, crowbar, pipe) `spear` (spear, pike, trident, harpoon, lance) `polearm` (halberd, naginata, glaive, scythe) `staff` `wand` `whip` `fist_weapon` (knuckles, claw, tonfa, sai) `tool` (Wep-prefixed pickaxe, spade, wrench, chainsaw: improvised) |
| thrown | `grenade` `bomb` (molotov, pipe bomb, dynamite) `mine` (claymore, landmine, IED; placed) `throwing_blade` (shuriken, kunai, throwing knife) |
| shield | `shield` |
| (emplaced, kind = ranged) | `turret` `cannon` `siege_engine` `mortar` |
| any | `unknown` (kept, flagged for review, never dropped) |

Role-specific sub-fields: parts carry `component.slot` and optional `component.fits` (list of archetypes, else null);
carriers `carrier.kind` (`quiver|sheath|scabbard|holster`); ammo `ammo.projectile` (`bullet|shell|arrow|bolt|rocket|other`).

**hold_class** (closed, nullable only for non-wielded roles; derived by the archetype table in `weapon_rules.yaml`):

| value | maps onto | used by archetypes (default) |
|---|---|---|
| `one_hand` | sit_weapons pose class `one_hand` (`SitRanged.CLASS_ONE_HAND`) | pistol, revolver, utility_gun (small), smg when `gear.twoHanded != true` |
| `long_gun` | sit_weapons pose class `long_gun` (two-handed, needs a support point) | rifle, shotgun, sniper, lmg, heavy_gun, launcher, flamethrower, smg (default) |
| `melee_one` | sit_melee guard `one` (`SitMeleeSection.GUARD_ONE`) | knife, sword, axe, mace, whip, wand, tool, fist_weapon |
| `melee_two` | sit_melee guard `two` | spear, polearm, staff; any melee with `gear.twoHanded == true` or length_m >= 1.1 and archetype in {sword, axe, mace, hammer} |
| `melee_bat` | sit_melee guard `bat` | club, hammer |
| `bow` `crossbow` | **none shipped** (no pose class in sit_weapons or sit_melee today) | bow; crossbow |
| `thrown` `shield` | **none shipped** | grenade, bomb, mine, throwing_blade; shield |
| `none` | not hand-held | emplaced; mech_scale flagged weapons; ammo; carrier; part |

`bow`, `crossbow`, `thrown`, `shield` are directory vocabulary only; whether the sibling addons add pose classes for
them is their decision. This is a gap the lead must carry to the sit_weapons/sit_melee owners (report item). The
directory never invents a pose class an addon lacks: the value is a *name* the overlay can map when the pose exists.
`gear.twoHanded` (filled on ~55 % of confirmed weapons) only confirms or breaks ties; it never creates a class.

**Confidence** (float, 2 dp, deterministic):
`base = matched_rule.confidence` (0.5-0.95);
`+0.05` if `gear.twoHanded` agrees with the hold class;
`-0.25` if measured `length_m` is outside the archetype's plausible range (`rules.plausible_length_m[archetype]`);
`-0.15` if the forward-axis sign came from the cross-section fallback, the firearm convention tiebreak or the bow-rule origin fallback (§3.5.2; a measured belly carries no penalty);
`-0.20` if the candidate source is `name_token`, then capped at 0.6;
`-0.10` per extra shadowed rule that also matched with a different archetype (ambiguity);
clamp to [0.05, 0.99]. An override sets 1.0.

#### 3.4.3 Genre

`genre` closed: `modern` | `scifi` | `fantasy` | `western` | `other`. Source of truth is the existing curated
`data/pack_settings.yaml` (`setting`, `era`), so no second pack table:

| pack `setting` | `era` | genre |
|---|---|---|
| `military`, `modern_city`, `post_apoc`, `nature` | any | `modern` |
| `horror` | `modern` | `modern` |
| `horror` | `near_future`, `far_future` | `scifi` |
| `scifi_city`, `scifi_frontier`, `space` | any | `scifi` |
| `fantasy` (includes ancient, viking, pirate, samurai packs per the table) | any | `fantasy` |
| `western` | any | `western` |
| `generic` (and any pack missing from the table) | any | undetermined, see below |

Undetermined falls back to `rules.genre_by_archetype` (firearms -> `modern`; swords, axes, bows, staves -> `fantasy`;
else `other`) with `genre_source: "archetype"`. `genre_source` in `pack | archetype | override`. Per-asset override
beats everything. (Pack-level only: a mixed pack never gets per-asset genre guessing from tags.)

#### 3.4.4 Family

`family = lower(id with a trailing _NN and these suffix tokens stripped: Clean, Rigged, Unrigged, Alt, Optimised,
Separate, Covered, Preset-NN)` joined with `_`. It groups the 80-way shield sets and numbered series for the review
page and for shop-side "pick one of the series". It is informational; it never merges records.

#### 3.4.5 Flags

`flags` (closed, sorted): `token_candidate` `preset` `prefab_only` `shared_glb_node` `mech_scale` `origin_outside_bounds`
`forward_by_fallback` `unmeasured` `duplicate_mesh` `needs_scale_check`. `mech_scale` comes from
`rules.pack_flags` (`POLYGON_Mech: [mech_scale]`); such records keep their archetype but get `hold_class: none` and
`hints.size_class` computed from raw length with `size_basis: "raw"`.

### 3.5 Geometry (measurement rules)

Input: the record's GLB via `sources.glb_geometry.load_triangles(path, node_name, scale=files.glb_scale)` (same loader
and scale handling as footprint, so shared-GLB `glb_node` lists and the 100x-small corrections apply). Collision
hulls are excluded with `naming.SKIP_STEM_RE`. All coordinates are **asset-local metres**, the space of the catalog's
`bounds` (never re-centred). Cache key = `glb_measure._cache_key` + `WEAPON_GEOMETRY_VERSION` + node tag + scale tag.

> **PATCH (W2f, 2026-10-16): cache self-invalidation.** A geometry rule change without a version bump served stale
> cached measurements. Each cache entry now carries `"<WEAPON_GEOMETRY_VERSION>+<12 hex>"`, the 12 hex being the
> sha256 of `geometry.py` with CRLF normalised to LF, so an edit to the file invalidates every entry by itself.
> `directory.json` `generated_from.geometry_version` stays the plain integer (now 4). Known limit: the digest covers
> `geometry.py` only, not helpers it imports (`glb_geometry`, `naming`, `glb_scale`); a change there still needs a
> manual `WEAPON_GEOMETRY_VERSION` bump or `--rebuild`.

#### 3.5.1 Why an axes block

Survey (aggregate, 1,176 whole weapons with bounds): firearms are long on **+Z** with the barrel toward +Z, the
origin 17-35 % from the rear end and laterally centred. Melee (fantasy, sci-fi, samurai, viking, modern) is long on
**+Y**, blade/head toward +Y, origin 10-40 % from the butt end. sit_weapons' hold assumes barrel +Z (`GRIP_BASIS`);
sit_melee's hold measures `tip_z_m`/`butt_z_m` along Z. So one convention cannot be assumed and `geometry` states its
own axes; `export` bakes the rotation into the item frame by default (`--frame item`, §3.10).

#### 3.5.2 Axes

- `long_axis`: the axis of largest AABB extent (`x|y|z`); tie within 5 % resolves to the archetype default
  (ranged `z`, melee `y`, shield: the thinnest axis is the face normal and the longest of the other two is `up`).
- `axes.forward` (signed, e.g. `"+z"`): butt -> muzzle/tip direction.
  1. Let `f` = origin position along `long_axis` as a fraction of extent from the min face (`origin_frac`). If
     `|f - 0.5| >= 0.10`, forward points away from the origin (the origin sits in the grip, nearer the butt:
     measured medians 0.12-0.35 for every group, so the longer side is the working end). `forward_source = "pivot"`.
  2. Else (origin near the middle: polearms, some bows) compare end cross-sections over the outer 10 % of length:
     pointed archetypes (sword, knife, spear, polearm, staff) take the end with the *smaller* cross-section as the
     tip; headed archetypes (axe, mace, hammer, club) the *larger*. `forward_source = "section"`, flag
     `forward_by_fallback`, confidence penalty.

     > **PATCH (W2c, 2026-10-16): firearm convention tiebreak.** The end cross-sections cannot tell a muzzle from a
     > stock: on the live whole-role ranged weapons that fell through to this step, every `-z` result that could be
     > judged by eye was wrong. No shape feature separated the groups (each candidate flipped 8-28 % of the correct
     > ones). For `kind == ranged` and `role == "whole"` only, when the long axis equals the axis named by
     > `rules.axes_expected[genre][kind]`, the sign of that convention decides instead of the end sections. This is
     > NOT a measured shape rule; it stays flagged `forward_by_fallback`, a pivot-decided sign is never overridden
     > (a mismatch there is still the `axes_unexpected` reason), and emplaced weapons (`role != whole`) keep the end
     > sections, unverified. Live effect: 17 whole firearms flipped to `+z`. Known residue: 10 whole ranged records
     > stay `-z` because their pivot decided (3 clearly wrong rocket launchers, 3 ambiguous ones, 2 bunker guns and
     > 2 tripods whose direction is meaningless); they are handled by overrides or exclusion, not by this rule.

     > **PATCH (W2f, 2026-10-16): head-forward rule (geometry version 4).** Hand-checking 16 mid-origin melee on the live
     > set found 6 with the tip/head pointing the wrong way: the "smaller end cross-section" test mistakes a flared
     > butt or pommel for a head. For `kind == melee` on a record whose forward came from this step (origin in the
     > middle band, `forward_source = "section"`) and whose archetype is a *headed* one (`_HEAD_FORWARD` in
     > `geometry.py`: axe, mace, hammer, club, staff, tool, polearm), forward points to the end whose **lateral AABB extent over the outer 25 % of the length is
     > larger**, provided the ratio between the two ends is at least 1.15 (`_HEAD_RATIO`; `_HEAD_FRAC = 0.25`). Below
     > the ratio the old `_section_sign` decides. The source stays `"section"` and `forward_by_fallback` stays set. Not
     > covered, on purpose (reversible, one entry each in `_HEAD_FORWARD`):
     > - **spear** (incl. trident, fishing spear): excluded after the hand check. Reversible: seven live ids would flip
     >   if it were added back (Ancient_Egypt Spear_01, Goblin_War_Camp Prop_Spear_02 and Spear_01, Pirate_Realm
     >   Trident_01, Viking_Realm Spear_01 and Spear_02, Vikings FishingSpear_01). Tom can re-enable the rule for spears
     >   after looking at those seven. **Tom confirmed the spear exclusion on 2026-10-17** (still reversible).
     > - **sword and knife**: on pivot-sourced records the larger-end rule agrees with the pivot sign only 43 % / 51 % of
     >   the time, no better than chance, so it is not applied.
     > - `Wrench_01` is symmetric end to end and keeps the old sign.
     >
     > Effect on the live set: the known-wrong ids of the 16-record hand check are fixed, and the forward flips moved 24
     > records into review (`axes_unexpected`). A per-id `forward` override (§3.9) remains the way to fix any residue.
     > **PATCH (W7, 2026-10-22): head over pivot (geometry version 5).** The W2f rule only decided mid-origin records.
     > A pivot-sourced headed melee whose origin sits nearer the head than the butt (Halberd_06, Farm Scythe_01,
     > AncientEmpire Axe_02, Farm Tool_Axe_01, Horror_Mansion Hatchet_01) pointed away from its head: the pivot rule
     > assumes the origin is in the grip. Two additions, both from the same `_head_sign` measurement (outer 25 % lateral
     > extent, ratio at least 1.15):
     > 1. **R-H1**: for `kind == melee` with archetype in `_HEAD_PIVOT` (axe, mace, hammer, polearm, staff), a
     >    pivot-decided sign is replaced by the head sign when `_head_sign` is non-zero. `forward_source = "head"` (a free
     >    string in the schema), the flag `forward_by_fallback` is NOT set (a measured rule, like the bow belly), and an
     >    override still wins. `club` and `tool` are not in `_HEAD_PIVOT`: side-handle batons (Police_Baton_01, ratio 4.3,
     >    and the Police/Apocalypse/Asylum batons), PipeWrench_01 and the motor-heavy Chainsaw_01 have a bigger end that is
     >    not the working end, and no ratio separates them from the right flips. Sword, knife, spear: as W2f.
     > 2. **R-H2**: `weapon_rules.yaml: head_lead_tokens` (spade, shovel, pitchfork) names the tool tokens whose head leads
     >    (the blade, not the handle, is the working end). For `kind == melee`, archetype `tool`, with one of those tokens,
     >    the head sign replaces the pivot sign the same way. The tokens are passed from `directory.py` to the measurement
     >    as `head_lead` and are part of the cache fingerprint. Live effect: the one `Gen_Spade_01` mesh (17 records
     >    across packs) flips; `Shovel_01` already agreed.
     > `Fireaxe_01` (archetype `unknown`, section sign) becomes `axe` through the `fireaxe` alias (3.4.1 PATCH W7) and is
     > then decided by the W2f rule. Live effect on `forward`: only records whose pivot and head disagree move; every
     > moved record is listed and hand-checked on a before/after sheet (16 records minimum, green arrow = `forward`).
     > Flipped records get a new `item_basis` and therefore a new `icon_input_sha`, so `icons` redraws them.
  3. `bow`: `axes.up` = the long axis; `forward` = the larger of the remaining two axes, sign away from the origin,
     `forward_source = "bow_rule"`, always flagged `forward_by_fallback` (a bow's arrow direction is not recoverable
     from the mesh alone). `crossbow` follows the firearm rule.

     > **PATCH (W2c, 2026-10-16): bow belly rule.** "Away from the origin" gave the wrong sign for most real bows (31
     > flipped on the live set). A strung bow's belly (riser / grip) bulges toward the target, and its limb tips and
     > string sit toward the archer, so the arrow flies from the string toward the riser. The sign is now measured:
     > `belly` = (mean position of the vertices in the middle 20 % along `up`) - (mean position of the vertices in the
     > two outer 10 % tip windows), along the forward axis, as a share of the forward extent; `forward` points to the
     > positive side of `belly`. Only when `|belly| < 0.15` (`_BOW_BELLY_MIN`; a flat stave, or a mesh that is not a
     > bow) does the old origin sign apply, and only that fallback keeps the `forward_by_fallback` flag and its -0.15
     > confidence penalty. `forward_source = "bow_rule"` either way. Live gate: bows from five packs render with the
     > arrow toward the riser.
  4. `shield`: `forward` = the face normal (thinnest axis), sign away from the origin (the origin sits near the arm
     face); `up` = the longest remaining axis.

     > **PATCH (W2b, 2026-10-16): shield front face.** The "sign away from the origin" rule rendered the BACK of
     > real shields (Adventure Shield_01 was `-z`; 64/106 right on the measured set). The sign is now decided by,
     > in order: (a) `strap`: the arm straps / handles are small elongated pieces standing off the back of the
     > plate, so forward points away from the single biggest such piece; (b) `dish`: the plate is convex toward the
     > front, so forward points toward the side where the plate centre stands further out than its rim; (c) only
     > when neither signal decides, the origin rule above, with the middle band resolving to `+`. Signals (a) and
     > (b) set `forward_source = "shield_front"` (new value); (c) keeps `shield_rule`. Result: 104/106 right on the
     > measured set; library-wide `-z` shields 43 -> 2 of 297. Known regression: the two Kids shields (dish signal
     > fires `-z`) and the residual cases go to review via the `axes_unexpected` reason.
     >
     > **PATCH (W2c): Kids shields by rule.** The strap signal now has two tiers. A piece in the outer 10 % of the
     > bounding thickness (centre >= 40 % off the mid-plane) with a stand-off of at least 1.05 counts as a handle even
     > when it is a flat bar barely deeper than wide (Kids stand-off 1.10, offset 0.47); the first tier (stand-off
     > >= 1.5, offset >= 12 %) is unchanged, and the decorative spike arms (offset <= 0.25, stand-off 1.16) and flat
     > bands (stand-off <= 1.0) stay out. Both Kids shields now resolve to `+z` via `shield_front` with no override.
- `axes.up` (signed): ranged `+y` unless the long axis is `y` (then `+z`); melee = the widest remaining axis (the
  blade/guard width), sign `+`, `up_source = "width_axis"`; shield as above.
- `item_basis`: the signed permutation `[[...],[...],[...]]` taking asset-local vectors to the sit_weapons/sit_melee
  item frame (forward -> +Z, up -> +Y, right-handed; the third axis follows). Pure function of `axes`; included so the
  consumer never re-derives it.

Pack convention check: `rules.axes_expected` lists, per (pack-genre, archetype class), the expected `forward`. A
mismatch is not corrected silently: it adds `-0.15` confidence and the reason `axes_unexpected` to `review.reasons`.

#### 3.5.3 Length, tip, butt

`length_m` = extent along `long_axis` (shield: the `up` extent). `tip` = mean of vertices within 2 mm of the max
`forward` coordinate (melee/thrown/shield); `butt` the same at the min end. `pivot_frac` = `origin_frac` along the long
axis. Points are 3-vectors in asset-local metres, rounded to 1e-4.

#### 3.5.4 Muzzle (ranged only: all ranged archetypes except `bow`)

Reuse, do not reinvent: **sit_weapons spec §3.6 `muzzle_local` M1-M6** is the reference (amendments 0.2.0/0.2.1:
muzzle face, tolerance widening). Port, applied at the max-`forward` end:

1. Collect all mesh vertices (post scale, collision excluded), dedupe by position snapped to 0.0001 m.
2. For tol in (0.001, 0.002, 0.005, 0.010) m in turn: keep vertices with `forward_coord >= max_forward - tol`; the
   first tol giving >= 3 distinct points yields `muzzle` = (mean of the two lateral coordinates, `max_forward`) with
   `muzzle_source: "face"`.
3. If 0.01 m still has < 3 points: `muzzle` = (bounds centre on the two lateral axes, `min_up + 0.75 * up_extent`,
   `max_forward`), `muzzle_source: "bounds_fallback"`, reason `muzzle_fallback` in `review.reasons`.

For a +Z-forward, +Y-up gun this is identical to sit_weapons' rule. AC12 holds the port to the Godot implementation.

#### 3.5.5 Grip (`grip`, `grip_r_m`, `grip_source`)

- Melee / thrown_blade / hammer-class: find the handle. Bin the mesh along `forward` in 1 cm bins; `e(bin)` = the
  larger lateral AABB extent of the vertices in the bin (empty bins inherit the previous). Restrict to the butt-side
  60 % of length. The **handle** is the longest contiguous run of bins of length >= 6 cm with `e <= 1.3 * p10(e)`.
  `grip` = the run's centre on the long axis, lateral coordinates = mean of the run's vertices; `grip_r_m` = mean(e)/2
  over the run; `grip_source: "handle"`. No run -> `grip` = origin projected onto the long axis,
  `grip_source: "pivot"`, `grip_r_m` = null.

  > **PATCH (W2d, 2026-10-16): melee grip, surface profile and origin snap.** Measured on the live set, 480 of ~775
  > melee records fell to the `pivot` fallback (grip_r_m null), because the width profile `e` was built from vertices
  > only: a low-poly haft has bins holding one vertex or none, so `e` is 0 there, `p10(e)` is 0, the threshold
  > collapses and no run qualifies. A first W2d attempt (grip = centre of the thin run nearest the butt) was tried
  > and REJECTED on a hand-checked sample of 15 mid-origin melee: the designer's pivot already lies on the handle or
  > shaft for 15 of 15, while the butt-nearest rule landed on butt-end spikes, ferrules and the blade of a
  > machete for 5 of 15 (long poles gripped at their very end). The rule is therefore anchored on the pivot:
  > 1. The base rule above (longest run, vertex profile, p10) runs first and wins when it finds a handle, unchanged.
  > 2. Otherwise a **surface profile** `e'(bin)` is built: the points of a bin are the vertices plus points sampled
  >    along every triangle edge at no more than 5 mm spacing (bins with no points inherit the previous bin). Over the
  >    butt-side 60 % window, `w_ref = max(p20(e'), 3 mm)`, a bin is thin when `e' <= 1.3 * w_ref`, and a **counting
  >    run** is a run of thin bins at least `max(2 cm, min(6 cm, 0.2 * length))` long (rounded up to whole bins).
  > 3. If the origin, projected on the long axis, lies inside a counting run, `grip` = the origin's position on the
  >    long axis with lateral coordinates = mean of the surface points of the run, `grip_r_m` = mean(e')/2 over the
  >    run, `grip_source = "handle"` (the pivot is confirmed as a handle and gains a measured radius).
  > 4. Else, if the origin lies at least 30 % of the length from the butt and a counting run lies within 10 % of
  >    the length of it, `grip` snaps to the nearest point of that run kept `min_run/2` inside the run's end, lateral
  >    and radius as in step 3, `grip_source = "handle"`. (A pivot in the butt-side 30 % is a designer's grip and is
  >    never moved: a machete's hilt is wider than its blade by this profile.)
  > 5. Else the pivot fallback, unchanged. Geometry version 3.
  > Accuracy gate (AC40): a labelled synthetic set, and a hand-checked live sample with the displacement of the grip
  > from the pivot reported (p50 / p90 / max).
  >
  > **PATCH (W2d2/W2f, 2026-10-16): butt inset and live grip check.** A grip centred on a handle run could sit at the
  > very end of the butt, where a hand cannot close. The melee grip's forward coordinate is clamped to at least
  > `fmin + min(0.045, flen / 2)` (`_GRIP_BUTT_INSET_M`; 0.045 m is half the sit_melee `bat_hand_gap_m` of 0.09 m, one
  > hand width); the lateral coordinates and `grip_r_m` are unchanged. Live hand check after the change: the grip lies
  > on the handle or shaft for 15 of 16 sampled mid-origin melee. Known limit: on scythes (a polearm) and other long poles the
  > pivot-anchored rule leaves the grip where the designer put the pivot, which can be far from where a hand would
  > hold it. **Future option, not built:** per-id grip overrides in `weapon_overrides.json` (like the `forward`
  > override, §3.9) for those cases; nothing in this spec depends on it.
- Ranged one_hand / long_gun: `grip` = the origin (`grip_source: "pivot"`): the survey shows the pivot at the
  pistol grip for guns (laterally centred, 17-35 % from the rear). `grip_r_m` = null. This is **assumption A-grip**
  (§8 NB-6), validated in build slice W2 against the hand-tuned `pos` values of the Synty Military guns that
  Extraction/District 7 already measured; if it fails, the table in `rules.grip_proportion[archetype]`
  (fraction along forward, fraction of up) replaces it and the source becomes `"proportion"`.
- `bow`: grip = bounds centre (the riser), `grip_source: "centre"`. `shield`: grip = bounds centre of the back face,
  `grip_source: "centre"`.
- If the origin lies outside the AABB (flag `origin_outside_bounds`, ~1.6 % of whole weapons) the pivot rule is not
  used: `grip` falls to the rules above without the pivot, or null, and `review.reasons` gets `origin_outside_bounds`.

#### 3.5.6 Support point (long_gun hold only)

**Radii are unclamped measured facts** (`grip_r_m`, `support_r_m`). The directory applies no range cap; consumers cap
them to their own pose limits (sit_weapons `support_r` <= 0.06, sit_melee `grip_r` <= 0.045) and treat null as "not
measured".

`support` = point on the forward axis at 0.62 of `length_m` from the butt, lateral/up = centroid of the vertices in
the +-1 cm slice there; `support_r_m` = half the smaller lateral extent of that slice, **unclamped** (a measured
fact; null when the slice has no vertices). `support_source: "proportion"`. Null for any other hold class. These are
estimates by construction; the confidence of the record is not raised by them.

#### 3.5.7 Failure to measure

No GLB, undecodable GLB or a degenerate mesh -> `geometry: null`, flag `unmeasured`, `review.reasons += "no_geometry"`.
Never copied from a sibling or family member (INV-6). Prefab-only presets and 9 bow variants fall here (§4.9).

### 3.6 Hints

All hints are suggestions a game MAY default from; none is a stat. Tables live in `weapon_rules.yaml`.

- `size_class`: `tiny | small | medium | large | huge` by `length_m` against `rules.size_class_cuts_m` (default
  `[0.20, 0.45, 0.90, 1.50]`); `size_basis: "measured" | "raw"` (raw for `mech_scale`); null when geometry is null.
- `inventory_cells`: `[w, h]` ints for grid inventories: `w = clamp(ceil(length_m / 0.30), 1, 6)`, `h = 1` if the
  larger lateral extent < 0.12 m else `2`. (An addition to the shared contract, §10 C-7.)
- `weight_class`: `light | medium | heavy | very_heavy` from `rules.weight_by_archetype`, +1 step when `size_class ==
  huge`, -1 step when `tiny`, clamped.
- `quality_tier`: int 1-5, or **null**. It is null exactly when `rules.tier_base` has no entry for the record: `role`
  in {part, ammo, carrier} or `archetype == "unknown"`. Null means "no tier suggested"; it is not the lowest tier and
  it does not mean "unmeasured" (a record with `geometry: null` still gets a tier; only the triangle-count term is
  skipped). Every `whole` or `emplaced` record with a known archetype has a non-null tier. Consumers fall back to
  their own default tier on null. `base = rules.tier_base[archetype]`; `+1` if a tier-up token is present in the id
  (`gold|golden|ornate|royal|legendary|ancient|elite|master|plasma|power`); `-1` for tier-down tokens
  (`rusty|broken|improvised|makeshift|toy|clean|simple|old`); `+1` if the mesh triangle count is above the p75 of its
  `(archetype, genre)` group (group >= 8 members, else no term); clamp 1-5. Triangle count is objective and cheap
  (read from the same decode).
- `ammo_family`: `handgun | rifle | shotgun | heavy | rocket | grenade | arrow | bolt | energy | fuel | null`
  from `rules.ammo_by_archetype` plus token overrides (`plasma|laser|arc|energy|power` -> `energy`); null for melee,
  shield, parts.

### 3.7 Variants

`visuals.variants[]` describes colourways, found by `variants.discover_variants`:

| mechanism | evidence | v1 handling |
|---|---|---|
| `atlas_alt` | the record's `files.unity_materials` has a material under `Materials/Alts/<Atlas>_NN_<L>.mat`; sibling letters exist on disk in the extracted tree (survey: ~50 % of weapon-class records; 3-6 siblings each) | variants listed with `source` = the sibling material path, relative to the extracted root |
| `material` | a dedicated weapon material with no Alts sibling (~16 %) | none (single colourway) |
| `mesh` | a separate mesh is the colourway (`*_Clean`, `*_Alt_NN`, faction pairs, 80-way shield sets) | not a variant; surfaced via `family` |

Each variant: `{variant_id: "A"|"B"|..., mechanism, source, is_default, icon: str|null}`. The default variant is the
one the catalog points to. **v1 renders only the default colourway** for `icon`; variant icons are produced by
`weapons icons --variants`, which substitutes the sibling atlas texture in the icon harness (§3.8) and is delivered
in slice W5, not W3. A record with unknown colourway (no `unity_materials`, ~16 % of confirmed records) has
`variants: []` and reason `colourway_unknown`.

> PATCH (W5, 2026-10-16): a record whose Alts atlas has a single colourway letter gets `variants: []` (one colourway is
> no choice). A `variants[]` entry may carry `icon_input_sha` (16 hex): digest of the default icon's `icon_input_sha`,
> the sibling texture file's sha256 and the `variant_id`. It decides re-rendering exactly as the default hash does; the
> colourway thumbnail path is derived from the icon path (`<id>@<L>.png` -> `<id>@<L>@64.png`) and is not stored.
> `icons --variants` needs the configured `extracted_root`; a variant whose material or texture cannot be resolved (a
> `.tga` the harness cannot load, a missing tree) is a per-variant failure with its reason, its stale files are
> deleted (INV-8), and `icon` goes back to null.

> **PATCH (W6, 2026-10-16): `visually_identical`.** About 60 % of the colourways in a 60-id live sample are pixel
> duplicates of the default (113 of 189 pairs differ by exactly 0), so a picker listing them is noise. Every
> `variants[]` entry whose default and variant PNGs both exist gets `visually_identical: bool`, computed from the PNGs
> on disk after each render: the share of covered pixels (alpha > 0 in either image) whose largest RGBA channel
> difference exceeds 12/255 is below `VISUALLY_IDENTICAL_MAX_SHARE = 0.005`, **or** is below
> `VISUALLY_IDENTICAL_FAINT_SHARE = 0.01` and none of those pixels differs by more than 40/255 (`ICON_STRONG_CHANNEL`;
> a "faint tail"). The variant is kept (the data says the colourway exists); the flag lets a consumer hide it.
> Calibration (all 285 variant pairs with icons on disk, 2026-10-16): 165 pairs differ in exactly 0 pixels and nothing
> lies in (0, 0.0055); two pairs sit at 0.0055 and two at 0.0062; the next pair is at 0.035. The 0.0055 pair is
> Apocalypse_Wasteland Shield_01 B/C: a real but faint palette shift (render is deterministic: A equals the default
> exactly and B equals C), 26.7 % of the pixels moved by more than 4 levels, 154 pixels (0.55 %) by more than 12, none by
> more than 34; side by side it is the same shield. The 0.0062 pair is Dark_Fantasy Staff_01 B/C, whose only change is a
> 13-pixel gem (up to 125 levels, 11 pixels over 40): a different colourway. The share alone cannot separate them
> (the gem has the larger share), so the strong-pixel count does. Pairs that are subtle but real stay different
> (Goblin_War_Camp Prop_Sword_02 C: 10 % of pixels, at most 22 levels). The flag is carried across a directory
> rebuild only while the icon link itself is carried, and it is recomputed from the PNGs on disk on every `icons` run
> (with or without `--variants`), because it compares with the default icon: redrawing the default (`--rebuild`, or a
> blank icon that now needs the BLEND retry) updates every colourway's flag. `icon_mode` plays no part in it.
> **Tom confirmed the faint-tail rule on 2026-10-17.**

### 3.8 Icon pipeline

Render options, evaluated:

| option | transparent bg | ortho + fixed orientation | grid/HUD-free | new dependency | verdict |
|---|---|---|---|---|---|
| A. synty-glb QA harness (`synty_glb.qa render`, Playwright + three.js) as used by `review`/`packs contact-sheet` | no (`alpha:false`; `bg=magenta/black` only) | no (perspective, fixed named views) | no (grid, HUD, human gizmo) | none | rejected: needs an upstream (synty-glb) change to be icon-grade |
| B. **Own icon harness** in this repo (`weapons/icon_harness/`: one HTML + JS) that imports three.js and the meshopt decoder from the already-installed `synty-glb/node_modules`, driven by the Playwright already used by `qa.py` | yes (`alpha:true`, page screenshot with omitted background) | yes | yes | none new (reuses synty-glb's Node/three install and Playwright) | **recommended** |
| C. Blender 4.2 headless (synty-glb already depends on it) | yes | yes | yes | none new, but ~5-10x slower per asset and a second material model | fallback if B's GL is unavailable; not built in v1 |
| D. Godot | no: `--headless` cannot render; windowed runs steal Tom's desktop | | | | rejected |

Decision: **B**. It reads `synty_glb_root` from config (as `review` does) and fails with `RendererUnavailable`
(exit 5) when `synty_glb_root`, Playwright or Chromium is missing: no placeholder icons are ever written (INV-8).
No file in `synty-glb` is modified. If Tom prefers an upstream change (option A + an alpha/ortho param), that is a
change in a repo this spec does not own (§8 NB-8).

Framing (so a 1.4 m rifle is not a sliver and a 0.2 m pistol is not tiny):
- Orthographic camera looking down the weapon's lateral axis; the icon is rendered with `axes.forward` pointing to
  screen **right** and `axes.up` to screen up, applied through `item_basis` (melee therefore reads horizontally too).
  Shields: face-on, `up` up. `geometry: null` records get no icon.
- Fit: the projected AABB scaled to fill 88 % of the long edge of a square canvas (6 % padding each side), centred
  on the AABB centre; a fixed 3/4 elevation of 15 deg and azimuth 25 deg for depth cues (constant across all icons,
  so icons are comparable).
- Lighting: the synty-glb harness' three-point rig and ACES tone mapping (so colours match the existing stills); no
  grid, gizmo or HUD; background fully transparent.
- Output: 256 px square PNG (`<id>.png`) plus a 64 px thumbnail (`<id>@64.png`, same render downsampled), sRGB.
- Cache: `<catalogs>/weapons/icons/...`; a record's icon is skipped when its `visuals.icon_input_sha` input hash
  (`glb file sha + node + glb_scale + item_basis + harness version`; PATCH W6-0: `item_basis` is hashed because the
  icon depends on orientation) is unchanged, unless `--rebuild`.
- Determinism: the *metadata* (paths, input hash) is deterministic; PNG bytes depend on the GPU/ANGLE backend and
  are not byte-compared across machines. The renderer is launched with a software ANGLE/SwiftShader backend by
  default so repeated runs on one machine are byte-identical (AC17); `--gpu` opts out.

> **PATCH (W6, 2026-10-16): blank renders.** Some alpha-masked materials (MASK, `alphaTest > 0`) render fully
> transparent in the harness (the Mech Shotgun default icon was an empty PNG). A render whose pixels are all alpha 0 is
> retried once with every MASK material forced to BLEND; success is recorded as `visuals.icon_mode = "blend_retry"`
> (the same key on a `variants[]` entry; absent for a normal render, carried across a rebuild only when it is
> `"blend_retry"`). If the retry is still blank the asset fails with reason `blank_render`, no PNG is kept (INV-8), and
> it is listed in `report.failed`. `ICON_HARNESS_VERSION` stays 1, so previously cached icons are not re-checked: a
> pre-W6 blank icon needs `--rebuild` to be retried. `icons` refuses to start beside another inventory process (§7).
> `--gpu` is accepted by the `icons` command (it was documented but not wired).

> **PATCH (W7, 2026-10-22): wrong embedded textures and washed-out retries.** Two converter faults, seen on the live
> icons, are handled at render time (the GLBs belong to the converter and are not touched):
> - **Albedo from the Unity material.** Every `SM_Wep_Shield_Set_*` and `SM_Wep_Shield_Set_Optimised_*` GLB in
>   `POLYGON_Viking_Realm` (160 records) embeds the pack's general decor atlas instead of the shield texture, so the
>   icons show piano keys and plaid. A pixel audit of every whole record with a Unity material found these 160
>   to be the only systematic mismatch (1,132 of 1,295 embed their material's texture; three single records,
>   Samurai `Sword`, `Rigged_Bow_01`, Wasteland `Superheavy_01`, differ and are not touched). `weapon_rules.yaml:
>   icon_albedo_from_material` lists `{name, packs_any, id_regex}` entries; a matching record is drawn with the
>   albedo of its first Unity material (`variants.resolve_variant_texture`, with the extra slot `_Base_Texture` passed
>   by this caller only, so variant resolution is unchanged), substituted by the same mechanism as a colourway. The
>   texture file's sha256 is added to `icon_input_sha` under the key `albedo` ONLY for such records, so every other
>   icon keeps its stored hash and is not redrawn. If the texture cannot be resolved the record keeps the embedded one
>   and the run reports it in `report.warnings`, never a silent fallback.
> - **Retry opacity.** The Mech `GattlingGun_01` GLB carries a single material, the Unity `_Screens` material, with a
>   base-colour factor alpha of 0.47 on an RGB atlas, so MASK at 0.5 discards everything and the BLEND retry then drew the
>   gun translucent and washed out. In the retry, a forced-BLEND material is also set to opacity 1: the factor alpha of
>   an atlas without an alpha channel is an authoring artifact, not translucency. Texture alpha still blends.
>   `ICON_HARNESS_VERSION` stays 1; the two live `blend_retry` records (GattlingGun_01, Shotgun_01) are redrawn with
>   `icons --rebuild --ids`. The Mech GLB's missing body material (Unity lists `PolygonMech_01_A` and
>   `PolygonMech_01_A_Screens`, the GLB keeps only the second) is a converter issue and is recorded in NB-16.

### 3.9 Review page and corrections

`weapons review` writes one self-contained static page `<catalogs>/weapons/review/index.html` (no server, no network,
usable on a phone), referencing the 64 px thumbnails by relative path:

- Sections, in order: **Low confidence** (< 0.6), **Unknown**, then one section per `archetype` (alphabetical), then
  **Parts**, **Ammo**, **Carriers**, then **Excluded** (from `excluded.json`, so false rejections can be restored).
  A record appears in the first section that applies. **Unknown** holds only `role` whole/emplaced records with
  `archetype == unknown`; `role` part/ammo/carrier records (about 775 on the live library) go to their own role
  section so they cannot flood it. Every tile carries a role chip; the jump nav shows a count per section.
  *PATCH note (Tom via lead, 2026-10-16, W4 review): page layout only, no schema change.* Within a section, sorted by genre, then
  family, then id; a family of > 12 near-identical members is collapsed to one tile with a count (`Shield_Set` x80)
  and expands on tap.
- A tile shows: thumbnail, `<pack>/<asset_id>`, archetype, genre, confidence, `review.status`, flags.
- Tap a tile to open a panel with dropdowns for `role`, `kind`, `archetype`, `hold_class`, `genre`, buttons **Mark
  correct**, **Not a weapon**, **Restore** (excluded tiles), a checkbox **Apply to family** (emits a glob), and a note.
- All state is held in `localStorage` (guarded; page works without it). **Download corrections.json** and **Copy to
  clipboard** (for mobile) emit the file below. The page makes no file writes and sends nothing anywhere.

`weapon-corrections/1` (input of `apply-corrections`):

```json
{"schema": "weapon-corrections/1",
 "corrections": [
   {"target": {"id": "POLYGON_Fantasy_Kingdom/SM_Wep_Mace_03"}, "set": {"archetype": "club", "hold_class": "melee_bat"}, "note": "..."},
   {"target": {"glob": "POLYGON_Viking_Realm/SM_Wep_Shield_Set_*"}, "confirm": true},
   {"target": {"id": "POLYGON_City/SM_Prop_Bow_Ribbon_01"}, "exclude": true},
   {"target": {"id": "POLYGON_Fantasy_Kingdom/SM_Wep_Mace_03"}, "renamed_from": ["POLYGON_Fantasy_Kingdom/SM_Wep_Mace_03_old"]}
 ]}
```

`apply-corrections` validates (unknown enum -> exit 6; unknown target pack -> warning), merges into
`data/weapon_overrides.json` (keys sorted, 2-space indent, LF, deterministic; a later correction for the same target
replaces the earlier), and prints the diff. Tom commits the changed file; the next `weapons build` reproduces the fix
on any machine. `weapon_overrides.json` holds ids/globs and enum values only: no measurements, no pack data.

Precedence per field, highest first: **exact-id override** > **longest matching glob override** > **rule match** >
measurement fallback (`unknown`). `set` fields land with `provenance.<field> = "override"`; `confirm: true` with no
`set` marks `review.status = "reviewed"` (the build's own values stand); a `set` marks it `"overridden"`;
`exclude` removes the record to `excluded.json` with reason `override`. A `renamed_from` correction (target must be an
exact id) is merged into that id's entry as a sorted, de-duplicated list (§4.5, INV-13). Overrides that no longer match any asset are
reported, never silently dropped (§7).

### 3.10 Snapshot export

`weapons export` filters the directory to the packs/ids a game uses and writes a JSON file that games commit in their
own private repo and `sit_armory` reads:

```json
{"schema_version": 1,
 "generated_from": {"tool": "synty-inventory 0.1.0", "weapon_version": 1, "geometry_version": 1,
                    "rules_digest": "<16 hex>", "overrides_digest": "<16 hex>",
                    "packs": [{"pack": "POLYGON_Military", "scanned_at": "2026-09-26T..Z", "asset_count": 0}],
                    "filter": {"game": "district7", "roles": ["whole"], "engines": ["godot", "glb"], "frame": "item"}},
 "weapons": [ <weapon record, §4.1>, ... ]}
```

Rules: `weapons` sorted by `id`; JSON written with sorted keys, 1-space indent, `\n` endings, trailing newline; **no
wall-clock, machine path or hostname** anywhere (`scanned_at` is copied from the pack catalog, so identical inputs
give identical bytes, AC19). `--engine` keeps only the named `files.*` keys (always `glb`+`glb_node` when `threejs`
or `all`). `--roles` default `whole`; `all` includes part/ammo/carrier/emplaced. `--icons-dir DIR` copies the 256 px
and 64 px PNGs to `DIR/<pack>/...` and rewrites `visuals.icon`/`thumb` to be relative to the snapshot file.

`--frame item` is the **default**: it bakes every geometry point (and `bounds`, `tip`, `butt`, `muzzle`, `grip`,
`support`) through `item_basis` into the sit_weapons/sit_melee item frame (forward +Z, up +Y), sets
`geometry.frame = "item"` and `generated_from.filter.frame = "item"`, and keeps `item_basis` so the consumer can rotate
the *mesh* to match (the mesh itself is never modified or exported). The bake is a rotation (signed axis permutation)
about the GLB scene origin; it adds no translation. `geometry.node_offset` is the one geometry field the bake does
not touch (see §4.1). Games are the export's only consumer, and `sit_armory` rejects a
snapshot whose frame is not `item` (its ARM_E05). `--frame asset` is opt-in: it leaves geometry in the asset-local
space of the directory (`geometry.frame = "asset"`) with `axes` + `item_basis` for a consumer that rotates itself.
`directory.json` always stores the asset frame; the frame is chosen only at export.

> **PATCH (W6, 2026-10-16): export target.** `--out` is optional; the default is
> `<catalogs>/weapons/snapshots/<game>.json` (`<game>` must be a plain name; a path-like or empty name exits 2). That
> default is a staging file under the generated sidecar, never committed; a game copies it into its own private repo.
> An explicit `--out` is refused with exit 3 when it lies inside this checkout or inside any git work tree that tracks
> `*.synty*` files, so a pack-derived snapshot cannot be written into a public repo by accident (INV-1).
>
> **PATCH (W7b, 2026-10-22): explicit `--out` under the default folder.** An explicit `--out` that lies under
> `<catalogs>/weapons/snapshots/` (the folder the default already writes to) is accepted. Every other refusal stays: an
> `--out` elsewhere inside the catalogs dir, inside a pack root, inside this checkout, or inside a git work tree that tracks
> `*.synty*` files exits 3 and writes nothing. The export also refuses (exit 6, nothing written) when any selected record
> violates the `kind` rule of 3.4.2 PATCH W7b.

**Public profile** (`--profile public`, for an external storefront): emits only `id`, `kind`, `role`, `archetype`,
`genre`, `family`, `hints`, `geometry.length_m`, `visuals.icon`/`thumb`; no `files`, no bounds, no points, no
`pack`-relative paths other than the id. It **refuses (exit 3)** unless `config.yaml` sets
`weapons_public_icons_approved: true`, and prints the reason. Whether public icon renders are licence-safe is not
decided by this spec (§8 B-1).

## 4. Data shapes

### 4.1 `weapon/1` record (one element of `directory.json: weapons[]` and of a snapshot)

```jsonc
{
  "schema_version": 1,
  "id": "POLYGON_Fake_Modern/SM_Wep_Rifle_01",      // "<pack>/<asset_id>", unique (INV-2)
  "pack": "POLYGON_Fake_Modern",
  "asset_id": "SM_Wep_Rifle_01",
  "files": {"glb": "...", "glb_node": null, "godot_scene": null, "unity_prefab": "...", "unity_mesh": "..."},
                                                      // copied from the catalog (engine-filtered on export).
                                                      // glb_node: null | string | [string, ...], see below
  "renamed_from": [],                                 // earlier ids of this weapon (override table, §4.5); default []
  "family": "sm_wep_rifle",
  "role": "whole",                                    // whole | part | ammo | carrier | emplaced
  "kind": "ranged",                                   // ranged | melee | thrown | shield | null (non-whole/emplaced)
  "genre": "modern",                                  // modern | scifi | fantasy | western | other
  "genre_source": "pack",                             // pack | archetype | override
  "archetype": "rifle",                               // closed list §3.4.2, or "unknown"
  "hold_class": "long_gun",                           // one_hand|long_gun|melee_one|melee_two|melee_bat|bow|crossbow|thrown|shield|none
  "component": null,                                  // role=part: {slot, fits}
  "carrier": null,                                    // role=carrier: {kind}
  "ammo": null,                                       // role=ammo: {projectile}
  "flags": [],                                        // §3.4.5
  "duplicate_of": null,                               // "<pack>/<asset_id>" of the first record sharing the same files.glb path
  "geometry": {                                       // null when unmeasured (§3.5.7)
    "frame": "asset",                                 // asset | item (a snapshot is "item" unless exported with --frame asset)
    "node_offset": null,                              // [x,y,z] scene-space translation of the glb_node node, else null
    "axes": {"forward": "+z", "up": "+y", "forward_source": "pivot", "up_source": "fixed"},
    "item_basis": [[1,0,0],[0,1,0],[0,0,1]],
    "bounds": {"min": [0,0,0], "max": [0,0,0], "size": [0,0,0], "pivot": "other"},
    "long_axis": "z",
    "length_m": 0.0,
    "pivot_frac": 0.0,
    "tip": null, "butt": [0,0,0],
    "muzzle": [0,0,0], "muzzle_source": "face",      // ranged (not bow) only, else null
    "grip": [0,0,0], "grip_r_m": null, "grip_source": "pivot",
    "support": [0,0,0], "support_r_m": 0.0, "support_source": "proportion",   // long_gun only, else null
    "triangles": 0
  },
  "hints": {
    "size_class": "large", "size_basis": "measured", "inventory_cells": [4, 1],
    "weight_class": "medium", "quality_tier": 2, "ammo_family": "rifle"
  },
  "visuals": {
    "icon": "icons/POLYGON_Fake_Modern/SM_Wep_Rifle_01.png",        // relative to the directory/snapshot file; null until rendered
    "thumb": "icons/POLYGON_Fake_Modern/SM_Wep_Rifle_01@64.png",
    "icon_input_sha": "<16 hex>",
    "variants": [{"variant_id": "A", "mechanism": "atlas_alt", "source": "<relative material path>", "is_default": true, "icon": null}]
  },
  "review": {
    "status": "auto",                                 // auto | reviewed | overridden
    "confidence": 0.9,
    "reasons": [],                                    // e.g. low_confidence, no_geometry, axes_unexpected, muzzle_fallback, origin_outside_bounds, colourway_unknown, kind_guessed
    "matched_rule": "assault_rifle",
    "candidate_source": "catalog"                     // catalog | name_token
  },
  "provenance": {"archetype": "rules", "kind": "rules", "hold_class": "rules", "genre": "pack_settings",
                 "geometry": "measured", "hints": "rules"}   // per field: rules | override | pack_settings | measured
}
```

`files.glb_node` (copied from the catalog, never written back):
- `null`: the asset is its own GLB (or uses the whole file); geometry covers the entire scene minus collision hulls.
- a **string**: the name of one node inside a shared GLB (e.g. several bows in one `Bows.glb`); geometry covers that
  node and its descendants only.
- a **list of strings**: several node names of one shared GLB shown together (union of their meshes).
All `geometry` points, `bounds` and `length_m` refer to the selected node(s) only, never the whole shared file, and are
expressed in the **GLB scene space** that `sources.glb_geometry.load_triangles` returns (the same space as the catalog's
`bounds`), after `files.glb_scale`. They are not re-based to the node's own origin, so a node placed away from the
scene origin has its pivot away from the weapon (`pivot_frac` and `origin_outside_bounds` report that honestly). For a
single-name selection, `geometry.node_offset` holds the node's world translation so a consumer that instantiates the
node on its own can subtract it. `node_offset` is ALWAYS the node's GLB scene-space translation, unrotated and not
item-baked, in both export frames: it describes the file, and a consumer rotates it itself (`item_basis * node_offset`); it is null for `glb_node` null or a list. A selected node with rotation or scale in
its world transform is not item-baked: it gets reason `node_transform` and is left for review (assumption NB-15). The
export's `--frame item` rotation applies to these points as to any other record; `item_basis` is computed from the
scene-space axes. `shared_glb_node` is set on every record with a non-null `glb_node`.

Types and nullability: strings are non-empty; `kind` null iff `role` in {part, ammo, carrier} (and never null for whole/emplaced, PATCH W7b: also for archetype `unknown`); `hold_class` is `none`
for part/ammo/carrier/emplaced and for `mech_scale`; `geometry` null iff flag `unmeasured`; `tip` null for ranged and
bow; `muzzle` null unless `kind == ranged` and archetype != `bow`; `support` null unless `hold_class == long_gun`;
`hints.size_class`/`inventory_cells` null iff `geometry` null; `hints.quality_tier` null iff role in {part, ammo,
carrier} or archetype `unknown` (§3.6); all float fields rounded to 1e-4 (confidence 2 dp).

### 4.2 `weapon-directory/1` (`directory.json`)

```json
{"schema": "weapon-directory/1", "weapon_version": 1, "geometry_version": 1,
 "rules_digest": "<16 hex>", "overrides_digest": "<16 hex>",
 "packs": [{"pack": "...", "scanned_at": "...", "asset_count": 0, "candidates": 0, "records": 0, "excluded": 0}],
 "counts": {"by_role": {}, "by_kind": {}, "by_genre": {}, "by_archetype": {}, "by_status": {}},
 "weapons": [ ... ]}
```

### 4.3 `excluded.json`

```json
{"schema": "weapon-excluded/1", "excluded": [{"id": "<pack>/<asset_id>", "reason": "scenery", "matched": "<rule or token>", "source": "name_token"}]}
```

### 4.4 `weapon_rules.yaml` top-level keys (schema-checked on load, exit 6 on violation)

`version`, `token_aliases`, `candidates.{include,exclude}`, `rules[]` (`name`, `match`, `set`, `confidence`),
`hold_by_archetype`, `genre_by_archetype`, `plausible_length_m`, `axes_expected`, `grip_proportion`,
`size_class_cuts_m`, `weight_by_archetype`, `tier_base`, `ammo_by_archetype`, `pack_flags`, `family_strip_tokens`;
PATCH W7: `head_lead_tokens` (list of canonical tokens) and `icon_albedo_from_material` (`[{name, packs_any, id_regex}]`),
PATCH W7b: `kind_hints` (`{ranged|melee|thrown: [canonical tokens]}`); all optional, defaulting to empty.

### 4.5 `weapon_overrides.json`

```json
{"schema": "weapon-overrides/1",
 "ids":   {"<pack>/<asset_id>": {"set": {}, "confirm": false, "exclude": false, "renamed_from": [], "note": ""}},
 "globs": {"<pack>/<pattern>":  {"set": {}, "confirm": false, "exclude": false, "note": ""}}}
```

`renamed_from` (ids entries only, never globs) lists the earlier `<pack>/<asset_id>` ids of the weapon now at the entry's
key, for when an id changes (a pack rename, a re-key). The build copies it into the record's `renamed_from` (sorted,
de-duplicated; default `[]`) and into every snapshot, so a game's saved references and `sit_armory`'s previous-id
lookup survive the change. An old id must not equal any live record id or any other record's renamed id (INV-13). An
entry that carries only `renamed_from` changes no classification and does not change `review.status`.

`set` keys allowed: `role`, `kind`, `archetype`, `hold_class`, `genre`, `component`, `carrier`, `ammo`. Geometry,
hints and visuals are never overridable: they are measured/derived, and a wrong one means a wrong rule or a wrong
classification upstream.

> **PATCH (W2e, 2026-10-16): two id-only entry fields.** (1) `forward`: a signed axis (`"+z"`) that replaces the
> measured forward SIGN of that one record, for the few weapons whose pivot or sections decide wrongly and that no
> shape rule can fix (the live set: 3 rocket launchers and 3 siege engines, each judged by eye). Its axis must equal
> the measured forward axis (the long axis; for a bow the depth axis, `forward` being the arrow direction); a different axis is rejected with a warning in `report.warnings`
> and not applied. The record gets `geometry.axes.forward_source = "override"` (new value), loses the
> `forward_by_fallback` flag and the `axes_unexpected` reason that this measurement would have added, and its
> `butt`, `tip`, `muzzle` and `item_basis` follow the overridden sign. The geometry cache fingerprint includes the
> value. (2) `confidence_cap`: a number in `[0.05, 0.59]` that caps `review.confidence` (so the record lands in the
> Low confidence section with reason `low_confidence`); for weapons whose direction is genuinely ambiguous and Tom
> should look. Neither field sets `review.status`; neither forces confidence to 1.0.

### 4.6 Enumerations (single source: `weapons/__init__.py`, mirrored in `weapon_rules.yaml` validation)

`ROLES`, `KINDS`, `ARCHETYPES` (§3.4.2), `HOLD_CLASSES`, `GENRES`, `STATUSES = (auto, reviewed, overridden)`,
`FLAGS`, `REASONS`, `EXCLUDE_REASONS`, `CANDIDATE_SOURCES = (catalog, name_token)`, `SIZE_CLASSES_W =
(tiny, small, medium, large, huge)`, `WEIGHT_CLASSES = (light, medium, heavy, very_heavy)`,
`AMMO_FAMILIES = (handgun, rifle, shotgun, heavy, rocket, grenade, arrow, bolt, energy, fuel)`,
`COMPONENT_SLOTS = (optic, magazine, stock, barrel, body, grip, silencer, bayonet, rail, trigger, handguard, misc)`.

### 4.7 Relation to existing records

| existing | how the directory uses it | written? |
|---|---|---|
| `id`, `files.*`, `files.glb_scale`, `glb_node` | copied into the record | never written back |
| `bounds` | reused when non-null (98 % of confirmed weapons); measured from the GLB otherwise | never written back |
| `gear.kind / twoHanded / paintFamily` | input signals (candidate source, confidence nudge, tier token) | never |
| `type`, `semantic_role` | candidate selection only | never |
| `tags`, `description`, `name` | not consulted when `provenance` is VLM; rules-derived tags may break ties | never |
| `part.*` (mech/ship) | not used | never |
| `data/pack_settings.yaml` | genre source | read only |

Because nothing is written to the pack catalogs, `diff_catalog`, `validate`, `search.db` and `gauntlet`'s existing
gates are unaffected by construction (AC29).

### 4.8 Fixture set (synthetic; committed under `tests/fixtures/weapons/`)

`FakePack` catalogs `FAKE_Modern`, `FAKE_Fantasy`, `FAKE_SciFi`, `FAKE_Generic` plus a programmatically generated GLB
set (boxes/cylinders/cones in `tests/fixtures/weapons/make_glbs.py`, no Synty geometry) and `expected.json` (label per
id). About 140 ids: for each archetype at least two positives; modular parts, ammo, carriers, an emplaced turret; and
the **trap set** from the survey (each must be rejected or classified non-weapon): ribbon bow, road arrow, mine
tunnel, club awning, windshield, face shield, crosshair UI mesh, torch, pickaxe prop, weapon rack/sign, confetti
cannon FX, grass blade, finger-gun emote clip, syringe prop. Plus a synthetic gun GLB with an inflated bounds box
(magazine, scope), a sword with a known
handle, a bow, a shield, an origin-outside-bounds mesh, and a Z-long melee (the one observed odd case).

### 4.9 Survey (2026-10-16, read-only, aggregate figures; per-pack table in the build report, not committed)

126 pack catalogs, 59,259 asset records. Broad matcher: 4,527 candidates.

| bucket | count |
|---|---|
| catalog-confirmed placeable (`type`/`semantic_role`/`gear.kind` = weapon) | 2,266 |
| of which whole weapon-like | 1,237 (742 distinct ids) |
| of which modular gun parts | ~600 (432 `gear.kind == attachment`) |
| of which ammo/projectiles | 124 |
| of which carriers (quiver, sheath, scabbard, holster) | 51 |
| of which prefab presets | 48 (14 with GLBs; 34 prefab-only, no bounds) |
| of which emplaced / vehicle-mounted | 43 |
| of which shield-set kit meshes (one pack, 80 + 80 optimised) | 160 |
| token-only placeable (name match; noisy, ~209 look like real weapon props) | 699 |
| non-placeable (1,132 animation clips, 299 UI/HUD, 41 character attachments) | 1,472 |

By genre (catalog-confirmed / whole): modern+military+apoc+ww2 909 / 311 (22 packs); fantasy incl. ancient, viking,
the two bow/sword animation packs 848 / 534 (20); scifi 230 / 160 (7); other (pirate, samurai, kids, novelty) 221 /
178 (28); horror 36 / 35 (5); western 22 / 19 (2). 62 packs have a confirmed weapon; 31 have no hit at all.

Naming: `SM_Wep_*` (2,122 records, 55 packs) is the confirmed backbone; `SM_Gen_Wep_*` (shared tools, 17 packs, same
mesh); un-prefixed `Wep_*` (bow/sword animation packs); `SM_Prop_*` / `SM_Item_*` / `SM_Veh_*` carry real weapons
mixed with scenery; `SM_Chr_Attach_*` (non-placeable); one pack names weapons per creature rather than per type.

Ids collide across packs: 156 of the 1,736 distinct confirmed ids occur in >= 2 packs, and all but ~12 differ in
size (one sword id appears in 24 packs with different meshes). `(pack, asset_id)` is unique; `asset_id` alone is not.

Measurement: bounds present on 98.1 % of confirmed weapons (all `measured`), GLB on 98.1 %, `godot_scene` on 19 %,
`glb_node` on 7 records (shared bow GLB, mech geo nodes), 44 prefab-only records without any mesh. Pivot labels:
`other` 64 %, `center` 16 %, `center_bottom` 14 %, `corner` 6 %. Origin is outside the AABB for ~1.6 % of whole
weapons. Mech-pack weapons are 4-5x hand scale. Colourways: ~50 % of weapon-class records ride a pack-level
`Materials/Alts` atlas swap (same mesh), ~16 % have one dedicated material, ~16 % have no recorded material.

## 5. Invariants

- INV-1 **Nothing derived from a pack is committed here or anywhere public.** `directory.json`, `excluded.json`,
  caches, icons, review pages, snapshots and the survey's per-asset numbers live outside this repo. Only
  `weapon_rules.yaml` and `weapon_overrides.json` (patterns, ids, enums) are committed, plus synthetic fixtures.
- INV-2 `id = "<pack>/<asset_id>"` is unique across the directory and across any snapshot; ids are never reused for
  a different mesh.
- INV-3 Every candidate yields exactly one outcome: one record in `weapons[]` or one row in `excluded.json`
  (`records + excluded == candidates` per pack). A weapon is never silently dropped; unclassifiable ones are
  `archetype: unknown`.
- INV-4 `build` is deterministic: same catalogs + rules + overrides + versions -> byte-identical `directory.json`
  (no clock, no machine path, sorted keys, LF).
- INV-5 The pack catalogs, `search.db` and `index.json` are never modified by any `weapons` verb.
- INV-6 `geometry` is measured from this record's own mesh or null. It is never inherited from a sibling, family
  member, `duplicate_of` or another pack.
- INV-7 All enum-valued fields hold values from §4.6; `hold_class` is derived only from the table in
  `weapon_rules.yaml` or an override, never invented outside `HOLD_CLASSES`.
- INV-8 No placeholder or stale icon is ever written as if rendered; a failed render leaves `visuals.icon: null`.
- INV-9 Hints never carry stats: the schema validator rejects any hints key outside §4.1.
- INV-10 Override precedence is exact id > longest glob > rule > measurement, and re-running `apply-corrections`
  with the same file is a no-op (idempotent).
- INV-13 `renamed_from` ids are well-formed `<pack>/<asset_id>` strings, never equal to a live record id, and each is
  claimed by at most one record; a violation is a schema error (exit 6).
- INV-11 The public profile contains no `files`, no bounds/points and no engine path.
- INV-12 `muzzle` lies on the max-`forward` plane within 0.01 m of `bounds` (`muzzle_source == face`) and inside the
  AABB laterally.

## 6. Acceptance criteria

All numeric thresholds are literals in the tests, not imported constants (so loosening a constant cannot loosen the
test). "Fixture" means §4.8; "live" means this machine's real catalogs.

Classification and candidates
- AC1. Given the fixture catalogs, when `build` runs, then every id in `expected.json` labelled positive has a record
  and `archetype` accuracy over positives >= 0.95 and `kind` accuracy = 1.00 and `role` accuracy >= 0.97.
- AC2. Given the fixture trap set, when `build` runs, then 0 of the trap ids appear in `weapons[]` and each appears in
  `excluded.json` with a reason in `EXCLUDE_REASONS`.
- AC3. Given a fixture with a `name_token` candidate (`SM_Prop_Axe_01`-style), then it yields a record with
  `candidate_source == "name_token"` and `confidence <= 0.6`.
- AC4. For every record, `hold_class` equals the `hold_by_archetype` table value (or the documented `melee_two` /
  `one_hand` exceptions), and a `mech_scale` fixture weapon has `hold_class == "none"`.
- AC5. Given `pack_settings` rows for each setting/era in §3.4.3, `genre_for_pack` returns the table value for all 12
  fixture combinations; a pack missing from `pack_settings.yaml` returns None and the record gets
  `genre_source == "archetype"`.
- AC6. `tokenize_id("SM_Wep_SubMGun_Lite_01")` = `["sm","wep","smg","lite"]`; `tokenize_id("Wep_RecurveBow_01")` =
  `["wep","recurve","bow"]` (camelCase split, digits dropped, alias applied).
- AC7. Given 5 fixture ids sharing a stem across 3 packs, then 15 distinct records, 0 id collisions, and `show` of the
  bare stem exits 2 listing the qualified ids.
- AC8. Every survey false-positive family in §3.4.1 has >= 1 fixture trap and `expected.json` marks it rejected.
- AC9. For every rule in `weapon_rules.yaml` there is >= 1 fixture id for which it is the first match (no shadowed
  rules); `weapons validate` reports shadowed rules and fails (exit 6) if any exist.
- AC10. Every enum field of every record is in §4.6 and the document validates against the `weapon-directory/1`
  jsonschema; a record with a `hints.damage` key fails validation.

Geometry
- AC11. Fixture axes: for the generated gun (Z-long), sword (Y-long), spear (origin mid-length), axe (heavy head),
  bow, shield and Z-long melee GLBs, `axes.forward`, `axes.up` and `long_axis` equal the labels in `expected.json`;
  the spear/axe cases report `forward_source == "section"` and flag `forward_by_fallback`.
- AC12. Muzzle port parity: the fixture `tests/fixtures/weapons/muzzle_golden.json` is copied byte for byte from
  sit-capabilities (`tools/probes/muzzle_golden.json`, schema `sit_muzzle_golden/1`, produced by the sit_armory-owned
  Godot probe running `SitGunHold.muzzle_local`, sit_weapons 0.2.1). It holds five synthetic cases, each with a unique
  vertex list, the `muzzle_local` result and a `fallback` flag. Given each case's vertex list (bounds taken as the
  AABB of that list), `muzzle_point` returns a muzzle within 0.0005 m per axis of `muzzle_local` and a `muzzle_source`
  that equals `bounds_fallback` iff the case's `fallback` is true, for these cases by name: `plain` -> (0, 0.05, 0.5);
  `inflated_bounds` -> (0, 0.05, 0.5), differing from the bounds-centre rule by >= 0.02 m; `edge2_widened` ->
  (0.001333, 0.05, 0.503) (M6 widens a 2-point edge to a face, so `face`, not a fallback); `edge3_face` -> (0,
  0.053333, 0.503), `face`; `cone_apex` -> fallback (0, 0.01, 0.2), `bounds_fallback`. The test reads the golden and
  fails if any of the five names is missing or the file is absent. **A skipped test does not pass AC12**: W2 stays
  open on AC12 until the golden is present and this test passes.
- AC13. Handle detection: the fixture sword/axe/knife with a known handle centre give `grip` within 0.02 m along the
  long axis and `grip_r_m` within 0.005 m of the label; a mesh with no qualifying run gives
  `grip_source == "pivot"`.
- AC14. A long_gun fixture has a non-null `support` at 0.62 +- 0.01 of length with `support_r_m` equal to half the smaller
  lateral extent of the fixture slice within 0.002 m (a fixture whose slice is 0.14 m wide gives 0.07, i.e. no cap at
  0.06); a one_hand fixture has `support == null`.
- AC15. A fixture whose GLB is missing, undecodable or zero-triangle yields a record with `geometry == null`, flag
  `unmeasured`, reason `no_geometry`, hints size fields null; its `family` siblings' geometry is untouched (INV-6).
- AC16. An origin-outside-AABB fixture gets flag `origin_outside_bounds` and does not use `grip_source == "pivot"`.

Icons, variants
- AC17. With the renderer available, `icons` on the 6 rendered fixture GLBs writes 256 px and 64 px PNGs with an alpha
  channel; the corner pixels are fully transparent (alpha == 0); the opaque bounding box fills 0.88 +- 0.02 of the long
  image edge; the tip-side half of the opaque mask has a larger centre-of-mass x than the butt side (forward points
  right); two consecutive runs on the same machine give identical PNG bytes; a second run with unchanged inputs writes
  0 files.
- AC18. With Playwright/Chromium or `synty_glb_root` unavailable, `icons` exits 5, writes no file, and no record gets
  a non-null `visuals.icon`.
- AC19. Fixture `atlas_alt` pack with three sibling materials gives `variants` = [A (default), B, C]; a pack without
  Alts gives `[]` and reason `colourway_unknown` iff no material is recorded.

Review, corrections, export
- AC20. `review` on the fixture directory writes a page that is valid HTML5 (parses with the stdlib parser), contains
  one tile per record and per excluded row, sections in the §3.9 order, references only relative paths, contains
  no `http://`/`https://` URL, and includes a Low-confidence section holding exactly the records with confidence < 0.6.
- AC21. Applying a corrections file (one id, one glob, one exclude, one confirm) then rebuilding yields: the id
  record has the set fields and `review.status == "overridden"`; glob members the glob's values; the excluded id
  moves to `excluded.json` with reason `override`; the confirmed record has status `reviewed` and unchanged fields;
  precedence id > glob holds when both match; applying the same file twice leaves `weapon_overrides.json`
  byte-identical (INV-10).
- AC22. A corrections file with an unknown enum value exits 6 and changes nothing; a target pack that is not
  cataloged yields a warning and is still stored.
- AC23. `export` for a 2-pack filter writes only those packs' records of the requested roles, `weapons` sorted by id,
  top-level keys exactly `schema_version`, `generated_from`, `weapons`; two runs with identical inputs are
  byte-identical (no clock); the output contains no drive letter, `\\` path or hostname.
- AC24. `export` with no `--frame` option on the Y-long fixture sword: `geometry.frame == "item"`,
  `generated_from.filter.frame == "item"`, and the forward direction maps to +Z (`tip.z > butt.z`, tip/butt lateral
  coordinates ~0 within the fixture's tolerance); `export --frame asset` of the same weapon has `geometry.frame ==
  "asset"` and the long extent on y; the two exports of one weapon differ only in the baked geometry fields and
  `frame` values.
- AC25. `export --profile public` without `weapons_public_icons_approved: true` exits 3 and writes nothing; with it,
  the output has no `files` key and no key outside the public list in §3.10.
- AC26. `export --engine godot` keeps only the `files.godot_scene` key (every other `files.*` key removed, including
  `glb` and `glb_node`); `--engine threejs` keeps only `files.glb`, `files.glb_node` and `files.glb_scale`; `--engine all` keeps all.
  > PATCH (W5, 2026-10-16): `glb_scale` added to the threejs set. Dropping it left a threejs consumer unable to size the mesh
  > (the exported bounds are post-scale, the GLB is not). See AC37.

Determinism, additivity, live gates
- AC27. Two `build` runs on the fixture produce byte-identical `directory.json` (INV-4); a run after touching only
  an unrelated file in `<catalogs>` produces the same bytes; bumping `WEAPON_VERSION` changes `weapon_version` and
  nothing else in a no-op rules delta.
- AC28. After `build`, every pack catalog, `index.json` and `search.db` is byte-identical to before (INV-5), checked by
  hashing in the test.
- AC29. The existing `gauntlet` gates and `diff_catalog` pass unchanged on the live catalogs after a full build.
- AC30. `gauntlet` gains gate `weapons_directory` (live, skipped when no directory exists): coverage (`records +
  excluded == candidates`, per pack) = 100 %; ids unique; every enum valid; `geometry` non-null for >= 97 % of
  records whose catalog has a GLB; every `kind == ranged`, non-bow `whole` record with geometry has a `muzzle`;
  every override in the committed file still matches >= 1 asset (stale overrides listed, fail only with `--strict`);
  and **gold regression**: every id in `weapon_overrides.json` classifies to its overridden values after a clean
  rebuild.
  > PATCH (W5): the gold comparison covers the five scalar fields an override can set (role, kind, genre, archetype,
  > hold_class) plus `exclude`. `component`, `carrier` and `ammo` overrides are not compared yet. The gate's checks
  > (directory current, structure, coverage, ids, enums, geometry share, muzzle, overrides, gold) each run
  > independently, so one failing check does not hide the rest; `--strict` (a CLI flag on `gauntlet`) turns stale
  > overrides into a failure.
- AC31. Live first-run report (informational, not a pass/fail gate): counts by role/kind/genre/archetype, the share of
  records with confidence < 0.6, the share `unknown`, the share `needs_review`; printed by `build --report`. The
  first Tom review round turns the corrections it produces into the gold set for AC30.
- AC32. Performance budget: `build` (cached geometry) on the live library <= 120 s; first uncached full geometry pass
  <= 20 min; `icons` for the default colourway of ~1,500 whole weapons <= 90 min on this machine.

- AC33. Given an override entry for fixture id `FAKE_Fantasy/SM_Wep_Sword_02` with `renamed_from:
  ["FAKE_Fantasy/SM_Wep_Sword_02_old"]` and a catalog that only contains the new id, then `build` yields that record
  with `renamed_from == ["FAKE_Fantasy/SM_Wep_Sword_02_old"]`; a record with no such entry has `renamed_from == []`;
  `export` carries the field unchanged; applying the same renamed-target correction twice leaves
  `weapon_overrides.json` byte-identical; a `renamed_from` equal to a live record id exits 6 and writes nothing.
- AC34. Given a fixture shared GLB holding two bow nodes, a record with `glb_node: "Bow_B"` has `bounds` equal to the
  AABB of node `Bow_B` alone, unchanged by the presence of the other node; a record with `glb_node: ["Bow_B",
  "Quiver_B"]` has the union AABB; a record with `glb_node: null` on a single-mesh GLB has the whole-file AABB;
  `node_offset` equals the node's world translation for the single-name record and is null for the list and null
  cases; a node with a rotated world transform gets reason `node_transform`; an item-frame export of the single-name record
  leaves `node_offset` byte-equal to the asset-frame export (it is not rotated by `item_basis`).
- AC35. Given fixture records of role `part`, `ammo`, `carrier` and archetype `unknown`, then `hints.quality_tier` is
  null for all four (and `hints.size_class` is still set where geometry exists); every `whole`/`emplaced` fixture with
  a known archetype, including one with `geometry: null`, has an integer `quality_tier` in 1-5.

- AC36. The review page's family tile and its "Apply to family" scope agree. A family tile collapses the members of ONE
  (pack, family) within a section (never across packs), its count is the number of records it holds in that section, and
  when the family's apply glob matches more ids than that (members in other sections, or excluded rows) the tile reads
  "k of N". The checkbox label reads "Apply to family (N ids)" with N = the number of ids the glob really matches in
  the directory plus excluded rows, and a family correction written from the page matches exactly those N ids. Test:
  a fixture family split over two sections and a second pack with the same family name; for every family tile the
  displayed N equals the length of the id set `corrections` resolves the written glob to.
- AC37. `export --engine threejs` keeps `files.glb_scale` when the record has it, and `validate --snapshot` accepts it
  under the glb engine filter and rejects it under `--engine godot`/`unity` snapshots. Test on a fixture record with a
  non-1.0 `glb_scale`.
- AC38. A fixture override `{"forward": "+z"}` on a record whose measured forward is `-z` yields `forward == "+z"`,
  `forward_source == "override"`, a muzzle at the `+z` end (ranged) and an `item_basis` equal to that of the same mesh
  measured with `+z` natively; the same override with the axis `+x` on a z-long mesh is not applied and appears in
  `report.warnings`; changing only the override value changes the cache entry used (a cached `-z` result is never
  served for a `+z` override); removing the override restores the measured sign.
- AC39. A fixture override `{"confidence_cap": 0.55}` on a record that would score 0.83 gives `confidence == 0.55`,
  reason `low_confidence` and the review page's Low confidence section; a value of 0.6 or above, or a glob entry
  carrying `forward` or `confidence_cap`, is a schema error (exit 6).

- AC40. Melee grip. On a labelled synthetic set of at least 12 meshes (sword with pommel, guard and blade; axe; hammer;
  club/bat tapered to a thin butt; crowbar with hooked ends; short knife; a long spear/staff; a haft whose bins hold
  one vertex or none; each with the origin at the butt, at 20 % and at the middle of its length) the grip lies inside
  the labelled handle span for every mesh and `grip_source == "handle"` whenever the labelled handle contains the
  origin or lies within the snap distance; a mesh whose origin sits on a wide blade within the butt-side 30 % keeps
  `pivot`. On a long pole the grip stays at the origin (never moved to the pole's end). Live: for a hand-checked
  sample of at least 10 mid-origin melee (crowbar, fire axe, machete, bat among them) the grip lies on the handle or
  shaft for at least 9 of 10; the share of melee with `grip_source == "handle"` and the displacement of the grip
  from the pivot (p50 / p90 / max) are reported before and after (480 of 775 were `pivot`).

- AC41. Butt inset. A synthetic melee whose labelled handle run reaches the butt face has `grip` at least
  `min(0.045, flen/2)` m from the butt face along the long axis (literal bounds in the test, not the constant); a mesh
  shorter than 0.09 m clamps to half its length; lateral coordinates and `grip_r_m` are identical with and without the
  clamp.
- AC42. Head-forward rule. On synthetic mid-origin headed melee (axe, mace, hammer, club) with the head at the `-` end,
  `forward` points to the head and `forward_source == "section"`; with an end ratio below 1.15 the old section sign is
  kept; spear, sword, knife and a symmetric wrench are unchanged by the rule. Removing the rule makes the headed cases
  fail.
- AC43. Cache digest. Editing `geometry.py` (a one-byte change in a copy of the module) changes the cache entry version
  string and a cached result is not served; a CRLF-to-LF difference alone does not change it;
  `generated_from.geometry_version` is the plain integer 5 (PATCH W7: it was 4).
- AC44. Blank render. A synthetic MASK-material GLB that renders empty is retried with BLEND and gets
  `visuals.icon_mode == "blend_retry"` with a non-empty PNG; a GLB that stays blank fails with `blank_render`, keeps no
  PNG and appears in `report.failed`; a normal render has no `icon_mode` key; a `directory.json` rebuild keeps the key.
- AC45. `visually_identical`. For a synthetic default/variant pair whose PNGs differ in under 0.5 % of covered pixels
  the variant entry has `visually_identical: true`; between 0.5 % and 1 % it is true only when no differing pixel is
  off by more than 40/255 (8 of 1600 pixels at +30 is true, at +100 false; 17 at +30 is false); above 1 % false; a
  variant with a missing PNG has no key; the flag survives a directory rebuild (a strict test, not an xfail). A default
  icon redrawn by `icons --rebuild` without `--variants` refreshes the flags of its colourways, also when the default
  needed the BLEND retry.
- AC46. Process lock. With another `synty_inventory` python process in the (stubbed) process listing, `weapons build`
  and `weapons icons` exit 2 naming its pid; a listing that raises does not block; `export`, `show`, `list` and
  `validate` are not locked. The suite stubs the listing empty except in the guard's own tests.
- AC47. Export refusals. `export --out` inside this checkout, or inside a git work tree that tracks a `*.synty*` file,
  exits 3 and writes nothing; `--out` omitted writes `<catalogs>/weapons/snapshots/<game>.json`; a game name containing
  a path separator or `..` exits 2.
- AC48. `weapons icons --gpu` is accepted by the parser and drops the software-ANGLE flags from the renderer launch.
- AC49. The synthetic `FAKE_*` fixture catalogs under `tests/fixtures/weapons/catalogs/` are tracked despite the
  `*.synty*` ignore pattern (`.gitignore` negation); no pack-derived file is.
- AC50. StripClub (PATCH W7). Synthetic ids `SM_Bld_StripClub_01` and `SM_Prop_StripClub_01` are `excluded` (reason
  `scenery`), while `SM_Wep_Club_01` and `SM_Prop_Club_01` stay `club`; the existing `club_awning` cases still exclude.
  Removing the `strip_club` entry makes the Prop id classify as `club`; the Bld id is then still caught by
  `bld_env_prefix` (its `matched` changes), and only removing both makes it a `club`.
- AC51. Scenery and furniture excludes (PATCH W7). One synthetic id per entry (`bld_env_prefix`, `chr_prefix`, `sign_prop`,
  `container_furniture`, `pestle`) is excluded with its reason; counter-cases stay: `SM_Wep_Sign_Shield_01` is a `shield`,
  a `Crate_Bullets` id is `ammo`, a `Wep`-prefixed gun with a `case` word in the name is not excluded. Removing any one
  entry makes its id a candidate again (mutation per entry). A fixture proves the table is not shadowed (AC9).
- AC52. Vehicle attachments (PATCH W7). `SM_Veh_Attach_HMG_01`, `SM_Jet_Attach_Bomb_01` and `SM_Wep_Attach_Axe_01` are
  `part` with `component.slot == "misc"`; `SM_Heli_Attach_Missile_01` and `SM_Veh_Attach_Bolt_01` stay `ammo`;
  `SM_Wep_Veh_MiniGun_01` and `SM_Veh_Extra_Gun_01` are `emplaced`/`turret`/`ranged`; `SM_Veh_Cannon_01` stays
  `cannon`. Removing `part_attach` or `emplaced_vehicle` makes the cases fail.
- AC53. Aliases (PATCH W7). `SM_Wep_Fireaxe_01` -> `axe`, `Straightsword`/`Zweihander`/`Ninjato`/`Odachi`/`Machette` ->
  `sword`, `Wep` `Pickacxe` -> `tool`, `CannonBalls_01` -> `ammo`; each fails without its alias.
- AC54. Head over pivot, R-H1 (PATCH W7). On synthetic pivot-sourced axe, mace, hammer, polearm and staff meshes whose
  origin sits at the head end (head extent ratio at least 1.15), `forward` points to the head,
  `forward_source == "head"` and `forward_by_fallback` is false; at a ratio below 1.15 the pivot sign and
  `"pivot"` stay; a club, a tool without a head-lead token, a sword, a knife and a spear with the same shape keep the
  pivot sign; a `forward` override still wins (`"override"`). The test bounds are literals; removing the rule makes
  the headed cases fail.
- AC55. Head-lead tools, R-H2 (PATCH W7). A synthetic `tool` with token `spade`, `shovel` or `pitchfork` and the head
  at the pivot end follows the head; a `wrench`, `chainsaw` and `pickaxe` tool with the same shape keep the pivot sign.
  Editing `head_lead_tokens` changes the cache fingerprint (a stale result is not served). Removing the table makes
  the spade case fail.
- AC56. Albedo from the material (PATCH W7). A synthetic GLB embedding texture A, with a synthetic extracted tree whose
  Unity material points to texture B (by `_Base_Texture`), listed in `icon_albedo_from_material`, renders with B (the
  dominant colour of the tile is B's, not A's) and its `icon_input_sha` differs from the same record without the
  entry; a record not in the table has the same `icon_input_sha` as before (a literal hash); a material with only a
  `_Base_Texture` slot is still unresolved by `resolve_variant_texture` with its default slots (variant behaviour is
  unchanged); an unresolvable material keeps the embedded texture and is reported.
- AC57. Retry opacity (PATCH W7). A synthetic MASK-material GLB whose base-colour factor alpha is 0.4 on an opaque RGB
  texture renders blank first, is retried, gets `icon_mode == "blend_retry"` and the covered pixels have alpha 255
  (not about 102); a MASK material with a real texture alpha channel still blends. Removing the opacity line makes the
  alpha assertion fail.
- AC58. Kind contract (PATCH W7b). `check_record` and `weapons validate` reject a synthetic `whole` record with
  `kind: null` and `archetype: unknown`, and an `emplaced` record with `kind: null`; accept the same record with a kind;
  `weapons export` of a directory holding such a record exits 6 and writes no file. Re-adding the old exemption makes the
  rejection tests fail. A full build of the synthetic fixture catalogs has no whole/emplaced record with a null kind.
- AC59. Kind inference (PATCH W7b). Synthetic ids: `SM_Wep_Assault_01` -> `rifle`, `SM_Wep_Heavy_01` -> `heavy_gun` and
  `SM_Wep_Alien_01` -> `rifle` in a `*SciFi_Worlds*` pack (and unchanged outside it), `SM_Wep_FlameThrower_01` ->
  `flamethrower`, `SM_Wep_Blunderbuss_01` -> `shotgun`, `SM_Wep_Stungun_01` -> `utility_gun`, `SM_Wep_Gunstock_01` -> `part`
  (stock), `SM_Wep_Mining_Laser_Battery_01` -> `part`; a `*_Preset_*` prefab -> `ranged`/`unknown`; kind hints:
  `Shock_Stick`, `Sickle` -> `melee`, a laser id -> `ranged`, `Rock` -> `thrown`, each `kind` provenance `rule` and
  archetype `unknown`. A synthetic measured unknown with long axis `z` -> `ranged`, with `y` -> `melee`, provenance
  `measured`, reason `kind_guessed`, and its geometry is the one measured for that kind (a ranged one has a muzzle and no
  tip); an unmeasured unknown without a hint -> `melee` with `kind_guessed`; an id override of `kind` has no
  `kind_guessed`. Removing each rule, hint list or the measured fallback makes its cases fail (mutation per entry).
- AC60. Explicit export target (PATCH W7b). `--out <catalogs>/weapons/snapshots/x.json` and a nested path below it are
  accepted and written; `--out <catalogs>/weapons/x.json`, `--out <catalogs>/x.json` and a path inside a pack root or
  this checkout still exit 3 and write nothing; a `..` path that resolves out of the snapshots folder exits 3.

## 7. Failure modes

- Catalog missing or unreadable for a requested pack -> exit 2 naming the pack; other packs unaffected only with
  `--pack`; a full build never emits a partial directory.
- `weapon_rules.yaml` / `weapon_overrides.json` fails schema -> exit 6, no output written, message names the key.
- A rule references an unknown enum -> exit 6 at load (never at match time).
- GLB missing / undecodable / zero triangles -> `geometry: null`, flag `unmeasured` (§3.5.7), build continues.
- Shared-GLB `glb_node` not found in the GLB -> treated as undecodable, reason `no_geometry`, one warning in the report.
- Override targets an id/glob that matches nothing -> warning listed under `report.stale_overrides`; exit 0
  (exit 3 with `--strict`). Never silently dropped.
- A `renamed_from` id equals a live record id, or two records claim the same old id -> exit 6 at `build` and at
  `apply-corrections`, naming both ids; nothing is written.
- Two globs of equal length match one id with conflicting values -> exit 6 at `apply-corrections`, naming both.
- `forward` cannot be determined (zero extent on the long axis) -> `geometry: null`, reason `degenerate`.
- Muzzle face has < 3 points at 10 mm -> bounds fallback with `muzzle_source: "bounds_fallback"` and a reason;
  never a null muzzle on a measured ranged weapon (INV-12).
- Renderer unavailable or one asset fails to render -> exit 5 / that asset's `visuals.icon` stays null and is listed
  in `report.failed`; the batch continues; no placeholder (INV-8).
- Icon cache poisoned or `icon_input_sha` mismatch -> re-rendered (not trusted).
- Catalog re-scanned while a build runs -> `build` and `icons` refuse to start if another `synty-inventory` /
  `-m synty_inventory` / `synty_inventory.cli` python process is running (same lesson as the footprint pass: both
  write cache files) -> exit 2 naming the pid. The process listing is PowerShell CIM on Windows or `/proc` on POSIX; if
  the listing itself fails the guard does not block.
- An icon render stays blank after the MASK-to-BLEND retry -> that asset fails with `blank_render` (listed in
  `report.failed`, no PNG kept); the batch continues.
- `export` filter names an unknown pack -> exit 2; an id absent from the directory -> exit 2 listing the ids (a game's
  snapshot must not silently shrink).
- `export` output path inside a git repo that tracks `*.synty*` or inside this repo -> refuse (exit 3): the snapshot is
  pack-derived and goes to a *game's* private repo, never here (INV-1). The default target
  (`<catalogs>/weapons/snapshots/<game>.json`) is exempt because it sits in the generated sidecar.
- Two cataloged packs share an `id` but one mesh file (the `SM_Gen_Wep_*` kit) -> two records, the later one with
  `duplicate_of` set; no merge.
- Pack missing from `pack_settings.yaml` -> genre falls back to archetype with a `genre_source` of `archetype` and a
  report warning (no guess, no crash).

## 8. Open questions / assumptions

**BLOCKING: none.**

**NON-BLOCKING (each states a default; any can be vetoed):**

- B-1 **Are public icon renders licence-safe? (Tom decides; this spec does not.)** Synty's licence forbids distributing the meshes; whether a rendered
  2D icon of a Synty weapon may be shown on a public storefront (a derivative image of licensed art) is not decided
  here. Tom needs to confirm against the Synty EULA (or Synty support) before any `--profile public` use. Default until Tom answers:
  `weapons_public_icons_approved` is false and the public export refuses (AC25). Private in-game shop use
  (icons inside the shipped game build) is the ordinary use of the licensed assets and is not blocked.

- NB-1 The directory is a sidecar under `<catalogs>/weapons/`, not a per-asset catalog block (rationale in §3.1).
  Default: sidecar.
- NB-2 `weapon_overrides.json` (ids + enums) is committed in this public repo. Ids are filenames the repo already
  commits elsewhere (`knowledge.py`, `curated.json`). Default: commit; if Tom judges even ids sensitive, the file
  moves under `<catalogs>/` and loses its "next scan on any machine" property.
- NB-3 Mech-pack attachments (`SM_Mech_*_Weapon_*`) and `geo_*` weapon nodes are out of v1. Whole `SM_Wep_*` weapons
  in the Mech pack are in, flagged `mech_scale`, `hold_class: none`. Default: out.
- NB-4 `SM_Chr_Attach_*` holstered props (41, non-placeable, 15 packs) are excluded (`character_attachment`); they
  are wardrobe pieces. Default: excluded; restorable from the review page "Excluded" section.
- NB-5 Torches and non-`Wep` tool props (pickaxe/spade props) are not weapons; `Wep`-prefixed pickaxe/spade/wrench/
  chainsaw are archetype `tool`. Default as stated.
- NB-6 **A-grip**: for guns the pivot sits at the grip (survey: laterally centred, 17-35 % from the rear). Verified
  in slice W2 against the hand-tuned `pos` of the Synty Military guns; fallback is a proportion table. The grip/
  support points are estimates; sit_armory must treat them as defaults, not truth.
- NB-7 Frame equivalence: geometry is measured on the converted GLB. It is assumed the `godot_scene` export of the
  same weapon shares the GLB's axes (both are Y-up, no mirror). Slice W2 includes a probe on one gun and one sword
  that compares tip direction in both; a mirror would be handled by an `engine_frame` note per pack in
  `weapon_rules.yaml`, not by silent conversion.
- NB-8 Icon renderer: own harness (option B, §3.8). If Tom would rather extend synty-glb's harness upstream
  (alpha + ortho params), that is a change in a repo not owned here and would replace `icon_harness/`.
- NB-9 Prefab-only presets (34 Wasteland presets, 9 bow variants, 1 other) get `geometry: null` in v1. Phase 2 may
  compose them from child-part prefabs via `scene_mine.unity_yaml` + `guid_index`, or resolve to a base mesh via
  `sources.prefab_glb`.
- NB-10 Variant icons (alt colourways, ~half the library) ship after the default icons (slice W5); v1 lists variants
  but renders only the default colourway.
- NB-11 Crossbow is classed `ranged` with hold_class `crossbow`; bows have `forward` flagged as a low-confidence
  guess (arrow direction is not recoverable from the mesh).
- NB-12 Genre follows the pack, not the asset: a modern-looking gun in a fantasy pack is `fantasy`. Override per
  asset or glob when it matters.
- NB-13 Exports default to `--roles whole`; games wanting magazines/scopes/ammo ask for them explicitly.
- NB-14 `quality_tier` and `weight_class` are tuned on the first review round; their tables are data, not code.
- NB-15 `glb_node` records (7 in the survey) are assumed to have translation-only node transforms, so `node_offset` is
  enough to re-base them; verified in slice W2 on those records. A node with rotation or scale is flagged
  `node_transform` and not item-baked until Tom decides. Default: as stated.
- NB-16 (build findings, 2026-10-16; none block, each is Tom's call):
  - Spear is excluded from the head rule and can be re-enabled (7 live ids would flip; §3.5.2 PATCH W2f).
  - Per-id grip overrides are a future option only (§3.5.5 PATCH W2d2/W2f).
  - The firearm convention tiebreak (§3.5.2 PATCH W2c) is not a measured shape rule.
  - `whole` records that are props rather than weapons exist (Knife_Holder, PikeFence).
  - `unknown_share` and a null `quality_tier` are not reconciled.
  - The default-colourway icon batch for the ~1,500 whole weapons is untimed against the AC32 90-minute budget; the
    full ~6,000-render variant batch has not been run and is Tom's call (about 60 % of sampled variants are exact
    duplicates, so `visually_identical` will flag most of them).
  - Blank pre-W6 icons are not re-checked without `--rebuild`.
  - The geometry cache digest covers `geometry.py` only, not its helper modules.
  - W7 (2026-10-22), Tom's call: golf clubs (`Golf_Club`, `Minigolf`, `Sport_Golf_Club`, 9 records) stay `club`; they are
    sports gear, not weapons, and were not named. About 100 real weapons the vocabulary does not know (Cleaver, Sickle,
    Slingshot, Elephant_Gun, BlunderBuss, FlameThrower, Hacksaw, Spanner, Sceptre, Stungun, ...) stay `unknown` and are
    listed in the W7 report; only unambiguous compound spellings were aliased.
  - W7: the Viking_Realm shield GLBs embed the wrong texture and the Mech `GattlingGun_01` GLB keeps only its `_Screens`
    material. Both are converter faults outside this repo (a game that loads these GLBs sees them too); the icons are fixed
    at render time (3.8 PATCH W7), the GLBs are not. Three single records (Samurai `Sword`, `Rigged_Bow_01`, Wasteland
    `Superheavy_01`) embed a texture that differs from their material's and were not investigated.
  - W7b: `kind_guessed` records (kind from the measured long axis, or `melee` when unmeasured) are guesses for the review
    page; the long axis is right for about 3 in 4 `z` and 9 in 10 `y` records.

**Suggested build slices (non-binding; the plan stage decides):** W1 rules + candidates + classify + overrides +
directory without geometry (AC1-10, 27-28); W2 geometry + muzzle parity + grip/support (AC11-16, NB-6/NB-7 probes);
W3 hints + default icons (AC17-18, 3.6); W4 review page + corrections + export + public gate (AC20-26); W5 variants +
variant icons + gauntlet gate + perf (AC19, 29-32). Non-visual slices are number-gated and suit a builder; the icon
harness (W3) and review page (W4) are visual and need the lead to look at captures.

## 9. Gate (run last)

- [x] Every section 1-8 filled (N/A entries justified)? YES (§2 lists non-goals; §8 has no blocking item).
- [x] Every interface in §3 a concrete signature, not prose? YES (CLI synopsis §3.2, Python signatures §3.3, algorithms
      with constants §3.5-3.8).
- [x] Every data shape in §4 a concrete type/schema, not a description? YES (§4.1-4.5 literal JSON shapes, §4.6 enums).
- [x] Every acceptance criterion in §6 testable (maps to an assertion)? YES (AC31 is labelled informational by design;
      it has no pass/fail threshold and is excluded from the gate count).
- [x] Every failure mode in §7 paired with a required behavior? YES.
- [x] §8 BLOCKING list empty? YES. The public-icon licence question (B-1) is carried as NON-BLOCKING with a safe
      default: `--profile public` refuses until Tom sets `weapons_public_icons_approved: true` (AC25), so no
      v1 slice depends on the answer.

GATE RESULT: PASS. Planning for W1-W5 may proceed.

## 10. Changes to the shared contract with the `sit_armory` spec (lead reconciles)

| # | brief's contract | this spec | reason |
|---|---|---|---|
| C-1 | `kind`: ranged \| melee \| thrown \| shield | unchanged, but **nullable** (null for part/ammo/carrier) | the library holds ~600 gun parts, 124 ammo, 51 carriers that are not weapons |
| C-2 | no `role` | new `role`: whole \| part \| ammo \| carrier \| emplaced (+ `component` / `carrier` / `ammo` sub-objects) | same; turrets, siege engines and flak (43) must not get hand holds |
| C-3 | `hold_class` maps onto `one_hand` / `long_gun` and sit_melee's classes | values: `one_hand`, `long_gun`, **`melee_one`, `melee_two`, `melee_bat`** (= sit_melee guards one/two/bat, prefixed to avoid clashing with `one_hand`), plus directory-only **`bow`, `crossbow`, `thrown`, `shield`, `none`**. Bow/crossbow/thrown/shield have **no shipped pose class** in sit_weapons or sit_melee: gap for the lead | survey: shields (~19 % of whole weapons by id), bows and grenades are common; `none` for non-wielded and mech-scale |
| C-4 | `geometry`: bounds, pivot, length_m, nullable grip/support/muzzle/strike-tip | adds **`axes` {forward, up, sources}**, **`item_basis`**, `long_axis`, `pivot_frac`, `tip`, `butt`, `grip_r_m`, `support_r_m`, `*_source` fields, `triangles`, `frame`; whole block nullable; **points in asset-local space** (never re-centred) and `export --frame item` bakes them to the sit_weapons/sit_melee item frame | survey: guns are +Z-long but all melee is +Y-long, while both addons assume a +Z item frame; without `axes` every sword breaks silently |
| C-5 | `visuals`: icon path(s), variants[] | adds `thumb`, `icon_input_sha`; `variants[]` = {variant_id, mechanism, source, is_default, icon}; v1 renders default colourway only; icons are *relative* paths | atlas-swap variants; icons live outside the record file |
| C-6 | `review`: status, confidence | adds `reasons[]`, `matched_rule`, `candidate_source`; status stays auto \| reviewed \| overridden | explains low confidence on the review page |
| C-7 | `hints`: size_class, weight_class, quality_tier, ammo_family | adds `size_basis`, **`inventory_cells`**; `quality_tier` is int 1-5; `size_class` is tiny..huge | grid inventories / shops; mech-scale flag |
| C-8 | `id` `<pack>/<asset_id>`, `pack`, `asset_id`, `files` per engine | adds `family`, `flags[]`, `duplicate_of`, `genre_source`, `provenance{}` | grouping, mech scale, shared-mesh dedupe |
| C-9 | `genre`: modern \| scifi \| fantasy \| … | closed list: modern, scifi, fantasy, western, other; derived from `pack_settings.yaml` | existing curated table, no second pack table |
| C-10 | snapshot `{schema_version, generated_from, weapons:[…]}` | shape kept exactly; `generated_from` = tool version, weapon/geometry versions, rules + overrides digests, per-pack `scanned_at`, filter; no paths or clock; `--roles`, `--engine`, `--frame`, `--icons-dir`, `--profile` options | determinism; public profile gated by B-1 |
| C-11 | `archetype` closed list incl. pistol, smg, rifle, shotgun, sniper, lmg, launcher, sword, axe, mace, spear, bow, crossbow, staff | extended per the survey: + revolver, heavy_gun, flamethrower, utility_gun, knife, hammer, club, polearm, wand, whip, fist_weapon, tool, grenade, bomb, mine, throwing_blade, shield, turret, cannon, siege_engine, mortar, unknown | covers the observed vocabulary |
| C-12 | snapshot frame is the producer's choice | `export` defaults to `--frame item`; `--frame asset` is opt-in; the snapshot records `generated_from.filter.frame` (reconciliation with sit_armory ARM_E05) | games are the only consumer and sit_armory requires the item frame |
| C-13 | no rename tracking | optional `renamed_from: [ids]` on the record (default `[]`), sourced from the override table (§4.5), INV-13 | ids change when packs rename or re-key; sit_armory reads it as `previous_ids` |
| C-14 | `files.glb_node` not defined | defined as null / node name / list of names in a shared GLB; geometry covers the selected node(s) in GLB scene space; `geometry.node_offset` for single-node records (§4.1) | shared bow GLBs and mech nodes |
| C-15 | `hints.quality_tier` always an integer | int 1-5 or null; null iff role in part/ammo/carrier or archetype `unknown`; meaning "no suggestion" (§3.6) | records with no tier base |
| C-16 | radii clamped | `grip_r_m` and `support_r_m` are unclamped measured facts; consumers cap them (§3.5.6) | measured facts stay raw |
| C-17 | `node_offset` frame unspecified | `geometry.node_offset` is always the node's GLB scene-space translation, unrotated and not item-baked, in both export frames; consumers apply `item_basis * node_offset` themselves (§4.1, §3.10, AC34) | it describes the file, not the weapon |

## 11. Build plan (slices W1-W5)

Approved with the spec (Tom, 2026-10-16). Nothing is built yet. This section replaces the non-binding slice sketch in §8.
It moves `hints.py` from W3 to W2 (hints need the measured length and triangle count, so they belong with geometry) and
leaves W3 as icons only.

### 11.1 Rules for every slice

- **Lane:** Claude Sonnet builder subagent (`builder` agent type, brief from `builder-brief-template.md`) in its own
  git worktree of this repo, cut from a lead-resolved base SHA and given a positive file scope (`.agent-scope.json`).
  No Opus builders. Grok and Codex are out of credit and not used. The builder gates and scope-gates its own result;
  the lead verifies the result against the slice's ACs before the next slice starts.
- **Gate command** (run from the slice's worktree; gate on the process exit code, never on piped output):
  `python -m pytest -q tests -k weapons` must exit 0 with a summary line that has no `failed` or `error`
  (`N passed`); then the full `python -m pytest -q` must also exit 0 (existing tests stay green; live-marked tests
  skip in CI). Commits are gated on those two exit codes, not chained after them.
- **Data rules:** every test uses synthetic fixtures under `tests/fixtures/weapons/` (INV-1, AGENTS rule: no Synty
  data in the repo). "Live" below means a local-only step run on this machine against the real catalogs; its output
  stays outside the repo and is reported, never committed.
- **Shared files are owned by one slice:** `src/synty_inventory/cli.py` and `pyproject.toml` are edited only by W1
  (W1 wires every verb to a lazy handler, so later slices add modules, not registrations). `weapons/__init__.py`
  (enums, versions) is W1's and is append-only afterwards only through the `WEAPON_*` constants named in §3.3.
- **Visual checkpoint:** a slice marked "look" is not done until the lead has viewed the named captures and accepted
  them (a builder's description does not count).

### 11.2 Slice table

| slice | depends | parallel-with | ACs | lane | live data | size |
|---|---|---|---|---|---|---|
| W1 rules, candidates, classify, overrides, directory | none | none (foundation) | AC1-AC10, AC27, AC28, AC33 (build half) | Sonnet builder | no (live smoke after merge) | L: ~1,800 lines + fixtures |
| W2 geometry, hints | W1 | W3, W4 | AC11, AC13-AC16, AC34, AC35; AC12 (blocked, §11.4) | Sonnet builder | no (live probe after merge) | L: ~1,500 lines |
| W3 icon harness and icons | W2 | W4 | AC17, AC18 | Sonnet builder, lead reviews captures | renderer needs synty-glb on this machine; fixtures are synthetic GLBs | M: ~700 lines JS/HTML/py |
| W4 review page, corrections, export | W2 | W3 | AC20-AC26, AC33 (rest) | Sonnet builder, lead reviews captures | no | M: ~1,100 lines |
| W5 variants, gauntlet gate, perf, docs | W3 and W4 | none | AC19, AC29-AC32 | Sonnet builder | yes (AC29-AC32 run live) | M: ~700 lines |

W3 and W4 run in parallel after W2 merges; they touch disjoint files (below). W2 itself could start its fixture
generator before W1 merges, but the order is kept strict (W2 needs W1's record skeleton and enums).

### 11.3 Slices in detail

**W1: rules, candidates, classify, overrides, directory skeleton**
- Scope: §3.1 layout up to `directory.json`; §3.2 CLI wiring for ALL verbs (verbs whose module does not exist yet
  exit 2 with "not built in this checkout"); §3.4 candidate selection, tokenizer, ordered rules, role/kind/archetype/
  hold_class/genre/family/flags/confidence; override table load and precedence (§3.9 precedence, §4.5, `renamed_from`
  build half); `directory.json` and `excluded.json` writers; schema validation (`weapons validate`); `build`,
  `show`, `list`. Records written by W1 have `geometry: null` with flag `unmeasured` pending W2 and `hints` all null.
  W1's validator runs in a `pre_geometry` mode that tolerates those nulls; W2 fills them and removes the mode, so
  from W2 on the strict §4.1 nullability rules (including AC35) apply.
- Creates: `src/synty_inventory/weapons/{__init__,cli,candidates,classify,directory,schema,overrides}.py`,
  `src/synty_inventory/data/weapon_rules.yaml`, `src/synty_inventory/data/weapon_overrides.json` (empty
  `weapon-overrides/1`), `tests/test_weapons_{candidates,classify,overrides,directory,determinism}.py`,
  `tests/fixtures/weapons/` (FakePack catalogs `FAKE_Modern`, `FAKE_Fantasy`, `FAKE_SciFi`, `FAKE_Generic`,
  `expected.json`, the §4.8 trap set; GLBs are not needed yet).
- Edits: `src/synty_inventory/cli.py` (one import, one registration call), `pyproject.toml` (package-data globs for
  `data/*.yaml` and `weapons/icon_harness/*` so W3 need not edit it again).
- Gate: the §11.1 command; pass line = both exit codes 0. Plus the AC27/AC28 byte-equality tests inside the suite.
- Live step (after merge, lead or operator, not committed): `synty-inventory weapons build` against the real
  catalogs; report counts by role/kind/genre/archetype, share below 0.6 confidence, share `unknown`. The first
  numbers feed tuning of `weapon_rules.yaml` (a data edit, same slice scope, no new interface).
- Look: none.

**W2: geometry and hints** (depends on W1)
- Scope: §3.5 (axes, length, tip/butt, muzzle port of M1-M6, grip, support, failure to measure, `glb_node` scoping and
  `node_offset`), the geometry cache, §3.6 hints, and the pass-2 measurement fallback in classification (`long_m`,
  plausibility penalty).
- Creates: `src/synty_inventory/weapons/{geometry,hints}.py`, `tests/test_weapons_{geometry,hints,glb_node}.py`,
  `tests/fixtures/weapons/make_glbs.py` (procedural GLB generator: gun, inflated-bounds gun, sword with known
  handle, spear, axe, bow, shield, Z-long melee, origin-outside mesh, shared two-node GLB with
  one rotated node) and its generated output directory (generated at test time, not committed if large).
- Edits (the only shared edits, kept to the call sites): `weapons/directory.py` (call `measure_weapon` and
  `derive_hints` where W1 left the `unmeasured`/null stubs), `weapons/classify.py` (pass 2 only).
- Gate: §11.1 command. AC12 is a separate test file `tests/test_weapons_muzzle_parity.py` that reads the golden of
  §11.4 and calls `muzzle_point` on its vertex lists (no GLB needed). While the golden is absent the test skips with
  reason "muzzle golden not present"; the skip is not a pass, and W2 stays open on AC12 until it passes.
- Live step (after merge): `synty-inventory weapons build` with geometry on the real catalogs; report geometry
  coverage, `origin_outside_bounds` count, forward-source mix, and the two verification probes the spec names: A-grip
  against the Synty Military guns' hand-tuned `pos` (NB-6) and GLB vs `godot_scene` tip direction (NB-7), plus the 7
  `glb_node` records' node transforms (NB-15). Findings are reported to the lead; a failed assumption is a spec
  amendment, not a silent code change.
- Look: none for the code. The lead may ask for a numeric table, not captures.

**W3: icon harness and icons** (depends on W2; parallel with W4)
- Scope: §3.8 option B: the orthographic transparent-background harness, framing and fit, 256 and 64 px output,
  caching, exit 5 / no placeholder on failure, software ANGLE default.
- Creates: `src/synty_inventory/weapons/icons.py`, `src/synty_inventory/weapons/icon_harness/{icon.html,icon.js}`,
  `tests/test_weapons_icons.py` (marked to skip, with a reason, when Playwright/Chromium or the synty-glb root is
  absent; AC18 runs everywhere).
- Edits: none outside those files.
- Gate: §11.1 command; AC17 must PASS (not skip) on this machine at the lead's verification step, run once by the
  lead or operator with the renderer present.
- Look: yes. Checkpoint of exactly 2 captures, produced by the builder from the synthetic fixture GLBs and also from
  one real pack weapon of each of rifle, pistol, sword, axe, bow, shield rendered locally (real renders are not
  committed): (1) a contact sheet of the six fixture weapons at 256 px on a checker background proving transparency
  and forward-points-right; (2) the same six at 64 px. The lead reviews both. The slice does not count as done
  until the lead accepts them.

**W4: review page, corrections, export** (depends on W2; parallel with W3)
- Scope: §3.9 (page generator, corrections schema, `apply-corrections`, merge into the override table), §3.10
  (snapshot export, `--frame item` default and `asset` opt-in, `--engine`, `--roles`, `--icons-dir`, public-profile
  refusal, output-path refusal), `renamed_from` correction handling.
- Creates: `src/synty_inventory/weapons/{review,export,corrections}.py`,
  `src/synty_inventory/weapons/review_template.html`, `tests/test_weapons_{review,corrections,export}.py`.
- Edits: none outside those files. The review page shows an icon when `visuals.thumb` exists and a text-only tile
  otherwise, so W4 does not depend on W3.
- Gate: §11.1 command.
- Look: yes. Checkpoint of exactly 2 captures of the generated page from the fixture directory (headless browser
  screenshots, desktop width and a 390 px phone width) showing the Low-confidence, a per-archetype and the Excluded
  sections, a collapsed family tile and the correction panel open. The lead reviews both.

**W5: variants, gauntlet gate, performance, docs** (depends on W3 and W4)
- Scope: §3.7 variant discovery and `icons --variants`, the `weapons_directory` gauntlet gate (AC30), the live
  report (AC31), the performance budget measurement (AC32), skill and README updates.
- Creates: `src/synty_inventory/weapons/variants.py`, `tests/test_weapons_{variants,gauntlet}.py`, fixture
  `atlas_alt` pack under `tests/fixtures/weapons/`.
- Edits: `src/synty_inventory/gauntlet.py` (add one gate), `src/synty_inventory/weapons/icons.py` (variants branch
  only), `skill/SKILL.md` and `src/synty_inventory/skill.md` (kept in sync), `README.md` (verb list).
- Gate: §11.1 command, then live: `synty-inventory gauntlet` passes with the new gate, and AC29 (existing gates and
  `diff_catalog` unchanged) is shown by a before/after run on the live catalogs.
- Live step: the AC30-AC32 numbers are measured here; the first Tom review round (a W4 output) provides the gold
  corrections AC30 regresses against. Variant icons are produced for a sample of 30 records only in this slice; the
  full ~6,000-render batch is a separate operator job after Tom accepts the sample.
- Look: yes. Checkpoint of 1 capture: one weapon's default and alternate colourway icons side by side. The lead
  reviews it.

### 11.4 Cross-repo dependency (AC12 only)

AC12 compares the Python muzzle port with `SitGunHold.muzzle_local` (sit_weapons 0.2.1) on the fixture GLBs. The
golden values come from a Godot probe that runs in sit-capabilities through `tools/run_godot.ps1` with the console
binary named in that repo's AGENTS.md; the **sit_armory side owns that probe**. Contract between the two repos:
- Source: `tools/probes/muzzle_golden.json` in sit-capabilities (schema `sit_muzzle_golden/1`), five synthetic cases
  (`plain`, `inflated_bounds`, `edge2_widened`, `edge3_face`, `cone_apex`), each holding a unique vertex list, the
  `muzzle_local` result and `fallback`. It is copied byte for byte to `tests/fixtures/weapons/muzzle_golden.json` in
  synty-inventory (plain synthetic literals, no pack data). No GLB is exchanged. If W2 needs a case the golden lacks,
  it names the case to the lead; it does not invent one.
- Consumed by W2 (`tests/test_weapons_muzzle_parity.py`), tolerance 0.0005 m per axis and `fallback` exact. Its absence
  blocks **only AC12**: every other W2 AC gates normally and W2's other work may merge, but AC12 stays open on the
  board and W2 is not closed until the golden lands and the test passes (a skip never counts). No other slice depends
  on it, and nothing in W1-W5 writes to sit-capabilities.
