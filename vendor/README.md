# Vendored front-end libraries

Browser-ready builds copied from `node_modules` (see `package.json` for versions),
so the static `index.html` can use them without a CDN or build step.

| Library | Files | Load with |
|---|---|---|
| GSAP 3.15 (all plugins) | `gsap/*.min.js` | `<script src="/vendor/gsap/gsap.min.js"></script>` then e.g. `ScrollTrigger.min.js`, `gsap.registerPlugin(ScrollTrigger)` |
| three.js r187 | `three/three.module.js` (+ `three.core.js`) | `import * as THREE from '/vendor/three/three.module.js'` in a `<script type="module">` |
| Spline runtime 2.0 | `spline/runtime.js` (standalone) | `import { Application } from '/vendor/spline/runtime.js'; new Application(canvas).load('https://prod.spline.design/.../scene.splinecode')` |
| Rive (canvas) 2.51 | `rive/rive.js`, `rive/rive.wasm` | `<script src="/vendor/rive/rive.js"></script>`, then `rive.RuntimeLoader.setWasmUrl('/vendor/rive/rive.wasm')` before `new rive.Rive({ src, canvas, autoplay: true })` |

To update: `npm install <pkg>@latest`, then re-copy the files above.
