import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'serverkit-sdk';
import SurfaceView from './SurfaceView.jsx';

const MIN_REFRESH_MS = 2000;
const DEFAULT_REFRESH_MS = 4000;

/**
 * The server as a surface-v1 desktop, for hosts without a display. The
 * backend builds the document from agent data (backend/surface.py); this
 * component only polls it and hands it to SurfaceView.
 */
export default function SyntheticDesktop({ serverId, fetchJson }) {
    const { t } = useTranslation();
    const [surface, setSurface] = useState(null);
    const [error, setError] = useState(null);
    const [reloadKey, setReloadKey] = useState(0);

    const every = surface?.refresh?.every;
    useEffect(() => {
        let cancelled = false;
        const load = () => {
            fetchJson(`/server-gui/${serverId}/surface`)
                .then(d => { if (!cancelled) { setSurface(d); setError(null); } })
                .catch(err => { if (!cancelled) setError(err.message); });
        };
        load();
        // The document's refresh is a floor: never poll faster than it asks.
        const ms = Math.max(MIN_REFRESH_MS, every ? every * 1000 : DEFAULT_REFRESH_MS);
        const id = setInterval(load, ms);
        return () => { cancelled = true; clearInterval(id); };
    }, [serverId, fetchJson, every, reloadKey]);

    const onAction = useCallback(async (actionId, input) => {
        await fetchJson(`/server-gui/${serverId}/actions/${encodeURIComponent(actionId)}`, {
            method: 'POST',
            body: { input },
        });
        setReloadKey(k => k + 1);
    }, [serverId, fetchJson]);

    if (error && !surface) return <div className="sk-gui__banner sk-gui__banner--error">{error}</div>;
    if (!surface) return <div className="sk-gui__loading">{t('gui.syntheticDesktop.loadingSyntheticDesktop', 'Loading synthetic desktop…')}</div>;

    return <SurfaceView surface={surface} onAction={onAction} />;
}
