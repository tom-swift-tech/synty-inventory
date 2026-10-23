# Spec: weapon attachments (amendment to the weapon directory)

**Written:** 2026-10-22. **Status:** APPROVED (Tom, 2026-10-22), with all defaults: "Approve both T4 attachment specs (synty-inventory 17cc1c6,
sit-capabilities b800211) with all defaults: no rail probe in v1 (W9 spike), seats without a measured point come from game
overlays, cross-pack off, additive-percent stacking, magazine = mesh swap, ~150 phone labels after W8d. Start the builds."
Decisions D-1 to D-12 came from Tom's three 2026-10-22 decisions; Q-1 to Q-10 (§12) are decided on their defaults.
The approved base for the build slices is the commit that records this approval.
**Branch:** `spec/attachments`, based on `main` at `e6e82b6` (W7 merged).
**Parent:** [weapon_directory.md](weapon_directory.md) (called "the directory spec" below). Everything there still
holds; this document adds fields and verbs and amends nothing it does not name. `DS§N` points into the directory spec;
a bare `§N` points into this document.
**Consumers:** `sit_armory` (stats per attachment, through game overlays) and `sit_weapons` (mounts the mesh on the gun
at runtime). Both are specced by DM-B in parallel; the lead reconciles the contract list in §10 with their drafts.
**Workflow:** intent -> **spec** -> plan -> build -> validate.

> Public-repo rule (INV-1) applies in full. This document carries token patterns, enum values, algorithms and
> *aggregate* survey figures only. No host ids, no GLB node names, no per-asset numbers. Fixtures are synthetic.

## 1. Problem statement and scope

Tom decided on 2026-10-22 (via the coordinator):

1. **Scope.** The attachments for BONDED's 48 guns only (plus its 4 grenades, which get none). The set is read from
   BONDED's committed overlay; BONDED is read-only here. The mechanism must not be BONDED-specific: it runs on every pack
   the directory already covers, and BONDED's packs are the first live acceptance set.
2. **Depth.** The directory gains *attachment records* (this document). `sit_armory` stats come through game overlays and
   `sit_weapons` mounts the mesh at runtime; both are DM-B's.
3. **Fit.** Measured, plus overrides, as in the weapon pass. Infer from the pack, the names and the *measured mount
   points on the host gun*. Corrections go through the review page and the committed override file.

What the directory must therefore answer, per attachment and per gun: *what is this accessory* (slot, kind, icon, its own
contact frame), *where on this gun does it seat* (point, direction, available span, what already sits there), and *which
guns does it fit* (tiered, explainable, correctable).

### 1.1 Non-goals

- No stats (damage, recoil, spread, magazine capacity). `sit_armory` overlays own them.
- No runtime mounting code, no hide/show logic, no animation (`sit_weapons`).
- No new pack scanning. Attachments are existing `part` records; hosts are existing `whole` records.
- No stock, barrel, bayonet, handguard or rail-segment attachments in v1 (Q-3). The slot vocabulary leaves room.
- No numeric corrections in the committed override file (D-5, INV-17).
- No tilted or curved magazine seating: a magazine seats along the host's up axis, axis-aligned.

### 1.2 Survey (2026-10-22, read-only, aggregate; per-asset numbers stay out of the repo)

BONDED's overlay selects 52 ids from five packs: 48 ranged guns and 4 grenades. Findings that drive this design:

| fact | figure | consequence |
|---|---|---|
| packs with `part` records among the five | 3 of 5 (41 records: 30 + 9 + 2); the other two (one SciFi pack, CyberCity) have none | 8 guns can only get **cross-pack** attachments (Q-1) |
| parts by current `component.slot` | optic 17, magazine 8, grip 2, silencer 2, misc 12 | the `misc` bucket hides red-dots (3), a laser (1), a bipod (1), a carry handle (1), rail segments (4) and 2 non-attachments |
| known false part | 1 vehicle accessory classed `part`/`misc` | the attachment rules must not claim it (AC62) |
| host GLBs with named child meshes | every one of the 48 guns carries at least one (a trigger child on 47) | child nodes are the primary mount source (D-3) |
| host child meshes that are magazines / optics | magazine on 19 of 48, scope or red-dot on 12 of 48, none for laser, silencer, underbarrel | magazine and optic mounts are *measured*; the other three slots are not, by anything in the mesh |
| standalone parts that are dimensional twins of a host child (sorted AABB extents within `max(3 %, 0.8 mm)` per axis; re-run with this exact rule, same 11) | 11 of 40, each matching exactly one host | the pack's own authoring gives a ground truth for compatibility and for placement (D-7) |
| authored forward sign of parts | scopes and red-dots disagree (`-z` for some, `+z` for others, one red-dot has its long axis on `y`) | `long_axis` and `axes.forward` of a part are not the mount axis (§3.3) |
| muzzle face extent of the 48 hosts (A0 probe, max radial extent) | 22 mm to 216 mm, median about 48 mm; the 2 suppressors' mating ends measure about 26 mm | the face extent is polluted by slides and shrouds; a bore diameter needs a ring estimator and may fall back (§4.4) |
| top-of-body probe vs the child-scope seat (12 hosts) | simple top-line estimator: 42 to 172 mm too high; top-facing-area plateau estimator: -98 to +140 mm | **no rail probe is promised in v1**; it is spike W9 with a literal gate (§4.5, AC81) |

## 2. Decisions

| # | decision | reason |
|---|---|---|
| D-1 | Attachments are `role == "part"` records. No new role. | parts already carry role/kind/hold_class conventions, review sections, exclusion and `export --roles part`; a new role would touch `ROLES`, sit_armory ARM_E02 and every `role in {...}` rule |
| D-2 | Attachment data lives in a **new nullable top-level block `attachment`** on part records and a **new `geometry.mounts`** on host records. `component.slot` is **not remapped**. | `component.slot` is read by the schema enum, the rules/overrides validators and the committed gold fixtures; remapping churns all three and gains nothing a derived block cannot give. Red-dots stay `component.slot: misc` until a separate gold regeneration (Q-4) |
| D-3 | Host mount source precedence: `override > child_node > probe > none`. v1 ships `override`, `child_node` and the muzzle `probe` (the A0 probe, reused); the rail probe is W9. | the measurements that exist today are the baked child meshes and the muzzle; everything else was tried and failed (§1.2) |
| D-4 | Occupancy is a first-class field: `mounts.<slot>.occupied_by` lists the baked child nodes (sorted names; empty = free) the game must hide when it mounts a separate attachment in that slot. | a sniper that already has a scope has no *free* optic slot unless the node is hidden; sit_weapons needs the name |
| D-5 | Overrides are **categorical**: they select a mount source, name a child node, disable a slot, add or remove compatibility, flip a forward sign, set slot/kind. They never carry coordinates. Numeric nudges stay game-side in the overlay. | DS§4.5 ("ids/globs and enum values only") and INV-1: a hand-set coordinate on a Synty mesh is pack-derived data. Precedent: BONDED's three hand-probed support points live in its overlay. Q-2 asks whether Tom wants DS§4.5 amended instead |
| D-6 | One frame convention for every attachment/mount: `{point, forward, up}` (§3.1). Placement is `part_T = host_mount_T * anchor_T^-1`. | the only form that is the same for an optic on top, a foregrip underneath and a suppressor on the muzzle |
| D-7 | Compatibility is tiered: `override > twin > same_pack_fit > cross_pack_fit`. Twin pairs are also the *only measured placement truth* for the placement gates. | a pack-authored twin needs no hand labelling; fit tiers are inference and are scored by precision/recall on Tom's labels |
| D-8 | A host slot with `source: none` is **unavailable**, never defaulted to a bounds guess. Compatible-but-unmounted hosts are listed in `pending_hosts` so a game overlay can supply its own mount. | a wrong mount puts a scope in the receiver; a missing one is visible and fixable |
| D-9 | Grenades, melee, shields and ammo get `mounts: null` (`not_applicable`). | no slot exists for them |
| D-10 | Default export output is **byte-identical** to the W7 export unless `--attachments` is passed. | sit_armory and every game snapshot keep working untouched |
| D-11 | Cross-pack fit candidates are generated but excluded from the default export (`--min-compat-tier same_pack_fit`). | 8 BONDED guns have no same-pack attachments; Tom decides whether they borrow (Q-1) |
| D-12 | `WEAPON_ATTACH_VERSION` (new, starts 1) versions attachment records and mounts; it joins the geometry/attachment cache keys, so the cache invalidates without touching `WEAPON_GEOMETRY_VERSION`, which **stays 5** (the exported `generated_from.geometry_version` therefore stays 5 and the default export stays byte-identical, D-10). Record `schema_version` stays 1: the changes are additive. | cache invalidation without breaking readers that ignore unknown keys |

