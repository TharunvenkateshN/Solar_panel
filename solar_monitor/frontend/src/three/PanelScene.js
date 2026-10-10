// Realistic 3D solar-panel rig driven by the simulation state (tilt angle, dust, shade, cleaning sweep,
// thermal grid). Pure three.js, no React. Everything shown is SIMULATED - it mirrors the backend's world state.
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

const DEG = Math.PI / 180
const PW = 1.7, PD = 1.0            // panel width (x) and depth (z), metres
const GW = PW - 0.09, GD = PD - 0.09 // glass / cell area
const PIVOT_Y = 1.3                 // height of the tilt axis above ground
const TUBE_DROP = 0.11              // torque tube sits this far under the panel centre
const DOCK_X = -GW / 2 + 0.02       // parked position of the cleaning robot (on the left end of the glass)

const VIEWS = {
  perspective: { pos: [2.0, 1.9, 2.7], target: [0, 1.1, 0] },
  side: { pos: [0, 1.25, 3.9], target: [0, 1.22, 0] },
  top: { pos: [0, 3.7, 0.7], target: [0, 1.2, 0] },
}

// ---------- procedural textures -------------------------------------------------------------------------
function canvas(w, h) { const c = document.createElement('canvas'); c.width = w; c.height = h; return c }
function rng(seed) { let s = seed >>> 0; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296 } }

function valueNoise(size, octaves, seed) {
  const rand = rng(seed)
  const grids = octaves.map((n) => ({ n, v: Array.from({ length: (n + 1) * (n + 1) }, rand) }))
  const out = new Float32Array(size * size)
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    let acc = 0, amp = 1, tot = 0
    for (const g of grids) {
      const fx = (x / size) * g.n, fy = (y / size) * g.n
      const x0 = Math.floor(fx) % g.n, y0 = Math.floor(fy) % g.n, x1 = (x0 + 1) % g.n, y1 = (y0 + 1) % g.n
      const tx = fx - Math.floor(fx), ty = fy - Math.floor(fy)
      const sx = tx * tx * (3 - 2 * tx), sy = ty * ty * (3 - 2 * ty)
      const idx = (a, b) => b * (g.n + 1) + a
      const v = (g.v[idx(x0, y0)] * (1 - sx) + g.v[idx(x1, y0)] * sx) * (1 - sy) + (g.v[idx(x0, y1)] * (1 - sx) + g.v[idx(x1, y1)] * sx) * sy
      acc += v * amp; tot += amp; amp *= 0.5
    }
    out[y * size + x] = acc / tot
  }
  return out
}

function dustTexture() {
  const S = 256, c = canvas(S, S), g = c.getContext('2d'), img = g.createImageData(S, S)
  const n = valueNoise(S, [4, 8, 16, 32, 64], 11)
  const rand = rng(5)
  for (let i = 0; i < S * S; i++) {
    const speck = rand() > 0.985 ? 0.35 : 0
    const v = Math.min(1, Math.max(0, (n[i] - 0.25) * 1.9 + speck))
    img.data[i * 4] = img.data[i * 4 + 1] = img.data[i * 4 + 2] = v * 255
    img.data[i * 4 + 3] = 255
  }
  g.putImageData(img, 0, 0)
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; return t
}

function grassTexture() {
  const S = 512, c = canvas(S, S), g = c.getContext('2d'), n = valueNoise(S, [4, 8, 16, 64], 3)
  const img = g.createImageData(S, S)
  for (let i = 0; i < S * S; i++) {
    const v = n[i]
    img.data[i * 4] = 128 + v * 40; img.data[i * 4 + 1] = 158 + v * 44; img.data[i * 4 + 2] = 104 + v * 30; img.data[i * 4 + 3] = 255
  }
  g.putImageData(img, 0, 0)
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(14, 14); t.colorSpace = THREE.SRGBColorSpace
  return t
}

function gravelTexture() {
  const S = 256, c = canvas(S, S), g = c.getContext('2d'), rand = rng(9)
  g.fillStyle = '#bdb9ae'; g.fillRect(0, 0, S, S)
  for (let i = 0; i < 2600; i++) {
    const l = 62 + rand() * 30
    g.fillStyle = `hsl(40 6% ${l}%)`
    g.beginPath(); g.arc(rand() * S, rand() * S, 0.8 + rand() * 1.8, 0, 7); g.fill()
  }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(3, 2); t.colorSpace = THREE.SRGBColorSpace
  return t
}

function cellTexture(maxAniso) {
  const W = 1360, H = 800, c = canvas(W, H), g = c.getContext('2d'), rand = rng(21)
  g.fillStyle = '#0b1429'; g.fillRect(0, 0, W, H)
  const cols = 10, rows = 6, gap = 7
  const cw = (W - gap * (cols + 1)) / cols, ch = (H - gap * (rows + 1)) / rows, cut = 18
  for (let r = 0; r < rows; r++) for (let q = 0; q < cols; q++) {
    const x = gap + q * (cw + gap), y = gap + r * (ch + gap), l = 20 + rand() * 5
    const grad = g.createLinearGradient(x, y, x + cw, y + ch)
    grad.addColorStop(0, `hsl(222 58% ${l + 7}%)`); grad.addColorStop(1, `hsl(229 62% ${l}%)`)
    g.fillStyle = grad
    g.beginPath()
    g.moveTo(x + cut, y); g.lineTo(x + cw - cut, y); g.lineTo(x + cw, y + cut); g.lineTo(x + cw, y + ch - cut)
    g.lineTo(x + cw - cut, y + ch); g.lineTo(x + cut, y + ch); g.lineTo(x, y + ch - cut); g.lineTo(x, y + cut)
    g.closePath(); g.fill()
    g.strokeStyle = 'rgba(150,170,225,.10)'; g.lineWidth = 1
    for (let f = y + 6; f < y + ch; f += 6) { g.beginPath(); g.moveTo(x + 2, f); g.lineTo(x + cw - 2, f); g.stroke() }
    g.strokeStyle = 'rgba(205,214,235,.85)'; g.lineWidth = 3.2
    for (let k = 1; k <= 3; k++) { const bx = x + (cw * k) / 4; g.beginPath(); g.moveTo(bx, y + 3); g.lineTo(bx, y + ch - 3); g.stroke() }
  }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = maxAniso; return t
}

