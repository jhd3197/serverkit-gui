# Runtime-frontend migration (ServerKit plan 25)

This extension now ships a **runtime ESM bundle** so it loads on a production
panel with **no rebuild** — Marketplace install → the launcher appears.

## What changed

- `frontend/runtime-entry.jsx` — the runtime entry. Same exports as `index.js`,
  but imports the CSS as a string (`?inline`) and injects it at load, so the
  single `dist/index.mjs` carries its own styles.
- `frontend/vite.config.mjs` — lib build that **externalizes** the host-shared
  libraries (`react`, `react-dom`, `react/jsx-runtime`, `react-router-dom`,
  `serverkit-sdk`). Never bundle React — a second copy crashes hooks.
- `frontend/package.json` — `npm run build` → `frontend/dist/index.mjs`.
- `plugin.json` — `frontend_entry` is now `dist/index.mjs` and declares
  `sdk_version: "^1.0.0"`.

## Dual-path window

`frontend/index.js` (the original baked entry) is kept for one release so the
extension still renders on panels that bundled it the old way. Remove it once all
target panels are on a runtime-loading panel (≥ the plan-25 release).

## Build + release

```bash
cd frontend && npm install && npm run build
node <serverkit>/scripts/new-extension.mjs --validate ..   # lints manifest + bundle
cd .. && zip -r serverkit-gui-<version>.zip plugin.json frontend/dist backend
sha256sum serverkit-gui-<version>.zip
```

Then attach the zip to a GitHub release and open a PR against
`serverkit-extensions/index.json` bumping the entry's `version`, `source`,
`sha256`, and adding `sdk_version`. See ServerKit `docs/EXTENSIONS_CI.md`.