## 3. Attachment record (`attachment` on `role == "part"` records)

### 3.1 Frame convention (used by anchors and mounts)

All points are asset-local metres in GLB scene space after `files.glb_scale`, rounded to 1e-4, exactly as in DS§4.1
(`glb_node` rules unchanged: a part in a shared GLB is measured on its selected node(s) only). A **frame** is

```
{"point": [x, y, z], "forward": [x, y, z], "up": [x, y, z]}     // unit vectors, 4 dp; orthogonal within 1e-3
```

with `right = up x forward`, so the rotation matrix of the frame has columns `[right | up | forward]` and its origin is
`point`. `T(F)` denotes that rigid transform. Meaning of the two vectors, per slot (this table is normative and is the
same for an anchor on the attachment and for a mount on the host):

| slot | `up` = contact normal | `forward` |
|---|---|---|
| `optic` | from the foot toward the body of the optic (host: out of the receiver, host up) | look direction (host: host `axes.forward`) |
| `underbarrel` | from the foot toward the body (host: out of the underside, `-up`) | the device's front (host: host forward) |
| `laser_light` | from the foot toward the body (host: out of the mounting side, default `-up`) | beam direction (host: host forward) |
| `magazine` | from the seat toward the magazine's free end (host: `-up`, down) | the magazine's front (host: host forward) |
| `muzzle` | bore direction, out of the mating face (host: host forward) | roll reference: the device's authored up (host: host `axes.up`) |

Placement: `part_T = T(mount) * T(anchor)^-1` carries the part's asset-local coordinates into the host's asset-local
coordinates. Then `part_T(anchor.point) == mount.point` and the two `up` and `forward` vectors coincide. In an
`--frame item` export each record's fields are baked through **that record's own** `item_basis` (§7, C-20); the same
formula then holds in the item frame provided the consumer has applied each record's own `item_basis` to its own mesh.

### 3.2 Shape

```jsonc
"attachment": {                      // null unless role == "part" and the rules recognise a user-swappable accessory
  "slot": "optic",                   // ATTACH_SLOTS = (optic, muzzle, underbarrel, magazine, laser_light)
  "kind": "scope",                   // per-slot closed list, ATTACH_KINDS below
  "anchor": {                        // the attachment's own contact frame (§3.1), null with reason when unmeasurable; `footprint` is then null too
    "point": [0,0,0], "forward": [0,0,1], "up": [0,1,0],
    "foot_source": "authored_up",    // authored_up | measured | override
    "forward_source": "section",     // section | authored | override
    "symmetric": false               // true when the forward sign is a coin flip (forward_source "authored")
  },
  "footprint": {                     // metres, along the anchor frame
    "length_m": 0.0,                 // extent along anchor.forward
    "width_m": 0.0,                  // extent along right
    "height_m": 0.0,                 // extent along anchor.up
    "foot_length_m": 0.0,            // extent of the contact patch along forward (the rail span it needs)
    "foot_width_m": 0.0,
    "mate_d_m": null                 // muzzle devices only: diameter of the mating ring, else null
  },
  "compatible_hosts": [              // §5; sorted by (tier rank, -score, host); empty list is valid
    {"host": "<pack>/<asset_id>", "tier": "twin", "score": 0.95, "signals": ["twin"], "replaces": []}
  ],
  "pending_hosts": []                // directory: [{"host", "tier"}]; export: ids only. Hosts that look compatible but have mounts.<slot>.source == "none" (D-8)
}
```

`ATTACH_KINDS` (closed, per slot): `optic` = scope, sniper_scope, reflex, iron, carry_handle_scope; `muzzle` =
suppressor, brake, flash_hider (v1 recognises suppressor only); `underbarrel` = foregrip, bipod; `magazine` = standard,
extended, drum, cell; `laser_light` = laser, light; every slot also has `other`. An unrecognised kind inside a known slot is `other` with review reason
`attach_kind_unknown`. Consumers must ignore slots and kinds they do not know (C-25).

`visuals` (icon, thumb, variants) and `kind`/`hold_class`/`hints` follow the existing part conventions unchanged
(DS§3.6, DS§3.7, DS§3.8): `kind` stays null, `hold_class` stays `none`, `hints.quality_tier` stays null; icons render through
the existing pipeline; colourway variants are discovered as for any record. `component` is untouched; its `fits` stays
null (the `compatible_hosts` list supersedes it).

### 3.3 Classification: which parts are attachments

A new ordered table `attachment_rules` in `weapon_rules.yaml` (same first-match-wins machinery as DS§3.4, same
`tokens_any/tokens_all/not_tokens` keys, plus `component_slot` to match on the existing slot) maps a part to
`{slot, kind}`. It runs *after* the part rules, reads `component.slot` and the name tokens, and never changes
`component`. Initial table (token patterns, not asset names):

| tokens | not | -> slot / kind |
|---|---|---|
| `scope` with `sniper` | `handle` | optic / sniper_scope |
| `scope` | `handle`, `sniper` | optic / scope |
| `handle` with `scope` | | optic / carry_handle_scope |
| any of `redot`, `reddot`, `reflex`, `holo` | | optic / reflex |
| `ironsight`, or `iron` with `sight` | | optic / iron |
| `silencer` or `suppressor` | | muzzle / suppressor |
| `foregrip` or `vertgrip` | | underbarrel / foregrip |
| `bipod` | | underbarrel / bipod |
| `laser` | `mining` | laser_light / laser |
| `flashlight` or `torch` | | laser_light / light |
| `drummag`, or `drum` with `mag` | | magazine / drum |
| `mag` or `magazine` (no `cell`) | | magazine / standard |
| `cell` | `mining` | magazine / cell |

