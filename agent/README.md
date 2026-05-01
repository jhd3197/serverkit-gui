# Agent capability — `gui:*`

Drop these files into the ServerKit agent at:

```
agent/internal/capabilities/gui/
```

Then register the actions in the agent's dispatcher (typically
`agent/internal/agent/agent.go`):

```go
import "github.com/jhd3197/serverkit/agent/internal/capabilities/gui"

// inside agent setup:
dispatcher.Register("gui:capabilities", gui.HandleCapabilities)
dispatcher.Register("gui:screenshot",   gui.HandleScreenshot)
```

The capability returns one of:

- `windows-gdi` — Windows session, captured via GDI
- `linux-x11`   — X11 session, `scrot`/`import` available
- `linux-wayland` — Wayland session, `grim` available
- `none` — headless, no display server

Returned frame payload:

```json
{
  "image_base64": "<b64 png/jpeg>",
  "format": "jpeg",
  "width": 1440,
  "height": 810,
  "captured_at": "2026-05-01T12:34:56Z"
}
```
