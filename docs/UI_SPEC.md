# UI spec (tokens live in `src/lib/client/theme.ts`)

No reference recording was supplied, so timings are from the spec's starting values, **not measured against Glance**.

## Shape
One SVG path (fill + same-path edge stroke): flat top at the screen edge, rounded bottom corners (`r`), and concave "ears" of radius 9 px at the top corners (`M0,0 Q e,0 e,e …`). Width, height and radius are driven together by one spring loop (`Notch.tsx`), written straight to the DOM (no React render per frame). The loop stops when settled (no per-frame work while idle).

## Springs
| | k | c | ζ | overshoot (theory) | settle (theory, 2%) |
|---|---|---|---|---|---|
| expand | 380 | 27 | 0.69 | ≈ 5 % | ≈ 0.30 s |
| collapse | 330 | 36.3 | 1.0 | none | ≈ 0.22 s |
Direction is chosen when the target changes (area comparison). Interrupting keeps position **and velocity**, so reversal is smooth. Semi-implicit Euler, 4 substeps per frame. Reduce-motion (OS setting or checkbox): snap sizes, 150 ms fades.

## Geometry (w×h, bottom radius) and light
idle 200×32 r14 white 8→14% breathing · wake 360×64 `#8AB4FF` one dash sweep 450 ms · listening 420×112 `#4DA3FF` glow follows mic level · thinking 420×88 `#8B7CFF` travelling dash · acting 460×120 `#34D399` + step dots · approval 480×176 `#FF9F0A` 1.2 s pulse + countdown ring · speaking 460×140 `#7DF9E6` + speech bubble · error 400×72 `#FF453A` flash · echo 300×64 compact value bar (folds in 1.2 s) · hover 520×232 panel (120 ms intent / 400 ms leave; click pins; Esc/outside closes; right-click menu).

## Content motion
Entering items: 240 ms, stagger 40 ms, blur 8 px → 0 + 4 px rise. Newest transcript word fades in. Waveform: canvas bars, attack ≈ 20 ms / release ≈ 120 ms smoothing; the smoothed level also drives glow via the `--lvl` CSS variable (compositor-only filter).

## Differences from the spec (web build)
- Not Qt Quick/QML; no `ShaderEffect` (CSS `drop-shadow` filter + SVG dash animation instead).
- No Win32 window flags: "click-through when idle" is approximated by `pointer-events` limited to the pill; no fullscreen auto-hide; no multi-monitor/DPI re-positioning logic beyond the browser's.
- No measured frame-time numbers in this repo (headless browser could not launch in the build sandbox). The Perf tab measures them live in your browser; `scripts/ui-capture.mjs` automates capture.