Tokens not in the table (rack and rail segments, carry handles without a scope, batteries of a tool, bayonets, stocks)
stay `attachment: null` in v1. A part whose name contains `veh`, `vehicle` or a vehicle-pack family is never an
attachment (AC62). Corrections: `attachment_slot` / `attachment_kind` overrides (§6.1).

### 3.4 Anchor measurement (new module `weapons/attach.py`, one function used for parts and for host child meshes)

Input: the triangles of one mesh (a part's selected node(s), or one child node of a host GLB), `slot`, and the record's
`item_basis` is *not* used. Output: the `anchor` and `footprint`. The authored axes of Synty parts are Y-up; the
algorithm uses that as a prior and verifies it.

1. **Contact side.** Per slot the expected contact side along the authored up axis `Y` is: `optic`, `laser_light` -> the
   `-Y` end (foot at the bottom); `underbarrel`, `magazine` -> the `+Y` end (foot at the top, body hangs down). The
   *foot slab* is the set of vertices within 4 mm of that extreme. `foot_source = "authored_up"`. If the slab holds
   fewer than 3 distinct points (after 0.1 mm dedupe) the other end is tried; if neither gives 3 points the anchor is
   null with reason `anchor_unmeasured`. `up` is the unit vector from the slab toward the opposite end (so it is `+Y`
   for a foot at the bottom). *Known limit (W8c):* a `laser_light` child baked into a host hangs under the receiver, so its foot is at the top; measured with the part rule (foot at the bottom first) an unrotated baked laser takes the wrong end unless the bottom slab has fewer than 3 points. No live host carries a laser child, so this is recorded and not fixed; a later change may treat `laser_light` like `underbarrel` for baked children.
2. **Point.** The centre of the slab's AABB in the two coordinates perpendicular to `up`, at the slab's extreme
   coordinate along `up`. Not the vertex mean (vertex density is arbitrary) and not the part's pivot.
3. **Forward sign (optic, underbarrel, laser_light, magazine).** The along-rail axis is the longer horizontal AABB
   extent (perpendicular to `up`). The sign is the direction of the end whose cross-section area (perpendicular to
   that axis, binned over the outer 25 % of the length) is larger: an objective bell faces forward; for a magazine the
   convex side; for a laser the emitter. When the larger/smaller ratio is below 1.15 the part is `symmetric: true`,
   `forward_source = "authored"` (+axis), review reason `anchor_forward_unsure`, and confidence is capped at 0.59 so it
   lands on the review page. The DS§4.5 `forward` override applies to a part (it sets `forward_source = "override"`).
4. **Muzzle devices.** `up` is the bore direction: the long axis, toward the *larger* end (the free end of a suppressor
   is wider than its mating end; this rule rests on two live samples only, so it is a prior to be re-checked on the
   first labelled muzzle devices, and `symmetric`-style review applies if the end ratio is below 1.15). The mating face is the opposite end; `point` is its ring centre; `mate_d_m` is twice
   the mean radial distance of the mating-face vertices (first tolerance of 1, 2, 5, 10 mm giving 3 or more distinct
   points, like the A0 probe) from that centre. `forward` (roll reference) is the authored `+Y` projected
   perpendicular to `up` (`+Z` if that projection vanishes).
5. **Footprint.** `foot_length_m` / `foot_width_m` are the slab AABB extents along `forward` / `right`;
   `length_m`, `width_m`, `height_m` are the whole mesh AABB extents along the anchor axes.
6. **Confidence and reasons.** `review.confidence` of the record is multiplied by 0.9 when the anchor is null and
   capped at 0.59 for `symmetric`; reasons `anchor_unmeasured`, `anchor_forward_unsure`, `attach_kind_unknown` are new
   members of `REASONS`.

## 4. Host mounts (`geometry.mounts` on whole, ranged hosts)

### 4.1 Eligibility and shape

`mounts` is non-null for records with `role == "whole"`, `kind == "ranged"` and `hold_class` in `one_hand`, `long_gun`
(D-9: grenades, melee, shields, emplaced, bows get `mounts: null`; an optional `geometry.mounts_reason:
"not_applicable"`). For eligible hosts every slot key is present:

```jsonc
"mounts": {
  "optic": {
    "source": "child_node",          // override | child_node | probe | none
    "point": [0,0,0], "forward": [0,0,1], "up": [0,1,0],     // §3.1 frame, null iff source == "none"
    "span_m": 0.0,                   // available length along forward for the foot; null when unknown
    "span_source": "child_foot",     // child_foot (a lower bound) | probe | null
    "occupied_by": ["<GLB node name>"],  // sorted baked children to hide; [] if the slot is free
    "child_node": "<GLB node name>", // the one node the seat was measured from (source child_node/override); else null
    "bore_d_m": null, "bore_source": null,    // muzzle only: ring | face_extent | null
    "confidence": 0.9,
    "reason": null                   // source none: no_child_no_probe | slot_disabled | probe_unavailable
  },
  "muzzle": {...}, "underbarrel": {...}, "laser_light": {...}, "magazine": {...}
}
```

### 4.2 Sources

- **`child_node`.** The host GLB's mesh nodes (collision hulls dropped with `SKIP_STEM_RE`; limited to the descendants
  of the selected `glb_node` when set) are matched by name token against `attachment_rules.child_tokens`:
  `optic` <- scope, sight, reddot, redot, holo; `magazine` <- mag, magazine, drummag, cell, battery;
  `underbarrel` <- foregrip, bipod; `laser_light` <- laser, flashlight; `muzzle` <- silencer, suppressor, brake, compensator, flashhider (for the muzzle slot these children only fill `occupied_by`; the seat always comes from the probe below). Tokens that
  *never* match (trigger, slide, hammer, cylinder, pump, charge, handle, forestock, barrel, stock, switch, pin, clip)
  are a not-list. The child is measured with the **same anchor function** as a part (§3.4), giving its `point`;
  `up` is the slot's contact direction expressed in host axes (optic `+host up`, underbarrel and magazine
  `-host up`, laser_light `-host up`); `forward` is the host's `axes.forward`. `span_m = child.foot_length_m`,
  `span_source = "child_foot"`. `occupied_by` is the sorted list of **every** matching child of that slot (a rifle may carry
  a drum and a box magazine, a shotgun two cells: all of them are hidden when something else is mounted). When there is
  more than one, the seat (`child_node`, `point`, `span_m`) comes from the larger by AABB volume and the record gets
  review reason `mount_ambiguous`.
- **`probe` (muzzle).** `point` is the **seat**: the barrel end, measured by the A0 probe (no second algorithm, AC67) run on the
  host mesh **minus the nodes listed in this slot's `occupied_by`** (vertices and bounds of the reduced mesh). It is not the face of
  a baked brake or suppressor: with a baked device the seat sits behind the device face by the device length (AC84). With an
  empty `occupied_by` the seat equals `geometry.muzzle` exactly. W7's bare-gun `geometry.muzzle` is unchanged, so firing a gun
  with nothing mounted does not change. If removing the nodes leaves no mesh the slot is `none` (`probe_unavailable`).
  `up = host axes.forward`, `forward = host axes.up`. `bore_d_m` comes from a ring estimator on the muzzle-face points: radial histogram of the
  points around the face centre (1 mm bins); the innermost ring holding at least 6 points gives `bore_d_m`,
  `bore_source = "ring"`; no such ring -> `bore_d_m = face extent`, `bore_source = "face_extent"` and the muzzle mount
  confidence is 0.5. `muzzle_source == "bounds_fallback"` -> confidence 0.4 and review reason `muzzle_fallback`
  (existing). `occupied_by` is `[]` unless a muzzle-device child exists; the ring estimator also runs on the reduced mesh.