function shadowTexture() {
  const S = 128, c = canvas(S, S), g = c.getContext('2d'), img = g.createImageData(S, S)
  const e0 = 8, soft = 18
  for (let y = 0; y < S; y++) for (let x = 0; x < S; x++) {
    const d = Math.min(x - e0, S - 1 - e0 - x, y - e0, S - 1 - e0 - y)
    const a = Math.min(1, Math.max(0, d / soft + 0.5))
    const i = (y * S + x) * 4
    img.data[i] = img.data[i + 1] = img.data[i + 2] = 255; img.data[i + 3] = a * a * (3 - 2 * a) * 255
  }
  g.putImageData(img, 0, 0)
  return new THREE.CanvasTexture(c)
}

function brushTexture() {
  const c = canvas(64, 256), g = c.getContext('2d')
  g.fillStyle = '#1f6fd6'; g.fillRect(0, 0, 64, 256)
  for (let y = 0; y < 256; y += 8) { g.fillStyle = y % 16 ? '#5fa2f5' : '#e8f1fe'; g.fillRect(0, y, 64, 4) }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t
}

function glowTexture(inner, outer) {
  const c = canvas(128, 128), g = c.getContext('2d'), gr = g.createRadialGradient(64, 64, 2, 64, 64, 62)
  gr.addColorStop(0, inner); gr.addColorStop(1, outer); g.fillStyle = gr; g.fillRect(0, 0, 128, 128)
  return new THREE.CanvasTexture(c)
}

const HEAT = [[29, 78, 216], [34, 193, 195], [253, 216, 53], [251, 140, 0], [229, 57, 53], [255, 255, 255]]
function heatRGB(t, lo, hi) {
  const x = Math.min(1, Math.max(0, (t - lo) / (hi - lo || 1))) * (HEAT.length - 1)
  const i = Math.min(HEAT.length - 2, Math.floor(x)), k = x - i
  return HEAT[i].map((v, j) => Math.round(v + (HEAT[i + 1][j] - v) * k))
}

