// Weapon icon harness (docs/weapon_directory.md section 3.8, option B). One page renders a whole batch:
//
//   await window.iconPrepare({glb, nodes, scale, itemBasis, camDir})  -> view-space bounds of the selected meshes
//   await window.iconRender({frustum, size})                          -> premultiplied RGBA pixels (base64)
//
// The split is deliberate: Python owns the framing math (icons.fit_frustum, unit-tested without a browser). This
// file only loads, orients, lights and draws. The page never fits anything itself.
//
// Frame: the model is rotated into the *item frame* with item_basis (forward -> +Z, up -> +Y, right-handed), so every
// icon is posed the same way and the camera/light rig is a fixed function of camDir. Transparent background
// (alpha:true, clear alpha 0), no grid, gizmo or HUD. Lighting and tone mapping follow the synty-glb QA harness.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";

// Mirror of naming.SKIP_STEM_RE: collision hulls / LODs are never drawn and never framed (the geometry module
// drops the same nodes, so the icon shows what was measured).
const SKIP_NODE = /(?:_Convex|_Col(?:lider)?|_Collision|_LOD[1-9]|_ColMesh)$/i;

// synty-glb qa/harness.js rig, authored for its "quarter" camera. Re-expressed relative to our camera below.
const QUARTER_DIR = new THREE.Vector3(0.7, 0.45, 0.75).normalize();
const KEY_POS = new THREE.Vector3(6, 10, 4);
const FILL_POS = new THREE.Vector3(-6, 2, -4);

window.__ICON__ = { ready: false, error: null };

const canvas = document.getElementById("view");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.setClearColor(0x000000, 0);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;

const scene = new THREE.Scene();
scene.background = null; // transparent

const hemi = new THREE.HemisphereLight(0xe8f0ff, 0x3a342c, 1.6);
const key = new THREE.DirectionalLight(0xffffff, 2.1);
const fill = new THREE.DirectionalLight(0x88aacc, 0.45);
scene.add(hemi, key, fill);
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, -100, 100);
const loader = new GLTFLoader();
if (MeshoptDecoder) loader.setMeshoptDecoder(MeshoptDecoder);

let current = null; // {holder, kept}

function lookRotation(dir) {
  // Rotation of a camera that sits along `dir` looking at the origin with +Y up.
  const m = new THREE.Matrix4().lookAt(dir, new THREE.Vector3(), new THREE.Vector3(0, 1, 0));
  return new THREE.Matrix4().extractRotation(m);
}

function nodeName(obj) {
  // GLTFLoader sanitises names (spaces -> underscores); the original is kept in userData.name.
  return (obj.userData && obj.userData.name) || obj.name || "";
}

function collectMeshes(root, wanted) {
  const kept = [];
  const walk = (obj, active) => {
    if (obj !== root && SKIP_NODE.test(nodeName(obj))) return; // the whole subtree is dropped
    const on = active || wanted === null || wanted.has(nodeName(obj));
    if (on && obj.isMesh) kept.push(obj);
    for (const child of obj.children) walk(child, on);
  };
  walk(root, false);
  return kept;
}

function disposeCurrent() {
  if (!current) return;
  scene.remove(current.holder);
  current.holder.traverse((o) => {
    if (o.geometry) o.geometry.dispose();
    const mats = o.material ? (Array.isArray(o.material) ? o.material : [o.material]) : [];
    for (const m of mats) {
      for (const v of Object.values(m)) if (v && v.isTexture) v.dispose();
      m.dispose();
    }
    if (o.skeleton) o.skeleton.dispose();
  });
  current = null;
}

