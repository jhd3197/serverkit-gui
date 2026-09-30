# Servers in Vela

Status: plan. Nothing here ships yet beyond the surface format itself.

## What exists

- **The format.** [surface-v1](https://github.com/jhd3197/vela-contracts/blob/main/docs/SURFACES.md)
  (vela-contracts, branch `feat/surface-v1`) describes a screen as data: panels,
  stats, tables, and a `desktop` of windows with a dock.
- **A producer.** This extension builds a surface for any managed server
  (`GET /api/v1/server-gui/<server_id>/surface`).
- **A renderer.** `frontend/components/SurfaceView.jsx` draws any surface. It is
  pure (a document in, `onAction` out) and has no ServerKit imports beyond
  translation and formatting hooks.

## Many servers, one app

Vela has so far been one computer, one owner. Showing ServerKit servers adds
many hosts, but it doesn't need Vela to become multi-server. The servers stay
ServerKit's. Vela only draws them.

**One app, not one per server.** A single "ServerKit" app in Vela holds one
connection to a ServerKit panel: its URL plus an API token, saved with the new
`http` connection provider (vela-contracts `feat/http-connection`). That
connection can see every server the token can. The app:

1. lists servers from the panel (`GET /api/v1/servers`);
2. lets the viewer switch between them, like a server switcher in the app's own
   top bar;
3. fetches the chosen server's surface and draws it.

Why one app:

- Installing an app per server would duplicate the token, the grants and the
  install review for every server.
- A panel already knows its fleet, so the list should come from there, not be
  re-entered in Vela.

If someone runs two panels, the app holds one connection per panel and the
switcher groups servers by panel.

## Windows, not only an app

Switching inside one app window covers "look at a server". To see two servers
side by side, Vela needs a window that is *one server*. That is a new view kind
on Vela desktops:

```
kind: "surface"
target: { appId: "serverkit", source: "<server id>" }
```

- The window's content comes from the owning app's connection, never from the
  window itself. The window names a source; the app resolves it.
- Vela draws the document with its own surface renderer (a port of
  `SurfaceView`, reusing the desk widget components for the value nodes).
- Several windows can point at different servers of the same app. Each window
  title is the surface `title` (the hostname).
- The same kind works for any producer: a companion or another app can offer
  sources too. Nothing in it is ServerKit-specific.

This is the "remote window": not a new network path, just a window that draws
a surface from a source an installed app already has access to.

## Screens

A server with a display can also stream frames. The live-screen window reuses
Vela's `RemoteView` (built for agent desktops, `web/src/desktops/RemoteView.jsx`)
with the frame source swapped for this extension's `/frame` endpoint. The shape
already matches: `{image_base64, width, height}`.

## Mini desktops from ServerKit

ServerKit can already deploy Vela as a service (`vela/serverkit.yaml`, the
same way it deploys WordPress). An extension action could add "Create desktop"
for a server:

1. deploy a Vela instance onto that server from the template;
2. pre-connect it to the panel with a scoped token;
3. pin that server's surface as its first window.

That gives each team or customer a personal desktop sitting next to their
servers. It can be built on the pieces above and doesn't change the format.

## Order

1. Merge `feat/http-connection` and `feat/surface-v1` in vela-contracts; adopt
   both in the Vela hub.
2. Vela: a `surface` view kind and a renderer. Draw `web` views too, which are
   stored but show "not available" today.
3. A `vela-serverkit` app: connection, server switcher, surface sources.
4. Surface actions in Vela, routed back through the app's connection and
   Vela's approval flow.
5. Screen windows via `RemoteView`.
6. "Create desktop" in this extension.
