// Attachment placement preview harness (docs/weapon_attachments.md 6.2, weapons/preview.py).
//
//   await window.previewPrepare({host, part, itemBasis, camDir}) -> view-space bounds of the host plus its placed attachment
//   await window.iconRender({frustum, size})                     -> premultiplied RGBA pixels (icon.js, unchanged)
//
// One scene, two GLBs. The host is drawn in its own asset space (glb_scale applied about the GLB origin, collision geometry
// and the baked child the attachment replaces left out). The attachment is drawn in the same space through the placement
// transform Python computed, `T(mount) * T(anchor)^-1` (spec 3.1), applied AFTER the attachment's own glb_scale, because the
// anchor and mount points are metres in scaled GLB scene space. Both sit under the host's item_basis, so the picture is posed
// like the host's icon. This file only loads, places and draws: Python owns the maths (attach.place) and the framing
// (icons.fit_frustum), and checks both without a browser.
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";
import { THREE, loader, collectMeshes, disposeCurrent, adopt, aimRig, viewBounds } from "/harness/icon.js";

window.__PREVIEW__ = { ready: false };

async function load(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`);
  const buffer = await res.arrayBuffer();
  return new Promise((ok, bad) => loader.parse(buffer, "", ok, bad));
}

// Keep the selected meshes (all of them when `nodes` is null) without the `hide` subtrees; everything else is invisible,
// exactly as iconPrepare does, so the bounds and the picture agree.
function select(gltf, nodes, hide, label) {
  const wanted = nodes === null || nodes === undefined ? null : new Set(nodes);
  const kept = collectMeshes(gltf.scene, wanted, hide && hide.length ? new Set(hide) : null);
  if (!kept.length) throw new Error(`${label}: no meshes selected (glb_node not found, only collision geometry, or all hidden)`);
  const keptSet = new Set(kept);
  gltf.scene.traverse((o) => {
    if (o.isMesh && !keptSet.has(o)) o.visible = false;
  });
  return kept;
}

// The placed attachment is drawn in one flat colour (hex string, e.g. "e8742a"), so it reads against the host whatever the
// host's own materials are. The host keeps its own look. Only the kept (visible) meshes are touched.
function tint(meshes, hex) {
  const color = new THREE.Color(parseInt(hex, 16));
  for (const mesh of meshes) {
    // GLTFLoader shades a mesh without normals flat; a replacement material must do the same or it renders black
    const flat = !(mesh.geometry && mesh.geometry.attributes && mesh.geometry.attributes.normal);
    mesh.material = new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0, flatShading: flat });
  }
}

// The host is drawn opaque (W8e): a translucent host (a glTF BLEND material, e.g. the Military preset rifles) shows the placed
// attachment and ghosting along its body through it, and Tom judges placements by eye. Every drawn host material gets
// transparent = false, opacity = 1, depthWrite = true. An alphaTest material (glTF MASK) is a genuine cut-out (grille, glass
// frame) and keeps cutting out, so it is left alone. The GLB was parsed for this call only and nothing else holds its
// materials, so they are changed in place; icon.js (shared with `weapons icons`) is untouched.
function opaque(meshes) {
  const seen = new Set();
  for (const mesh of meshes) {
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    for (const mat of mats) {
      if (!mat || seen.has(mat)) continue;
      seen.add(mat);
      if (mat.alphaTest > 0) continue;
      mat.transparent = false;
      mat.opacity = 1;
      mat.depthWrite = true;
      mat.needsUpdate = true;
    }
  }
}

function scaled(s) {
  return new THREE.Matrix4().makeScale(s, s, s);
}

window.previewPrepare = async function previewPrepare(p) {
  disposeCurrent();
  if (MeshoptDecoder && MeshoptDecoder.ready) await MeshoptDecoder.ready;
  const hostGltf = await load(p.host.glb);
  const partGltf = await load(p.part.glb);
  const hostKept = select(hostGltf, p.host.nodes, p.host.hide, "host");
  const partKept = select(partGltf, p.part.nodes, null, "attachment");
  opaque(hostKept);
  if (p.part.tint) tint(partKept, p.part.tint);

  // item_basis rows are the item-frame axes expressed in asset space: item = B * asset (as in icon.js)
  const b = p.itemBasis;
  const holder = new THREE.Group();
  holder.matrixAutoUpdate = false;
  holder.matrix.set(b[0][0], b[0][1], b[0][2], 0, b[1][0], b[1][1], b[1][2], 0, b[2][0], b[2][1], b[2][2], 0, 0, 0, 0, 1);

  const hostGroup = new THREE.Group();
  hostGroup.matrixAutoUpdate = false;
  hostGroup.matrix.copy(scaled(p.host.scale));
  hostGroup.add(hostGltf.scene);

  // p.part.matrix is the row-major 4x4 of attach.place(anchor, mount): attachment-scaled space -> host-scaled space
  const m = p.part.matrix;
  const partGroup = new THREE.Group();
  partGroup.matrixAutoUpdate = false;
  partGroup.matrix.set(
    m[0][0], m[0][1], m[0][2], m[0][3],
    m[1][0], m[1][1], m[1][2], m[1][3],
    m[2][0], m[2][1], m[2][2], m[2][3],
    m[3][0], m[3][1], m[3][2], m[3][3],
  );
  partGroup.matrix.multiply(scaled(p.part.scale));
  partGroup.add(partGltf.scene);

  holder.add(hostGroup, partGroup);
  adopt(holder);
  aimRig(new THREE.Vector3(...p.camDir).normalize());
  return viewBounds([...hostKept, ...partKept]);
};

window.__PREVIEW__.ready = true;
