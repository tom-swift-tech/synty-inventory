# Spec: weapon attachments (amendment to the weapon directory)

**Written:** 2026-10-22. **Status:** APPROVED (Tom, 2026-10-22), with all defaults: "Approve both T4 attachment specs (synty-inventory 17cc1c6,
sit-capabilities b800211) with all defaults: no rail probe in v1 (W9 spike), seats without a measured point come from game
overlays, cross-pack off, additive-percent stacking, magazine = mesh swap, ~150 phone labels after W8d. Start the builds."
Decisions D-1 to D-12 came from Tom's three 2026-10-22 decisions; Q-1 to Q-10 (§12) are decided on their defaults.
The approved base for the build slices is the commit that records this approval.
**Amendment A1 (W8f, approved by Tom 2026-10-23):** twin evidence seats a twin pair on the baked child it matches and corrects the part's
forward (§3.4 step 3a, §4.2 `seats`, §4.3, §5.1). `WEAPON_ATTACH_VERSION` goes 1 to 2; nothing else about the contract moves (D-12).
**Erratum E1 (2026-10-23, from the lead):** on a `twin` entry `replaces` names the seat child, and hiding always follows the slot's `occupied_by`, as the
runtime does (sit_weapons §3.9.5): a game mounting a part in a slot hides every node of that slot's `occupied_by`, whichever child the part is seated on. Previews do the same.
**Amendment A2 (W8h, merged 016f709, Tom 2026-10-23: "iron sights usually are a pair, front and rear" and "you are mixing modern and apocalypse and sci fi parts"):**
iron sights leave `optic` for two new slots `sight_front` and `sight_rear` (§3.2, §3.3, §4.1, §4.2); a front and a rear of one set pair by name
(`attachment.pair`, §3.5); a mounted optic may hide the rear sight (`hides_slots`, §4.3); a pack-to-setting table gates every candidate that is
not an override (§5.1, A2). `WEAPON_ATTACH_VERSION` goes 2 to 3 (D-12). The default export stays byte-identical (INV-19); §13.1 records what
moves and why.
**Amendment A3 (W8i, lead 2026-10-23, after the A2 look gate; the probe mesh also drops baked muzzle, underbarrel and laser children, §4.6 item 1, AC97; a host that already carries a baked iron sight or carry handle child refuses that sight slot, §4.6 item 7, AC98; addendum 3, lead 2026-10-23 after the census of 257 hosts: baked optics and iron sights refuse their slots as a rule, §4.6 item 8, AC99 to AC103; addendum 3b, lead 2026-10-23 after the W8j recount: the same rules reach the sight slots the probe could not seat, so a baked host has no pending sights either, §4.6 item 9, AC104):** an iron sight is a pack-generic part, so it needs no name overlap with its host: on a same-pack host whose sight seat is available a `same_pack_fit` candidate needs only `affinity` (the span-less probe seat counts as neutral; §5.1). Flare guns and prop-class hosts (`attachment_rules.attach_host_never`, §7) get no sight seat: the look gate showed sights on top of a briefcase and high on a flare-gun block. `WEAPON_ATTACH_VERSION` goes 3 to 4 (D-12). The default export stays byte-identical (INV-19); §13.2 records what moves.
**Amendment A4 (W8l, addendum 4, lead 2026-10-23, after AC80(c) was scored NOT MET on the 90 hand labels; items 1 to 5, AC105 to AC110):** five measured defects, none of them a threshold fitted to a label. (1) The forward sign of a standard magazine or a bipod comes from where its free end sits relative to its foot (§3.4 step 3b), not from the larger end section: 13 of the 16 section-decided magazines bend away from the section prior's forward, and the free-end reading agrees with the twin evidence on all 9 twin-evidenced magazines it decides (the other 2 lean under 3 mm and keep their correct section sign). (2) `muzzle` and `underbarrel` join the sight slots in not needing `family_overlap` (§5.1 A4): 12 of 13 muzzle parts and 12 of 24 underbarrel parts have an empty name-token set. (3) A foot that the 4 mm slab cuts as a lip is measured one rung deeper (§3.4 step 1a: `Mod_A_Mag_05` read a 4 mm foot, `Attach_Foregrip_05` 2.5 mm). (4) A `child_node` optic seat is lifted to the host surface under the baked scope's footprint when the scope's underside sits inside the receiver (§4.2). (5) A mirrored left and right pair of children seats at its midpoint (§4.2). `WEAPON_ATTACH_VERSION` goes 6 to 7; `WEAPON_GEOMETRY_VERSION` stays 5 (the anchor code digest is in the cache key); the default export stays byte-identical; §13.5 records what moves. Because the items were found on the 90 labels, a re-score on them does not count towards AC80(c): the held-out set of §13.5 does.
**Amendment A5 (W8m, addendum 5, lead 2026-10-23, after the contact check of the W8l directory; items 0 to 2, AC111 to AC116):** the look gate and a map-wide downward-ray check of the W8l directory found parts hanging off or sunk into their host that no seat rule explained (a bipod 11 to 12.6 mm below its rail, a red dot 6.5 mm above a receiver, a scope 29.6 mm up; 62 of 182 optic and underbarrel pairs more than 3 mm off, 38 of all 234 listed pairs sunk). (0) The host-name token `prop` refuses every slot, not only the two sight slots (§7). (1) **Settle to contact (§5.4):** each optic or underbarrel pair whose seat is geometry (not an override, not an authored twin) gets a per-pair `seat_shift_m` on its `compatible_hosts` entry, found by casting the part's contact face onto the host's outer surface. (2) The optic seat lift of A4 item 4 is retired (§4.2): the per-pair shift replaces it and covers the same hosts, because a seat that starts up to 20 mm sunk is brought to the surface by the rule when the clamp is 60 mm (measured: 157 of 157 lifted-host pairs within 3 mm either way). `WEAPON_ATTACH_VERSION` goes 7 to 8 (item 0, shipped) and 8 to 9 (items 1 and 2); `WEAPON_GEOMETRY_VERSION` stays 5; the default export stays byte-identical; §13.6 records what moves. This amends the consumer contract (C-23 gains the optional entry key `seat_shift_m`, C-27 stops saying the directory carries no numeric correction): the lead tells DM-B.
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
| D-12 | `WEAPON_ATTACH_VERSION` (new, starts 1; 2 from amendment A1, W8f, because twin evidence changes part anchors, twin entries and multi-child mounts; 3 from amendment A2, W8h, because slots, kinds, classification, mounts and candidate lists change; 4 from amendment A3, W8i, because same-pack sight candidates appear and flare and prop hosts lose their sight seats) versions attachment records and mounts; it joins the geometry/attachment cache keys, so the cache invalidates without touching `WEAPON_GEOMETRY_VERSION`, which **stays 5** (the exported `generated_from.geometry_version` therefore stays 5 and the default export stays byte-identical, D-10). Record `schema_version` stays 1: the changes are additive. | cache invalidation without breaking readers that ignore unknown keys |

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
| `sight_front`, `sight_rear` (A2) | as `optic`: from the foot toward the body (host: out of the top of the body, host up) | as `optic`: look direction (host: host `axes.forward`) |

Placement: `part_T = T(mount) * T(anchor)^-1` carries the part's asset-local coordinates into the host's asset-local
coordinates. Then `part_T(anchor.point) == mount.point` and the two `up` and `forward` vectors coincide. In an
`--frame item` export each record's fields are baked through **that record's own** `item_basis` (§7, C-20); the same
formula then holds in the item frame provided the consumer has applied each record's own `item_basis` to its own mesh.

### 3.2 Shape

```jsonc
"attachment": {                      // null unless role == "part" and the rules recognise a user-swappable accessory
  "slot": "optic",                   // ATTACH_SLOTS = (optic, muzzle, underbarrel, magazine, laser_light, sight_front, sight_rear)
  "kind": "scope",                   // per-slot closed list, ATTACH_KINDS below
  "pair": null,                      // A2: id of the front/rear partner of the same set (§3.5), else null; always null outside the two sight slots
  "anchor": {                        // the attachment's own contact frame (§3.1), null with reason when unmeasurable; `footprint` is then null too
    "point": [0,0,0], "forward": [0,0,1], "up": [0,1,0],
    "foot_source": "authored_up",    // authored_up | measured | override
    "forward_source": "section",     // section | authored | twin | override (twin: A1, §3.4 step 3a)
    "symmetric": false               // true when the forward sign is a coin flip (forward_source "authored"); false for twin and override
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

`ATTACH_KINDS` (closed, per slot): `optic` = scope, sniper_scope, reflex, carry_handle_scope (A2: `iron` left the list with the iron sights); `muzzle` =
suppressor, brake, flash_hider (v1 recognises suppressor only); `underbarrel` = foregrip, bipod; `magazine` = standard,
extended, drum, cell; `laser_light` = laser, light; `sight_front` = post, hooded, canted; `sight_rear` = notch, aperture, canted; every slot also has `other`. An unrecognised kind inside a known slot is `other` with review reason
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
| iron-sight name (`ironsight`, or `iron` with `sight`) with `front` or `post` | `rear` | sight_front / `canted` if the name has `canted`, `hooded` for `hood` or `hooded`, `post` for `post`, else `other` (A2) |
| iron-sight name with `rear` | `front`, `post` | sight_rear / `canted` if the name has `canted`, `aperture` for `ring`, `aperture` or `peep`, `notch` for `notch`, else `other` (A2) |
| `silencer` or `suppressor` | | muzzle / suppressor |
| `foregrip` or `vertgrip` | | underbarrel / foregrip |
| `bipod` | | underbarrel / bipod |
| `laser` | `mining` | laser_light / laser |
| `flashlight` or `torch` | | laser_light / light |
| `drummag`, or `drum` with `mag` | | magazine / drum |
| `mag` or `magazine` (no `cell`) | | magazine / standard |
| `cell` | `mining` | magazine / cell |

Tokens not in the table (rack and rail segments, carry handles without a scope, batteries of a tool, bayonets, stocks, and a bare `sight` token without `iron`)
stay `attachment: null` in v1. A part whose name contains `veh`, `vehicle` or a vehicle-pack family is never an
attachment (AC62). Corrections: `attachment_slot` / `attachment_kind` overrides (§6.1).

**Iron sights (A2).** The two iron-sight rows are written as token rows like every other (a `kind` row for each of `canted`, `hooded`, `aperture`, `notch`
and `post` before the plain row of its side; `rows` is first-match-wins). The side comes from the name only: `front` and `post` mark a front sight
(Synty's `Post` parts are front blades on a barrel clamp), `rear` marks a rear sight. A side-marked sight whose name carries no kind token takes kind `other`
from its row and does **not** raise `attach_kind_unknown` (that reason is for a kind the closed list does not know). An iron-sight name whose side the name does not decide (no `front`, `rear` or
`post`, or a `rear` together with a `front` or `post`) never gets a slot: the geometry is **not** used to pick a side (the earlier idea of reading
post, ring or blade from the mesh is dropped: it would need the part's forward axis, which is itself unsure on 6 of the 23 live unmarked parts, and a wrong
side is worse than a visible review reason). Such a part keeps `attachment: null`, gets the new review reason `sight_side_unsure`
(rules rows may carry a `reason` instead of a `set`) and, as `anchor_forward_unsure` does, a confidence capped at 0.59 and the reason
`low_confidence`, so it lands on the review page under **Parts**. The slot and kind are then set by the categorical `attachment_slot` / `attachment_kind`
overrides (§6.1, D-5), which drops the reason; no override means no attachment. A rail-length one-piece sight (a sight at each end of one mesh) has no single side and falls in the same bucket. *Known limit (lead, 2026-10-23):* there is no `combined` kind in this pass; those parts (SciFi_City_03, the Wasteland Fork_01/02/04, Apocalypse 06 and 08) stay `sight_side_unsure`.
The classification never reads `component.slot`, so `component` stays untouched (D-2).

### 3.4 Anchor measurement (new module `weapons/attach.py`, one function used for parts and for host child meshes)

Input: the triangles of one mesh (a part's selected node(s), or one child node of a host GLB), `slot`, and the record's
`item_basis` is *not* used. Output: the `anchor` and `footprint`. The authored axes of Synty parts are Y-up; the
algorithm uses that as a prior and verifies it.

1. **Contact side.** Per slot the expected contact side along the authored up axis `Y` is: `optic`, `sight_front`, `sight_rear`, `laser_light` -> the
   `-Y` end (foot at the bottom); `underbarrel`, `magazine` -> the `+Y` end (foot at the top, body hangs down). The
   *foot slab* is the set of vertices within 4 mm of that extreme. `foot_source = "authored_up"`. If the slab holds
   fewer than 3 distinct points (after 0.1 mm dedupe) the other end is tried; if neither gives 3 points the anchor is
   null with reason `anchor_unmeasured`. `up` is the unit vector from the slab toward the opposite end (so it is `+Y`
   for a foot at the bottom). *Known limit (W8c):* a `laser_light` child baked into a host hangs under the receiver, so its foot is at the top; measured with the part rule (foot at the bottom first) an unrotated baked laser takes the wrong end unless the bottom slab has fewer than 3 points. No live host carries a laser child, so this is recorded and not fixed; a later change may treat `laser_light` like `underbarrel` for baked children.
   **1a. Foot lip (A4, item 3).** A fixed 4 mm slab is only a foot when the mesh is flat at its contact end. A mesh whose contact end is a thin ridge, rim or stub is cut by the slab into a sliver, and the sliver's extent is the slab's own thickness, not the foot. The slab is therefore measured on a ladder of depths 4, 8 and 16 mm (`attachment_rules.anchor.foot_depths_m`). Along each of `forward` and `right`, the extent of the slab at one rung is a **lip** when it is at most `lip_max_m` (4.5 mm) and at least `lip_min_m` (1 mm: a flashlight's line contact has extent 0 and stays a line), and the next rung is at least `lip_growth` (2.0) times as large on that axis. While any axis of the slab is a lip, the next rung is used (at most two steps). A foot that is thin and stays thin (an iron-sight post 4.3 mm deep at both 4 and 8 mm) is a foot and is not stepped. `foot_length_m`, `foot_width_m` and `point` (the centre of the chosen slab, still at the extreme coordinate along `up`) follow the chosen rung; `length_m`, `width_m`, `height_m`, `up` and the forward sign are unchanged. The same function measures a host's baked children, so a child mount's `point` and `span_m` follow it too. The numbers are parameters. Live: exactly two of the 157 measured attachments are lips (`Mod_A_Mag_05`, foot 4 mm to 49.7 mm; `Attach_Foregrip_05`, 2.5 mm to 84 mm).
2. **Point.** The centre of the slab's AABB in the two coordinates perpendicular to `up`, at the slab's extreme
   coordinate along `up`. Not the vertex mean (vertex density is arbitrary) and not the part's pivot.
3. **Forward sign (optic, sight_front, sight_rear, underbarrel, laser_light, magazine).** The along-rail axis is the longer horizontal AABB
   extent (perpendicular to `up`). The sign is the direction of the end whose cross-section area (perpendicular to
   that axis, binned over the outer 25 % of the length) is larger: an objective bell faces forward; for a magazine the
   convex side; for a laser the emitter. When the larger/smaller ratio is below 1.15 the part is `symmetric: true`,
   `forward_source = "authored"` (+axis), review reason `anchor_forward_unsure`, and confidence is capped at 0.59 so it
   lands on the review page. The DS§4.5 `forward` override applies to a part (it sets `forward_source = "override"`).
   **3a. Twin correction (A1).** Steps 1 to 3 measure a part alone. When the part is a `twin` (§5.1) of a baked child of a host slot, that child's
   pose in the host is ground truth for the gun-forward direction, because a baked child sits as the game's own authoring put it. So, for a
   non-muzzle part with at least one twin host child whose per-axis (unsorted) AABB extents equal the part's within the twin tolerance (no yaw
   between the two meshes), the part's `forward` must equal that host's `axes.forward` (a unit axis vector in the shared asset axes). If the
   measured forward differs, it is replaced: `forward_source = "twin"`, `symmetric = false`. When the axis changes (a near-round drum measured
   along x on a host that points along z), the footprint is swapped exactly, since the anchor frames are axis-aligned: `length_m` with `width_m`
   and `foot_length_m` with `foot_width_m`; a sign flip alone changes no number. `point`, `up`, `height_m` and `mate_d_m` never change. The
   correction is skipped when the part carries an explicit `forward` override (the human wins), and when its twin hosts disagree (it then keeps
   the measurement and the `anchor_forward_unsure` reason). Muzzle devices are out of scope: their frame uses `up` as the bore direction and
   every live muzzle twin already agrees with its host. The correction runs inside `compat.apply_compat` before the candidates are scored (so
   `fit_span` reads the corrected `foot_length_m`), over the whole record set (a partial build gives the result a full build gives), and it never
   touches `review.confidence` or `review.reasons` (a correction never raises confidence).
   *Known limit.* Only parts with a twin child (about a fifth of the attachments) get this evidence. For every other part the forward SIGN is a
   geometric guess, and the guess is poor: measured against the baked children of the live hosts, the step-3 rule picks the gun-forward end on
   about half of the optics and on a minority of the magazines (a reversed magazine is near-symmetric about its foot, so it rarely shows; a reversed
   scope does). Label review (Label mode, §6.2) and the categorical `forward` override (§6.1) are the cover for those parts; replacing the
   step-3 rule is a separate decision.
   **3b. Free-end forward (A4, item 1).** For the slot and kind pairs of `attachment_rules.anchor.free_end` (shipped: `magazine` of kind `standard`, `underbarrel` of kind `bipod`) the forward sign is decided by where the part's free end sits relative to its foot, along the along-rail axis of step 3. The free end is the outer `_WINDOW_FRAC` (25 %) of the extent along `up`, at the end away from the foot slab; the **displacement** is the midpoint of that window's AABB along the axis minus the midpoint of the foot slab's AABB along the same axis. When its magnitude is at least `min_displacement_m` (0.010) the forward is the direction of the displacement: a banana magazine or a splayed bipod leans toward the muzzle. `forward_source = "free_end"`, `symmetric = false`, no `anchor_forward_unsure`. Below the threshold the section rule of step 3 decides as before (so a near-straight magazine is unchanged). The order of authority is override, then twin (3a), then free end, then section, then authored; 3a still replaces a free-end sign when twin evidence disagrees. The slot's kind is an input of `measure_anchor` (a new optional argument; a host child is measured without it and keeps step 3). **The rule is not generic and is not applied to other slots.** Measured against the live twin children, the displacement of an optic, laser or sight body points the wrong way on three of the four optic twins it would decide (a fifth leans under 10 mm) (the free end of a scope is its top, which says nothing about its objective), and the drum and foregrip kinds have no ground truth at all. The 10 mm threshold sits in a clean gap of the twin evidence: the magazines it decides lean 15.5 mm (`B_Mag_04`) to 88 mm and all 9 agree with their twin; the two it does not decide lean 2.1 mm (`A_Mag_04`) and 0 mm (`Rifle_Mag_Separate_01`) and keep their correct section result. Two magazines without twin evidence lie inside the gap and are decided without validation: `Mag_Thin_01` (12.3 mm) and `Mag_Receiver_01` (14.1 mm); the lead looks at their renders.
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
   members of `REASONS`. A2 adds `sight_side_unsure` (§3.3), with the same cap and `low_confidence`.

### 3.5 Sight sets: `attachment.pair` (A2)

A front and a rear iron sight of one set are two parts that mount together. `attachment.pair` names the partner (`"<pack>/<asset_id>"`) or is `null`; the
relation is stored on **both** members (INV-20 tests the symmetry) and nowhere else, so a host record never changes (INV-14 spirit). It is derived
from names only, with these keys, computed on the raw lower-case tokens of the asset id (the §3.3 tokenizer; digits are dropped by it) and **not**
with `attach_compat.generic_tokens`, whose list also strips `front` and `rear` and would merge unrelated variants:

- `variant` = the part's tokens minus `wep`, `sm`, `mod`, `attach`, `attachment`, `a`, `ironsight`, `iron`, `sight`, `front` and `rear`. Other tokens
  (`canted`, `post`, `hood`, ...) stay in the variant. `number` = the last digit group of the asset id (`01`), or empty.
- A `sight_front` and a `sight_rear` pair when they are in the **same pack**, have the same `variant` and the same `number`, and each is the only
  part of its side with that key in the pack. A key matching more than one part on either side pairs none of them. A part with no partner has
  `pair: null` and is simply mounted alone; that is a normal state and raises no reason.
- Override: `ids["<pack>/<part>"].pair` = another part id or `null` (§6.1). It pairs or unpairs that part and its partner symmetrically, and is the only way a
  pair that the names do not give (every unmarked Apocalypse, Wasteland or SciFi City sight) comes to exist.
- A pair is a **set candidate** on a host only when both members list that host in `compatible_hosts` (the set's tier is the lower rank of the two). Where only
  one member lists it, that member mounts alone. The directory adds no pair-level compatibility list; previews and `weapons review` draw both members
  of a set candidate together, and a game seats the front on the host's `sight_front` mount and the rear on `sight_rear`.

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
    "seats": {                       // A1, optional: present only when occupied_by lists more than one measurable child; else absent
      "<GLB node name>": {"point": [0,0,0], "forward": [0,0,1], "up": [0,1,0], "span_m": 0.0}   // one frame per listed child
    },
    "bore_d_m": null, "bore_source": null,    // muzzle only: ring | face_extent | null
    "confidence": 0.9,
    "reason": null                   // source none: no_child_no_probe | slot_disabled | probe_unavailable
  },
  "muzzle": {...}, "underbarrel": {...}, "laser_light": {...}, "magazine": {...},
  "sight_front": {...}, "sight_rear": {...}     // A2, same object shape as optic
}
```

