# ServerKit Agent GUI

The first official ServerKit agent extension. Adds a "Desktop" view for any
managed server: a live screenshot stream when the host has a display, or a
*synthetic desktop* rendered from agent data when it doesn't.

The package slug stays `serverkit-gui` for install compatibility, but the
product name is **ServerKit Agent GUI** because the feature is powered by
native `gui:*` actions on the ServerKit agent.

## How it fits together

```
Browser  ── HTTP poll ──▶  ServerKit panel  ── send_command ──▶  Agent
                              │ (extension blueprint)              │ (gui SDK)
                              ▼                                    ▼
                          /api/v1/server-gui/...        gui:screenshot / gui:capabilities
```

This extension is **panel-side only**. It does not ship binaries to agents and
does not require a custom agent build. It calls the standard `gui:*` actions
that the main ServerKit agent exposes natively (since v0.4.0), the same way
existing features call `docker:*` or `system:*`.

The agent's GUI SDK is intentionally small: capability probing and a single
encoded frame per call. Anything more elaborate (mode switching, session
recording, mouse passthrough) is the extension's responsibility — we just
build on the bridge.

## Modes

The extension exposes two co-equal viewing modes per server:

| Mode         | When it works                              | What you see                                   |
|--------------|--------------------------------------------|------------------------------------------------|
| `screenshot` | Host has a display server (Win session, X11, Wayland) | Live remote desktop, ~1.5 fps |
| `synthetic`  | Always                                     | A desktop drawn from agent data: system, services, containers, top processes and storage as windows, with a dock |
| `auto`       | Default                                    | Prefers `screenshot`, falls back to `synthetic` |

`synthetic` is **not** just a fallback. On a headless production box it's the
primary view: a glanceable, OS-themed dashboard that turns "this server is a
black box" into "this server has a face."

## Surfaces

The synthetic desktop is a [surface-v1](https://github.com/jhd3197/vela-contracts/blob/main/docs/SURFACES.md)
document: JSON describing panels, stats, tables and a desktop of windows,
which the frontend draws with its own components. `backend/surface.py` builds
it from agent data; `GET /api/v1/server-gui/<server_id>/surface` serves it.

Because the format is shared, the same document can be drawn by any host that
speaks it, Vela included. See [docs/VELA.md](docs/VELA.md).

Buttons on the desktop (restart a failed service, restart a running container)
appear only for developer-role users, ask before running, and go through
`POST /api/v1/server-gui/<server_id>/actions/<action_id>`, which validates the
input again and maps it to exactly one agent command.

## Install

Panel UI:

```
Settings → Plugins → Install from URL
https://github.com/jhd3197/serverkit-gui
```

API:

```bash
curl -X POST $PANEL/api/v1/plugins/install \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://github.com/jhd3197/serverkit-gui"}'
```

After install, restart the panel and `npm run build` the frontend so Vite
picks up `frontend/src/plugins/serverkit-gui/`.

## Agent requirement

Agents **≥ v0.4.0** ship the `gui:*` actions natively — no further work needed.
On older agents the extension still loads: `gui:capabilities` returns "none"
and the synthetic mode takes over. Sections whose agent action is missing
(no Docker, no systemd) are left out of the desktop.

The agent SDK lives at `ServerKit/agent/internal/gui/`. If you're hacking the
agent and want to add e.g. multi-monitor capture or input proxying, that's the
file to edit. The contract returned to the panel:

```json
{
  "image_base64": "<b64 jpeg/png>",
  "format": "jpeg",
  "width": 1440,
  "height": 810,
  "captured_at": "2026-05-01T12:34:56Z"
}
```

## Configuration

Per-server, controlled from the toolbar of the Desktop view:

| Setting       | Default | Notes                                        |
|---------------|---------|----------------------------------------------|
| Mode          | auto    | auto / screenshot / synthetic                |
| Frame rate    | 1.5 fps | Capped at 5 fps                              |
| Quality       | 70      | JPEG; ignored for PNG                        |
| Scale         | 0.75    | Server-side downscale before encoding        |

## Security

- Frames are not persisted by the panel — they pass through memory only.
- The extension's routes inherit ServerKit's JWT auth and the existing
  `agent.command:*` permission model.
- On Windows, capture relies on an active user session. Hosts with no
  interactive login report `capability=none` and degrade to synthetic mode.

## Roadmap

- [x] Plugin scaffold + manifest
- [x] Marketplace-ready global widget contribution
- [x] Panel blueprint
- [x] Frontend streaming component + synthetic desktop
- [x] Agent SDK landed in main ServerKit (`agent/internal/gui/`)
- [x] Synthetic desktop as a surface-v1 document (services, containers, storage)
- [ ] Per-server mode toggle (screenshot / synthetic / auto) — in progress
- [ ] Serve surfaces to Vela (see docs/VELA.md)
- [ ] Input proxying (mouse / keyboard) — Phase 2
- [ ] Native fast-path for Windows (replace PowerShell shell-out) — Phase 2
- [ ] WebRTC for full RDP-grade interactivity — Phase 3

## License

MIT
