import React, { useEffect, useRef, useState, useCallback } from 'react';
import SyntheticDesktop from './SyntheticDesktop.jsx';

const FRAME_INTERVAL_MS_DEFAULT = 700;
const FRAME_INTERVAL_MS_MIN = 200;
const FRAME_INTERVAL_MS_MAX = 5000;

/**
 * The actual desktop streaming surface. Polls /frame, falls back to
 * SyntheticDesktop when the agent reports no display.
 */
export default function ServerGui({ api, serverId }) {
    const [caps, setCaps] = useState(null);
    const [frame, setFrame] = useState(null);
    const [error, setError] = useState(null);
    const [paused, setPaused] = useState(false);
    const [intervalMs, setIntervalMs] = useState(FRAME_INTERVAL_MS_DEFAULT);
    const [scale, setScale] = useState(0.75);
    const [quality, setQuality] = useState(70);

    const inflightRef = useRef(false);
    const timerRef = useRef(null);

    const baseUrl = `/api/v1/server-gui/${serverId}`;

    const fetchJson = useCallback(async (path) => {
        // Use the panel's fetch wrapper so JWT + base URL behave consistently.
        // ApiService exposes `request` on most ServerKit builds; fall back to
        // window.fetch with the stored token if not.
        if (api && typeof api.request === 'function') {
            return api.request(path);
        }
        const token = localStorage.getItem('access_token');
        const r = await fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
    }, [api]);

    // Probe capabilities once when serverId changes.
    useEffect(() => {
        let cancelled = false;
        setCaps(null);
        setFrame(null);
        setError(null);
        fetchJson(`${baseUrl}/capabilities`)
            .then(data => { if (!cancelled) setCaps(data); })
            .catch(err => { if (!cancelled) setError(err.message); });
        return () => { cancelled = true; };
    }, [baseUrl, fetchJson]);

    // Frame polling loop.
    useEffect(() => {
        if (!caps || caps.capability === 'none' || paused) return undefined;

        let cancelled = false;

        const tick = async () => {
            if (cancelled || inflightRef.current) return;
            inflightRef.current = true;
            try {
                const url = `${baseUrl}/frame?scale=${scale}&quality=${quality}&format=jpeg`;
                const data = await fetchJson(url);
                if (cancelled) return;
                setFrame(data);
                setError(null);
            } catch (err) {
                if (cancelled) return;
                setError(err.message);
            } finally {
                inflightRef.current = false;
            }
        };

        tick();
        timerRef.current = setInterval(tick, intervalMs);
        return () => {
            cancelled = true;
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, [caps, paused, intervalMs, scale, quality, baseUrl, fetchJson]);

    if (!caps) {
        return <div className="sk-gui__loading">Probing display capability…</div>;
    }

    if (caps.capability === 'none') {
        return (
            <div className="sk-gui">
                <div className="sk-gui__banner sk-gui__banner--info">
                    No display server detected on this host
                    {caps.reason ? ` (${caps.reason})` : ''}.
                    Showing synthetic desktop.
                </div>
                <SyntheticDesktop api={api} serverId={serverId} fetchJson={fetchJson} />
            </div>
        );
    }

    const imgSrc = frame
        ? `data:image/${frame.format || 'jpeg'};base64,${frame.image_base64}`
        : null;

    return (
        <div className="sk-gui">
            <div className="sk-gui__toolbar">
                <span className="sk-gui__cap">
                    {caps.capability}
                    {caps.resolution ? ` · ${caps.resolution}` : ''}
                </span>
                <button
                    className="sk-gui__btn"
                    onClick={() => setPaused(p => !p)}
                >
                    {paused ? 'Resume' : 'Pause'}
                </button>
                <label className="sk-gui__field">
                    Rate
                    <select
                        value={intervalMs}
                        onChange={e => setIntervalMs(
                            Math.max(FRAME_INTERVAL_MS_MIN,
                                Math.min(FRAME_INTERVAL_MS_MAX, Number(e.target.value)))
                        )}
                    >
                        <option value={2000}>0.5 fps</option>
                        <option value={1000}>1 fps</option>
                        <option value={700}>1.5 fps</option>
                        <option value={500}>2 fps</option>
                        <option value={300}>3 fps</option>
                    </select>
                </label>
                <label className="sk-gui__field">
                    Scale
                    <select
                        value={scale}
                        onChange={e => setScale(Number(e.target.value))}
                    >
                        <option value={0.5}>50%</option>
                        <option value={0.75}>75%</option>
                        <option value={1}>100%</option>
                    </select>
                </label>
                <label className="sk-gui__field">
                    Quality
                    <input
                        type="range"
                        min="20"
                        max="95"
                        value={quality}
                        onChange={e => setQuality(Number(e.target.value))}
                    />
                    <span className="sk-gui__field-num">{quality}</span>
                </label>
            </div>

            <div className="sk-gui__viewport">
                {error && <div className="sk-gui__banner sk-gui__banner--error">{error}</div>}
                {imgSrc ? (
                    <img className="sk-gui__frame" src={imgSrc} alt="Remote desktop frame" />
                ) : (
                    <div className="sk-gui__loading">Waiting for first frame…</div>
                )}
                {frame?.captured_at && (
                    <div className="sk-gui__stamp">
                        {frame.width}×{frame.height} · {new Date(frame.captured_at).toLocaleTimeString()}
                    </div>
                )}
            </div>
        </div>
    );
}