- **`override` (categorical, §6.1).** Selects the child node to use (`child_node` name), or forces `none`
  (`slot_disabled`). It cannot supply coordinates.
- **`none`.** All of `point`, `forward`, `up`, `span_m` are null; `reason` says why. D-8 applies: consumers treat the
  slot as unavailable. The record gains review reason `mount_missing` per eligible slot that has `none` *and* at least
  one inferred-compatible attachment (so the review page lists exactly the cases that matter).

### 4.3 Occupancy contract

`occupied_by` is a sorted list of GLB node names exactly as in the file (empty = the slot is free). A game that mounts a
separate attachment in that slot hides every listed node (sit_weapons, DM-B) and restores them when it is removed. Each
`compatible_hosts[]` entry carries `replaces`, a copy of that host slot's `occupied_by`, so the part-side view shows what
it displaces. Open assumption (Q-9): node names survive into the engine scene
(true for Synty names, which are alphanumeric plus `_`); DM-B confirms.

### 4.4 Bore and diameter fit

`bore_d_m` is a *fit signal*, never a gate on its own (§5.1): face extents on the live hosts range from 22 mm to
216 mm, so only a ring-derived diameter is trusted; `bore_source = "face_extent"` mounts do not take part in the
diameter rule.

### 4.5 Rail probe (spike W9, not part of the v1 contract)

For hosts without a child node, an estimator of the optic/underbarrel/laser seat from the body mesh is *explored* in
W9, calibrated on the hosts that do carry a child (optic 12, magazine 19 on BONDED's packs), because the child is exact
ground truth. Two simple estimators already failed on that set (§1.2). Any estimator is non-normative until it meets
the literal gate in AC81; until then these hosts keep `source: none`. When it does pass, the source value is `probe`
with `span_source: "probe"`, `confidence <= 0.7`, and the record gets review reason `mount_estimated`.

## 5. Compatibility

### 5.1 `compatible_hosts` and tiers

For every attachment with a recognised `slot`, for every eligible host, the build computes one candidate with a tier
and a score in [0, 1]:

| tier | rank | rule | score band |
|---|---|---|---|
| `override` | 1 | an override entry adds it (§6.1) | 1.0 |
| `twin` | 2 | host has a child of the same slot whose sorted AABB extents equal the attachment's within `max(3 %, 0.8 mm)` per axis, exactly one such host child per part (a part twinning several hosts' children is `twin` for all of them, flagged `twin_multi`) | 0.95 |
| `same_pack_fit` | 3 | same pack, `family_overlap` AND `affinity` AND no veto | 0.6 - 0.9 |
| `cross_pack_fit` | 4 | different pack, `affinity` AND measured fit AND no veto | 0.3 - 0.6 |