// ---------- the scene ------------------------------------------------------------------------------------
export class PanelScene {
  constructor(host) {
    this.host = host
    this.disposables = []
    this.target = { tilt: 90, dust: 0, shade: 0, sweep: -1, eff: 1, thermalOn: false, hotspot: false, light: 0.9, weather: {} }
    this.cur = { tilt: 90, dust: 0, shade: 0, sweep: 0, arc: -999, light: 0.9, cloud: 0, rain: 0, storm: 0, heat: 0, cloudPhase: 0 }
    this.sig = ''
    this.camTween = null
    this.running = true

    const r = (this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' }))
    r.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    r.shadowMap.enabled = true
    r.shadowMap.type = THREE.PCFSoftShadowMap
    r.toneMapping = THREE.ACESFilmicToneMapping
    r.toneMappingExposure = 1.05
    r.outputColorSpace = THREE.SRGBColorSpace
    r.domElement.style.display = 'block'
    r.domElement.style.width = '100%'
    r.domElement.style.height = '100%'
    host.appendChild(r.domElement)

    this.scene = new THREE.Scene()
    this.camera = new THREE.PerspectiveCamera(36, 1, 0.1, 120)
    this.controls = new OrbitControls(this.camera, r.domElement)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.minDistance = 2.2
    this.controls.maxDistance = 13
    this.controls.maxPolarAngle = Math.PI / 2 - 0.03
    this.controls.autoRotateSpeed = 1.2
    this.controls.addEventListener('start', () => { this.userMoved = true })
    this._resize()
    this.setView('perspective', true)

    this._sky(); this._ground(); this._structure(); this._panel(); this._rig(); this._spray(); this._angleGauge(); this._weather()

    this.clock = new THREE.Clock()
    this.ro = new ResizeObserver(() => this._resize())
    this.ro.observe(host)
    this._resize()
    this._loop = this._loop.bind(this)
    this.raf = requestAnimationFrame(this._loop)
  }

  _track(o) { this.disposables.push(o); return o }

  // ---- environment ----
  _sky() {
    const mk = (hdr) => {
      const mat = new THREE.ShaderMaterial({
        side: THREE.BackSide, depthWrite: false, fog: false,
        uniforms: { top: { value: new THREE.Color(0x4f8fe0) }, mid: { value: new THREE.Color(0xa9cdf5) }, bot: { value: new THREE.Color(0xe9f2fc) }, uDim: { value: 1 }, uHazeCol: { value: new THREE.Color(1, 1, 1) }, uHaze: { value: 0 } },
        vertexShader: 'varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.); }',
        fragmentShader: 'uniform vec3 top; uniform vec3 mid; uniform vec3 bot; uniform float uDim; uniform vec3 uHazeCol; uniform float uHaze; varying vec3 vP; void main(){ float h = clamp(vP.y,-0.2,1.0); vec3 c = h>0.0 ? mix(mid, top, pow(h,0.6)) : mix(mid, bot, -h*5.0); gl_FragColor = vec4(mix(c, uHazeCol, uHaze)*uDim*' + (hdr ? '1.15' : '1.0') + ',1.); }',
      })
      return this._track(mat)
    }
    this.skyMat = mk(false)
    const dome = new THREE.Mesh(this._track(new THREE.SphereGeometry(60, 32, 16)), this.skyMat)
    this.scene.add(dome)

    // environment map for reflections on the glass / frame (sky + bright sun)
    const envScene = new THREE.Scene()
    envScene.add(new THREE.Mesh(new THREE.SphereGeometry(60, 32, 16), mk(true)))
    this.sunDir = new THREE.Vector3(5.5, 6.5, 3.2).normalize()
    const sunDisk = new THREE.Mesh(new THREE.SphereGeometry(3, 16, 8), new THREE.MeshBasicMaterial({ color: new THREE.Color(14, 12, 9) }))
    sunDisk.position.copy(this.sunDir).multiplyScalar(50)
    envScene.add(sunDisk)
    const floor = new THREE.Mesh(new THREE.CircleGeometry(60, 24), new THREE.MeshBasicMaterial({ color: 0x8fa682 }))
    floor.rotation.x = -Math.PI / 2; floor.position.y = -0.2
    envScene.add(floor)
    const pm = new THREE.PMREMGenerator(this.renderer)
    this.envRT = pm.fromScene(envScene, 0.03)
    this.scene.environment = this.envRT.texture
    pm.dispose()

    this.scene.fog = new THREE.Fog(0xdbe8f6, 16, 48)
    this.fogBase = new THREE.Color(0xdbe8f6)
    const sun = (this.sun = new THREE.DirectionalLight(0xfff1d6, 3.4))
    sun.position.copy(this.sunDir).multiplyScalar(9)
    sun.castShadow = true
    sun.shadow.mapSize.set(2048, 2048)
    const sc = sun.shadow.camera
    sc.left = -4; sc.right = 4; sc.top = 4; sc.bottom = -4; sc.near = 1; sc.far = 24
    sun.shadow.bias = -0.0004; sun.shadow.normalBias = 0.02; sun.shadow.radius = 3
    this.scene.add(sun)
    this.hemi = new THREE.HemisphereLight(0xcfe3ff, 0x8aa07a, 0.55)
    this.scene.add(this.hemi)

    const glow = (this.sunGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: this._track(glowTexture('rgba(255,244,205,1)', 'rgba(255,230,160,0)')), fog: false, depthWrite: false, transparent: true, blending: THREE.AdditiveBlending })))
    glow.position.copy(this.sunDir).multiplyScalar(52); glow.scale.set(22, 22, 1)
    this.scene.add(glow)
  }

  _ground() {
    const grass = new THREE.Mesh(new THREE.CircleGeometry(40, 48), this._track(new THREE.MeshStandardMaterial({ map: this._track(grassTexture()), roughness: 1, metalness: 0, envMapIntensity: 0.3 })))
    grass.rotation.x = -Math.PI / 2; grass.receiveShadow = true
    this.scene.add(grass)
    const pad = new THREE.Mesh(new THREE.PlaneGeometry(4.6, 3.2), this._track(new THREE.MeshStandardMaterial({ map: this._track(gravelTexture()), roughness: 0.95, envMapIntensity: 0.3 })))
    pad.rotation.x = -Math.PI / 2; pad.position.y = 0.004; pad.receiveShadow = true
    this.scene.add(pad)
  }

  // ---- fixed structure: footings, posts, bearings, servo ----
  _structure() {
    const steel = this._track(new THREE.MeshStandardMaterial({ color: 0x9aa3ad, metalness: 0.85, roughness: 0.42 }))
    const concrete = this._track(new THREE.MeshStandardMaterial({ color: 0xb4b2ac, roughness: 0.95, metalness: 0 }))
    const dark = this._track(new THREE.MeshStandardMaterial({ color: 0x23272e, roughness: 0.5, metalness: 0.2 }))
    const add = (geo, mat, x, y, z) => { const m = new THREE.Mesh(this._track(geo), mat); m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true; this.scene.add(m); return m }
    const postTop = PIVOT_Y - TUBE_DROP - 0.075
    for (const z of [-PD / 2 - 0.18, PD / 2 + 0.18]) {
      add(new THREE.BoxGeometry(0.55, 0.16, 0.5), concrete, 0, 0.08, z)
      add(new THREE.BoxGeometry(0.3, 0.025, 0.3), steel, 0, 0.17, z)
      add(new THREE.BoxGeometry(0.085, postTop - 0.17, 0.085), steel, 0, 0.17 + (postTop - 0.17) / 2, z)
      add(new THREE.BoxGeometry(0.16, 0.1, 0.16), dark, 0, postTop + 0.04, z)   // bearing block
    }
    // servo (fixed to the front post) driving the tube
    const servo = add(new THREE.BoxGeometry(0.2, 0.11, 0.15), dark, 0.0, PIVOT_Y - TUBE_DROP - 0.19, PD / 2 + 0.42)
    servo.castShadow = true
    const label = new THREE.Mesh(new THREE.PlaneGeometry(0.12, 0.04), new THREE.MeshBasicMaterial({ color: 0x2f9be8 }))
    label.position.set(0, 0.0, 0.0755); servo.add(label)
  }

  // ---- the tilting module ----
  _panel() {
    const tilt = (this.tilt = new THREE.Group())
    tilt.position.set(0, PIVOT_Y, 0)
    this.scene.add(tilt)
    const maxA = this.renderer.capabilities.getMaxAnisotropy()
    const frameMat = this._track(new THREE.MeshStandardMaterial({ color: 0xd3d8df, metalness: 0.9, roughness: 0.36, envMapIntensity: 1.1 }))
    const backMat = this._track(new THREE.MeshStandardMaterial({ color: 0x20252d, roughness: 0.7 }))
    const add = (geo, mat, x, y, z) => { const m = new THREE.Mesh(this._track(geo), mat); m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true; tilt.add(m); return m }

    add(new THREE.BoxGeometry(PW - 0.02, 0.03, PD - 0.02), backMat, 0, 0.002, 0)                      // laminate body
    const ft = 0.05, fh = 0.045                                                                          // aluminium frame
    add(new THREE.BoxGeometry(PW, fh, ft), frameMat, 0, 0.012, PD / 2 - ft / 2)
    add(new THREE.BoxGeometry(PW, fh, ft), frameMat, 0, 0.012, -PD / 2 + ft / 2)
    add(new THREE.BoxGeometry(ft, fh, PD - 2 * ft), frameMat, PW / 2 - ft / 2, 0.012, 0)
    add(new THREE.BoxGeometry(ft, fh, PD - 2 * ft), frameMat, -PW / 2 + ft / 2, 0.012, 0)
    // mounting rails, torque tube, clamps, junction box
    add(new THREE.BoxGeometry(0.05, 0.035, PD * 0.92), frameMat, -PW * 0.28, -0.035, 0)
    add(new THREE.BoxGeometry(0.05, 0.035, PD * 0.92), frameMat, PW * 0.28, -0.035, 0)
    const tube = add(new THREE.CylinderGeometry(0.042, 0.042, PD + 0.95, 24), frameMat, 0, -TUBE_DROP, 0)
    tube.rotation.x = Math.PI / 2
    add(new THREE.BoxGeometry(0.09, 0.075, 0.1), frameMat, 0, -0.07, PD * 0.3)
    add(new THREE.BoxGeometry(0.09, 0.075, 0.1), frameMat, 0, -0.07, -PD * 0.3)
    add(new THREE.BoxGeometry(0.16, 0.035, 0.1), backMat, PW * 0.3, -0.03, -PD * 0.2)
    // servo horn (turns with the tube, in front of the fixed servo body)
    const horn = add(new THREE.BoxGeometry(0.32, 0.035, 0.025), this._track(new THREE.MeshStandardMaterial({ color: 0xf2f4f7, roughness: 0.4 })), 0, -TUBE_DROP, PD / 2 + 0.34)
    horn.castShadow = false

    // photovoltaic cells + glass
    const cells = new THREE.Mesh(this._track(new THREE.PlaneGeometry(GW, GD)), this._track(new THREE.MeshStandardMaterial({ map: this._track(cellTexture(maxA)), roughness: 0.4, metalness: 0.35, envMapIntensity: 0.6 })))
    cells.rotation.x = -Math.PI / 2; cells.position.y = 0.0225; cells.receiveShadow = true
    tilt.add(cells)
    const glass = new THREE.Mesh(this._track(new THREE.PlaneGeometry(GW, GD)), this._track(new THREE.MeshPhysicalMaterial({ color: 0xffffff, transparent: true, opacity: 0.14, roughness: 0.04, metalness: 0, clearcoat: 1, clearcoatRoughness: 0.03, envMapIntensity: 1.9, depthWrite: false })))
    glass.rotation.x = -Math.PI / 2; glass.position.y = 0.0245; glass.renderOrder = 2
    tilt.add(glass)

    // overlays (all in panel UV space: u = left->right, v = front->back)
    const overlay = (mat, y, order) => {
      const m = new THREE.Mesh(this._track(new THREE.PlaneGeometry(GW, GD)), mat)
      m.rotation.x = -Math.PI / 2; m.position.y = y; m.renderOrder = order; tilt.add(m); return m
    }
    this.dustMat = this._track(new THREE.ShaderMaterial({
      transparent: true, depthWrite: false,
      polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
      uniforms: { uTex: { value: this._track(dustTexture()) }, uDust: { value: 0 }, uSweep: { value: 0 }, uKeep: { value: 0 } },
      vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.); }',
      fragmentShader: `uniform sampler2D uTex; uniform float uDust; uniform float uSweep; uniform float uKeep; varying vec2 vUv;
        void main(){
          float n = texture2D(uTex, vUv * vec2(2.4, 1.5)).r;
          float base = 0.30 + 0.70 * smoothstep(0.15, 0.85, n);
          float swept = uSweep > 0.0 ? 1.0 - smoothstep(uSweep - 0.012, uSweep + 0.012, vUv.x) : 0.0;
          float a = clamp(uDust * base * mix(1.0, uKeep, swept) * 1.55, 0.0, 0.9);
          gl_FragColor = vec4(0.66, 0.54, 0.36, a);
        }`,
    }))
    overlay(this.dustMat, 0.0262, 3)

    this.wetMat = this._track(new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3,
      uniforms: { uSweep: { value: 0 } },
      vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.); }',
      fragmentShader: `uniform float uSweep; varying vec2 vUv;
        void main(){ float w = uSweep > 0.0 ? 1.0 - smoothstep(uSweep - 0.01, uSweep + 0.01, vUv.x) : 0.0;
          float streak = 0.5 + 0.5 * sin(vUv.y * 90.0 + vUv.x * 40.0);
          gl_FragColor = vec4(0.72, 0.88, 1.0, w * (0.10 + 0.07 * streak)); }`,
    }))
    overlay(this.wetMat, 0.0268, 4)

    this.shadowMat = this._track(new THREE.MeshBasicMaterial({ map: this._track(shadowTexture()), color: 0x05070d, transparent: true, opacity: 0.58, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 }))
    this.shadowMesh = new THREE.Mesh(this._track(new THREE.PlaneGeometry(1, 1)), this.shadowMat)
    this.shadowMesh.rotation.x = -Math.PI / 2; this.shadowMesh.position.y = 0.0274; this.shadowMesh.renderOrder = 5
    tilt.add(this.shadowMesh)

    // thermal grid draped over the cells (toggle) and hotspot glow
    this.heatCanvas = canvas(8, 8)
    this.heatTex = this._track(new THREE.CanvasTexture(this.heatCanvas))
    this.heatTex.generateMipmaps = false; this.heatTex.minFilter = THREE.LinearFilter; this.heatTex.magFilter = THREE.LinearFilter
    this.heatMat = this._track(new THREE.MeshBasicMaterial({ map: this.heatTex, transparent: true, opacity: 0, depthWrite: false, toneMapped: false, polygonOffset: true, polygonOffsetFactor: -5, polygonOffsetUnits: -5 }))
    this.heatMesh = overlay(this.heatMat, 0.0278, 6)
    this.hotCanvas = canvas(128, 128)
    this.hotTex = this._track(new THREE.CanvasTexture(this.hotCanvas))
    this.hotMat = this._track(new THREE.MeshBasicMaterial({ map: this.hotTex, transparent: true, opacity: 0, depthWrite: false, toneMapped: false, blending: THREE.AdditiveBlending, polygonOffset: true, polygonOffsetFactor: -6, polygonOffsetUnits: -6 }))
    overlay(this.hotMat, 0.0282, 7)
  }

  // ---- cleaning robot (brush rides along the panel) ----
  _rig() {
    const rig = (this.rig = new THREE.Group())
    rig.position.set(DOCK_X, 0.075, 0)
    this.tilt.add(rig)
    const bt = this._track(brushTexture())
    const brush = (this.brush = new THREE.Mesh(this._track(new THREE.CylinderGeometry(0.05, 0.05, GD - 0.02, 28).rotateX(Math.PI / 2)), this._track(new THREE.MeshStandardMaterial({ map: bt, roughness: 0.9 }))))
    brush.castShadow = true; rig.add(brush)
    const body = this._track(new THREE.MeshStandardMaterial({ color: 0x2b3340, roughness: 0.45, metalness: 0.4 }))
    const accent = this._track(new THREE.MeshStandardMaterial({ color: 0xf5a524, roughness: 0.4 }))
    for (const s of [-1, 1]) {
      const end = new THREE.Mesh(this._track(new THREE.BoxGeometry(0.1, 0.1, 0.075)), body)
      end.position.set(0, 0.0, s * (GD / 2 + 0.01)); end.castShadow = true; rig.add(end)
      const cap = new THREE.Mesh(this._track(new THREE.BoxGeometry(0.1, 0.02, 0.078)), accent)
      cap.position.set(0, 0.06, s * (GD / 2 + 0.01)); rig.add(cap)
    }
    const nozzle = new THREE.Mesh(this._track(new THREE.CylinderGeometry(0.012, 0.012, GD - 0.1, 8).rotateX(Math.PI / 2)), this._track(new THREE.MeshStandardMaterial({ color: 0x9fb3c8, metalness: 0.8, roughness: 0.3 })))
    nozzle.position.set(0.075, 0.035, 0); rig.add(nozzle)
  }

  _spray() {
    const N = 320
    this.spray = { n: N, pos: new Float32Array(N * 3), vel: new Float32Array(N * 3), life: new Float32Array(N).fill(-1) }
    for (let i = 0; i < N; i++) this.spray.pos[i * 3 + 1] = -10
    const geo = this._track(new THREE.BufferGeometry())
    geo.setAttribute('position', new THREE.BufferAttribute(this.spray.pos, 3))
    this.sprayPts = new THREE.Points(geo, this._track(new THREE.PointsMaterial({ color: 0xcfe9ff, size: 0.04, transparent: true, opacity: 0.85, depthWrite: false, sizeAttenuation: true })))
    this.sprayPts.frustumCulled = false
    this.scene.add(this.sprayPts)
    this._v = new THREE.Vector3(); this._n = new THREE.Vector3()
  }

  _angleGauge() {
    const g = (this.gauge = new THREE.Group())
    g.position.set(0, PIVOT_Y - TUBE_DROP, PD / 2 + 0.52)
    this.scene.add(g)
    const ref = new THREE.Mesh(this._track(new THREE.BoxGeometry(0.004, 0.42, 0.004)), new THREE.MeshBasicMaterial({ color: 0x8b97a8, transparent: true, opacity: 0.6 }))
    ref.position.y = 0.21; g.add(ref)
    this.gaugeNeedle = new THREE.Mesh(this._track(new THREE.BoxGeometry(0.008, 0.42, 0.008)), new THREE.MeshBasicMaterial({ color: 0xe8890c }))
    this.gaugeNeedle.geometry.translate(0, 0.21, 0); g.add(this.gaugeNeedle)
    this.gaugeArc = new THREE.Mesh(new THREE.RingGeometry(0.34, 0.37, 2, 1, 0, 0.001), new THREE.MeshBasicMaterial({ color: 0xe8890c, side: THREE.DoubleSide, transparent: true, opacity: 0.85 }))
    g.add(this.gaugeArc)
  }


  // ---- weather: cloud, rain, dust storm ----
  _weather() {
    const cloud = (this.cloud = new THREE.Group())
    const cm = (this.cloudMat = this._track(new THREE.MeshStandardMaterial({ color: 0xc9cfd8, roughness: 1, metalness: 0, transparent: true, opacity: 0, emissive: 0xe8eef8, emissiveIntensity: 0.85, fog: false })))
    const blobs = [[0, 0, 0, 1.5], [1.4, 0.15, 0.3, 1.2], [-1.4, 0.1, -0.2, 1.25], [0.5, 0.35, -0.7, 1.0], [-0.6, 0.3, 0.8, 1.0], [2.5, 0, 0, 0.8], [-2.5, 0, 0.1, 0.85]]
    for (const [x, y, z, r] of blobs) {
      const m = new THREE.Mesh(this._track(new THREE.SphereGeometry(r, 18, 12)), cm)
      m.position.set(x, y, z); m.scale.set(1.25, 0.5, 1); m.castShadow = true; cloud.add(m)
    }
    cloud.position.set(-4, 4.1, 1.35); cloud.visible = false
    this.scene.add(cloud)
    const far = (this.cloudFar = new THREE.Group())
    for (const [x, y, z, r] of blobs) {
      const m = new THREE.Mesh(this._track(new THREE.SphereGeometry(r, 16, 10)), cm)
      m.position.set(x * 1.6, y * 1.6, z * 1.6); m.scale.set(1.7, 0.6, 1.3); far.add(m)
    }
    far.position.set(-8, 4.6, -9); far.visible = false
    this.scene.add(far)

    const N = 700, rain = new Float32Array(N * 6)
    this.rainSpeed = new Float32Array(N)
    for (let i = 0; i < N; i++) this._resetDrop(rain, i, true)
    this.rainGeo = this._track(new THREE.BufferGeometry())
    this.rainGeo.setAttribute('position', new THREE.BufferAttribute(rain, 3))
    this.rainMat = this._track(new THREE.LineBasicMaterial({ color: 0xc3d6ee, transparent: true, opacity: 0, depthWrite: false }))
    this.rain = new THREE.LineSegments(this.rainGeo, this.rainMat); this.rain.frustumCulled = false; this.rain.visible = false
    this.scene.add(this.rain)

    const M = 520, dust = new Float32Array(M * 3)
    for (let i = 0; i < M; i++) { dust[i * 3] = (Math.random() - 0.5) * 10; dust[i * 3 + 1] = 0.1 + Math.random() * 3.4; dust[i * 3 + 2] = (Math.random() - 0.5) * 8 }
    this.dustGeo = this._track(new THREE.BufferGeometry())
    this.dustGeo.setAttribute('position', new THREE.BufferAttribute(dust, 3))
    this.dustPtMat = this._track(new THREE.PointsMaterial({ color: 0xc9a56a, size: 0.06, transparent: true, opacity: 0, depthWrite: false, sizeAttenuation: true }))
    this.dustPts = new THREE.Points(this.dustGeo, this.dustPtMat); this.dustPts.frustumCulled = false; this.dustPts.visible = false
    this.scene.add(this.dustPts)
  }

  _resetDrop(a, i, anywhere) {
    const x = (Math.random() - 0.5) * 9, z = (Math.random() - 0.5) * 8, y = anywhere ? Math.random() * 6 : 6 + Math.random() * 0.5
    a[i * 6] = x; a[i * 6 + 1] = y; a[i * 6 + 2] = z
    a[i * 6 + 3] = x - 0.05; a[i * 6 + 4] = y + 0.38; a[i * 6 + 5] = z
    this.rainSpeed[i] = 10 + Math.random() * 5
  }

  _updateWeather(dt, time, k) {
    const T = this.target, C = this.cur, W = T.weather || {}
    C.cloud += ((W.cloud ? 1 : 0) - C.cloud) * k
    C.rain += ((W.rain ? 1 : 0) - C.rain) * k
    C.storm += ((W.dust_storm ? 1 : 0) - C.storm) * k
    C.heat += ((W.heat_wave ? 1 : 0) - C.heat) * k
    C.light += (T.light - C.light) * k

    // clouds drift across the sun path while active
    if (W.cloud) C.cloudPhase = Math.min(1.2, C.cloudPhase + dt / 8)
    else if (C.cloud < 0.03) C.cloudPhase = 0
    this.cloud.visible = C.cloud > 0.03
    this.cloud.position.x = -4 + C.cloudPhase * 9
    this.cloudFar.visible = this.cloud.visible
    this.cloudFar.position.x = -9 + C.cloudPhase * 14
    this.cloudMat.opacity = 0.93 * C.cloud

    this.rain.visible = C.rain > 0.03
    if (this.rain.visible) {
      const a = this.rainGeo.attributes.position.array
      for (let i = 0; i < this.rainSpeed.length; i++) {
        const dy = this.rainSpeed[i] * dt
        a[i * 6 + 1] -= dy; a[i * 6 + 4] -= dy
        if (a[i * 6 + 1] < 0) this._resetDrop(a, i, false)
      }
      this.rainGeo.attributes.position.needsUpdate = true
      this.rainMat.opacity = 0.55 * C.rain
    }

    this.dustPts.visible = C.storm > 0.03
    if (this.dustPts.visible) {
      const a = this.dustGeo.attributes.position.array
      for (let i = 0; i < a.length / 3; i++) {
        a[i * 3] += (2.6 + Math.sin(time * 1.7 + i) * 0.6) * dt
        a[i * 3 + 1] += Math.sin(time * 2.3 + i * 1.3) * 0.25 * dt
        if (a[i * 3] > 5) a[i * 3] = -5
      }
      this.dustGeo.attributes.position.needsUpdate = true
      this.dustPtMat.opacity = 0.75 * C.storm
    }

    // lighting follows the effective irradiance (clouds, rain, dusk and night all dim the scene)
    const L = Math.min(1.15, Math.max(0, C.light)), lk = Math.sqrt(Math.min(1, L * 1.1)), dim = 0.12 + 0.88 * lk
    this.sun.intensity = 0.1 + 3.3 * L
    this.sun.color.setHex(0xfff1d6).lerp(new THREE.Color(0xffd29a), C.heat * 0.8)
    this.hemi.intensity = 0.1 + 0.5 * L
    this.renderer.toneMappingExposure = 0.3 + 0.78 * Math.sqrt(Math.min(1, L)) + 0.1 * C.heat
    this.skyMat.uniforms.uDim.value = dim
    const hz = Math.max(C.storm, C.rain), wS = C.storm / (C.storm + C.rain + 1e-4)
    this.skyMat.uniforms.uHazeCol.value.setRGB(0.55 + 0.25 * wS, 0.6 + 0.04 * wS, 0.66 - 0.24 * wS)
    this.skyMat.uniforms.uHaze.value = Math.min(0.78, 0.72 * hz)
    this.sunGlow.material.opacity = Math.min(1, L) * (1 - 0.7 * C.cloud) * (1 - 0.6 * C.rain)
    const fog = this.scene.fog
    fog.color.copy(this.fogBase).multiplyScalar(dim).lerp(new THREE.Color(0xcfa66b), C.storm * 0.6).lerp(new THREE.Color(0x9aa6b4), C.rain * 0.5)
    fog.near = 16 - 12 * Math.max(C.storm, C.rain); fog.far = 48 - 26 * Math.max(C.storm, C.rain)
  }

  // ---- public API ----------------------------------------------------------------------------------------
  update(state) {
    Object.assign(this.target, state)
    const t = state.thermal
    if (t) {
      const sig = t.grid.flat().join(',') + '|' + t.hot.map((p) => p.join(':')).join(';')
      if (sig !== this.sig) { this.sig = sig; this._paintThermal(t) }
    }
  }

  _paintThermal(t) {
    const flat = t.grid.flat(), lo = Math.min(30, ...flat), hi = Math.max(80, ...flat)
    const g = this.heatCanvas.getContext('2d'), img = g.createImageData(8, 8)
    t.grid.forEach((row, r) => row.forEach((v, c) => {
      const [R, G, B] = heatRGB(v, lo, hi), i = (r * 8 + c) * 4
      img.data[i] = R; img.data[i + 1] = G; img.data[i + 2] = B; img.data[i + 3] = 255
    }))
    g.putImageData(img, 0, 0); this.heatTex.needsUpdate = true
    const h = this.hotCanvas.getContext('2d'); h.clearRect(0, 0, 128, 128)
    for (const [r, c] of t.hot) {
      const cx = ((c + 0.5) / 8) * 128, cy = ((r + 0.5) / 8) * 128, gr = h.createRadialGradient(cx, cy, 1, cx, cy, 22)
      gr.addColorStop(0, 'rgba(255,190,80,1)'); gr.addColorStop(0.45, 'rgba(255,90,20,.75)'); gr.addColorStop(1, 'rgba(255,40,0,0)')
      h.fillStyle = gr; h.fillRect(cx - 24, cy - 24, 48, 48)
    }
    this.hotTex.needsUpdate = true
  }

  setView(name, instant = false) {
    const v = VIEWS[name] || VIEWS.perspective
    this.viewName = name
    this.userMoved = false
    // portrait / narrow viewers: pull the camera back so the whole rig stays in frame
    const k = Math.max(1, 1.6 / ((this.camera.aspect || 2) + 0.4))
    const target = new THREE.Vector3(...v.target)
    const pos = new THREE.Vector3(...v.pos).sub(target).multiplyScalar(k).add(target)
    if (instant) {
      this.camera.position.copy(pos); this.controls.target.copy(target); this.controls.update(); return
    }
    this.camTween = { t: 0, from: this.camera.position.clone(), fromT: this.controls.target.clone(), to: pos, toT: target }
  }

  setAutoRotate(on) { this.controls.autoRotate = !!on }

  _resize() {
    const w = Math.max(1, this.host.clientWidth), h = Math.max(1, this.host.clientHeight)
    this.renderer.setSize(w, h, false)
    const changed = Math.abs(this.camera.aspect - w / h) > 0.05
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
    if (changed && !this.userMoved && this.viewName) this.setView(this.viewName, true)
  }

  _loop() {
    if (!this.running) return
    this.raf = requestAnimationFrame(this._loop)
    this._frame(Math.min(0.25, this.clock.getDelta()))
  }

  // Advance the animation by `seconds` in 1/30 s steps (used for debugging / automated checks when the
  // browser throttles requestAnimationFrame, e.g. in a hidden tab).
  advance(seconds) {
    for (let t = 0; t < seconds; t += 1 / 30) this._frame(1 / 30)
  }

  _frame(dt) {
    const time = (this.simTime = (this.simTime || 0) + dt)
    const k = 1 - Math.exp(-dt * 7), T = this.target, C = this.cur

    C.tilt += (T.tilt - C.tilt) * k
    this.tilt.rotation.z = -(C.tilt - 90) * DEG
    C.dust += (T.dust - C.dust) * k
    C.shade += (T.shade - C.shade) * k
    this.dustMat.uniforms.uDust.value = C.dust
    this.dustMat.uniforms.uKeep.value = 1 - T.eff

    const cleaning = T.sweep >= 0
    C.sweep += ((cleaning ? T.sweep : 0) - C.sweep) * k
    this.dustMat.uniforms.uSweep.value = cleaning ? C.sweep : 0
    this.wetMat.uniforms.uSweep.value = cleaning ? C.sweep : (C.rain > 0.3 ? 2 : 0)
    const targetX = cleaning ? -GW / 2 + C.sweep * GW : DOCK_X
    this.rig.position.x += (targetX - this.rig.position.x) * (1 - Math.exp(-dt * (cleaning ? 12 : 2.2)))
    this.brush.rotation.z += dt * (cleaning ? 16 : 0)

    // shadow: area fraction -> square-ish patch anchored at the front-right corner
    const f = Math.min(0.95, Math.max(0, C.shade)), side = Math.sqrt(f)
    this.shadowMesh.visible = f > 0.004
    this.shadowMesh.scale.set(Math.max(0.001, side * GW), Math.max(0.001, side * GD), 1)
    this.shadowMesh.position.x = GW / 2 - (side * GW) / 2
    this.shadowMesh.position.z = GD / 2 - (side * GD) / 2

    this.heatMat.opacity += ((T.thermalOn ? 0.92 : 0) - this.heatMat.opacity) * k
    this.hotMat.opacity += (((T.hotspot && !T.thermalOn) ? 0.75 + 0.25 * Math.sin(time * 5) : 0) - this.hotMat.opacity) * k

    this._updateWeather(dt, time, k)
    this._updateSpray(Math.min(dt, 0.05), cleaning)
    this._updateGauge(C.tilt - 90)

    if (this.camTween) {
      const tw = this.camTween; tw.t = Math.min(1, tw.t + dt / 0.7)
      const e = tw.t * tw.t * (3 - 2 * tw.t)
      this.camera.position.lerpVectors(tw.from, tw.to, e); this.controls.target.lerpVectors(tw.fromT, tw.toT, e)
      if (tw.t >= 1) this.camTween = null
    }
    this.controls.update()
    this.renderer.render(this.scene, this.camera)
  }

  _updateSpray(dt, active) {
    const s = this.spray
    this.rig.updateWorldMatrix(true, false)
    this._n.set(0, 1, 0).applyQuaternion(this.tilt.getWorldQuaternion(new THREE.Quaternion()))
    let alive = 0
    for (let i = 0; i < s.n; i++) {
      const o = i * 3
      if (s.life[i] <= 0) {
        if (active && Math.random() < 0.55) {
          this._v.set(0.09, 0.05, (Math.random() - 0.5) * (GD - 0.14)).applyMatrix4(this.rig.matrixWorld)
          s.pos[o] = this._v.x; s.pos[o + 1] = this._v.y; s.pos[o + 2] = this._v.z
          const up = 0.7 + Math.random() * 1.1
          s.vel[o] = this._n.x * up + 0.35 + (Math.random() - 0.5) * 0.5
          s.vel[o + 1] = this._n.y * up + Math.random() * 0.4
          s.vel[o + 2] = this._n.z * up + (Math.random() - 0.5) * 0.5
          s.life[i] = 0.5 + Math.random() * 0.45
        } else { s.pos[o + 1] = -10; continue }
      }
      s.vel[o + 1] -= 5.2 * dt
      s.pos[o] += s.vel[o] * dt; s.pos[o + 1] += s.vel[o + 1] * dt; s.pos[o + 2] += s.vel[o + 2] * dt
      s.life[i] -= dt
      if (s.pos[o + 1] < 0.02) s.life[i] = 0
      alive++
    }
    this.sprayPts.visible = alive > 0
    this.sprayPts.geometry.attributes.position.needsUpdate = true
  }

  _updateGauge(offsetDeg) {
    this.gaugeNeedle.rotation.z = -offsetDeg * DEG
    this.gaugeNeedle.visible = Math.abs(offsetDeg) > 0.6
    if (Math.abs(offsetDeg - this.cur.arc) < 0.25) return
    this.cur.arc = offsetDeg
    const len = Math.abs(offsetDeg) * DEG
    this.gaugeArc.geometry.dispose()
    this.gaugeArc.visible = len > 0.01
    if (len > 0.01) {
      // angle measured from +x axis; vertical (up) is pi/2; positive offset leans toward +x
      const start = offsetDeg > 0 ? Math.PI / 2 - len : Math.PI / 2
      this.gaugeArc.geometry = new THREE.RingGeometry(0.34, 0.37, 48, 1, start, len)
    }
  }

  dispose() {
    this.running = false
    cancelAnimationFrame(this.raf)
    this.ro.disconnect()
    this.controls.dispose()
    for (const d of this.disposables) d.dispose?.()
    this.gaugeArc.geometry.dispose()
    this.envRT?.dispose()
    this.renderer.dispose()
    this.renderer.forceContextLoss?.()
    this.renderer.domElement.remove()
  }
}