### 4.2 Sources

- **`child_node`.** The host GLB's mesh nodes (collision hulls dropped with `SKIP_STEM_RE`; limited to the descendants
  of the selected `glb_node` when set) are matched by name token against `attachment_rules.child_tokens`:
  `optic` <- scope, sight, reddot, redot, holo; `magazine` <- mag, magazine, drummag, cell, battery;
  `underbarrel` <- foregrip, bipod; `laser_light` <- laser, flashlight; `muzzle` <- silencer, suppressor, brake, compensator, flashhider (for the muzzle slot these children only fill `occupied_by`; the seat always comes from the probe below);
  A2: `sight_front` <- frontsight, sightfront, ironsightfront, frontironsight; `sight_rear` <- rearsight, sightrear, ironsightrear, rearironsight (the joins of §3.3's
  tokenizer, so `Front_Sight`, `FrontSight` and `IronSight_Front` all reach them). **`optic` keeps `sight`:** the live optic children named `*_Sight_Glass*` (11 hosts) and
  `Sight_01` are scope or reflex glass, not iron sights, so the sight slots must never claim a bare `sight` and the optic coverage of AC80(d) does not move.
  A baked iron-sight child with no side in its name (`Sights`, `Sights_01`, `IronSight`; 2 live hosts) is **not** matched by any slot in v3, and a baked pair named only
  `Sight_01` and `Sight_02` stays under `optic` as it does today; both are known limits, and a host override (§6.1) can name a child for either sight slot. Tokens that
  *never* match (trigger, slide, hammer, cylinder, pump, charge, handle, forestock, barrel, stock, switch, pin, clip)
  are a not-list. The child is measured with the **same anchor function** as a part (§3.4), giving its `point`;
  `up` is the slot's contact direction expressed in host axes (optic `+host up`, underbarrel and magazine
  `-host up`, laser_light `-host up`); `forward` is the host's `axes.forward`. `span_m = child.foot_length_m`,
  `span_source = "child_foot"`. `occupied_by` is the sorted list of **every** matching child of that slot (a rifle may carry
  a drum and a box magazine, a shotgun two cells: all of them are hidden when something else is mounted). When there is
  more than one, the seat (`child_node`, `point`, `span_m`) comes from the larger by AABB volume and the record gets
  review reason `mount_ambiguous`. A1: the mount then also carries `seats`, one frame per listed child that could be measured, built exactly like
  the seat above (that child's own `point`, `forward` and `up` as above, `span_m` its own foot length). A pair that twins a smaller child is
  seated on that child's frame (§4.3, §5.1); every other pair keeps using the mount's own seat. A mount with a single listed child has no `seats`.
- **A4 on the child seat (items 4 and 5).** *Optic seat lift (retired by A5 item 2).* A4 lifted a `child_node` optic seat to the host surface under the baked scope's footprint (cap 30 mm, `attachment_rules.optic_seat`). A5 deletes the lift: the seat is again the child's own `point`, and the per-pair contact rule of §5.4 brings a replacement optic to the host's outer surface, which is what the lift approximated per host (a host-wide height cannot be right for two parts that sit at different heights on one seat: measured on a rocket launcher host, one seat leaves a red dot 6.5 mm high and a scope 24.5 mm high). `optic_seat`, `lifted_point` and `lift_optic_seat` leave the code and the rules file; AC108 is retired. *Mirrored pair.* When a slot has exactly two measured children whose sorted AABB extents agree within the twin tolerance of §5.1, whose anchor points differ by at most 1 mm along `forward` and along `up` and by more than 5 mm along the third axis, the mount's `point` is the midpoint of the two anchor points (the left and the right leg of a bipod seat a whole bipod on the gun's centre line, not on one leg); `seats` keeps the per-child frames, `occupied_by` both names, `child_node` the lower name. Any other pair (sight 01 and 02 in a row, two cells in line, a drum and a box magazine) is not mirrored and keeps the larger-volume seat. Live: `MachineGun_Bandit_01` (52 mm off centre) and `Sniper_01` (20.5 mm) are the only mirrored pairs.
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
- **`probe` (sight_front, sight_rear; W8h-B, §4.6).** Approved by the lead (2026-10-23): W8h-A and W8h-B ship as one build. It reuses this source value (no new enum value) at confidence 0.5 with `mount_estimated`; the sight slots are otherwise `child_node`, `override` or `none`.
- **`override` (categorical, §6.1).** Selects the child node to use (`child_node` name), or forces `none`
  (`slot_disabled`). It cannot supply coordinates.
- **`none`.** All of `point`, `forward`, `up`, `span_m` are null; `reason` says why. D-8 applies: consumers treat the
  slot as unavailable. The record gains review reason `mount_missing` per eligible slot that has `none` *and* at least
  one inferred-compatible attachment (so the review page lists exactly the cases that matter).

### 4.3 Occupancy contract

`occupied_by` is a sorted list of GLB node names exactly as in the file (empty = the slot is free). A game that mounts a
separate attachment in that slot hides every listed node (sit_weapons, DM-B) and restores them when it is removed. Each
`compatible_hosts[]` entry carries `replaces`, so the part-side view shows what it displaces: for a non-twin entry a copy of that host slot's
`occupied_by`; for a `twin` entry (A1) the single baked child the part twins (a one-element list), so a game seats
the part on `seats[<that child>]` when the mount has `seats`, else on the mount itself; hiding still follows the slot's whole `occupied_by` (erratum E1). Open assumption (Q-9): node names survive into the engine scene
(true for Synty names, which are alphanumeric plus `_`); DM-B confirms.

**Optic over the rear sight (A2).** Whether a mounted optic covers the rear sight depends on which optic is mounted, so it cannot live in the host's
static `occupied_by`. It is a property of the candidate: an `optic` entry of `compatible_hosts` carries the optional key `hides_slots`, a sorted list that is
`["sight_rear"]` when the host's `optic` and `sight_rear` mounts are both measured (`source != none`) and, after placing the optic by §3.1, the optic's extent along
host forward, widened by 10 mm each way, contains the `sight_rear.point`'s forward coordinate. The key is absent otherwise (never an empty list, so entries that do not
change keep their shape). A game that mounts that optic on that host hides the `sight_rear` slot: its `occupied_by` nodes (erratum E1: whole slot) and any
rear-sight part. A front sight is never hidden by an optic. Previews apply the same rule.

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

### 4.6 Sight seat probe (W8h-B; approved by the lead 2026-10-23, shipped in the same build as W8h-A)

No host in the live catalog carries a baked iron-sight child that names its side (§4.2), so without an estimator `sight_front` and `sight_rear` are `none` on every
host (D-8) and no sight can be placed or previewed anywhere. §1.2 records that two optic-seat estimators missed a *known* child truth by 42 to 172 mm; for the sights there
is no child truth at all (the two hosts with an unsided baked `Sights` node cannot calibrate anything). So this probe is normative **only through its gates** (AC92),
its first gate is a look, and a host where it cannot decide stays `none`. Source `probe`, `span_m: null`, `span_source: null`, confidence 0.5, review reason `mount_estimated`.

1. **Mesh.** The host mesh minus the nodes of `occupied_by` of `optic`, `sight_front`, `sight_rear` and (A3, W8i) `muzzle`, `underbarrel` and `laser_light` (a baked scope is not the rail, and neither is a baked suppressor: the A2 close-up showed the front seat on the top of Apocalypse Pistol_01's baked suppressor).
2. **Profile.** Bin host forward in 5 mm bins; the height of a bin is the highest `up` coordinate of the vertices whose side coordinate is within `max(8 mm, 10 % of the host's side extent)` of the centre. An empty bin breaks a run.
3. **Runs.** `h_top` is the highest bin. The *receiver run* is the contiguous bins around it within 6 mm of `h_top`; the *rail run* continues the receiver run forward while the bins stay within 30 mm of `h_top` (a handguard lower than the receiver, above the barrel).
4. **Seats.** `sight_rear.point` is the rear end of the receiver run moved forward by 10 mm; `sight_front.point` is the forward end of the rail run moved back by 8 mm; each at the bin's height. `forward` is host forward, `up` is host up.
5. **Refusal.** A receiver run of fewer than 3 bins, or a front seat less than 60 mm ahead of the rear seat, makes both slots `none` (`probe_unavailable`).

The numbers (5, 8, 10, 6, 30, 10, 8, 60 mm) live in `attachment_rules.sight_probe` and are parameters, not contract.

6. **Numeric gates before the look gate (lead, 2026-10-23).** On every host where the probe sets a seat, over the whole live catalog: (a) each seat lies on the top surface of the host, i.e. the host mesh under the seat (rays along `-up`, median of a few over the footprint) is within 3 mm of the seat point; (b) the front seat is forward of the rear seat along the bore (`forward` coordinate strictly greater, and at least the 60 mm of step 5); (c) neither seat lies inside the `optic` seat's `span_m` unless that optic's `compatible_hosts` entry covers the sight with `hides_slots` (the front seat is never covered by `hides_slots`, which names `sight_rear` only). A violation fails the build; it is not a review reason. **The look gate (AC92) is the lead's.** The builder delivers the captures and the gate counts; the builder never passes the look gate itself.

7. **Baked sight children refuse their slot (A3, lead 2026-10-23).** The look gate showed `POLYGON_BattleRoyale/SM_Wep_Rifle_Assault_01` with two front sights: the host already has a front post at the gas block (`SM_Wep_Rifle_Assault_Sight_01`, a separate child mesh) and our part stood beside it. A host child is a **baked iron sight** when its name, after the host stem, has a token in `attachment_rules.baked_sights.tokens` (shipped: `sight`, `sights`, `ironsight`, `ironsights`) and none in `attachment_rules.baked_sights.not_tokens` (shipped: `glass`, `scope`, `lens`, `reticle`, `laser`, `red`, `dot`), or a token in `attachment_rules.baked_sights.rear_tokens` (shipped: `carryhandle`, `carry`; a carry handle is a rear sight). `ChargeHandle` and a bare `Handle` are not carry handles. The name carries no side (a child that names its side is the sided `child_node` of §4.2, unchanged), so the side is the child's axial position: the centre of its bounding box along the host's long axis, on the muzzle side of the middle of the host's axial extent, is `sight_front`; otherwise `sight_rear`; a carry handle is always `sight_rear`. For each side that has such a child, a slot that the probe would otherwise seat (source `probe`) becomes `none` / `slot_disabled`, and then the same veto as `attach_host_never` (§5.1) applies. A slot that is already `none`, `child_node` or `override` is not touched, so no existing reason changes (addendum 3b, item 9, supersedes this for the two reasons `probe_unavailable` and `no_child_no_probe`), and the `optic` mount (including a baked sight child such as `Sight_02` that is already the optic's child) is unchanged. The probe mesh (item 1) is unchanged. A baked sight that is **not** a separate child (it is part of the body mesh) cannot be detected from the node tree: such a host is refused by a data override (`mounts: {sight_front: {source: none}}`, §6.1); the one mesh heuristic is the fused front post detector of item 8 (D). Item 8 supersedes the per-side refusal of this item: the sight slots are refused as a pair.

8. **Baked optics and iron sights refuse their slots (A3 addendum 3, lead 2026-10-23).** The census of all 257 ranged hosts (every host rendered in side profile and reviewed by the lead) found that many guns carry their optic or sights in the model, as a separate child mesh or fused into the host mesh. A sight or optic part placed on such a host doubles what the host already has. **Recall comes before precision:** a wrong refusal costs one option, an override `add` (§6.1) brings it back, while a wrong acceptance puts double sights on screen. Terms, all with name tokens as in item 7 (the child's name minus the host's own name tokens unless stated; `raw_tokens`, whole words):
   - **Glass child.** A host child with a token in `baked_sights.glass_tokens` (shipped: `glass`, `lens`, `reticle`), judged on its full name (`Scope_Glass_01` is a glass child). Synty ships many optics as a 3 mm glass sheet that is the only child while the optic body is fused into the host mesh.
   - **Body child.** A host child with a token in `baked_sights.body_tokens` (shipped: `scope`, `optic`, `optics`, `acog`, `telescope`, `reddot`, `reflex`, `holo`, `holosight`) and no glass token: a real optic body that is a separate node, so it can be hidden (item 7 of 4.3, the existing `occupied_by` hide path).
   - **Carry handle child (new).** A host child with a token in `baked_sights.handle_tokens` (shipped: `handle`) and none in `handle_not_tokens` (shipped: `charge`, `pump`, `bolt`, `cocking`, `trigger`), whose bounding-box centre lies above `handle_min_height_frac` (shipped 0.55) of the host's extent along `up`. A handle lower than that is a grip, a trigger guard or a lever and is not a sight. `rear_tokens` of item 7 (`carryhandle`, `carry`) stay.
   Rules, applied in this order after the mounts are resolved (an override, §6.1, always wins and is never touched):
   - **(A) Body child.** The host keeps `optic` (unchanged: `child_node`, the child is hidden when an optic is shown over it) and both `sight_front` and `sight_rear` become `none` / `slot_disabled`.
   - **(B) Glass-only host** (it has at least one glass child and no body child): `optic`, `sight_front` and `sight_rear` all become `none` / `slot_disabled`. The optic body is fused and cannot be hidden, so no optic can replace it; a glass child that is the optic's `child_node` stops being a seat.
   - **(C) Iron pair.** If the host has any baked front post, baked rear sight or carry handle, child or fused, then BOTH `sight_front` and `sight_rear` become `none` / `slot_disabled`: half a pair is never offered. The sources are: the sided or unsided sight children of item 7; a carry handle child (above); and the **fused front post detector (D)**. Like item 7, (C) changes only a sight slot whose source is `probe` (addendum 3b, item 9, adds the two pending reasons); a slot that is `child_node` (a sided baked sight is replaced, not doubled) is left alone.
   - **(D) Fused front post (the one geometry rule here).** On the probe mesh (item 1) profile the host in 5 mm bins along forward as in item 2 (bin height = highest `up` within the side window). The local baseline of a bin is the median height of the populated bins within `half_bins` (8, so 40 mm) of it. A run of contiguous populated bins (a one-bin gap is bridged) that each stand at least `rise_m` (8 mm) above their baseline, whose width is `width_min_m` (10 mm) to `width_max_m` (30 mm), and whose centre lies at `min_pos` (0.6) or more of the host's forward extent, is a fused front post. A fused rear sight is **not** detected (the same test in the rear half fires on rail teeth, hammers and receiver steps, the lead reviewed it on the sheets and ignores it); fused rear sights and fused carry handles come from overrides. The numbers live in `baked_sights.fused_post` and are parameters, not contract; the contract is the gate of AC100.
   - **(E) Host names.** `attach_host_never` (section 7) may now name the slot `optic`: a host whose tokens hit the list gets that slot `none` / `slot_disabled` whatever its source (a `child_node` optic included). Shipped: `optic`, `sight_front` and `sight_rear` -> `water`, `watergun`, `toy` (the toy and water guns carry tanks and housings on top); `sight_front` and `sight_rear` keep `flare`, `flaregun`, `prop`.
   - **(F) Fused cases the checks cannot see** are data in `weapon_overrides.json` (`mounts`, §6.1, written by the lead's review of the census sheets, not by the build).
   Note on `optic` (the reason (A) and (B) bite on few hosts): the `optic` slot has no probe, its seat exists only where the host has an optic child (4.3), so the optic candidates exist only on those hosts.

9. **Baked hosts have no pending sights (A3 addendum 3b, lead 2026-10-23).** The W8j recount showed pending sight entries (`pending_hosts`) still listed on hosts that item 8 refuses, because item 7 and item 8 rewrite only a slot whose source is `probe`; a host the probe could not seat keeps `none` / `probe_unavailable` (or `none` / `no_child_no_probe` when the rules carry no probe table), and compat turns that into a pending entry. A pending entry promises that an override or a later probe could seat the part; on a host that already carries its sights that promise is wrong. **Rule:** rules (A), (B) and (C) of item 8 (and the item 7 children they include) rewrite a sight slot to `none` / `slot_disabled` when its mount is `none` with reason `probe_unavailable` or `no_child_no_probe`, in addition to the `probe` source. A slot that is `none` / `slot_disabled`, a `child_node` and an `override` are still never touched; `optic` is unchanged (item 8 (B) already rewrites it whatever its source). **Detector scope:** the fused front post detector (D) and the carry handle height test run on every host whose probe mesh yields a profile, including one on which the probe refused to seat (item 8 said they were only asked when the probe seated something). **Supersedes:** the sentence of item 7 that no existing reason changes, and the item 8 (C) restriction to `probe`, for exactly the two reasons above; every other existing reason is unchanged. **Effect:** `pending_hosts` of `sight_front` and `sight_rear` lose the entries of every baked host (an override `add`, section 6.1, still lists a pair); `compatible_hosts` do not change (a seated slot was already rewritten); review reasons `probe_unavailable` on those hosts become `slot_disabled`, so the review page lists them as disabled slots and not as missing seats.

## 5. Compatibility

### 5.1 `compatible_hosts` and tiers

For every attachment with a recognised `slot`, for every eligible host, the build computes one candidate with a tier
and a score in [0, 1]:

| tier | rank | rule | score band |
|---|---|---|---|
| `override` | 1 | an override entry adds it (§6.1) | 1.0 |
| `twin` | 2 | host has a child of the same slot whose sorted AABB extents equal the attachment's within `max(3 %, 0.8 mm)` per axis, exactly one such host child per part (a part twinning several hosts' children is `twin` for all of them, flagged `twin_multi`); A1: when two children of one host match, the closest sorted extents wins and the lower node name breaks a tie | 0.95 |
| `same_pack_fit` | 3 | same pack, `family_overlap` AND `affinity` AND no veto | 0.6 - 0.9 |
| `cross_pack_fit` | 4 | different pack, `affinity` AND measured fit AND no veto | 0.3 - 0.6 |

A1 (twin evidence). A twin entry names its child in `replaces` (§4.3) and its seat is that child's frame, so a pair is placed against the baked child it
matches, not against whichever child won the slot's seat. The same evidence corrects the part's forward (§3.4 step 3a). The `twin` tier is
decided from the sorted extents alone, so the correction (which only reorders axes) never changes a tier.

A2 (setting gate). Before any tier or score is decided, every candidate that is not an `override` must pass the **setting gate**: the part's pack and the host's pack
must have the same *setting*, read from `attachment_rules.attach_genre_by_pack` (§7: a map of full pack id to a lower-case setting word). A pack absent from the map is a
setting of its own, so it matches only itself. The gate covers `twin`, `same_pack_fit` and `cross_pack_fit` and the pending list (one candidate list, D-8): a cross-setting
pair is never a candidate, is not in `pending_hosts`, and is nowhere in the directory. `same_pack_fit` always passes (one pack, one setting). Only an override
(`compatible.add`, §6.1) can add one, with tier `override`. This is not the record `genre` of DS§3.4: that one comes from `pack_settings.yaml` and keeps Apocalypse and War
under `modern` and Pirate under `fantasy`; the gate does not read it. The shipped table:

| setting | packs (full ids carry the `POLYGON_` prefix) |
|---|---|
| `modern` | Military, BattleRoyale, Police_Station, Heist, Shops, Palm_City, Gang_Warfare, Spy_Kit, Town, City, Military_Warehouse_Map (added 2026-10-23) |
| `apocalypse` | Apocalypse, Apocalypse_Wasteland |
| `scifi` | SciFi_City, SciFi_Worlds, CyberCity, SciFi_Horror (added 2026-10-23), SciFi_Space (added 2026-10-23), SciFi_Outpost_Map (added 2026-10-23) |
| `historical` | War, Pirate, War_Map (added 2026-10-23) |

A3 (sights are pack-generic). For the two sight slots a `same_pack_fit` candidate needs the same pack, `affinity`, `mount_available` and no veto; `family_overlap` is **not** required (Military's iron sights name no gun, so a name overlap never exists), and its absence from `signals` is expected. A probe seat carries no `span_m`, so `fit_span` is None: neutral, no bonus and no veto; the score is the tier base (0.7). `cross_pack_fit` for a sight is unchanged (it still needs a measured fit, so a probe seat does not make one) and every other slot is unchanged. A host that `attach_host_never` excludes for the slot (§7) has `mounts.<slot>` = `none` with reason `slot_disabled`, so the veto already in this list applies and no candidate (listed or pending) is made for it; only an override `add` beats it (the existing rule).

A4 (muzzle devices and foregrips are name-generic too). For the slots `muzzle` and `underbarrel` a `same_pack_fit` candidate needs the same pack, `affinity` and no veto; `family_overlap` is not required (`attachment_rules.family_free_slots`, shipped `sight_front`, `sight_rear`, `muzzle`, `underbarrel`; a silencer or a foregrip names no gun, and 12 of 13 muzzle parts and 12 of 24 underbarrel parts have an empty name-token set). Every veto, `fit_span` and `fit_bore` stays as it is. `laser_light` has the same shape (6 of 6 parts have no tokens) but no labelled pair, so it is left out until it is labelled. `magazine` and `optic` keep the name test: their names carry the family (`Preset_A`, `Sniper`).

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
- `affinity` rows for the sight slots (A2): `attach_affinity.sight_front.default` and `sight_rear.default` are the archetypes of the former `optic.iron` row; the `optic.iron` row is removed.

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

### 5.4 Settle to contact (A5 item 1; the optional entry key `seat_shift_m`)

The seat of a mount is one point per host; two parts on the same seat can need different heights (a red dot and a scope, a bipod foot and a grip). A seat measured from a baked child also starts where the child's own underside is, which may be sunk into the receiver. So the build settles each pair against the host's surface and stores the result on the pair.

**Which pairs.** Every entry of `compatible_hosts` of a part whose slot is `optic` or `underbarrel`, when (a) the host's `mounts.<slot>` is not `none`, (b) the mount's `source` is not `override`, (c) the entry's tier is neither `twin` nor `override` (authored placements are ground truth and are never moved), (d) the part has a measured anchor, and (e) the mount's `up` is within 1 degree of a coordinate axis (every live mount is). Every other slot, and every pending pair, is untouched. A pair this skips has no `seat_shift_m` key.

**The rule** (lengths in metres, in the host's scaled GLB space, after the existing placement `place(anchor, seat)` of C-21, where `seat` is the mount frame; let `u` be the mount's `up` vector, so the host lies along `-u` from the part and the part's contact face is its extreme along `-u`):

1. *Contact face.* The part's mesh (its GLB selection, scaled, collision nodes excluded, as the preview draws it) is sampled with the probe's triangle sampler at a 2.5 mm pitch (`mount_probe.surface_samples`) and carried through the placement; the samples whose coordinate along `-u` is within 4 mm of the extreme are the contact face.
2. *Host mesh.* The host's render mesh: its GLB selection, scaled, minus collision nodes and minus the nodes the pair hides (`hide` of `preview.build_job`: the slot's `occupied_by` and `child_node`, and the `hides_slots` nodes of the entry).
3. *Outer surface.* For every face sample `p` the line through `p` along `u` (offset by 1.37e-5 m and 0.93e-5 m across, so no line runs exactly along an edge) meets the host triangles; the outer surface is the hit **first met from outside the host on the part's side**, i.e. the hit with the greatest coordinate along `u` (the topmost hit for an optic, the lowest for an underbarrel part). It is not the nearest surface: a hollow tube or a ladder sight has surfaces inside and below the one that matters. A sample with no hit, or whose distance to the outer surface exceeds `reach_m` (0.5), is ignored.
4. *Signed distance.* `s = p.u - h.u` for that hit `h`: positive is a gap (the part is on its own side of the surface), negative is sunk.
5. *Shift.* `d` is the **minimum** of `s` over the face samples (the sample that touches first). When no sample counts, or `|d| <= dead_m` (0.003), the pair has no key. Otherwise `seat_shift_m = -clamp(d, -clamp_m, +clamp_m)` with `clamp_m` 0.060, rounded to 1e-4 like every coordinate (C-20). A gap gives a negative value (the part moves toward the host), a sunk part a positive value (away from it).

`attachment_rules.contact` holds `{slots: [optic, underbarrel], slab_m: 0.004, pitch_m: 0.0025, dead_m: 0.003, clamp_m: 0.060, reach_m: 0.5}`; every parameter is required, it is excluded from `rules_digest` and hashed into `attach_rules_digest` like the other attachment tables.

**Where it lives and how it is used.** `seat_shift_m` is an optional key of the `compatible_hosts` entry (like `hides_slots`, §4.3), present only when non-zero, in metres, `|value| <= clamp_m`, positive along the mount's `up`. A consumer places the part with `part_T = translate(seat_shift_m * mount.up) * T(mount) * T(anchor)^-1` (C-21), where `mount` is the frame the placement used (the mount, or for a twin its `seats` frame; a twin has no key) and `mount.up` is in the export's frame (`--frame item` rotates the vector; the scalar is unchanged). `weapons.preview.build_job` and the review page apply it, so every picture the pipeline draws shows it. `anchor`, `mounts`, `footprint` and every other field are unchanged: a consumer that ignores the key sees the A4 placement. Computing it needs both meshes, so it is a post-pass after compatibility (the rule is `weapons.attach.settle_pair`, the pass is in `directory.py`); a pair's value is cached with the geometry cache and a build with nothing changed reads no mesh (AC78 applies: a cache hit equals a recompute).

**Known limits (stated so nobody expects more).** The rule settles *contact*; it cannot see that a part landed on the wrong feature of the host (a thin ladder post, one small tab under a hood). Every pair with `|seat_shift_m| > 0.030` is therefore reviewed by eye (the cards of §13.6), and a part whose contact face is a small tab still reads as resting on the tab. The rule never moves a pair along the other two axes and never rotates a part.

**Known authored defects (twin pairs the rule does not touch; follow-up after the held-out round).** On the W8l directory nine of the nineteen authored twin entries sit away from the host's mesh once the twin's own child is hidden (six gaps, three sunk), most likely because the hidden node carries the twin's own rail or mount, so host-minus-child has lost it: the twins of `Scope_03` on `Revolver_02`, `Scope_04` on `SniperRifle_01`, `Scope_06` on `Pneumatic_01`, `Foregrip_01` on `Launcher_01`, `Scope_Small_01` on `Assault_02`, `Scope_Small_02` on `SMG_03`, `Scope_Small_03` on `Assault_01`, `Scope_Sniper_02` on `Sniper_02` (a visible float) and `Scope_Unique_01` on `Heavy_01`. They keep tier `twin`, carry no `seat_shift_m`, and AC113 pins that nothing moves them.

## 6. Corrections and overrides (committed file, categorical only)

### 6.1 New keys in `weapon_overrides.json` (DS§4.5 additive)

```jsonc
"ids": {
  "<pack>/<part>": {
    "set": {"attachment_slot": "optic", "attachment_kind": "reflex"},     // enums only
    "forward": "+z",                         // existing DS§4.5 field, now also valid on a part (anchor forward sign)
    "compatible": {"add": ["<pack>/<host>", "<pack>/<glob>*"], "remove": ["<pack>/<host>"]},
    "pair": "<pack>/<part>"                  // A2, parts only: pair with another sight part (null unpairs); the two ids must be in one pack, one front and one rear
  },
  "<pack>/<host>": {
    "mounts": {"optic": {"source": "child_node", "child": "<GLB node name>"},
               "laser_light": {"source": "none"}}                         // none = slot_disabled
  }
},
"globs": { "<pack>/<part glob>": {"compatible": {"add": ["..."], "remove": ["..."]}} }
```

Allowed in `compatible`, `mounts` and `pair` only: ids, globs, node names and the enum `source in {child_node, none}`.
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
  (points: rotated; vectors: rotated; `span_m`, `footprint`, `bore_d_m` unchanged; A1: each frame in `seats` is baked like the mount frame). `node_offset` keeps its rule (DS§4.1).
  `generated_from` gains `attach_version`, `attach_rules_digest` and `filter.attachments` (boolean, `true`) **only with `--attachments`**; without it none of the three keys exists and `geometry_version` is unchanged (5).
  A3: `attachment_rules.attach_host_never` is a map `slot -> [host name tokens]` (lower-case; the host's id after the pack, split like `family_overlap` tokens, plus the joined form); shipped: `sight_front` and `sight_rear` -> `flare`, `flaregun`, `prop`. A host whose tokens hit the list for a slot gets that slot's mount `none` / `slot_disabled`. Like the other attachment tables it is excluded from `rules_digest` and hashed into `attach_rules_digest`. A3 (§4.6 item 7): `attachment_rules.baked_sights` is `{tokens, not_tokens, rear_tokens}` (lower-case name tokens, shipped values in §4.6 item 7), whitelisted in `ATTACH_TOP_KEYS`, with the same digest treatment. Addendum 3 (item 8) extends it with `glass_tokens`, `body_tokens`, `handle_tokens`, `handle_not_tokens`, `handle_min_height_frac` and the `fused_post` table (`bin_m`, `half_bins`, `rise_m`, `width_min_m`, `width_max_m`, `min_pos`), and `attach_host_never` may now carry the slot `optic` (shipped: `optic`, `sight_front`, `sight_rear` -> `water`, `watergun`, `toy`; the two sight slots keep `flare`, `flaregun`, `prop`). A5 item 0: the token `prop` refuses every slot, so a briefcase that hides a flare gun lists no silencer, scope, magazine or light: shipped `optic` -> `water`, `watergun`, `toy`, `prop`; `muzzle`, `underbarrel`, `magazine`, `laser_light` -> `prop`; `sight_front`, `sight_rear` unchanged (`attach_version` 7 to 8). `generated_from.rules_digest` is computed over exactly the rule sections W7 hashed: the attachment tables (`attachment_rules`, including `never`, `rows`, `child_tokens` and `child_never`) are excluded from it, so adding or editing attachment rules never moves the default export's `rules_digest` (Tom: the default export is byte-identical to W7). The attachment tables hash separately into `attach_rules_digest`. A2: the new `attach_genre_by_pack` and `sight_probe` tables live inside `attachment_rules` and join the `ATTACH_TOP_KEYS` whitelist of `rules.py`, so they move `attach_rules_digest` only, never `rules_digest`. The directory header records both digests and `WEAPON_ATTACH_VERSION`, and treats a change of any of them as stale, so an edit to an attachment rule still rebuilds `directory.json` (AC77, AC78).
- Exit 6 on a contract violation: `attachment` on a non-part, `compatible_hosts` naming an id absent from the
  directory, a mount with `source == "none"` that has coordinates, or non-orthonormal frames (INV-14 to INV-18).
- New verbs: `weapons attach-eval` (precision/recall against a labels file and the twin truth; JSON on stdout, exit 4
  below the stated gates) and `weapons attach-preview` (§6.2). Both are wired lazily by W8a.

## 8. Data shapes and enumerations

- `ATTACH_SLOTS = (optic, muzzle, underbarrel, magazine, laser_light, sight_front, sight_rear)` (A2 appends the two sight slots, so the existing order is kept); `ATTACH_KINDS` per slot, each including `other` (§3.2);
  `MOUNT_SOURCES = (override, child_node, probe, none)`; `ANCHOR_FORWARD_SOURCES = (section, authored, twin, override, free_end)` (A1 adds `twin`, A4 adds `free_end`); `COMPAT_TIERS = (override, twin, same_pack_fit, cross_pack_fit)`;
  `MOUNT_NONE_REASONS = (no_child_no_probe, slot_disabled, probe_unavailable)`; new `REASONS`: `anchor_unmeasured`,
  `anchor_forward_unsure`, `attach_kind_unknown`, `mount_missing`, `mount_ambiguous`, `mount_estimated`,
  `twin_multi`, `compat_cross_pack`, and, from A2, `sight_side_unsure`. New `FLAGS`: none. Single source `weapons/__init__.py`, mirrored in
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
- **INV-19** The default (no `--attachments`, default `--roles`, which is `whole` only) export is byte-identical to the W7 export. An export made with `--roles part` or `all` but without `--attachments` is identical to W7 except that, on parts whose `attachment` is non-null, `confidence` and `review_reasons` follow §3.4.6 (a symmetric part is capped at 0.59 and gains `anchor_forward_unsure` and `low_confidence`; an unmeasured anchor scales confidence by 0.9 and adds `anchor_unmeasured`) **and, from A2, on parts that carry `sight_side_unsure` (their `attachment` is null; they are capped at 0.59 and gain `low_confidence`)**; no other byte differs, and no attachment key is emitted.
- **INV-20** (A2) `attachment.pair` is symmetric: if A names B then B names A; both are sight parts of opposite slots in one pack; a `null` pair is always valid.
- **INV-21** (A2) every `compatible_hosts` and `pending_hosts` entry whose tier is not `override` has a host whose pack has the same setting as the part's pack (§5.1).

Failure modes: a host GLB whose child node name changed -> an override naming it is reported `child_not_found`, never
silently dropped (as DS§7); a shared-GLB host with `glb_node` set -> children outside the selected subtree are ignored;
a node with rotation or scale in its world transform (NB-15) -> `node_transform` reason, mount left at confidence 0.4;
two parts of identical geometry (a twin of a twin) -> both are `twin`; part mesh with no flat foot (a bipod's legs) ->
foot slab is tried on both ends, otherwise `anchor_unmeasured` and the part appears under review.

## 10. Contract for DM-B (C-18 and following; the lead reconciles with the sit_armory / sit_weapons drafts)

Continues the table in DS§10.

| # | field / rule | definition |
|---|---|---|
| C-18 | `geometry.mounts` | object or null (null iff the host is not eligible, D-9). Keys exactly `optic`, `muzzle`, `underbarrel`, `laser_light`, `magazine`, `sight_front`, `sight_rear` (A2), each an object as in §4.1. Present only when the export is made with `--attachments`. |
| C-19 | `attachment` | object or null on part records: `slot`, `kind`, `pair` (A2, §3.5), `anchor`, `footprint`, `compatible_hosts`, `pending_hosts` (§3.2). Present only with `--attachments`. Part records keep `kind: null`, `hold_class: "none"`, and carry `geometry.item_basis` like whole records; a part inside a shared GLB also carries `geometry.node_offset` and, when its node has rotation or scale, the `node_transform` reason (exactly as DS§4.1 for whole records), so `anchor` and the footprint are interpreted in the same frame. |
| C-20 | frame and units | §3.1: `{point, forward, up}`, metres, 1e-4, unit vectors 4 dp, right-handed with `right = up x forward`. Asset frame: asset-local GLB scene space after `glb_scale`. Item frame: each record baked through **its own** `item_basis`; consumer applies each record's own `item_basis` to its own mesh. `span_m`, `footprint.*`, `bore_d_m`, `mate_d_m` are scalars in metres, never baked. Part records always carry `geometry.item_basis` (and `geometry.node_offset` for shared-GLB nodes, unrotated and not item-baked, DS C-17), so a consumer can orient the part mesh before using item-frame fields. |
| C-21 | placement | `part_T = T(mount) * T(anchor)^-1` where `T(F)` has rotation columns `[right | up | forward]` and translation `point`. After placement `anchor.point -> mount.point` exactly and the two `up` and `forward` vectors coincide. Reference implementation: `weapons.attach.place(anchor, mount)` plus a GDScript port written by DM-B against the shared oracle `sit_mount_place/1` (AC69). The first three literal cases of that oracle (muzzle identity, optic authored on its side, underbarrel hanging down) were checked by hand against this formula and agree; the fourth, `three_cycle`, is a non-involutory axis rotation that a transpose of the rotation cannot pass. |
| C-22 | occupancy | `mounts.<slot>.occupied_by`: sorted list of GLB node names to hide when a separate attachment is mounted; `[]` = free. `occupied_by` and `child_node` are **raw GLB node names, unsanitised**; the engine importer's renaming (Godot replaces `. : @ / " %` with `_` and renames duplicates) is the consumer's job (sit_weapons M15). For the muzzle slot the mount `point` is the seat measured with these nodes excluded, not the face of a baked device (R1, AC84). A mount with `source: "none"` is unavailable, and the consumer never synthesises a position (D-8). |
| C-23 | compatibility | `compatible_hosts[]`: `{host, tier, score, signals[], replaces[]}` plus, on an `optic` entry only and only when non-empty, `hides_slots` (A2, §4.3) and, on an `optic` or `underbarrel` entry only and only when non-zero, `seat_shift_m` (A5, §5.4: metres along the mount's `up`, `|v| <= 0.060`); `tier` in `COMPAT_TIERS`; sorted by `(tier rank, -score, host)`. `pending_hosts[]` are ids only, filtered by the same `--min-compat-tier` rule as `compatible_hosts` (default up to `same_pack_fit`). Relation stored on the part only (INV-14). Default export keeps tiers up to `same_pack_fit`. An **empty `compatible_hosts` means the part fits nothing**: only `pending_hosts` and a game overlay's own `fits` add can extend it. |
| C-24 | export surface | `--attachments` alone emits host `mounts` plus the attachment part records; `--roles attachment` is only an extra filter to export attachments alone; also `--min-compat-tier`, `--keep-foreign-hosts`. Default output (default `--roles`, `whole` only) is byte-identical to W7, `generated_from` included; `--roles part|all` without `--attachments` differs only as INV-19 states (`geometry_version` stays 5, `rules_digest` excludes the attachment tables; `attach_version`, `attach_rules_digest` and `filter.attachments` appear only with `--attachments`). `sit_armory` ignores unknown keys (it already ignores `component`) and keeps the `whole`-only default. `generated_from.filter.attachments` is a boolean, present and `true` only when the export was made with `--attachments` (absent otherwise, so the default output stays byte-identical). |
| C-25 | vocabulary | `ATTACH_SLOTS` / `ATTACH_KINDS` may grow in minor versions; consumers ignore unknown slots/kinds. `compatible_hosts` and `mounts` may later gain keys. |
| C-26 | stats | The directory carries no attachment stats. `sit_armory` overlays key stat modifiers by the part's `<pack>/<asset_id>` (or `renamed_from`, C-13) and read the slot from `attachment.slot`. |
| C-27 | numeric corrections | There is one measured exception, the optional entry key `seat_shift_m` of C-23 (A5, §5.4); there is no authored correction in the directory. A game that needs a nudge carries it in its own overlay, relative to the exported `mounts.<slot>.point` (D-5). `seat_depth_m` (how far a part may sink into the host) is overlay-owned on the game side; the directory adds nothing for it. |

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
| AC62 | Classification (the iron-sight rows are AC87): each other token row of §3.3 maps its fixture part to the stated slot/kind; the vehicle-named part gets `attachment: null`; a part with no row stays null | delete the `not` list -> the vehicle part becomes an attachment |
| AC63 | Anchor accuracy on rotated copies of the fixtures: `point` within 1 mm of the known foot centre, `up` within 0.5 degrees, for every slot kind, with the foot at the top and at the bottom | measure `point` as the AABB centre instead of the foot slab -> fails on the offset-foot fixture |
| AC64 | Forward sign: tube-with-flare faces the flare (`forward_source "section"`); symmetric box -> `symmetric true`, `forward_source "authored"`, confidence <= 0.59, reason `anchor_forward_unsure`; a `forward` override flips it and sets `override` | set the ratio threshold to 1.0 -> the symmetric fixture is "decided" |
| AC65 | Muzzle device: the mating end is the narrower end, `up` points to the wider end, `mate_d_m` within 1 mm of the fixture's diameter | pick the wider end as mating -> `up` reverses, fails |
| AC66 | Host mounts from children: `optic.point` within 1 mm of the known child seat, `occupied_by` equals the sorted list of child node names (a two-magazine fixture yields both, seat from the larger), `span_m` equals the child's foot length (`span_source "child_foot"`); precedence `override > child_node > probe > none` (four fixtures, one per rung) | ignore the child (always probe) -> optic becomes `none`, fails |
| AC67 | Muzzle: with an empty `occupied_by`, `mounts.muzzle.point == geometry.muzzle` exactly (A0 parity), `up == axes.forward`; ring fixture gives `bore_d_m` within 1 mm with `bore_source "ring"`; a ring-less fixture gives `face_extent`, confidence 0.5; `bounds_fallback` gives confidence 0.4 and `muzzle_fallback` | compute the muzzle with a second algorithm that differs by 1 mm -> parity fails |
| AC68 | `none` behaviour: the childless host has `source none`, null coordinates, reason `no_child_no_probe`, and (with a compatible part present) review reason `mount_missing`; the grenade host has `mounts: null`; no code path defaults a missing mount to bounds | add a bounds default -> the childless host gains a point, fails |
| AC69 | Placement math: for every slot kind `place(anchor, mount)` maps `anchor.point` to `mount.point` within **0.5 mm** and each of `up`, `forward` within 0.1 degrees. **Twin ground truth:** placing the standalone twin on the fixture host gives an AABB centre within **3 mm** of the child's AABB centre and AABB IoU >= 0.90. **Shared oracle:** `place` also reproduces, within 0.5 mm / 0.1 degrees, every case of sit_weapons' `fixtures/mount_place.json` (schema `sit_mount_place/1`; four cases at sit-capabilities 5cd92cd40ed67d8c68794e65c992a443f9cc1aa5: muzzle_identity, optic_part_authored_on_its_side, underbarrel_hangs_down and the non-involutory three_cycle; the test loads whatever cases the file holds, never a fixed count), copied byte for byte to `tests/fixtures/weapons/mount_place.json` with a provenance note (source repo, commit, copy date), like the A0 muzzle golden (DS§11.4); no case is edited here (DM-B is committing `addons/sit_weapons/fixtures/mount_place.json` now: W8c copies that file, not the spec literals), and a disagreement is reported to the lead instead of fixed. The directory's own cases stay as well. The GDScript port passes the same cases (DM-B) | swap `T(mount)*T(anchor)^-1` for `T(anchor)^-1*T(mount)` -> fails |
| AC70 | No intrusion: after placement of each "fit" fixture attachment, penetration depth along `mount.up` into the host body AABB is <= **3 mm**, and the attachment's AABB volume outside its foot slab that overlaps the host body AABB is <= 5 % of its volume | shift the anchor by 10 mm -> fails |
| AC71 | Twin detection: extents within `max(3 %, 0.8 mm)` per sorted axis are `twin`; a 5 % difference is not; one-to-many is `twin_multi` | widen the tolerance to 6 % -> the 5 % fixture becomes a twin, fails |
| AC72 | Tiers: `same_pack_fit` requires `family_overlap` AND `affinity`; the other-pack host only reaches `cross_pack_fit` when its pack has the part's setting (A2, §5.1; the fixture rules list both packs under one setting; AC91) (score <= 0.6, reason `compat_cross_pack`); ordering is `(rank, -score, host)`; two builds give identical output | drop the pack check -> the other-pack host gets rank 3, fails |
| AC73 | `fit_span` and `fit_bore`: the oversize cut is 1.5x (section 5.1): a `foot_length_m` 1.2x a span is neutral (not vetoed); 1.8x a `child_foot` span is not vetoed either, because a `child_foot` span is only a lower bound; 1.8x a `probe` span is vetoed; `fit_bore` ignored for `face_extent` mounts | allow `child_foot` to veto -> the 1.8x `child_foot` fixture is rejected |
| AC74 | Overrides: `compatible` add/remove by id and glob; precedence exact id > longest glob > rule; a missing id/node is reported (`child_not_found`), not dropped; `mounts` rejects any key other than `source`/`child` with **exit 6**; `apply-corrections` round-trips a review-page file | allow a `point` key -> the numeric variant is accepted, fails |
| AC75 | `pending_hosts`: a compatible host with a `none` mount appears there and not in `compatible_hosts`; adding a measured mount by override moves it; **tier filter:** a `cross_pack_fit` candidate on a mountless host is in the directory's `pending_hosts` (with its tier) but must not appear in the default export's `pending_hosts` | list it in both -> fails; skip the tier filter on `pending_hosts` -> the cross-pack candidate leaks into the default export and fails |
| AC76 | Review page: Attachments section exists, checklist states round-trip into `weapon-corrections/1` (parsed from the embedded data); mounts table lists every slot for an eligible host; no network access | remove the section -> fails |
| AC77 | Export: default output equals the stored W7-format golden byte for byte (a `--roles all` export without `--attachments` differs from the W7 reference only in `confidence` and `review_reasons` of parts whose `attachment` is non-null, nothing else), `generated_from` included (`geometry_version` 5, no `attach_version`, no `filter.attachments`); the same snapshot exported with `--attachments` differs only by the added keys, `attach_version` and `filter.attachments`; with `--attachments` item-frame points equal `item_basis * asset point` within 1e-4 per record (host and part separately), `occupied_by` lists preserved, tiers below `--min-compat-tier` dropped, foreign hosts dropped, exit 6 on each violation of INV-14..18 | bake the part through the host's `item_basis` -> fails on a rotated fixture; bump `WEAPON_GEOMETRY_VERSION`, emit `attach_version` unconditionally, or hash `attachment_rules` into the default `rules_digest` -> the byte diff fails |
| AC78 | Determinism and caching: two builds identical; bumping `WEAPON_ATTACH_VERSION` or `WEAPON_GEOMETRY_VERSION` invalidates cached entries; a cache hit equals a recompute | omit the version from the key -> stale hit survives a bump |
| AC79 | `weapons attach-eval`: on the fixture labels, reported precision and recall equal hand-computed values exactly; exit 4 when below the supplied gates | remove one fixture rule -> recall drops below the gate, exit 4 |
| AC80 | **Live (local, not CI; reported, never committed).** On BONDED's packs: (a) sanity: the live `twin` count equals the survey figure (11 parts on BONDED's packs; a different count is reported and investigated, not gated); (b) twin placement on the real hosts: AABB centre within **5 mm** and IoU >= 0.85 for >= 90 % of twin pairs, each pair measured against the baked child its `replaces` names (A1: the twin seat and the twin-corrected anchor describe the same baked pose, so this gate is self-consistent by construction for twin pairs; it checks the plumbing and the placement math, not an independent prediction, and the independent evidence is the labels in (c)); (c) on Tom's labels (stratified, >= 150 pairs with >= 40 positives, Q-5): precision >= 0.90 and recall >= 0.80 for tiers up to `same_pack_fit`; cross-pack reported separately, ungated until Q-1 is answered; (d) child-node coverage printed (expected: magazine 19, optic 12 of 48). **Recorded 2026-10-24 on the W8m directory (`8ac2e01`): (c) FAILS on both bounds, see §13.5; the held-out draw is spent** | n/a (acceptance run) |
| AC81 | **Spike gate (W9).** An estimator may set `source: probe` for optic only if, on the child-bearing hosts, the median `|probe - child truth|` <= 10 mm and the maximum <= 25 mm for the seat height and the median forward error <= 15 mm; otherwise it stays disabled and hosts keep `none`. The estimator source never reads a child node | feed it the child -> the "independent" check is violated |
| AC82 | No regression: on the W7 live directory, role/kind/archetype counts equal the W7 report (the role/kind/archetype count table equals the W7 report, null-kind whole/emplaced count 0, and every pre-existing test keeps its outcome; the pytest totals grow by design and are not compared); every pre-existing field of every record is byte-equal to the W7 reference, with two enumerated exceptions that sections 3.4.6 and 4.2 mandate: `confidence` and `review_reasons` of a record may change, and only by the section 8 attachment reasons (`anchor_unmeasured`, `anchor_forward_unsure`, `attach_kind_unknown`, `mount_missing`, `mount_ambiguous`, `mount_estimated`, `twin_multi`, `compat_cross_pack`) and, from A2, `sight_side_unsure`, and the `low_confidence` and confidence cap or scale that they cause; the only new fields are `geometry.mounts` and `attachment` (the test fails on any other difference, and lists the changed records) | n/a (diff test over the fixture directory in CI; live diff reported) |
| AC83 | Visual checkpoint (look): `attach-preview` renders >= 6 twin pairs and >= 6 non-twin pairs covering every slot; the lead views the captures before W8d closes; the baked node is hidden in each; no capture shows the attachment inside the receiver by more than the AC70 depth | n/a (lead review) |
| AC84 | Muzzle seat: on fixture (g) `mounts.muzzle.occupied_by` lists the brake node, `source` is `probe`, `point` equals the A0 probe of the mesh minus the brake (the barrel end) within 0.5 mm, and sits behind the device face by the brake length within 1 mm; `geometry.muzzle` is still the face of the brake (W7 bare-gun value, unchanged); a host with no brake gives `point == geometry.muzzle` exactly | include the brake in the probe mesh -> the seat lands on the device face and the behind-by-length check fails |
| AC85 | Twin seat (A1): on a fixture host with two same-slot children, a part that twins the smaller one has `replaces` equal to that one child and is placed so its AABB equals that child's (centre <= 0.1 mm, IoU >= 0.99); the mount carries `seats` for both children and keeps the larger as `child_node`; a one-child slot has no `seats`; export bakes the `seats` frames through `item_basis` | place a twin on the mount's seat child -> the two-magazine fixture fails; drop `seats` from the export bake -> the item-frame check fails |
| AC86 | Twin forward correction (A1): a fixture part whose measured forward is the reverse of its host's, and one whose measured axis differs (a near-round drum), are corrected with `forward_source` `twin`, the footprint swapped on the axis change only, and then place onto their twin children (centre <= 0.1 mm, IoU >= 0.99); an explicit `forward` override, a part with disagreeing twin hosts, and a muzzle device are left as measured; `review.confidence` and `review.reasons` never change; `WEAPON_ATTACH_VERSION` is 2 at W8f (3 from W8h, AC93) and the cache misses on the bump | skip the correction -> the reversed fixture fails the placement; apply it to a muzzle part or ignore the override -> the left-alone cases fail |
| AC87 | **Iron sights (A2).** On synthetic parts: `IronSight_Front_01`, `Ironsight_Front_Canted_01`, `Iron_Post_Sight_01`, `Iron_Hooded_Front_Sight_01` map to `sight_front` / `other`, `canted`, `post`, `hooded`; `Ironsight_Rear_01`, `Ironsight_Rear_Ring_01`, `Ironsight_Rear_Notch_01`, `Ironsight_Rear_Canted_01` to `sight_rear` / `other`, `aperture`, `notch`, `canted`, none of them raising `attach_kind_unknown`; `IronSight_01` (no side), `IronSight_Front_Rear_01` and `Iron_Post_Rear_Sight_01` (two sides) have `attachment` null, review reason `sight_side_unsure`, confidence <= 0.59 and `low_confidence`; a bare `Sight_Add_01` is null without the reason; no part has slot `optic` with kind `iron`; an `attachment_slot` / `attachment_kind` override on an unsure part gives it a block and drops the reason; `component` is untouched on every part | fold the sights back into `optic` (restore the two `optic_iron_*` rows, drop the new ones) -> the front fixture reads `optic`, fails; drop the `rear` / `front` `tokens_none` of the rows -> the two-sided names get a slot, fails |
| AC88 | **Pairs (A2).** A fixture pack with `Front_01` / `Rear_01`, `Front_Canted_01` / `Rear_Canted_01`, a lone `Rear_02` and a lone `Post_01` yields exactly two pairs, stored on both members; a second part with the same key makes both of that side pair nothing; a part in another pack never pairs; the `pair` override pairs and unpairs symmetrically and exit 6 on two fronts, two packs or an unknown id; a host listed by only one member keeps that member alone and a host listed by both has a set candidate at the lower tier | ignore `variant` -> `Front_Canted_01` pairs with `Rear_01`, fails; store the pair on one side only -> the symmetry check fails |
| AC89 | **Sight mounts (A2).** A host with `FrontSight_01` and `RearSight_01` children gets `sight_front` and `sight_rear` `child_node` mounts, seats within 1 mm of each child, `occupied_by` its own child only; a `Sight_Glass_01` child still fills `optic` and neither sight slot; an unsided `Sights_01` child fills nothing; two sibling children `Sight_01` and `Sight_02` stay in `optic`; `mounts` has the seven keys on every eligible host; a host override names a child for `sight_rear` | add `sight` to the sight tokens -> the glass child migrates, fails |
| AC90 | **Optic over the rear sight (A2).** On a fixture host with measured `optic` and `sight_rear` mounts, an optic whose placed extent along host forward covers the rear seat (plus 10 mm) has `hides_slots == ["sight_rear"]` on that host's entry, a short optic seated forward of it has no `hides_slots` key, an optic on a host whose `sight_rear` is `none` has none, a front-sight part never has it, and the preview hides the rear-sight nodes with the covering optic | drop the overlap test (always hide) -> the short optic hides, fails |
| AC91 | **Setting gate (A2).** Fixture packs `P1` and `P2` are listed under one setting and `P3` under another, `P4` is unlisted. For a part in `P1`: hosts of `P1` are `same_pack_fit`, hosts of `P2` are `cross_pack_fit`, no host of `P3` or `P4` appears in `compatible_hosts` or `pending_hosts`, **including a host child it twins exactly**; a `compatible.add` of a `P3` host appears with tier `override`; an unlisted pack matches only itself; editing the table moves `attach_rules_digest` and not `rules_digest`; every non-override entry satisfies INV-21 | remove the setting check (or apply it to the cross-pack tier only) -> the `P3` host and the `P3` twin reappear, fails. Live (reported, never gated): on the 2026-10-23 catalog the gate removes 3,266 of 4,059 `cross_pack_fit` candidates and 8 of 46 `twin` candidates (§13.1) |
| AC92 | **Sight probe (A2, §4.6).** Fixture hosts: (i) a box receiver, a lower box handguard and a thin barrel: `sight_rear.point` within 3 mm along forward of the receiver's rear end plus 10 mm and within 1 mm of the receiver top, `sight_front.point` within 3 mm of the handguard's front end minus 8 mm and within 1 mm of the handguard top; (ii) the same host with a baked scope child on the receiver: the seats are unchanged (the scope is excluded); (iii) a slide-only pistol host: both seats or both `none`, never the front behind the rear; (iv) a host whose top run is under 3 bins: both `none`. **Numeric gates (§4.6 item 6):** over the live catalog, seats on the host top surface within 3 mm, front forward of rear, no seat inside the optic span unless `hides_slots` covers it; a fixture that breaks each of the three fails. **Look gate (the lead's, never self-passed by the builder):** the lead views paired cards on at least 12 hosts covering every archetype of the sight affinity rows (AC83 method) before W8h-B closes; a sight inside the body by more than AC70's 3 mm, or floating, fails the gate | keep the optic child in the mesh -> (ii) fails |
| AC94 | **Sight candidates (A3).** Fixture pack `P1` with `Ironsight_Front_01` (sight_front), a rifle host `Rifle_01` and a pistol host `Pistol_01` that share no token with the part, both with a probe seat on `sight_front`, a shotgun host with seat `none` and a melee record: the part is `same_pack_fit` (score 0.7, signals `affinity` and `mount_available`, no `family_overlap`) on the rifle and the pistol, `pending` (not listed) on the shotgun, nowhere on the melee; a host in pack `P2` of the same setting with the same seat gets nothing (cross-pack still needs a measured fit); an optic scope on the rifle host with no name overlap stays unlisted (the relaxation is for the sight slots only) | restore `family_overlap` for sights -> the rifle and pistol rows fail; apply the relaxation to every slot -> the optic case fails |
| AC95 | **Excluded hosts (A3).** Fixture hosts `Pistol_Flare_01`, `Prop_Briefcase_Flaregun_01` and `Rifle_Prop_01` have `mounts.sight_front` and `sight_rear` = `none` / `slot_disabled` and no sight candidate in `compatible_hosts` or `pending_hosts`, while their `optic` mount is unchanged; a same-shaped host without those tokens is seated by the probe; an override `add` still lists the pair as `override`; the two live hosts `POLYGON_Apocalypse/SM_Prop_Briefcase_Flaregun_01` and `POLYGON_BattleRoyale/SM_Wep_Pistol_Flare_01` are refused (checked on the scratch catalog, not a committed test); the tests fail on the A2 base | remove the table -> the three fixture hosts get a probe seat, fails |
| AC97 | **Probe mesh excludes baked accessories (A3).** A fixture host with a box slide and, in front of it, a baked `muzzle` child (a cylinder 20 mm taller than the slide top): `sight_front.point` lies on the slide top (within 1 mm of it), never on the cylinder; the same host with a baked `laser_light` or `underbarrel` child standing proud of the top: the seats are unchanged; the A2 fixture of a host whose laser child stood 20 mm above the receiver (`FAKE_Mount/Pistol_Mount`) is now seated, not refused; the live pistol `POLYGON_Apocalypse/SM_Wep_Pistol_01` front seat is never on its suppressor (checked on the scratch catalog; the W8i build found that, with the suppressor out of the mesh, the highest bin is the front sight block baked into the end of the slide mesh, 10 mm above the slide, so the probe refuses the host: both slots `none` / `probe_unavailable`, and `POLYGON_Spy_Kit/SM_Wep_Pistol_01`, whose slide carries baked sight nubs, is refused the same way; a baked sight inside the body mesh is a refusal, §4.6 item 7) | put the muzzle child back into the probe mesh -> the cylinder case fails |
| AC98 | **Baked sight children (A3, §4.6 item 7).** Fixture hosts: (i) a rifle with a child `Fake_Sight_01` on the muzzle half of its length and `Fake_Sight_02` on the rear half (the shape of the live `Rifle_Assault_01`): `mounts.sight_front` and `mounts.sight_rear` are `none` / `slot_disabled`, no sight candidate (listed or pending) exists for the host, and its `optic` mount is unchanged; (ii) a host with one unsided `Fake_Sights` child on the rear half only: `sight_rear` refused, `sight_front` still seated by the probe; (iii) a host with a `Fake_CarryHandle_01` child: `sight_rear` refused, `sight_front` unchanged; (iv) a host whose only such child is `Fake_ChargeHandle_01`, `Fake_Sight_Glass_01` or `Fake_Scope_01`: both slots seated by the probe as before (not baked sights); (v) a host whose sight slot is already `none`: the reason is unchanged; (vi) an override `add` still lists the pair as `override`; a host override `mounts: {sight_front: {source: none}}` refuses the front slot of a host with no baked child. Live (scratch catalog, not a committed test): `POLYGON_BattleRoyale/SM_Wep_Rifle_Assault_01` (both slots) and `POLYGON_War/SM_Wep_American_MachineGun_01` (`sight_rear`; its front post is baked into the body mesh and is refused by the data override) have no sight seat; the numeric gates of item 6 still hold and the default export is byte-identical. The tests fail on the A3-addendum base | ignore the `baked_sights` table -> (i), (ii) and (iii) fail |
| AC99 | **Optic children (A3 addendum 3, item 8 A/B).** Fixture hosts: (i) a host with a child `Fake_Scope_01` (body child): `mounts.optic` stays `child_node` with `occupied_by` that node, `sight_front` and `sight_rear` are `none` / `slot_disabled`, and an optic part is still a candidate on it; (ii) a host whose only optic child is `Fake_Sight_Glass_01` (a 3 mm sheet): `optic`, `sight_front` and `sight_rear` are all `none` / `slot_disabled` and no optic or sight candidate (listed or pending) exists for it; (iii) a host with `Fake_Scope_Glass_01` only: glass-only, as (ii); (iv) a host with both `Fake_Scope_01` and `Fake_Scope_Glass_01`: a body child, as (i); (v) a `Fake_RedDot_01` child is a body child; (vi) an override `mounts: {optic: {source: none}}` on a host as in (i) makes `optic` `none`, and an override `child_node` on a glass-only host keeps that seat. Live (scratch catalog, not a committed test): the 12 glass-only hosts are `Military/SM_Wep_Preset_A_Rifle_01`, `_A_Rifle_02`, `_A_SMG_01`, `_A_Sniper_01`, `_B_Rifle_01`, `_B_Rifle_02`, `_B_Rifle_03`, `_B_SMG_01`, `_B_Sniper_01`, `Police_Station/SM_Wep_Launcher_01`, `SM_Wep_Rifle_01` and `SM_Wep_Sniper_01`, and the body-child hosts number 27 (list them); the build reports both lists | treat a glass child as a body child -> (ii), (iii) fail |
| AC100 | **Iron pair and the fused post (A3 addendum 3, item 8 C/D).** Fixture hosts: (i) a box host with a sided or unsided baked front post child: both sight slots `none` / `slot_disabled`, never one; (ii) a baked rear sight child: both refused; (iii) a child `Fake_Handle_01` whose centre is above 55 % of the host height: both refused; the same child below it, `Fake_ChargeHandle_01` and `Fake_PumpHandle_01` at any height: both seated; (iv) a host with a sided `child_node` front sight and no rear: `sight_front` unchanged (`child_node`), `sight_rear` refused; (v) a box host whose mesh has a 20 mm wide block standing 14 mm above its top line at 0.8 of its length: both refused (fused front post); the same block at 0.4: both seated; a block 6 mm tall, 8 mm wide or 40 mm wide at 0.8: both seated; a block 14 mm tall and 20 mm wide at 0.8 on a host whose baseline steps up by 14 mm there (a handguard step, not a post): both seated; (vi) a rear-half block of 14 mm: no effect (the S ticks are ignored); (vii) the slot-state rule: a sight slot already `none` keeps its reason; an override `add` still lists the pair. **Live gate (reported, not a committed test):** the build lists every host the detector flags and, against the lead's census list of 132 hosts whose sheet check flagged a front post at 0.6 or more (`w8i_host_census/rule_sets.json`), every host in one set and not the other, with the reason. The census is NOT the reference: it profiled raw vertices with a window at the bounding-box centre, so a sparse mesh produced ticks that a densely sampled profile does not (W8j result: the build flags 83 hosts, 10 of them probe-seated; of the 30 census hosts the probe seats and the build does not flag, 3 are toy or water hosts caught by name and the other 27 were looked at in dense side profiles: none shows a raised post at 0.6 or more, except a block about 40 mm wide at the muzzle end of `Military/SM_Wep_Sniper_01`); a flagged host the lead disagrees with is fixed by an override `add`, a missed fused post by an override `none` (item F) | skip (D) -> (v) fails; refuse one side only -> (i), (ii), (iii) fail |
| AC101 | **Host names (A3 addendum 3, item 8 E).** Fixture hosts `Fake_ToyGun_Rifle_01` (with a `Fake_Scope_01` child), `Fake_Watergun_01` and `Fake_WaterPistol_01` have `optic`, `sight_front` and `sight_rear` `none` / `slot_disabled`, the toy host's scope child included; a host named `Fake_Waterfall_Rifle_01` (the word is not `water`) and `Fake_Rifle_01` are not excluded; an override `add` still lists a pair on an excluded host; `Fake_Flare_Pistol_01` still loses only the sight slots. Live: exactly nine hosts are caught: `Office/SM_Wep_ToyGun_Rifle_01`, `_SMG_01`, `_Shotgun_01`, `Starter/SM_Wep_WaterPistol_01`, `_Watergun_01`, `_Watergun_02`, `WaterGuns/SM_Wep_WaterPistol_01`, `_Watergun_01`, `_Watergun_02`; only `ToyGun_Rifle_01` loses an available optic mount | empty the `optic` row -> the toy host keeps its scope seat, fails |
| AC102 | **Overrides for the fused cases (A3 addendum 3, item 8 F).** The committed `weapon_overrides.json` (the lead's data commit) refuses `optic`, `sight_front` and `sight_rear` on `Military/SM_Wep_Preset_A_Rifle_03`, `BattleRoyale/SM_Wep_Rifle_Assault_02`, `BattleRoyale/SM_Wep_Rifle_Assault_04`, `SciFi_Space/SM_Wep_Rifle_01`, `SciFi_Worlds/SM_Wep_Shotgun_03` and `SM_Wep_Heavy_03`, and `sight_front` and `sight_rear` only on `SciFi_Worlds/SM_Wep_Assault_03`; the schema test already requires sorted keys and categorical values (INV-17) | n/a (data; checked by the live gate and the committed-file test) |
| AC103 | **Versions and impact (A3 addendum 3).** `WEAPON_ATTACH_VERSION` is 5 (6 after addendum 3b, AC104), `WEAPON_GEOMETRY_VERSION` stays 5, `rules_digest` stays `7b9829af37328fe7`, the default export is byte-identical, the `w8d_w7_*` references are untouched, the geometry mounts cache key carries the new tables. Live counts reported by the build (the W8i directory at `1205b64` is the base): sight candidates listed 48 (`sight_front` 15, `sight_rear` 33) before and the count after (expected 0), pending before and after; `optic` candidates listed 224 and pending 1379 before and the counts after; the list of every host that loses an available optic mount (expected 10: the nine glass-only hosts that had a glass `child_node` and `ToyGun_Rifle_01`); the numeric gates of item 6 still hold on the hosts that keep a seat | as AC93 |
| AC104 | **Pending sights on baked hosts (A3 addendum 3b, item 9).** Fixture hosts whose probe refuses (a receiver run under 3 bins) so that both sight slots start `none` / `probe_unavailable`: (i) with a `Fake_Scope_01` child: both sight slots `none` / `slot_disabled`, no `sight_front` or `sight_rear` candidate listed or pending, `optic` unchanged; (ii) glass-only (`Fake_Scope_Glass_01`): as (i) and `optic` `slot_disabled`; (iii) with a baked `Fake_Sight_01` front post child: both sight slots `slot_disabled`; (iv) with a carry handle child above 55 % of the host height: both refused; (v) with a fused front post (a 20 mm wide block 14 mm high at 0.8 of the length on a mesh whose receiver run is too short to seat): both refused; (vi) the same host without any baked child, post or handle keeps `probe_unavailable` and its pending entries; (vii) a sight slot that is `none` / `slot_disabled` keeps its reason, a `child_node` sided sight keeps its seat, an override mount is never touched, an override `add` still lists a pair. Live (scratch catalog, reported): `pending_hosts` of `sight_front` and `sight_rear` before and after (W8j state: 264 and 312 with the W8j overrides), the list of hosts whose sight reasons changed from `probe_unavailable` or `no_child_no_probe` to `slot_disabled` with the rule that did it, `compatible_hosts` unchanged for every part (list any difference), `optic` counts unchanged, default export byte-identical, `WEAPON_ATTACH_VERSION` 6 | restore the probe-only restriction for the two pending reasons -> (i) to (v) fail; apply the rules to a host with no baked child -> (vi) fails |
| AC105 | **Free-end forward (A4, item 1).** Fixtures (`Fake_` vertices, no packs): (i) a hanging `standard` magazine 0.20 m tall whose lower quarter leans 30 mm toward +z, with the larger end section at -z (the section prior says -z): forward +z, `forward_source = free_end`, `symmetric = false`, no `anchor_forward_unsure`; (ii) its mirror image: -z; (iii) the same magazine leaning 9 mm: the section result and `forward_source` of the old code, byte for byte; leaning 11 mm: the free-end result; (iv) a `bipod` whose legs lean 80 mm toward -z: -z; (v) the 30 mm lean on a `drum`, a `foregrip`, an `optic`, a `laser_light` and a `sight_front`: the old result for each; (vi) an explicit `forward` override: `override`; a part with twin evidence of the opposite sign: `twin`; (vii) a host child measured without a kind: the old result. Live, over the catalog: every magazine of kind `standard` and every bipod with twin evidence or a committed forward override whose displacement is at least 10 mm gets the sign of that evidence (9 of 9 magazines decided and 3 of 3 bipods; the two undecided magazines are printed with their lean), and the list of every part whose `forward` changes against the W8k directory is printed with its displacement for the lead's look (expected: `Mag_Banana_01`, `Mag_Banana_02`, `Mag_Receiver_01` and `Mag_Thin_01`, nothing on an optic, a drum or a foregrip) | threshold 10 mm to 5 mm -> the 9 mm case flips, fails; apply the rule to every slot -> case (v) fails |
| AC106 | **Name-generic slots (A4, item 2).** Fixtures: a `Fake_Silencer_01` (muzzle) and a `Fake_Foregrip_01` (underbarrel) in the pack of a host that shares no name token with them, affinity true and the seat available: `same_pack_fit`, `family_overlap` absent from `signals`; the same with the seat `none` / `probe_unavailable`: pending; with `slot_disabled`: none; a `Fake_Mag_01` and a `Fake_Scope_01` on the same host: still no candidate; a part in another pack: unchanged; a muzzle with a measured bore mismatch keeps its `bore_mismatch` signal and its score reduction. Live (the W8k directory is the base): `muzzle` listed 52 to 264 and pending 24 to 30; `underbarrel` listed 6 to 16 and pending 653 to 933; no other slot's list changes; 31 launcher and prop hosts gain the review reason `mount_missing` and nothing else in their record moves; the default export is byte-identical | put `muzzle` back out of `family_free_slots` -> the silencer is unlisted, fails; put `magazine` in -> the magazine case fails |
| AC107 | **Foot lip (A4, item 3).** Fixtures: a hanging part 0.24 m tall whose top is a ridge 4 mm along `forward` and 21 mm across, over a body 50 mm along `forward` that starts 5 mm below the top: `foot_length_m` 0.050 (the 8 mm rung), `point` at the centre of that slab; a post whose foot stays 4.3 mm deep over 12 mm: unchanged; a 2.5 mm stub over a body: the 8 mm rung; a line-contact foot (extent 0 across): unchanged; a flat foot: byte-identical; a ridge over a ridge (4 mm at 4 mm and 8 mm, 50 mm at 16 mm): the 16 mm rung; never a third step. Live: exactly two parts, `Mod_A_Mag_05` (0.004 to 0.0497, +-1 mm) and `Attach_Foregrip_05` (0.0025 to 0.084, +-1 mm), change their footprint and `point`, and exactly one host child does too: the magazine mount of the two `Pistol_Heavy_01` hosts (`POLYGON_BattleRoyale` and `POLYGON_Palm_City`; `geometry.mounts.magazine.span_m` 0.0045 to 0.0446, the same function measures a host child), and the printed list of every attachment and every host child whose `foot_length_m`, `foot_width_m` or `point` moves has no other entry (the iron-sight posts, `Scope_11` and the line-contact feet are on the list of parts checked and unchanged) | rung ladder removed -> the ridge fixture reads 0.004, fails; `lip_growth` removed -> the post fixture steps, fails |
| AC108 | **Optic seat lift (A4, item 4).** Fixture host: a box receiver whose top is 14 mm above the underside of a baked `Fake_Scope_01` child that sits in a recess: the mount's `up` coordinate is the receiver top (+-0.5 mm), `source` still `child_node`, every other field unchanged; a receiver 40 mm above the underside (over the cap): the child's own point; nothing above the underside: the child's own point; a host without a scope child: no `optic` change; a two-child host: each `seats` frame lifts for its own child. Live numeric gates, over every `child_node` optic mount: (a) for a lifted mount no probe-mesh surface over the child's rectangle lies higher than the seat by more than 1 mm; (b) `Sniper_02` lifts 13.0 mm and `Sniper_03` 22.3 mm (+-1 mm); (c) a mount with nothing above its underside, or a lift above the cap, is byte-identical; (d) the table of every lifted host (lift in mm) and every host above the cap is printed for the lead's look | cap removed -> the 40 mm fixture lifts, fails; lift skipped -> the recess fixture fails |
| AC109 | **Mirrored pair seat (A4, item 5).** Fixtures: two `Fake_Leg_L_01` and `Fake_Leg_R_01` underbarrel children at x = +52 mm and -52 mm, same y and z, equal extents: `point` x = 0.000, y and z unchanged, `seats` keeps both legs, `occupied_by` both, `child_node` the lower name; legs at +52 mm and -30 mm (not symmetric about the centre line): the point is their average, x = +11 mm; two children that differ by 3 mm along `forward`: not mirrored (the limit is 1 mm), the larger-volume seat; two unequal extents: not mirrored; three children: not mirrored. Live: only `MachineGun_Bandit_01` (x 0.052 to 0.000) and `Sniper_01` (x 0.0205 to 0.000) move, and every other multi-child mount (`RPG_01`, `Rifle_Assault_01`, `Rifle_Base_01`, `Shotgun_03`, `SniperRifle_01`) is byte-identical | midpoint -> larger-volume seat: both fixtures fail |
| AC108R | AC108 is **retired by A5 item 2** (§4.2): the optic seat lift is deleted, so its fixtures, its live gates and `optic_seat` go with it; a `child_node` optic mount is byte-identical to its pre-A4 value. The test that pinned the lift is removed in the same commit, not skipped | a test still lifting -> the new byte-identity check fails |
| AC110 | **Versions and impact (A4).** `WEAPON_ATTACH_VERSION` is 7, `WEAPON_GEOMETRY_VERSION` stays 5, `rules_digest` stays `7b9829af37328fe7`, the default export is byte-identical (sha1 `1cacd9a004bee57a56b0bc94f4bfcd08041cb893` on the scratch catalog), the `w8d_w7_*` references are untouched, the geometry anchor and mounts cache keys follow the new code. The live report prints, against the W8k directory: the changed parts of AC105 and AC107, the list counts of AC106, the lifted hosts of AC108, the two hosts of AC109, and that nothing else in any record moved (a field-by-field diff of the two directories whose only differences are the listed ones, `attach_version` and `attach_rules_digest`). The five forward overrides of `72f96e5` (`B_Mag_03`, `B_Mag_07`, `Bipod_01`, `Bipod_02`, `Bipod_03`) are removed by the lead in a data commit after the merge; the directory is identical before and after that commit except `forward_source` (`override` to `free_end`) | as AC93 |
| AC111 | **`prop` hosts (A5 item 0).** Fixture hosts `Fake_Prop_Briefcase_Flaregun_01` and `Fake_Prop_Rifle_01`: all seven slots `none` / `slot_disabled`, in no part's `compatible_hosts` or `pending_hosts`; a host `Fake_Properties_01` is not refused (whole-token match); a host with `watergun` still loses `optic` only. Live: `SM_Prop_Briefcase_Flaregun_01` is listed by no part | a token list that names the two sight slots only -> the briefcase fixture lists an optic |
| AC112 | **Settle to contact (A5 item 1, §5.4).** Fixtures (`Fake_` boxes, no packs), each with a measured placement: (i) an optic 11.0 mm above a box receiver: `seat_shift_m` -0.0110 +-0.0005; (ii) an optic sunk 8.0 mm: +0.0080 +-0.0005; (iii) a gap of 2.9 mm: no key, 3.1 mm: key -0.0031; (iv) an underbarrel part 12.0 mm below a rail: -0.0120, sunk 37.7 mm: +0.0377; (v) a 90 mm gap: -0.0600 (the clamp binds), a 59 mm gap: -0.0590; (vi) a host with a hollow tube under the part (inner floor 15 mm below the outer top): the outer top is used, not the nearest surface; (vii) a host child that is hidden (in `occupied_by`) and 20 mm taller than the receiver, and a collision node: neither counts as host surface; (viii) a part with a 3 mm tab below a body held 10 mm up: the tab is the contact face and decides; (ix) a face with no hit under it: no key; (x) a face with one sample touching and the rest 20 mm up: `d` is the touching sample's, so no key; (xi) a muzzle, magazine, laser_light or sight part: never a key; (xii) a mount whose `up` is 30 degrees off every axis: no key. A pair with no key places byte-identically to `place(anchor, mount)` | the nearest-surface variant fails (vi); no clamp fails (v); no dead zone fails (iii); counting hidden children fails (vii) |
| AC113 | **Authored placements never move (A5).** Fixtures: a `twin` entry placed on a `seats` frame, an entry of tier `override`, and a pair on an `override`-source mount: none has `seat_shift_m` although each is 20 mm off its host's mesh; `preview.build_job` returns the byte-identical matrix for them. Live: the 19 twin entries and every override-source or override-tier pair carry no key, and the nine known authored defects of §5.4 are unchanged | a rule that does not skip twins moves the twin fixture |
| AC114 | **Placement and export (A5).** `build_job(...)["matrix"]` equals `translate(seat_shift_m * mount.up) @ place(anchor, frame)` for a keyed entry and `place(anchor, frame)` otherwise (+-1e-9); `weapons export --attachments` carries the key unchanged (`--frame item`: the scalar is unchanged), the default export is byte-identical, a value above 0.060 in absolute terms or a non-number is exit 6, the key on a slot other than `optic` / `underbarrel` is exit 6 | a build_job that ignores the key fails; a missing schema check fails |
| AC115 | **Named cases and the map-wide count (A5 gate).** Live, on a scratch directory built from the A5 tree (never the live catalog), measured with the **independent method** below and not with the rule's own ray walk. Named cases (`seat_shift_m` in mm, measured on the built route, i.e. with the lift retired; "before" is the same pair on `e162b07`, with the contact gap `G` or cast depth `C` as printed): `MachineGun_Bandit_01` `Mod_Bipod_01` and `Mod_Bipod_03`: -11.9 to -10.9, `Mod_Bipod_02`: -13.1 to -12.1, `Mod_ForeGrip_01` to `_06`: -11.8 to -10.8 (`G` 11.3 to 11.4 before); `MachineGun_01` `Mod_Scope_11`: no key (`G` 10.5 before, under 1 after: the lifted seat held it 10 mm off, and retiring the lift seats it) and `Mod_Reddot_01`: +13.0 to +14.0; `Sniper_01` `Attach_Foregrip_01`: +37.2 to +38.2 (`C` 26.6 before); `Launcher_03` `Attachment_Redot_03`: +50.6 to +51.6 and `Attachment_Redot_01`, `_02`, `Attachment_Scope_01`, `_02`: +58.8 to +59.8 (`C` 29 to 51 before); `SniperRifle_01` `Attach_Scope_Roll_01`: +57.5 to +58.5; `Grenade_Launcher_01`: its 16 optic pairs that start 17 mm or more sunk (`C` before 17.6 to 46.9) take +17.0 to +47.5, each within 1.0 mm of its own `C` before, and its other 6 optic pairs take -26.0 to -17.0; two pairs the lead named that are not listed (Military `RPG_01` with `Mod_Reddot_01` and `Mod_Scope_11`) are measured with the rule applied on demand to a pair that has no entry (`geometry.settle_cached`, the same function): `Mod_Reddot_01` +18.0 to +20.0, `Mod_Scope_11` no key. After the build every one has `G <= 1.0` and `P`, `C` <= 1.5 (the 2 mm sampling grain; the parity test is not exact). A band that the lift's retirement moved from the dry run is reported, not silently widened. Map-wide: over every listed `compatible_hosts` entry of an optic or underbarrel part with a usable mount, tier not `twin` or `override`, mount source not `override` (215 pairs at the dry run), **0 pairs with `G > 3 mm`, 0 pairs with `C > 3 mm` or `P > 3 mm`** after the shift; the count of keyed pairs and the maximum `|seat_shift_m|` are printed; every pair with `|seat_shift_m| > 0.030` is on the cards for the lead's look. **Independent method:** `G` = closest distance from the contact face (same slab, same 2.5 mm pitch, at most 400 samples) to the host mesh sampled at 2 mm (brute force); `C` = for each face sample that a lateral-parity test (rays along the two axes across `u`, an odd number of hits on both sides) calls inside the host, the distance along `u` to the first surface met on the way out, maximum over the face; `P` = the nearest-surface distance of the same inside samples. `C` is the reliable depth: `P` saturates on thin features (a launcher body read `P` 2.6 against a true 46.9) and the parity test is unreliable on non-watertight meshes | a rule that moves nothing fails every named band; one that clamps at 30 mm leaves 24 pairs over 3 mm |
| AC116 | **Versions and impact (A5).** `WEAPON_ATTACH_VERSION` is 9, `WEAPON_GEOMETRY_VERSION` stays 5, `rules_digest` stays `7b9829af37328fe7`, the default export is byte-identical to the one of `e162b07` (sha1 `ec22a4334f720fdf2092a2a7a58f6eb3438c8be4` on the scratch catalog; the earlier `1cacd9a0...` differs only in `generated_from.overrides_digest`, which the data commit of the five forward overrides moved), the `w8d_w7_*` references are untouched, the geometry anchor and mounts cache keys follow the new code (the lift is gone from the mounts key), and `attach_rules_digest` changes (new `contact`, no `optic_seat`, `attach_host_never` of item 0). The live report prints, against the `e162b07` directory plus item 0: the keyed pairs and their shifts, the `child_node` optic mounts that return to the child's own point, the briefcase host, and that nothing else in any record moved (a field-by-field diff whose only differences are those, `attach_version` and `attach_rules_digest`) | as AC93 |
| AC96 | **Versions (A3).** `WEAPON_ATTACH_VERSION` is 4, `WEAPON_GEOMETRY_VERSION` stays 5, `rules_digest` stays `7b9829af37328fe7`, the default export is byte-identical, the `w8d_w7_*` references are untouched | as AC93 |
| AC93 | **Versions and digests (A2).** `WEAPON_ATTACH_VERSION` is 3 and `WEAPON_GEOMETRY_VERSION` is 5; the directory header and the `--attachments` export record `attach_version` 3; a bump of the constant invalidates the cache (AC78); the default export of the 2026-10-22 W7 catalog is byte-identical to the stored one (live sha1 `f5e64427fa186890d2306745502cef6d754ebe4a`, `rules_digest` `7b9829af37328fe7`); the `w8d_w7_*` reference files are untouched | hash `attach_genre_by_pack` into `rules_digest` -> the default export's `generated_from` differs, fails |

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
| W8f twin evidence (A1) | W8d | none | AC85, AC86, AC80 (b) re-run | `compat.py`, `mounts.py`, `schema.py`, `export.py`, `preview.py`, `weapons/__init__.py` (edit), tests | the AC80 re-run | M: ~500 lines |
| W8h-A sight slots, pairs, setting gate (A2) | W8f | none | AC87-AC91, AC93; AC62, AC72, AC77, AC82, AC86 re-pinned | `weapons/*.py` (edit: `__init__`, `attach`, `classify`, `compat`, `directory`, `export`, `mounts`, `overrides`, `corrections`, `preview`, `review`, `rules`, `schema`, `gate`), `weapon_rules.yaml` (edit), tests and fixtures `w8*` (edit) and `test_weapons_w8h_*` / `w8h_*` (new) | a local rebuild of the 2026-10-23 catalog, counts reported | M: ~700 lines |
| W8h-B sight probe (A2, §4.6; approved, same build as W8h-A) | W8h-A | none | AC92 | `weapons/mount_probe.py` (new), `mounts.py` (edit), `weapon_rules.yaml` (`sight_probe`), tests | the look gate: paired cards on live hosts | S: ~350 lines |

Shared files: `cli.py`, `pyproject.toml`, `weapons/__init__.py` constants are W8a's only; later slices use the named
constants. `weapon_rules.yaml` is edited sequentially (W8a tables, W8c compat), never in parallel. Parallel pairs
(W8c/W9, W8d/W9) touch disjoint files. The lead reviews W8d's captures (AC83) before it closes.

| W8i same-pack sights and excluded hosts (A3) | W8h | none | AC94-AC98; the `attach_version == 3` pins re-pinned | `weapons/{__init__,compat,mounts,rules}.py` (edit), `weapon_rules.yaml` (edit), tests and fixtures `w8*` (edit) and `test_weapons_w8i_*` / `w8i_*` (new) | the lead's look at the iron-sight cards | S: ~250 lines |
| W8j baked optics and sights (A3 addendum 3, §4.6 item 8) | W8i | none | AC99-AC103; the `attach_version == 4` pins re-pinned | `weapons/{__init__,compat,mounts,rules,geometry,directory}.py` (edit), `weapon_rules.yaml` (edit), tests and fixtures `w8*` (edit) and `test_weapons_w8j_*` / `w8j_*` (new); the lead adds the data overrides | the lead's census sheets reconciled with the build | S: ~300 lines |
| W8k no pending sights on baked hosts (A3 addendum 3b, §4.6 item 9) | W8j | none | AC104; the `attach_version == 5` pins re-pinned | `weapons/{__init__,mounts,geometry}.py` (edit), tests and fixtures `w8*` (edit) and `test_weapons_w8k_*` / `w8k_*` (new) | the W8j pending counts | XS: ~60 lines |
| W8l measured defects (A3 addendum 4, §3.4 steps 1a and 3b, §4.2, §5.1) | W8k | none | AC105-AC110; the `attach_version == 6` pins re-pinned | `weapons/{__init__,attach,compat,mounts,rules,geometry}.py` (edit), `weapon_rules.yaml` (edit), tests and fixtures `w8*` (edit) and `test_weapons_w8l_*` / `w8l_*` (new); the lead then removes the five redundant forward overrides | the lead's look at the changed parts and lifted hosts, then the held-out cards | M: ~350 lines |
| W8m settle to contact (A3 addendum 5, §5.4) | W8l | none | AC111-AC116; AC108 retired; the `attach_version == 7` and `== 8` pins re-pinned | `weapons/{__init__,attach,compat,mounts,preview,rules,schema,export,geometry,directory,review}.py` (edit), `weapon_rules.yaml` (edit), tests and fixtures `w8*` (edit) and `test_weapons_w8m_*` / `w8m_*` (new) | the lead's look at every pair that moves more than 30 mm (the cards of §13.6), then the held-out cards | M: ~300 lines |

### 13.7 Addendum 6 (A3 addendum 6, W8n; APPROVED by the lead 2026-10-24, built on `integ/attach`)

Status: **approved and built.** The lead approved items a to e with the decisions below, then Tom answered the two open rows (no optics on launchers; flame throwers, flare guns and stun guns refuse every slot like the nail gun) and both are built switched on. Tom's three rules (2026-10-24) are the spine: (1) silencers cover the last bit of the barrel on rifles, hiding the built-in muzzle brake; (2) stop trying to put attachments on launchers; (3) a nail gun is a tool, not a firearm. Public-repo rule: classes are given by name token, never by host id.

**A6-1 Host class (item a).** `attachment_rules.attach_host_class` maps a class to host name tokens (the same tokenizer as `attach_host_never`: lower-case words and their joins); a host in no class is a `firearm`. Shipped classes: `launcher` (`launcher`, `rpg`, `rocket`, `missile`) and `tool` (`nailgun`, `nail`, `glue`, `paint`, `syringe`, `welder`, `water`, `watergun`, `waterpistol`, `flamethrower`, `flamer`, `flame`, `flaregun`, `stungun`), plus the existing `prop` of `attach_host_never`; there is no `special` class (flame throwers, flare guns and stun guns are tools). `attachment_rules.attach_class_never` maps class to refused slots: `launcher` -> `muzzle`, `optic`; `tool` -> every slot; `prop` -> every slot (via `attach_host_never`). A refused slot gets mount `none` / `slot_disabled` like `attach_host_never` (a union of the two; an id override still wins), so the slot veto removes every non-override candidate. **Unmeasured hosts:** a prefab-only host has no geometry and so no mounts, and the mount veto cannot see it; the compat step therefore also vetoes a pair whose host class refuses the slot (`_host_view` carries a `refused` set read from `excluded_slots`), so a launcher or tool that is not measured gets no pending pair for a refused slot either. Foregrips on a launcher stay (three labelled fits). Heavy guns stay firearms; the minigun muzzle is already unlisted by affinity.

**A6-2 Silencer seat (item b; Tom's rule 1).** A probe `muzzle` mount sits at the barrel tip, so a suppressor starts where the barrel ends and leaves a built-in brake, flash hider or shroud stub exposed behind it. For a part of kind `suppressor`, tier not `twin` or `override`, on a host whose muzzle mount `source` is `probe` and carries no `occupied_by` child, the placement moves the part back along the bore: `M[:3,3] -= d * up`, with the **device-covering variant** `d = min(stub, max(cover * L, dev_rear_near + device_cover_m), max_frac * L)`, where `L` is the part's length along the bore (`footprint.height_m`), `cover` = 0.4, `device_cover_m` = 5 mm, `max_frac` = 0.75 and `dev_rear_near` is the rear face of the nearest widened device within `device_reach_m` (0.080 m) of the tip. `device_reach_m` is a refinement made while building: a device whose rear face is further than 80 mm from the tip is a sight post, a gas block or a collar, not a brake, and a suppressor is not sleeved over it (15 pairs on 7 hosts keep a front sight or collar visible; this is the correct look). `stub` is measured on the host mesh (without any baked muzzle child) as a radial silhouette along the bore in 2 mm bins: the reference radius is the thinnest sustained radius (the minimum over 10-bin windows of the window median) in the last 150 mm; `stub` is the distance from the tip back to the first run of at least `run_min_bins` (3) bins wider than 1.4 times the reference, capped at 150 mm. Round to 1e-4; `d <= 0.003` -> no key. All constants live in `attachment_rules.muzzle_seat` (required keys, validated, digest treatment as `contact`). Authored `twin` and `override` placements are never moved. The set-back is stored as the optional entry key `seat_setback_m` (metres, positive toward the host, present only when non-zero); a consumer places the part with `translate(-seat_setback_m * mount.up)` after `T(mount) * T(anchor)^-1`. **Built:** 125 entries gain `seat_setback_m`. The rule applies to every firearm with a probe muzzle mount and has no per-archetype branch.

**A6-3 Magazine (item c).** (i) *Drum by measured shape:* a magazine part whose `footprint.length_m` and `footprint.width_m` are both at least `drum_min_m` (0.11 m) is classified `kind: drum` whatever its name, so the existing drum row of `attach_affinity` applies; this includes a plasma cell whose body measures as a drum (approved: Tom's call to include it). (ii) *Lower bound on the foot against the well:* a non-twin, non-override magazine entry whose `foot_length_m / mount.span_m` is below `attach_compat.fit_span_min` (0.75) is not listed. The loss of the one labelled cross-pack fit in the 0.60 to 0.75 band is accepted (the band holds 13 labelled no).

**A6-4 Settle cap and the placement fixes (item d).** *Cap:* `attachment_rules.contact.cap_m` = 0.030 (required key, `0 < cap_m <= clamp_m`): an optic or underbarrel entry whose `|seat_shift_m|` would exceed it is removed from `compatible_hosts` (not listed, not pending); twin and override entries are never keyed and never affected; over-cap entries are not listed anywhere. *Placement of the rest:* (a) one optic placed backwards on a sniper host: a `forward` override on the scope part (`weapon_overrides.json`, categorical), which also flips the part's authored twin on the sibling host, because a `forward` override is per part, not per pair; the twin now renders reversed on its sibling host (a known cost, one pair, for the lead to keep or revert); (b) the rear sight on one submachine gun sits on the tooth crests of the receiver: a per-host tolerance in `sight_probe.receiver_tol_by_host` (a table, not an override, because overrides are categorical and carry no coordinates, INV-17), applied to four pairs and to no other host; (c) one red dot placed wrong on a submachine gun host: not fixable per pair (its `child_node` seat is the position of the host's own baked scope), left as is and listed.

**A6-5 Removals (item e).** Iron sights on one military sniper host are removed by a per-host mount override (`mounts` for `sight_front` and `sight_rear` -> source `none`), **not** by a `sniper` affinity rule (4 of 4 labelled pairs no, no labelled yes against it). Two per-pair removals through `compatible.remove`: one bipod on a machine gun host, and one silencer on a revolver host of a battle-royale pack. The data file `weapon_overrides.json` now carries four id entries (one forward, one mounts override, two `compatible.remove`).

**A6-6 Further rulings of 2026-10-24 (Tom; W8n build, same version bump).** (i) *Minigun:* "minigun doesn't take any attachments": a `fixed_heavy` host class (`attach_host_class.fixed_heavy` = `minigun`, a whole word, so `ChainGun` is not one) with `attach_class_never.fixed_heavy` = every slot; a minigun is not a tool, so it has its own class. (ii) *Presets:* "presets only refuse the slots their built-in parts already fill; other slots stay open": `attachment_rules.attach_filled_hosts` (shipped `[preset]`, host name tokens) makes such a host refuse (`none` / `slot_disabled`, an `override` mount is never touched) each slot one of its own measured baked children fills, i.e. a slot whose mount lists a child in `occupied_by` (magazine, muzzle device, foregrip, laser, sided iron sight) and `optic` when the host carries an optic body or glass child; no preset is listed by hand, a slot no child fills stays open, and a preset's authored magazine twin goes with its magazine seat. A prefab-only (unmeasured) preset has no measured children, so the rule has nothing to read there. (iii) *Per-id overrides* (`weapon_overrides.json`, the mechanism of A6-5): `POLYGON_BattleRoyale/SM_Wep_Sniper_Heavy_01` muzzle `none` ("takes no barrel attachments", read as the muzzle slot; its underbarrel and laser seats are left for Tom to confirm), and `POLYGON_Military/SM_Wep_Preset_A_Sniper_01` every slot `none` ("built in scope and silencer so no attachments needed"; Tom named this gun, so the override stays beside the generic preset rule).

**Built impact (the directory of `integ/attach` before and after; 4409 -> 3888 entries).** 521 entries removed and none added: 44 compatible and 16 pending `same_pack_fit`, 199 compatible and 262 pending `cross_pack_fit`; by slot: magazine 281, optic 181, muzzle 23, sight_rear 14, laser_light 13, sight_front 7, underbarrel 2. **Twin and override entries touched: 0.** Default view (compatible `twin` + `same_pack_fit`): 363 entries before, 319 after. 168 optic and underbarrel entries carry `seat_shift_m` (the cap removed those over 30 mm). Hosts that now refuse a slot: 20 hosts moved to refusing every slot (the tool class, 7 of them the flame throwers, flare gun and stun guns that Tom moved); 19 launcher-class hosts refuse `muzzle` and 18 of them also newly refuse `optic` (one already did).
- **Versions.** `WEAPON_ATTACH_VERSION` 9 -> 10 (11 with A6-6); `WEAPON_GEOMETRY_VERSION` stays 5; `rules_digest` stays `7b9829af37328fe7`; `attach_rules_digest` moves (the new class tables, `muzzle_seat`, `contact.cap_m`, `fit_span_min`, `drum_min_m`, `receiver_tol_by_host`).
- **Default export (AC77).** Everything in the default export is unchanged except `generated_from.overrides_digest` (`6db471a639e057a5` -> `274f57d07cbbf47b`), which moves because the committed override file gained entries. The new sha1 is `cd2f0ab6737f2f10d60cc8107b9d39e6fa95fbc0` (was `ec22a4334f720fdf2092a2a7a58f6eb3438c8be4`). The authored-twin identity check holds the same way: only `overrides_digest` moves.
- **Contact check.** Re-run on the built directory with the independent gap and penetration method: the counts stay 0 and 0 (see the build report).
- **Held-out re-score (diagnostic only; the set is spent).** With A6-1 to A6-5 applied as predicates, the 60 pairs gave TP 20, FP 0, FN 11 on the default view, unweighted precision 1.00 and recall 0.645. Recall is not touched by this addendum, so the recall bound of AC80(c) is expected to still fail by that diagnostic. **AC80(c) draw #2** (60 fresh pairs, new seed, every labelled pair excluded, stratified as before) is drawn and rendered and is waiting for Tom's labels; it is scored in two views, default (gated) and with `cross_pack_fit` included.

**Per-pair items left for Tom or the lead.** The forward flip also reverses an authored twin on a sibling host (keep or revert); the SMG rear sight is a table row, not an override; one red dot on an SMG host remains placed wrong (no rule, no per-pair fix); 15 silencer pairs on 7 hosts keep a front sight or collar visible by design (`device_reach_m`).

### 13.6 W8m impact record (A3 addendum 5; what moves, and why)

- **Does not move:** `rules_digest` (`7b9829af37328fe7`), `WEAPON_GEOMETRY_VERSION` (5), the default export byte for byte, the `w8d_w7_*` references, every anchor and footprint, every host's slot availability, every candidate list except the briefcase's, every twin and override pair.
- **Moves, with the reason:** `attach_version` 7 to 8 (item 0, shipped) and 8 to 9; `attach_rules_digest` (the `contact` table, no `optic_seat`, the `prop` token); the `optic` mounts the A4 lift changed return to the child's own point (25 mounts); 201 of the 215 non-twin optic and underbarrel pairs gain `seat_shift_m` (the dry run's 105 kept the lifted seat; without the lift most baked-scope seats start sunk, so most pairs carry a key); 24 of them shift more than 30 mm, on five hosts whose seat is 4 to 6 cm off; nine `SM_Prop_*` hosts (the briefcase, two syringe guns, a staple gun, a spray gun, two missile launchers, the Prototype pistol and rifle) lose every slot to the `prop` token of item 0, and 59 pending lists and 4 compatible lists shrink by one host.
- **Does not fix (stated so nobody expects it):** the nine authored twin defects of §5.4; a part that lands on the wrong feature of the host (a thin sight post, one small tab); the seats of the five hosts above (corrected per pair, not at the seat).
- **Cards.** Every pair that moves more than 30 mm is reviewed by eye: one card per host of those five (the worst-looking pair of each), judged by Tom as `Fits, but placed wrong` or not; cards v3 final is 29 cards (22 + 2 genre + 5).
- **Moves in the tests, deliberately:** the literals that pin `attach_version == 7` or `== 8`; the AC108 lift tests (removed); the tests that pin a lifted optic seat.

### 13.5 W8l impact record (A3 addendum 4; what moves, and why)

- **Does not move:** `rules_digest` (`7b9829af37328fe7`), `WEAPON_GEOMETRY_VERSION` (5), the default export byte for byte, the `w8d_w7_*` references, every host's `optic` availability, every sight list.
- **Moves, with the reason:** `attach_version` 6 to 7 and `attach_rules_digest` (new `anchor`, `family_free_slots` and `optic_seat` tables); the forward of the magazines and bipods whose free end disagrees with the section sign; the footprint and `point` of the two lip parts; `muzzle` and `underbarrel` candidate lists; 25 `child_node` optic mounts (lifted 5 to 26 mm); two bipod mounts (centred); the review reason `mount_missing` on 31 hosts.
- **Does not fix (stated so nobody expects it):** the eight magazine false positives of the 90 labels on `Preset_A` and `Preset_B` hosts (`A_Mag_05`, `A_Mag_06`, `A_Mag_07`, `A_Mag_08`, `B_Mag_03` on rifle, SMG and sniper presets): they pass `family_overlap` and `affinity` and the span test does not stop them (it only vetoes an oversize foot against a `probe` span; an undersize foot, a wide foot and a foot against a `child_foot` span all pass), and no item here touches them; the silencers on sniper and hunting rifles (a `bore_mismatch` signal is present on two of the four and is not a veto, §5.1); the `Scope_Unique_01` on `Heavy_01` twin (label NOT). A re-score of the 90 labels with items 1 to 5 in place is reported but never counts: the items were found on those labels.
- **Item 7, a `bore_mismatch` veto for same-pack muzzle devices: measured, not adopted.** The ask was a veto when a same-pack muzzle part's `mate_d_m` is more than 35 % off a ring-measured host bore, neutral when either side has no bore. Coverage on the W8k directory: 13 of 13 muzzle parts carry `mate_d_m` (21.3 to 60.4 mm); of 257 hosts with mounts, 196 have a `ring` bore, 57 a `face_extent` bore (not trusted, neutral) and 3 no bore (neutral). With the family exemption of item 2 in place the veto would remove 138 of the 212 same-pack muzzle listings (muzzle listed 264 to 126); `twin` and `override` entries are exempt and cross-pack entries already need `bore != bad`. The comparison is not a physical fit test: `mate_d_m` is the outer diameter of the device's mating end and `bore_d_m` the barrel ring, and a suppressor is wider than the barrel it covers (ring bores have a median of 16 to 21 mm on rifles, SMGs and snipers, silencer mates 21 to 60 mm). The game's own authored silencers show it without any label: two of the three `twin` muzzle entries (`Silencer_01` on `SubMGun_02` and `SubMGun_03`, 36.4 mm on a 15.7 mm ring) carry `bore_mismatch`, so the rule would refuse the pair the pack itself authors if the twin tier did not exempt it. On the 17 labelled muzzle pairs (a check, not a tuning input) it removes both silencer false positives (`c107`, `c108`) and five true fits (`c106`, `c110`, `c111`, `c113`, `c141`). A veto needs a quantity that compares like with like (the mating end against the host's own authored silencer, or the device's inner diameter), which the measurement does not yet produce; until then `bore_mismatch` stays a signal that lowers the score by 0.1, as in §5.1.
- **Held-out check (AC80(c)): RECORDED, FAIL (2026-10-24, W8m directory `8ac2e01`, 60 pairs drawn by a recorded seed from the post-W8l directory, the 90 tuning labels and the 29 round-3 cards excluded, all 60 labelled by Tom).** Weighting: the draw is stratified by tier x slot (quota twin 8, same_pack_fit 18, cross_pack_fit 14, unlisted 20); each stratum's weight is its population in the directory divided by its sample size, and intervals are a stratified bootstrap (4000 resamples, seed 20261024) for the weighted figures and Wilson for the unweighted ones. Predicted positive = a listed entry of tier up to `same_pack_fit` (the gated set).
  - **Result.** Unweighted: TP 20, FP 6, FN 11, TN 23; precision 0.769 (Wilson 0.579 to 0.890), recall 0.645 (0.469 to 0.789). Stratified-weighted: precision 0.764 (0.534 to 0.919), recall 0.383 (0.256 to 0.595). The gate is precision >= 0.90 and recall >= 0.80: **it fails on precision and on recall, whichever weighting is read.** The weighted recall is low because most of the true positives of the population sit in `cross_pack_fit` and `unlisted`, which the default view does not list.
  - **By tier (gated set).** `twin`: 8 of 8, precision 1.00. `same_pack_fit`: 12 TP, 6 FP, precision 0.667 (all six false positives are in this tier). `cross_pack_fit`: 8 of 8 positives fall below the default view (recall 0 there by construction; cross-pack included, recall rises to 0.903 unweighted, 0.846 weighted, and precision falls to 0.700 unweighted, 0.508 weighted [0.295 to 0.734], reported, ungated). `unlisted`: 3 positives missed (optic), 17 true negatives.
  - **By slot (gated set, unweighted).** magazine: precision 0.545, recall 0.857 (5 FP); muzzle: 0.875 and 0.778 (1 FP, 2 FN); optic: 1.000 and 0.583 (0 FP, 5 FN); underbarrel: no listed entry, 3 of 3 positives missed (all three are foregrips on a launcher host).
  - **False positives (6).** Magazine x 5 (three of one drum-like part on three presets, one standard part on a sniper preset, one cylindrical part on a rifle preset; every one has a foot much shorter than the well); muzzle x 1 (a silencer on a nail gun).
  - **False negatives (11).** Cross-pack: optics x 2 (one placed on the wrong spot), foregrips x 3 (launcher host), muzzle x 2, magazine x 1. Unlisted: optic x 3 (scopes on sniper hosts).
  - **Consequence.** The draw is spent: nothing tuned to it counts as evidence; a fresh draw (#2) scores the next fix. Addendum 6 (§13.7) is the response; its diagnostic re-score of these 60 pairs is reported there and never counts.
- **Moves in the tests, deliberately:** the literals that pin `attach_version == 6`; the tests that pin the old forward of a banana magazine or a bipod, the old `foot_length_m` of a lipped part, `family_overlap` as required for a muzzle or underbarrel, or the larger-volume seat of a mirrored pair.

### 13.4 W8k impact record (A3 addendum 3b; what moves, and why)

- **Does not move:** `rules_digest` (`7b9829af37328fe7`), `WEAPON_GEOMETRY_VERSION` (5), the default export byte for byte, the `w8d_w7_*` references, every `compatible_hosts` list, the `optic` counts.
- **Moves, with the reason:** `attach_version` 5 to 6; `pending_hosts` of `sight_front` and `sight_rear` (baked hosts lose them); the sight mount reasons of baked hosts the probe could not seat (`probe_unavailable` to `slot_disabled`), hence the review page's disabled-slot rows and the directory's `mount_reasons`.
- **Moves in the tests, deliberately:** the literals that pin `attach_version == 5`, and any W8j fixture that expected `probe_unavailable` on a baked host.

### 13.3 W8j impact record (A3 addendum 3; what moves, and why)

- **Does not move:** `rules_digest` (`7b9829af37328fe7`), `WEAPON_GEOMETRY_VERSION` (5), the default export byte for byte, the three `w8d_w7_*` references, `muzzle_golden.json`, `mount_place.json`.
- **Moves, with the reason:** `attach_version` 4 to 5 (candidate lists and the mounts of hosts with a baked optic or sight change); `attach_rules_digest` (new `baked_sights` keys and the `optic` row of `attach_host_never`); the geometry mounts cache key; the directory header; every `--attachments` export (the iron sights lose every listed host: 48 entries to the count AC103 reports; the glass-only hosts lose their optic seat; the nine toy and water hosts lose optic and sights).
- **Moves in the tests, deliberately:** the literals that pin `attach_version == 4` and any W8i test that counts sight candidates or probe seats on a host that item 8 now refuses.

### 13.2 W8i impact record (A3; what moves, and why)

- **Does not move:** `rules_digest` (`7b9829af37328fe7`), `WEAPON_GEOMETRY_VERSION` (5), the default export byte for byte, the three `w8d_w7_*` references, `muzzle_golden.json`, `mount_place.json`.
- **Moves, with the reason:** `attach_version` 3 to 4 (candidate lists and the mounts of excluded hosts change); `attach_rules_digest` (`3b22c1c1ecee3324` to a new value: `attach_host_never`); the directory header; every `--attachments` export (sight parts gain `same_pack_fit` entries, the excluded hosts lose their sight seats, and the hosts with a baked sight child lose the matching seat: live, `Rifle_Assault_01` both and `American_MachineGun_01` the rear).
- **Moves in the tests, deliberately:** the literals that pin `attach_version == 3` (W8h's `w8h_versions` and the w8a/w8b cache and identity tests), and any count of candidates or `probe` seats that the two excluded live-shaped fixtures change.

### 13.1 W8h impact record (what moves, and why)

Written before the build so that no digest is re-blessed silently.

- **Does not move:** `rules_digest` (`7b9829af37328fe7`; the new tables are inside `attachment_rules`, which it excludes); `WEAPON_GEOMETRY_VERSION` (5); the default (`whole`-only) export, byte for byte, because it
  carries neither `geometry.mounts` nor `attachment` (live check: sha1 `f5e64427fa186890d2306745502cef6d754ebe4a`, 165 records); the three W7 reference files `w8d_w7_directory.json.gz`,
  `w8d_w7_attach_default_export.json` and `w8d_w7_attach_roles_all_export.json` (generated by the untouched W7 tree with `w8d_gen_reference.py`: they are references, and
  regenerating them from this code would defeat the test); `muzzle_golden.json`, `mount_place.json`.
- **Moves, with the reason:** `attach_version` 2 to 3 (slots, kinds, classification, mounts and candidate lists change; it joins the cache keys, so every attachment part and eligible host is re-measured);
  `attach_rules_digest` (`db9f4a2b405729c9` to a new value: the iron rows, the sight child tokens, the `optic.iron` affinity row, `attach_genre_by_pack`, `sight_probe`); the directory header (both);
  every `--attachments` export (each eligible host gains two `mounts` keys, iron-sight parts change slot, `pair` appears, cross-setting entries leave `compatible_hosts` and `pending_hosts`, optic entries may gain `hides_slots`).
- **Moves in the tests, deliberately:** the three literals that pin `attach_version == 2` (`w8a_classify`, `w8d_regression`, `w8d_export`) and AC86's "is 2"; the slot-list assertions (`w8b_*`, `w8d_export`, which require exactly five mount keys); the `w8a_attach.py` iron fixtures
  (`(optic, iron)` becomes the AC87 rows, so the fixture's attachment counts of 35 and 54 weapons move by the parts that become `sight_side_unsure`); the `w8c_overrides` cases that set `attachment_kind: iron` under `optic`;
  AC72's cross-pack case (the fixture rules must list both fixture packs under one setting); and the allowed-difference sets of `w8d_regression` (AC82/INV-19 gain `sight_side_unsure`).
- **Live counts to report at W10, not gated:** setting gate on the 2026-10-23 catalog: 3,266 of 4,059 `cross_pack_fit` candidates and 8 of 46 `twin` candidates are cross-setting; the 8 twins are
  Apocalypse Scope_01, 06 and 07 on three BattleRoyale guns, Military Scope_04 on Apocalypse SniperRifle_02, and Military and SciFi City Silencer_02 on Apocalypse SubMGun_02 and 03.
  A twin is placement ground truth (D-7), so AC80(a)'s twin count of 11 on BONDED's packs may fall; it is reported, not investigated as a failure.

## 14. Changes to the directory spec (applied in the same commit as PATCH notes)

DS§4.1 gains the `attachment` block and `geometry.mounts`; DS§4.5 gains the `compatible`, `mounts` and part-side `forward`
keys; DS§4.6 gains the new enumerations; DS§3.10 gains the export flags; DS§3.9 gains the Attachments section; DS§10 gains
C-18 to C-27 by reference; DS§11 points to §13. Nothing existing changes meaning. A1 adds one enum value (`forward_source` `twin`), one optional mount key
(`seats`) and narrows `replaces` of a twin entry to its matched child; readers that ignore unknown keys and unknown enum values are unaffected (C-25), and the
default export stays byte-identical to W7 (INV-19), because none of this reaches it. A2 adds two enum values to `ATTACH_SLOTS` (`sight_front`, `sight_rear`), one to `REASONS`
(`sight_side_unsure`), removes the kind `iron` from `optic`, adds the optional key `attachment.pair`, the optional entry key `hides_slots` and the optional override key `pair`; the same reading rule
(C-25, ignore what you do not know) covers all of them, and the default export is again untouched.