window.iconPrepare = async function iconPrepare(p) {
  disposeCurrent();
  if (MeshoptDecoder && MeshoptDecoder.ready) await MeshoptDecoder.ready;
  const res = await fetch(p.glb);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${p.glb}`);
  const buffer = await res.arrayBuffer();
  const gltf = await new Promise((ok, bad) => loader.parse(buffer, "", ok, bad));
  const wanted = p.nodes === null || p.nodes === undefined ? null : new Set(p.nodes);
  const kept = collectMeshes(gltf.scene, wanted);
  if (!kept.length) throw new Error("no meshes selected (glb_node not found or only collision geometry)");
  const keptSet = new Set(kept);
  gltf.scene.traverse((o) => {
    if (o.isMesh && !keptSet.has(o)) o.visible = false;
  });

  // item_basis rows are the item-frame x, y, z axes expressed in asset space: item = B * asset. glb_scale is the
  // asset's size correction, applied about the GLB origin like load_triangles does.
  const b = p.itemBasis;
  const holder = new THREE.Group();
  holder.matrixAutoUpdate = false;
  holder.matrix
    .set(b[0][0], b[0][1], b[0][2], 0, b[1][0], b[1][1], b[1][2], 0, b[2][0], b[2][1], b[2][2], 0, 0, 0, 0, 1)
    .multiply(new THREE.Matrix4().makeScale(p.scale, p.scale, p.scale));
  holder.add(gltf.scene);
  scene.add(holder);
  current = { holder };

  // Camera at the origin looking along -camDir (camDir points from the model towards the camera). Only its
  // orientation matters for an orthographic fit; the frustum offsets Python sends are relative to this pose.
  const dir = new THREE.Vector3(...p.camDir).normalize();
  camera.position.set(0, 0, 0);
  camera.up.set(0, 1, 0);
  camera.lookAt(dir.clone().negate());
  camera.updateMatrixWorld(true);

  // The synty rig, rotated by the same rotation that takes its quarter camera to ours.
  const q = lookRotation(dir).multiply(lookRotation(QUARTER_DIR).transpose());
  key.position.copy(KEY_POS).applyMatrix4(q);
  fill.position.copy(FILL_POS).applyMatrix4(q);

  scene.updateMatrixWorld(true);
  const view = camera.matrixWorldInverse;
  const lo = [Infinity, Infinity, Infinity];
  const hi = [-Infinity, -Infinity, -Infinity];
  const v = new THREE.Vector3();
  const m = new THREE.Matrix4();
  let vertices = 0;
  for (const mesh of kept) {
    if (mesh.isSkinnedMesh && mesh.skeleton) mesh.skeleton.update();
    m.multiplyMatrices(view, mesh.matrixWorld);
    const n = mesh.geometry.attributes.position.count;
    for (let i = 0; i < n; i++) {
      mesh.getVertexPosition(i, v); // skinned meshes: the bind pose
      v.applyMatrix4(m);
      if (v.x < lo[0]) lo[0] = v.x;
      if (v.y < lo[1]) lo[1] = v.y;
      if (v.z < lo[2]) lo[2] = v.z;
      if (v.x > hi[0]) hi[0] = v.x;
      if (v.y > hi[1]) hi[1] = v.y;
      if (v.z > hi[2]) hi[2] = v.z;
    }
    vertices += n;
  }
  return { min: lo, max: hi, meshes: kept.length, vertices };
};

window.iconRender = async function iconRender(p) {
  if (!current) throw new Error("iconRender before iconPrepare");
  const f = p.frustum;
  camera.left = f.left;
  camera.right = f.right;
  camera.top = f.top;
  camera.bottom = f.bottom;
  camera.near = f.near;
  camera.far = f.far;
  camera.updateProjectionMatrix();
  renderer.setSize(p.size, p.size, false);
  renderer.render(scene, camera);
  const gl = renderer.getContext();
  const buf = new Uint8Array(p.size * p.size * 4);
  gl.readPixels(0, 0, p.size, p.size, gl.RGBA, gl.UNSIGNED_BYTE, buf); // premultiplied, bottom row first
  let bin = "";
  for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
  return { width: p.size, height: p.size, pixels: btoa(bin) };
};

window.__ICON__.ready = true;
