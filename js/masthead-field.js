// Ambient "signal field" behind the masthead (three.js).
// A grid of ink-coloured dots drifting in slow waves; the cursor lifts a soft ripple.
// Loaded lazily after the page is idle, paused when off-screen or the tab is hidden,
// rendered as a single still frame when the user prefers reduced motion.

const host = document.getElementById("masthead");
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

const idle = () => new Promise(r => (window.requestIdleCallback ? requestIdleCallback(r, { timeout: 2500 }) : setTimeout(r, 600)));

async function start() {
  if (!host) return;
  await idle();
  const THREE = await import("/vendor/three/three.module.js");

  const canvas = document.createElement("canvas");
  canvas.className = "mast-field";
  canvas.setAttribute("aria-hidden", "true");

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false, powerPreference: "low-power" });
  } catch (e) {
    return; // no WebGL – the masthead simply stays static
  }
  host.prepend(canvas);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
  camera.position.set(0, 6.5, 8.5);
  camera.lookAt(0, 0, 0.6);

  const small = window.innerWidth < 700;
  const COLS = small ? 90 : 170, ROWS = 26, SP = 0.36;
  const pos = new Float32Array(COLS * ROWS * 3);
  let k = 0;
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      pos[k++] = (c - (COLS - 1) / 2) * SP;
      pos[k++] = 0;
      pos[k++] = (r - (ROWS - 1) / 2) * SP;
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));

  const uniforms = {
    uTime: { value: 0 },
    uMouse: { value: new THREE.Vector2(99, 99) },
    uColor: { value: new THREE.Color() },
    uAlpha: { value: 0.5 },
    uSize: { value: 2.2 * renderer.getPixelRatio() },
  };

  const mat = new THREE.ShaderMaterial({
    uniforms,
    transparent: true,
    depthWrite: false,
    vertexShader: /* glsl */ `
      uniform float uTime; uniform vec2 uMouse; uniform float uSize;
      varying float vFade; varying float vLift;
      void main() {
        vec3 p = position;
        float w = sin(p.x * 0.42 + uTime * 0.55) * 0.32
                + sin(p.z * 0.65 - uTime * 0.38) * 0.22
                + sin((p.x + p.z) * 0.22 + uTime * 0.25) * 0.18;
        float d = distance(p.xz, uMouse);
        float bump = exp(-d * d * 0.35) * 0.9;
        p.y = w + bump;
        vLift = bump;
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        gl_Position = projectionMatrix * mv;
        gl_PointSize = uSize * (9.0 / -mv.z) * (1.0 + bump * 0.6);
        vFade = smoothstep(-16.0, -6.0, mv.z);
      }`,
    fragmentShader: /* glsl */ `
      uniform vec3 uColor; uniform float uAlpha;
      varying float vFade; varying float vLift;
      void main() {
        vec2 q = gl_PointCoord - 0.5;
        if (dot(q, q) > 0.25) discard;
        gl_FragColor = vec4(uColor, uAlpha * vFade * (0.55 + vLift * 0.8));
      }`,
  });
  scene.add(new THREE.Points(geo, mat));

  // Follow the site's ink colour in light and dark mode
  const readInk = () => {
    const cs = getComputedStyle(document.documentElement);
    uniforms.uColor.value.set(cs.getPropertyValue("--ink-1").trim() || "#1a1714");
    uniforms.uAlpha.value = document.documentElement.dataset.theme === "dark" ||
      (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches) ? 0.42 : 0.5;
    if (!running) render();
  };
  new MutationObserver(readInk).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", readInk);

  const resize = () => {
    const w = host.clientWidth, h = host.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    if (!running) render();
  };
  new ResizeObserver(resize).observe(host);

  // Cursor → position on the grid plane (smoothed in the loop)
  const target = new THREE.Vector2(99, 99);
  const ray = new THREE.Raycaster();
  const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  const hit = new THREE.Vector3();
  host.addEventListener("pointermove", e => {
    const r = host.getBoundingClientRect();
    ray.setFromCamera({ x: ((e.clientX - r.left) / r.width) * 2 - 1, y: -((e.clientY - r.top) / r.height) * 2 + 1 }, camera);
    if (ray.ray.intersectPlane(plane, hit)) target.set(hit.x, hit.z);
  });
  host.addEventListener("pointerleave", () => target.set(99, 99));

  const render = () => renderer.render(scene, camera);
  let running = false, visible = true, raf = 0, last = performance.now();
  const loop = now => {
    const dt = Math.min((now - last) / 1000, 0.05);
    last = now;
    uniforms.uTime.value += dt;
    uniforms.uMouse.value.lerp(target, 1 - Math.pow(0.002, dt));
    render();
    raf = requestAnimationFrame(loop);
  };
  const update = () => {
    const should = !reduce && visible && !document.hidden;
    if (should && !running) { running = true; last = performance.now(); raf = requestAnimationFrame(loop); }
    else if (!should && running) { running = false; cancelAnimationFrame(raf); }
  };
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; update(); }).observe(host);
  document.addEventListener("visibilitychange", update);

  uniforms.uTime.value = 4; // a pleasant starting phase for the still frame
  readInk();
  resize();
  render();
  requestAnimationFrame(() => canvas.classList.add("ready"));
  update();
}

start();
