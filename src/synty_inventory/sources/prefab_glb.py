"""Resolve a prefab with no same-named GLB to its base mesh's GLB (+ nodes).

enrich wires ``files.glb`` by asset id == GLB stem. A prefab whose mesh lives
in a differently named FBX gets nothing: ``SM_Chr_Biker_01.prefab`` shows the
``Character_Biker`` mesh of the shared ``Character.fbx``; a modular hero preset
shows five meshes of ``ModularCharacters.fbx``; a prop prefab can wrap
``SM_Prop_X_Base.fbx``. The prefab itself says which meshes it shows, so this
reads Unity's own references instead of guessing from names:

    active renderer rows (mech.parse_prefab) -> mesh GUID -> FBX file
    (mech.read_guid_fbx_map) -> FBX stem -> converted GLB (glb_index)
    -> the renderers' GameObject names, which are the GLB node names.

The GameObject name, not the mesh fileID, carries the node: newer Unity
imports leave ``internalIDToNameTable`` empty and the fileIDs are hashes.

Only the unambiguous case resolves: every active renderer from ONE FBX whose
GLB holds all of their names as mesh nodes. Out of scope (left unresolved,
counted by the caller): nested prefabs / prefab variants (no renderer rows of
their own), assemblies from several FBX (their parts sit at prefab-local
transforms the GLBs do not carry), meshes from another pack's FBX.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .glb_measure import bundle_node_names
from .mech import parse_prefab, read_guid_fbx_map

GlbSel = tuple[str, str | list[str] | None]


def resolve_prefab_glb(
    prefab: Path,
    guid_fbx: dict[str, str],
    glb_exact: dict[str, str],
    glb_ci: dict[str, str],
    mesh_nodes: Callable[[str], list[str]],
) -> GlbSel | None:
    """``(glb_rel, glb_node)`` for ``prefab``, or None when unresolvable.

    ``glb_node`` is None when the whole GLB is the asset (a single-mesh FBX,
    or every mesh node of it is shown), one name, or a sorted list of names.
    ``mesh_nodes(glb_rel)`` returns the GLB's mesh-bearing node names.
    """
    rows = [r for r in parse_prefab(prefab) if r["active"]]
    if not rows:
        return None
    fbx = {guid_fbx.get(r["mesh_guid"]) for r in rows}
    if len(fbx) != 1 or None in fbx:
        return None
    stem = Path(next(iter(fbx))).stem
    glb_rel = glb_exact.get(stem) or glb_ci.get(stem.lower())
    if not glb_rel:
        return None
    nodes = set(mesh_nodes(glb_rel))
    if len(nodes) <= 1:
        return glb_rel, None
    names = sorted({r["node"] for r in rows})
    if not set(names) <= nodes:
        return None
    if set(names) == nodes:
        return glb_rel, None
    return glb_rel, names[0] if len(names) == 1 else names


class PrefabGlbResolver:
    """Per-pack resolver; the GUID map and GLB node lists are built lazily,
    so a pack with no unmatched prefabs never walks its ``.meta`` files."""

    def __init__(
        self,
        extracted_root: Path | None,
        threejs_v2: Path | None,
        glb_exact: dict[str, str],
        glb_ci: dict[str, str],
    ) -> None:
        self._root = extracted_root
        self._tj = threejs_v2
        self._exact = glb_exact
        self._ci = glb_ci
        self._guid_fbx: dict[str, str] | None = None
        self._nodes: dict[str, list[str]] = {}

    def _mesh_nodes(self, glb_rel: str) -> list[str]:
        if glb_rel not in self._nodes:
            self._nodes[glb_rel] = bundle_node_names(self._tj / glb_rel) if self._tj else []
        return self._nodes[glb_rel]

    def resolve(self, asset: dict) -> GlbSel | None:
        prefab = (asset.get("paths") or {}).get("prefab")
        if not prefab or self._root is None or self._tj is None or not self._exact:
            return None
        path = self._root / prefab
        if not path.is_file():
            return None
        if self._guid_fbx is None:
            self._guid_fbx = read_guid_fbx_map(self._root)
        return resolve_prefab_glb(path, self._guid_fbx, self._exact, self._ci, self._mesh_nodes)
