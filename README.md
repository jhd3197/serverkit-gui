# ServerKit GUI

Streaming desktop view for ServerKit-managed servers.

This is the **first official ServerKit extension**. It adds a live "Desktop" tab
to the server detail page that streams screenshots from the agent. Hosts without
a graphical session fall back to a synthetic desktop rendered from agent data
(services as windows, processes as a taskbar, mounts as drives).

## How it works

```
Browser  ── HTTP poll ──▶  ServerKit panel  ── send_command ──▶  Agent
   ▲                            │                                   │
   │                            │                                   ▼
   └────── PNG frame ◀── agent response ◀──────────  capture screen
```

1. The frontend polls `GET /api/v1/server-gui/<server_id>/frame` every ~700ms.
2. The panel translates that into an `agent_registry.send_command(server_id, "gui:screenshot")`.
3. The agent runs the platform-specific capture path:
   - **Windows**: `Graphics.CopyFromScreen` (PowerShell shim) or native GDI (`agent/screenshot_windows.go`).
   - **Linux/X11**: `scrot` / `import` / `gnome-screenshot`.
   - **Linux/Wayland**: `grim`.
   - **Headless**: returns `{"capability":"none"}` — frontend renders synthetic UI.
4. Returned PNG is base64-encoded in the response so it can be `<img src="data:image/png;...">`.

## Install

From the panel UI:

```
Settings → Plugins → Install from URL
https://github.com/jhd3197/serverkit-gui
```

Or via API:

```bash
curl -X POST $PANEL/api/v1/plugins/install \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://github.com/jhd3197/serverkit-gui"}'
```

After install, restart the panel **and** rebuild the frontend (`npm run build`)
so Vite picks up `frontend/src/plugins/serverkit-gui/`.

## Agent requirement

The agent must implement two actions: `gui:capabilities` and `gui:screenshot`.
A reference Go implementation lives in `agent/` — drop it into
`ServerKit/agent/internal/capabilities/gui/` and register it in the agent's
action dispatcher.

If the agent does not yet handle these actions the plugin still loads — the UI
shows the synthetic desktop fallback and a banner explaining the agent needs
upgrading.

## Configuration

Per-server settings live in the plugin tab:

| Setting          | Default | Notes                                           |
|------------------|---------|-------------------------------------------------|
| Frame rate       | 1.5 fps | Capped at 5 fps to keep network/CPU sane        |
| JPEG quality     | 70      | Higher = sharper + bigger frames                |
| Scale            | 0.75    | Server-side downscale before encoding           |
| Show synthetic   | auto    | `auto` / `always` / `never`                     |

## Security

- Screenshots are sensitive. Only users with the
  `agent.command:gui:screenshot` permission can view frames.
- Frames are not persisted on the panel — they pass through memory only.
- The agent action checks the calling user has an active session before
  capturing on Windows (no capture from logged-out machines unless explicitly
  allowed).

## Roadmap

- [x] Plugin scaffold + manifest
- [x] Panel blueprint
- [x] Frontend streaming component
- [x] Agent capability stub (Go)
- [ ] Mouse/keyboard input proxying (Phase 2)
- [ ] WebSocket transport for sub-second frames (Phase 2)
- [ ] WebRTC for full RDP-grade interactivity (Phase 3)

## License

MIT