Signals (all listed in the entry's `signals`):

- `family_overlap`: after removing generic tokens (`wep`, `sm`, `attachment`, `separate`, numeric tokens, size words),
  the part's name tokens and the host's name tokens share at least one token (`plasma`, `sniper`, `smg`, `alien`...).
- `affinity`: a table `attach_affinity` in `weapon_rules.yaml`: `slot x kind -> allowed host archetypes` (sniper_scope
  -> sniper, rifle, launcher; reflex -> pistol, smg, rifle, shotgun, launcher; drum magazine -> rifle, smg, ...). Fixed
  and human-edited; this is where genre knowledge lives.
- `mount_available`: the host's `mounts.<slot>.source != "none"`. If false the candidate goes to `pending_hosts`
  instead of `compatible_hosts` (D-8).
- `fit_span`: `foot_length_m / mounts.<slot>.span_m`. `<= 1.0` adds 0.1; `1.0 - 1.5` is neutral (1.5, not 1.2: the veto cut leaves a half-again margin so authoring slop and a foot that overhangs the measured span a little never veto; the earlier AC73 wording with 1.2x described the neutral band, not a veto); `> 1.5` is a **veto only
  when `span_source == "probe"`** (a `child_foot` span is a lower bound, so it cannot veto).
- `fit_bore` (muzzle): `|mate_d_m - bore_d_m| <= 0.35 * bore_d_m` adds 0.1, otherwise subtracts 0.1; ignored when
  `bore_source != "ring"`.
- `veto`: `slot_disabled` on the host; an override removal; the host being `mech_scale` while the part is not.

Score = sum of the signal weights in `weapon_rules.yaml: attach_compat` (initial values are in that file's comments and
are *parameters*, not contract: the gate is AC80's precision and recall). Entries are sorted by `(rank, -score, host)`;
the list is deterministic. An attachment may have any number of hosts; a host any number of attachments per slot.

### 5.2 Why two lists

`pending_hosts` exists because a compatible gun without a measured mount is the normal case for 36 of 48 BONDED guns on
the optic slot. A game overlay (which may carry numeric nudges, D-5) can mount them; the directory just says which.

### 5.3 Direction of storage

The relation is stored once, on the **part** (`compatible_hosts`). Hosts carry no reverse list, so adding a part
never rewrites host records (no churn, INV-14). `weapons show <host>` and the review page compute the reverse view on
demand.

## 6. Corrections and overrides (committed file, categorical only)

### 6.1 New keys in `weapon_overrides.json` (DS§4.5 additive)

```jsonc
"ids": {
  "<pack>/<part>": {
    "set": {"attachment_slot": "optic", "attachment_kind": "reflex"},     // enums only
    "forward": "+z",                         // existing DS§4.5 field, now also valid on a part (anchor forward sign)
    "compatible": {"add": ["<pack>/<host>", "<pack>/<glob>*"], "remove": ["<pack>/<host>"]}
  },
  "<pack>/<host>": {
    "mounts": {"optic": {"source": "child_node", "child": "<GLB node name>"},
               "laser_light": {"source": "none"}}                         // none = slot_disabled
  }
},
"globs": { "<pack>/<part glob>": {"compatible": {"add": ["..."], "remove": ["..."]}} }
```

Allowed in `compatible` and `mounts` only: ids, globs, node names and the enum `source in {child_node, none}`.
Any other key (`point`, `up`, `span_m`, `offset`, a number...) is rejected with exit 6 (INV-17, AC74).
`mounts` is id-only; `compatible` is allowed on globs (the family case). Precedence is the existing one (DS§3.9): exact id
> longest glob > rule.

### 6.2 Review page (`weapons review`; slice W8d)

- A new section **Attachments** (between the per-archetype sections and **Parts**; an attachment appears there and not
  in **Parts**), grouped by slot, then family. Tile: thumbnail, slot/kind chips, host count by tier, reasons.
- Tapping an attachment opens a panel: `slot` and `kind` dropdowns, a **forward** flip, and the host list as a checklist
  with tri-state per host (inferred / added / removed), a tier chip and the score, a **Apply to family** checkbox
  (emits a glob), and a note. Hosts in `pending_hosts` are shown dimmed with "no mount".
- Tapping a host opens a **Mounts** table: one row per slot with `source`, `occupied_by`, `confidence`, and a dropdown
  to pick a different child node or `none`. Hosts with `mount_missing` are collected in a **No mount** filter chip.
- **Placement preview** (look-first): `weapons attach-preview` renders, through the existing three.js harness, a PNG per
  twin pair and a sample of other pairs (host with the attachment placed by §3.1, the baked node hidden). The page
  embeds the thumbnails. Tom reviews placements by eye; these are not committed.
- Corrections emit `weapon-corrections/1` entries with the new keys: `{"target": {...}, "set": {"attachment_slot": ...},
  "compatible": {"add": [...], "remove": [...]}, "mounts": {...}}`. `apply-corrections` validates (exit 6 on a non-enum
  or any numeric mount key) and merges.

## 7. Export (DS§3.10 additions)

- `weapons export ... --attachments` (new flag, default off, D-10): alone emits host `geometry.mounts` plus the attachment part records (parts with a non-null
  `attachment`, added to the exported set). `--roles attachment` is only an extra filter, to export the attachments alone
  (`all` includes them too). Without `--attachments` nothing changes and the output is byte-identical to the W7
  export of the same snapshot, `generated_from` included (AC77).
- `--min-compat-tier {override|twin|same_pack_fit|cross_pack_fit}` (default `same_pack_fit`, D-11) filters
  `compatible_hosts` **and `pending_hosts`** by the same rule (a cross-pack candidate on a mountless host must not reach a game's `fits` list). Entries whose host is not in the exported set are dropped from both unless `--keep-foreign-hosts`. In the directory, `pending_hosts` entries are `{host, tier}` so the filter has the tier; the export emits ids only, sorted by `(tier rank, host)`, for candidates that pass the filter.
- `--frame item` bakes every point and vector of `anchor` and `mounts` through the record's own `item_basis`
  (points: rotated; vectors: rotated; `span_m`, `footprint`, `bore_d_m` unchanged). `node_offset` keeps its rule (DS§4.1).
  `generated_from` gains `attach_version`, `attach_rules_digest` and `filter.attachments` (boolean, `true`) **only with `--attachments`**; without it none of the three keys exists and `geometry_version` is unchanged (5).
  `generated_from.rules_digest` is computed over exactly the rule sections W7 hashed: the attachment tables (`attachment_rules`, including `never`, `rows`, `child_tokens` and `child_never`) are excluded from it, so adding or editing attachment rules never moves the default export's `rules_digest` (Tom: the default export is byte-identical to W7). The attachment tables hash separately into `attach_rules_digest`. The directory header records both digests and `WEAPON_ATTACH_VERSION`, and treats a change of any of them as stale, so an edit to an attachment rule still rebuilds `directory.json` (AC77, AC78).
- Exit 6 on a contract violation: `attachment` on a non-part, `compatible_hosts` naming an id absent from the
  directory, a mount with `source == "none"` that has coordinates, or non-orthonormal frames (INV-14 to INV-18).
- New verbs: `weapons attach-eval` (precision/recall against a labels file and the twin truth; JSON on stdout, exit 4
  below the stated gates) and `weapons attach-preview` (§6.2). Both are wired lazily by W8a.

## 8. Data shapes and enumerations

- `ATTACH_SLOTS = (optic, muzzle, underbarrel, magazine, laser_light)`; `ATTACH_KINDS` per slot, each including `other` (§3.2);
  `MOUNT_SOURCES = (override, child_node, probe, none)`; `COMPAT_TIERS = (override, twin, same_pack_fit, cross_pack_fit)`;
  `MOUNT_NONE_REASONS = (no_child_no_probe, slot_disabled, probe_unavailable)`; new `REASONS`: `anchor_unmeasured`,
  `anchor_forward_unsure`, `attach_kind_unknown`, `mount_missing`, `mount_ambiguous`, `mount_estimated`,
  `twin_multi`, `compat_cross_pack`. New `FLAGS`: none. Single source `weapons/__init__.py`, mirrored in
  `weapon_rules.yaml` validation, like DS§4.6.
- Rounding: metres and unit-vector components at 1e-4; scores at 2 dp.
- `weapon_attach_labels.json` (hand labels, committed beside the overrides, ids and booleans only):
  `{"schema": "weapon-attach-labels/1", "pairs": [{"part": "<id>", "host": "<id>", "fits": true}]}`; produced by the
  review page's Attachments checklist ("Label mode") and consumed by `attach-eval`.

## 9. Invariants and failure modes

- **INV-14** `compatible_hosts[].host` and `pending_hosts[].host` (directory form `{host, tier}`; only the export form is bare ids) exist in the directory, are `whole`, ranged, and eligible;
  the relation is stored on the part only.
- **INV-15** `mounts.<slot>.source == "none"` iff `point`, `forward`, `up`, `span_m` are all null, and then `reason` is set.
- **INV-16** `occupied_by` is non-empty only for `child_node` or `override` sources, **except the muzzle slot**, where a `probe`
  source may carry a non-empty `occupied_by` (baked devices) with `child_node` null. Every name is a mesh node present in the
  host GLB (selected-node scope) and the list is sorted and duplicate-free; for every slot other than a `probe` muzzle it
  contains `child_node`.
- **INV-17** The committed override and labels files contain no coordinate, offset or measured number (extends INV-1).
- **INV-18** Every non-null frame is orthonormal within 1e-3 and right-handed (`right = up x forward`).
- **INV-19** The default (no `--attachments`, default `--roles`, which is `whole` only) export is byte-identical to the W7 export. An export made with `--roles part` or `all` but without `--attachments` is identical to W7 except that, on parts whose `attachment` is non-null, `confidence` and `review_reasons` follow §3.4.6 (a symmetric part is capped at 0.59 and gains `anchor_forward_unsure` and `low_confidence`; an unmeasured anchor scales confidence by 0.9 and adds `anchor_unmeasured`); no other byte differs, and no attachment key is emitted.

Failure modes: a host GLB whose child node name changed -> an override naming it is reported `child_not_found`, never
silently dropped (as DS§7); a shared-GLB host with `glb_node` set -> children outside the selected subtree are ignored;
a node with rotation or scale in its world transform (NB-15) -> `node_transform` reason, mount left at confidence 0.4;
two parts of identical geometry (a twin of a twin) -> both are `twin`; part mesh with no flat foot (a bipod's legs) ->
foot slab is tried on both ends, otherwise `anchor_unmeasured` and the part appears under review.

## 10. Contract for DM-B (C-18 and following; the lead reconciles with the sit_armory / sit_weapons drafts)

Continues the table in DS§10.

| # | field / rule | definition |
|---|---|---|
| C-18 | `geometry.mounts` | object or null (null iff the host is not eligible, D-9). Keys exactly `optic`, `muzzle`, `underbarrel`, `laser_light`, `magazine`, each an object as in §4.1. Present only when the export is made with `--attachments`. |
| C-19 | `attachment` | object or null on part records: `slot`, `kind`, `anchor`, `footprint`, `compatible_hosts`, `pending_hosts` (§3.2). Present only with `--attachments`. Part records keep `kind: null`, `hold_class: "none"`, and carry `geometry.item_basis` like whole records; a part inside a shared GLB also carries `geometry.node_offset` and, when its node has rotation or scale, the `node_transform` reason (exactly as DS§4.1 for whole records), so `anchor` and the footprint are interpreted in the same frame. |
| C-20 | frame and units | §3.1: `{point, forward, up}`, metres, 1e-4, unit vectors 4 dp, right-handed with `right = up x forward`. Asset frame: asset-local GLB scene space after `glb_scale`. Item frame: each record baked through **its own** `item_basis`; consumer applies each record's own `item_basis` to its own mesh. `span_m`, `footprint.*`, `bore_d_m`, `mate_d_m` are scalars in metres, never baked. Part records always carry `geometry.item_basis` (and `geometry.node_offset` for shared-GLB nodes, unrotated and not item-baked, DS C-17), so a consumer can orient the part mesh before using item-frame fields. |
| C-21 | placement | `part_T = T(mount) * T(anchor)^-1` where `T(F)` has rotation columns `[right | up | forward]` and translation `point`. After placement `anchor.point -> mount.point` exactly and the two `up` and `forward` vectors coincide. Reference implementation: `weapons.attach.place(anchor, mount)` plus a GDScript port written by DM-B against the shared oracle `sit_mount_place/1` (AC69). The first three literal cases of that oracle (muzzle identity, optic authored on its side, underbarrel hanging down) were checked by hand against this formula and agree; the fourth, `three_cycle`, is a non-involutory axis rotation that a transpose of the rotation cannot pass. |
| C-22 | occupancy | `mounts.<slot>.occupied_by`: sorted list of GLB node names to hide when a separate attachment is mounted; `[]` = free. `occupied_by` and `child_node` are **raw GLB node names, unsanitised**; the engine importer's renaming (Godot replaces `. : @ / " %` with `_` and renames duplicates) is the consumer's job (sit_weapons M15). For the muzzle slot the mount `point` is the seat measured with these nodes excluded, not the face of a baked device (R1, AC84). A mount with `source: "none"` is unavailable, and the consumer never synthesises a position (D-8). |
| C-23 | compatibility | `compatible_hosts[]`: `{host, tier, score, signals[], replaces[]}`; `tier` in `COMPAT_TIERS`; sorted by `(tier rank, -score, host)`. `pending_hosts[]` are ids only, filtered by the same `--min-compat-tier` rule as `compatible_hosts` (default up to `same_pack_fit`). Relation stored on the part only (INV-14). Default export keeps tiers up to `same_pack_fit`. An **empty `compatible_hosts` means the part fits nothing**: only `pending_hosts` and a game overlay's own `fits` add can extend it. |
| C-24 | export surface | `--attachments` alone emits host `mounts` plus the attachment part records; `--roles attachment` is only an extra filter to export attachments alone; also `--min-compat-tier`, `--keep-foreign-hosts`. Default output (default `--roles`, `whole` only) is byte-identical to W7, `generated_from` included; `--roles part|all` without `--attachments` differs only as INV-19 states (`geometry_version` stays 5, `rules_digest` excludes the attachment tables; `attach_version`, `attach_rules_digest` and `filter.attachments` appear only with `--attachments`). `sit_armory` ignores unknown keys (it already ignores `component`) and keeps the `whole`-only default. `generated_from.filter.attachments` is a boolean, present and `true` only when the export was made with `--attachments` (absent otherwise, so the default output stays byte-identical). |
| C-25 | vocabulary | `ATTACH_SLOTS` / `ATTACH_KINDS` may grow in minor versions; consumers ignore unknown slots/kinds. `compatible_hosts` and `mounts` may later gain keys. |
| C-26 | stats | The directory carries no attachment stats. `sit_armory` overlays key stat modifiers by the part's `<pack>/<asset_id>` (or `renamed_from`, C-13) and read the slot from `attachment.slot`. |
| C-27 | numeric corrections | There are none in the directory. A game that needs a nudge carries it in its own overlay, relative to the exported `mounts.<slot>.point` (D-5). `seat_depth_m` (how far a part may sink into the host) is overlay-owned on the game side; the directory adds nothing for it. |

## 11. Acceptance criteria

Synthetic fixtures (committed, `tests/fixtures/weapons/`): a catalog `FAKE_Attach` and generated GLBs from
`tests/fixtures/weapons/w8a_attach.py` (written per test into the test's tmp directory; it is NOT added to `make_catalogs.py`, to the committed `catalogs/` or to `expected.json`, because a sixth committed pack would shift the literal counts that the W7 suite pins): (a) a box-and-barrel host with a child "optic" mesh at a known transform, a child "magazine" mesh, a
trigger child and a muzzle ring of known radius; (b) a standalone optic that is an exact dimensional twin of the child
optic, a larger non-twin optic, a tube-with-flare scope, a symmetric box optic, a suppressor tube (wide free end,
26 mm-class mating end), a foregrip hanging from a top foot, a drum magazine; (c) a host without any child; (d) a
grenade-like host; (e) a host in a second pack; (f) a part with a vehicle-pack name; (g) a host whose muzzle carries a baked brake child of known length (0.08 m class). Mutation proofs name the change
that must make the test fail.

| AC | statement | mutation proof |
|---|---|---|
| AC61 | Records validate: `attachment` non-null only for `part`; its fields, enums and nullability match §3.2; `compatible_hosts[].host` and the directory form `pending_hosts[] = {host, tier}` (`tier` in `COMPAT_TIERS`; the export form is ids only) only name existing eligible hosts; `weapons validate` exit 0 on the fixture directory, exit 6 on each of six hand-broken variants | drop the role check -> the non-part variant validates, test fails |
| AC62 | Classification: each token row of §3.3 maps its fixture part to the stated slot/kind; the vehicle-named part gets `attachment: null`; a part with no row stays null | delete the `not` list -> the vehicle part becomes an attachment |
| AC63 | Anchor accuracy on rotated copies of the fixtures: `point` within 1 mm of the known foot centre, `up` within 0.5 degrees, for every slot kind, with the foot at the top and at the bottom | measure `point` as the AABB centre instead of the foot slab -> fails on the offset-foot fixture |
| AC64 | Forward sign: tube-with-flare faces the flare (`forward_source "section"`); symmetric box -> `symmetric true`, `forward_source "authored"`, confidence <= 0.59, reason `anchor_forward_unsure`; a `forward` override flips it and sets `override` | set the ratio threshold to 1.0 -> the symmetric fixture is "decided" |
| AC65 | Muzzle device: the mating end is the narrower end, `up` points to the wider end, `mate_d_m` within 1 mm of the fixture's diameter | pick the wider end as mating -> `up` reverses, fails |
| AC66 | Host mounts from children: `optic.point` within 1 mm of the known child seat, `occupied_by` equals the sorted list of child node names (a two-magazine fixture yields both, seat from the larger), `span_m` equals the child's foot length (`span_source "child_foot"`); precedence `override > child_node > probe > none` (four fixtures, one per rung) | ignore the child (always probe) -> optic becomes `none`, fails |
| AC67 | Muzzle: with an empty `occupied_by`, `mounts.muzzle.point == geometry.muzzle` exactly (A0 parity), `up == axes.forward`; ring fixture gives `bore_d_m` within 1 mm with `bore_source "ring"`; a ring-less fixture gives `face_extent`, confidence 0.5; `bounds_fallback` gives confidence 0.4 and `muzzle_fallback` | compute the muzzle with a second algorithm that differs by 1 mm -> parity fails |
| AC68 | `none` behaviour: the childless host has `source none`, null coordinates, reason `no_child_no_probe`, and (with a compatible part present) review reason `mount_missing`; the grenade host has `mounts: null`; no code path defaults a missing mount to bounds | add a bounds default -> the childless host gains a point, fails |
| AC69 | Placement math: for every slot kind `place(anchor, mount)` maps `anchor.point` to `mount.point` within **0.5 mm** and each of `up`, `forward` within 0.1 degrees. **Twin ground truth:** placing the standalone twin on the fixture host gives an AABB centre within **3 mm** of the child's AABB centre and AABB IoU >= 0.90. **Shared oracle:** `place` also reproduces, within 0.5 mm / 0.1 degrees, every case of sit_weapons' `fixtures/mount_place.json` (schema `sit_mount_place/1`; four cases at sit-capabilities 5cd92cd40ed67d8c68794e65c992a443f9cc1aa5: muzzle_identity, optic_part_authored_on_its_side, underbarrel_hangs_down and the non-involutory three_cycle; the test loads whatever cases the file holds, never a fixed count), copied byte for byte to `tests/fixtures/weapons/mount_place.json` with a provenance note (source repo, commit, copy date), like the A0 muzzle golden (DS§11.4); no case is edited here (DM-B is committing `addons/sit_weapons/fixtures/mount_place.json` now: W8c copies that file, not the spec literals), and a disagreement is reported to the lead instead of fixed. The directory's own cases stay as well. The GDScript port passes the same cases (DM-B) | swap `T(mount)*T(anchor)^-1` for `T(anchor)^-1*T(mount)` -> fails |
| AC70 | No intrusion: after placement of each "fit" fixture attachment, penetration depth along `mount.up` into the host body AABB is <= **3 mm**, and the attachment's AABB volume outside its foot slab that overlaps the host body AABB is <= 5 % of its volume | shift the anchor by 10 mm -> fails |
| AC71 | Twin detection: extents within `max(3 %, 0.8 mm)` per sorted axis are `twin`; a 5 % difference is not; one-to-many is `twin_multi` | widen the tolerance to 6 % -> the 5 % fixture becomes a twin, fails |
| AC72 | Tiers: `same_pack_fit` requires `family_overlap` AND `affinity`; the other-pack host only reaches `cross_pack_fit` (score <= 0.6, reason `compat_cross_pack`); ordering is `(rank, -score, host)`; two builds give identical output | drop the pack check -> the other-pack host gets rank 3, fails |
| AC73 | `fit_span` and `fit_bore`: the oversize cut is 1.5x (section 5.1): a `foot_length_m` 1.2x a span is neutral (not vetoed); 1.8x a `child_foot` span is not vetoed either, because a `child_foot` span is only a lower bound; 1.8x a `probe` span is vetoed; `fit_bore` ignored for `face_extent` mounts | allow `child_foot` to veto -> the 1.8x `child_foot` fixture is rejected |
| AC74 | Overrides: `compatible` add/remove by id and glob; precedence exact id > longest glob > rule; a missing id/node is reported (`child_not_found`), not dropped; `mounts` rejects any key other than `source`/`child` with **exit 6**; `apply-corrections` round-trips a review-page file | allow a `point` key -> the numeric variant is accepted, fails |
| AC75 | `pending_hosts`: a compatible host with a `none` mount appears there and not in `compatible_hosts`; adding a measured mount by override moves it; **tier filter:** a `cross_pack_fit` candidate on a mountless host is in the directory's `pending_hosts` (with its tier) but must not appear in the default export's `pending_hosts` | list it in both -> fails; skip the tier filter on `pending_hosts` -> the cross-pack candidate leaks into the default export and fails |
| AC76 | Review page: Attachments section exists, checklist states round-trip into `weapon-corrections/1` (parsed from the embedded data); mounts table lists every slot for an eligible host; no network access | remove the section -> fails |
| AC77 | Export: default output equals the stored W7-format golden byte for byte (a `--roles all` export without `--attachments` differs from the W7 reference only in `confidence` and `review_reasons` of parts whose `attachment` is non-null, nothing else), `generated_from` included (`geometry_version` 5, no `attach_version`, no `filter.attachments`); the same snapshot exported with `--attachments` differs only by the added keys, `attach_version` and `filter.attachments`; with `--attachments` item-frame points equal `item_basis * asset point` within 1e-4 per record (host and part separately), `occupied_by` lists preserved, tiers below `--min-compat-tier` dropped, foreign hosts dropped, exit 6 on each violation of INV-14..18 | bake the part through the host's `item_basis` -> fails on a rotated fixture; bump `WEAPON_GEOMETRY_VERSION`, emit `attach_version` unconditionally, or hash `attachment_rules` into the default `rules_digest` -> the byte diff fails |
| AC78 | Determinism and caching: two builds identical; bumping `WEAPON_ATTACH_VERSION` or `WEAPON_GEOMETRY_VERSION` invalidates cached entries; a cache hit equals a recompute | omit the version from the key -> stale hit survives a bump |
| AC79 | `weapons attach-eval`: on the fixture labels, reported precision and recall equal hand-computed values exactly; exit 4 when below the supplied gates | remove one fixture rule -> recall drops below the gate, exit 4 |
| AC80 | **Live (local, not CI; reported, never committed).** On BONDED's packs: (a) sanity: the live `twin` count equals the survey figure (11 parts on BONDED's packs; a different count is reported and investigated, not gated); (b) twin placement on the real hosts: AABB centre within **5 mm** and IoU >= 0.85 for >= 90 % of twin pairs; (c) on Tom's labels (stratified, >= 150 pairs with >= 40 positives, Q-5): precision >= 0.90 and recall >= 0.80 for tiers up to `same_pack_fit`; cross-pack reported separately, ungated until Q-1 is answered; (d) child-node coverage printed (expected: magazine 19, optic 12 of 48) | n/a (acceptance run) |
| AC81 | **Spike gate (W9).** An estimator may set `source: probe` for optic only if, on the child-bearing hosts, the median `|probe - child truth|` <= 10 mm and the maximum <= 25 mm for the seat height and the median forward error <= 15 mm; otherwise it stays disabled and hosts keep `none`. The estimator source never reads a child node | feed it the child -> the "independent" check is violated |
| AC82 | No regression: on the W7 live directory, role/kind/archetype counts equal the W7 report (the role/kind/archetype count table equals the W7 report, null-kind whole/emplaced count 0, and every pre-existing test keeps its outcome; the pytest totals grow by design and are not compared); every pre-existing field of every record is byte-equal to the W7 reference, with two enumerated exceptions that sections 3.4.6 and 4.2 mandate: `confidence` and `review_reasons` of a record may change, and only by the section 8 attachment reasons (`anchor_unmeasured`, `anchor_forward_unsure`, `attach_kind_unknown`, `mount_missing`, `mount_ambiguous`, `mount_estimated`, `twin_multi`, `compat_cross_pack`) and the `low_confidence` and confidence cap or scale that they cause; the only new fields are `geometry.mounts` and `attachment` (the test fails on any other difference, and lists the changed records) | n/a (diff test over the fixture directory in CI; live diff reported) |
| AC83 | Visual checkpoint (look): `attach-preview` renders >= 6 twin pairs and >= 6 non-twin pairs covering every slot; the lead views the captures before W8d closes; the baked node is hidden in each; no capture shows the attachment inside the receiver by more than the AC70 depth | n/a (lead review) |
| AC84 | Muzzle seat: on fixture (g) `mounts.muzzle.occupied_by` lists the brake node, `source` is `probe`, `point` equals the A0 probe of the mesh minus the brake (the barrel end) within 0.5 mm, and sits behind the device face by the brake length within 1 mm; `geometry.muzzle` is still the face of the brake (W7 bare-gun value, unchanged); a host with no brake gives `point == geometry.muzzle` exactly | include the brake in the probe mesh -> the seat lands on the device face and the behind-by-length check fails |

Gate commands are those of DS§11.1 (`pytest -k weapons`, then the full suite, each judged by exit
code). W8a/b/c/d add `tests/test_weapons_attach_*.py`; none reads Synty data.

## 12. Questions for Tom (DECIDED 2026-10-22: every default accepted)

Tom approved the spec "with all defaults" (quoted in the header), so Q-1 to Q-10 below stand as decided on the
recommendation each one states. Decided: no rail probe in v1 (W9 is a spike), seats without a measured point come from game
overlays, cross-pack off, magazine = mesh swap, about 150 phone labels after W8d. Q-2 (no numeric corrections in the
directory), Q-3, Q-4, Q-6, Q-9 and Q-10 stand on their stated defaults.

- **Q-1 Cross-pack borrowing.** Eight of BONDED's guns (one SciFi pack and CyberCity) have no same-pack attachments.
  Cross-pack candidates exist but stay out of the default export (D-11). *Recommend:* keep it that way; Tom opts a family
  in with a `compatible.add` glob when he sees the preview and likes the look. Alternative: allow `cross_pack_fit` by
  default for those two packs only.
- **Q-2 Numeric corrections.** D-5 keeps coordinates out of the public repo. *Recommend:* keep, and let BONDED's overlay
  carry nudges as it did for the support points. Alternative: amend DS§4.5 to allow *unitless* fractions of the host AABB
  (`mount_frac`), which are not pack-recoverable data. That is a real policy change, so Tom decides.
- **Q-3 More slots.** Stock, barrel, bayonet, handguard and the rack/rail segments are excluded from v1; BONDED's packs
  have no stock parts and the rack segments look like rail extenders. *Recommend:* leave out; add `stock` in a later slice
  if a Western or modern game needs it.
- **Q-4 `component.slot` regrouping.** Re-slotting red-dots, the laser and the bipod out of `misc` at the `component`
  level needs a gold-fixture regeneration. *Recommend:* not now; the `attachment` block already gives the right slot.
- **Q-5 Hand labels.** AC80(c) needs about 150 (part, host) pairs ticked in the review page ("Label mode", roughly 15
  minutes on a phone). *Recommend:* yes, after W8d. Without labels the live gate shrinks to twin placement only (AC80b), which
  proves little about cross-fit.
- **Q-6 Occupancy policy.** Mounting a separate optic on a host with a baked one hides the baked node (C-22). That is
  sit_weapons' decision to implement; *recommend* hide, with the baked node restored when the attachment is removed.
- **Q-7 Hosts with no child node.** 36 of 48 on the optic slot, 29 on magazine, and every host on underbarrel and
  laser_light have no measured mount. *Recommend:* accept `none` for v1, run the W9 spike with the literal gate, and let
  the overlay carry the few seats Tom actually wants.
- **Q-8 Magazine meaning.** The directory describes the magazine *mesh* swap only (a drum versus a box), not capacity.
  Confirm that is what BONDED wants from the slot.
- **Q-9 Node names in engine scenes.** `occupied_by` is the GLB node name; DM-B should confirm the Godot scene keeps it.
- **Q-10 Preview as part of the contract.** `attach-preview` is Tom's way to *see* the fit. Confirm he wants it in W8d
  rather than only the numeric gates.

## 13. Build plan (slices W8 to W10)

Same rules as DS§11.1 (Sonnet `builder`, own worktree, lead-resolved base SHA, positive file scope,
gates by exit code, synthetic fixtures only). Approval of this spec starts W8a. "Live" steps run locally and report.

| slice | depends | parallel-with | ACs | owns (new unless noted) | live data | size |
|---|---|---|---|---|---|---|
| W8a attachment records | none | none | AC61-AC65, AC78 (parts) | `weapons/attach.py` (anchor/footprint/place), `weapons/classify.py` hook (edit), `weapon_rules.yaml` tables (edit), `weapons/__init__.py` constants (edit, W8a owns the enum additions), `cli.py` lazy stubs for `attach-eval`/`attach-preview` (edit, W8a only), `schema.py` (edit), fixtures `FAKE_Attach`, tests | no | M: ~900 lines |
| W8b host mounts | W8a | none | AC66-AC68, AC84, AC78 (geometry) | `geometry.py` (edit: mounts, ring estimator, cache key gains WEAPON_ATTACH_VERSION, WEAPON_GEOMETRY_VERSION stays 5), `weapons/mounts.py`, tests | live probe after merge: coverage counts | M: ~800 lines |
| W8c compatibility, overrides, eval | W8b | W9 | AC69-AC75, AC79 | `tests/fixtures/weapons/mount_place.json` (copy of DM-B's committed `mount_place.json`, provenance note), `weapons/compat.py`, `overrides.py` + `corrections.py` (edit), `weapon_rules.yaml` compat table (edit), `weapons/eval.py`, tests | no | L: ~1,100 lines |
| W8d review page, export, preview | W8c | W9 | AC76, AC77, AC82, AC83 (look) | `review.py` + `review_template.html` (edit), `export.py` (edit), `weapons/preview.py` + harness additions, the wiring of `compat.export_compatible` / `export_pending` into `--attachments`, a corrections path for the review page's forward flip, tests | preview needs the renderer on this machine | L: ~1,200 lines |
| W9 rail-probe spike | W8b | W8c, W8d | AC81 | `weapons/mount_probe.py`, a report script (not shipped if it fails) | yes (calibration on the child-bearing hosts) | S: ~400 lines |
| W10 acceptance | W8d | none | AC80, AC82 (live) | none (a report) | yes; Tom's labels | the lead runs it |

Shared files: `cli.py`, `pyproject.toml`, `weapons/__init__.py` constants are W8a's only; later slices use the named
constants. `weapon_rules.yaml` is edited sequentially (W8a tables, W8c compat), never in parallel. Parallel pairs
(W8c/W9, W8d/W9) touch disjoint files. The lead reviews W8d's captures (AC83) before it closes.

## 14. Changes to the directory spec (applied in the same commit as PATCH notes)

DS§4.1 gains the `attachment` block and `geometry.mounts`; DS§4.5 gains the `compatible`, `mounts` and part-side `forward`
keys; DS§4.6 gains the new enumerations; DS§3.10 gains the export flags; DS§3.9 gains the Attachments section; DS§10 gains
C-18 to C-27 by reference; DS§11 points to §13. Nothing existing changes meaning.
