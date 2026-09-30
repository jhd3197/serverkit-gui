import React, { useState } from 'react';
import { useFormat, useTranslation } from 'serverkit-sdk';

/**
 * Draws a surface-v1 document (vela-contracts/surface-v1.schema.json) with
 * our own components. Pure: it knows nothing about ServerKit, fetching or
 * servers — give it a document and an `onAction(actionId, input)` and it draws.
 *
 * The contract is data, never markup: text renders as text, images are only
 * the inline data: URLs the schema allows, and a button can only name an
 * action the document declared, which the host confirms before running.
 */
export default function SurfaceView({ surface, onAction }) {
    const { t } = useTranslation();
    if (!surface || surface.surface !== 1) {
        return (
            <div className="sk-surface__unsupported">
                {t('gui.surface.unsupportedVersion', 'This view uses a format this version cannot draw.')}
            </div>
        );
    }
    const actions = Object.fromEntries((surface.actions || []).map(a => [a.id, a]));
    return (
        <div className="sk-surface">
            <SurfaceNode node={surface.root} ctx={{ actions, onAction }} />
        </div>
    );
}

const tone = (value) => (value && value !== 'neutral' ? ` sk-tone--${value}` : '');

function SurfaceNode({ node, ctx }) {
    const { t } = useTranslation();
    if (!node || typeof node !== 'object') return null;
    const Component = NODES[node.type];
    if (!Component) {
        // Newer producers may add node types within v1; draw the rest.
        return <div className="sk-surface__unknown">{t('gui.surface.cannotShowPart', 'Cannot show this part.')}</div>;
    }
    const span = node.span ? { gridColumn: `span ${Math.min(node.span, 6)}` } : undefined;
    return <Component node={node} ctx={ctx} style={span} />;
}

function Children({ nodes, ctx }) {
    return (nodes || []).map((child, i) => <SurfaceNode key={child?.id || i} node={child} ctx={ctx} />);
}

function useValueFormatter() {
    const { formatNumber, formatPercent, formatDuration, formatDateTime } = useFormat();
    return (value, format) => {
        if (typeof value !== 'number') {
            if (format === 'time' && typeof value === 'string') return formatDateTime(value);
            return value == null ? '—' : String(value);
        }
        switch (format) {
            case 'percent': return formatPercent(value, { decimals: value < 10 ? 1 : 0 });
            case 'bytes': return formatBytes(value, formatNumber);
            case 'duration': return formatDuration(value);
            case 'time': return formatDateTime(new Date(value));
            default: return formatNumber(value);
        }
    };
}

function formatBytes(bytes, formatNumber) {
    const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
    let value = bytes;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
        value /= 1024;
        unit += 1;
    }
    return `${formatNumber(value, { maximumFractionDigits: unit === 0 ? 0 : 1 })} ${units[unit]}`;
}

// ---- containers

function Stack({ node, ctx, style }) {
    const dir = node.direction === 'row' ? ' sk-surface__stack--row' : '';
    return (
        <div className={`sk-surface__stack${dir} sk-gap--${node.gap || 'm'}`} style={style}>
            <Children nodes={node.children} ctx={ctx} />
        </div>
    );
}

function Grid({ node, ctx, style }) {
    return (
        <div className="sk-surface__grid" style={{ ...style, '--sk-cols': node.columns || 2 }}>
            <Children nodes={node.children} ctx={ctx} />
        </div>
    );
}

function Panel({ node, ctx, style }) {
    return (
        <section className={`sk-surface__panel${tone(node.tone)}`} style={style}>
            {node.title && <h4 className="sk-surface__panel-title">{node.title}</h4>}
            <Children nodes={node.children} ctx={ctx} />
        </section>
    );
}

/**
 * Windows on a wallpaper with a dock. Which windows are minimized is the
 * viewer's state, kept by window id so it survives refreshes; the surface
 * only supplies the starting value.
 */
function Desktop({ node, ctx, style }) {
    const { formatTime } = useFormat();
    const [minimized, setMinimized] = useState({});
    const [focused, setFocused] = useState(null);
    const isMin = (w) => (w.id && w.id in minimized ? minimized[w.id] : Boolean(w.minimized));
    const toggle = (id, value) => setMinimized(prev => ({ ...prev, [id]: value }));

    const openFromDock = (id) => {
        toggle(id, false);
        setFocused(id);
        requestAnimationFrame(() => document.getElementById(`sk-win-${id}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }));
    };

    const windows = node.windows || [];
    return (
        <div className={`sk-synth sk-wallpaper--${node.wallpaper || 'plain'}`} style={style}>
            <div className="sk-synth__wallpaper">
                {node.title && <div className="sk-synth__hostname">{node.title}</div>}
                <div className="sk-synth__windows">
                    {windows.filter(w => !isMin(w)).map((w, i) => (
                        <Window
                            key={w.id || i}
                            node={w}
                            ctx={ctx}
                            focused={focused === w.id}
                            onMinimize={w.id ? () => toggle(w.id, true) : undefined}
                        />
                    ))}
                </div>
            </div>
            <div className="sk-synth__taskbar">
                <span className="sk-synth__start" aria-hidden="true">≡</span>
                {(node.dock || []).map((item, i) => {
                    const target = item.window && windows.some(w => w.id === item.window) ? item.window : null;
                    const Tag = target ? 'button' : 'span';
                    return (
                        <Tag
                            key={item.id || i}
                            type={target ? 'button' : undefined}
                            className={`sk-synth__task${tone(item.tone)}${target && isMin(windows.find(w => w.id === target)) ? ' is-minimized' : ''}`}
                            title={item.label}
                            onClick={target ? () => openFromDock(target) : undefined}
                        >
                            {item.label}
                            {item.badge && <span className="sk-synth__badge">{item.badge}</span>}
                        </Tag>
                    );
                })}
                <span className="sk-synth__clock">{formatTime(new Date(), { seconds: true })}</span>
            </div>
        </div>
    );
}

function Window({ node, ctx, focused, onMinimize }) {
    const { t } = useTranslation();
    return (
        <div
            id={node.id ? `sk-win-${node.id}` : undefined}
            className={`sk-synth__window sk-window--${node.size || 'm'}${tone(node.tone)}${focused ? ' is-focused' : ''}`}
        >
            <div className="sk-synth__titlebar">
                <span className="sk-synth__title">{node.title}</span>
                {onMinimize && (
                    <button
                        type="button"
                        className="sk-synth__minimize"
                        onClick={onMinimize}
                        aria-label={t('gui.surface.minimize', 'Minimize')}
                    >
                        —
                    </button>
                )}
            </div>
            <div className="sk-synth__body">
                <Children nodes={node.children} ctx={ctx} />
            </div>
        </div>
    );
}

// ---- values

function Text({ node, style }) {
    return <p className={`sk-surface__text sk-text--${node.style || 'body'}${tone(node.tone)}`} style={style}>{node.value}</p>;
}

function Stat({ node, style }) {
    const fmt = useValueFormatter();
    return (
        <div className={`sk-surface__stat${tone(node.tone)}`} style={style}>
            {node.label && <div className="sk-surface__label">{node.label}</div>}
            <div className="sk-surface__stat-value">
                {fmt(node.value, node.format)}
                {node.unit && <span className="sk-surface__unit"> {node.unit}</span>}
                {node.delta && <span className="sk-surface__delta"> {node.delta}</span>}
            </div>
            {node.caption && <div className="sk-surface__caption">{node.caption}</div>}
        </div>
    );
}

function Progress({ node, style }) {
    const value = Math.max(0, Math.min(Number(node.value) || 0, 100));
    const fmt = useValueFormatter();
    return (
        <div className={`sk-surface__progress${tone(node.tone)}`} style={style}>
            <div className="sk-surface__row">
                <span className="sk-surface__label">{node.label}</span>
                <span>{fmt(value, 'percent')}</span>
            </div>
            <div className="sk-surface__bar" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
                <span style={{ width: `${value}%` }} />
            </div>
            {node.caption && <div className="sk-surface__caption">{node.caption}</div>}
        </div>
    );
}

function List({ node, style }) {
    return (
        <ul className="sk-surface__list" style={style}>
            {(node.rows || []).map((row, i) => (
                <li key={row.id || i} className={tone(row.tone).trim()}>
                    <span className="sk-surface__list-label">{row.label}</span>
                    {row.detail && <span className="sk-surface__list-detail">{row.detail}</span>}
                    {row.badge && <span className={`sk-surface__badge${tone(row.tone)}`}>{row.badge}</span>}
                    {typeof row.progress === 'number' && (
                        <span className="sk-surface__bar sk-surface__bar--inline"><span style={{ width: `${Math.max(0, Math.min(row.progress, 100))}%` }} /></span>
                    )}
                </li>
            ))}
        </ul>
    );
}

function KeyValue({ node, style }) {
    const fmt = useValueFormatter();
    return (
        <dl className="sk-synth__kv" style={style}>
            {(node.rows || []).map((row, i) => (
                <React.Fragment key={`${row.label}-${i}`}>
                    <dt>{row.label}</dt>
                    <dd>{fmt(row.value, row.format)}</dd>
                </React.Fragment>
            ))}
        </dl>
    );
}

function Chart({ node, style }) {
    const series = (node.series || []).filter(Number.isFinite);
    if (series.length < 2) return null;
    const [min, max] = Array.isArray(node.domain) ? node.domain : [Math.min(...series), Math.max(...series)];
    const range = max - min || 1;
    const y = (v) => 30 - ((Math.max(min, Math.min(v, max)) - min) / range) * 30;
    const step = 100 / (series.length - 1);
    return (
        <figure className={`sk-surface__chart${tone(node.tone)}`} style={style}>
            {node.label && <figcaption className="sk-surface__label">{node.label}</figcaption>}
            <svg viewBox="0 0 100 30" preserveAspectRatio="none" role="img" aria-label={node.label || ''}>
                {node.kind === 'line' ? (
                    <polyline fill="none" vectorEffect="non-scaling-stroke" points={series.map((v, i) => `${i * step},${y(v)}`).join(' ')} />
                ) : (
                    series.map((v, i) => {
                        const w = 100 / series.length;
                        return <rect key={i} x={i * w + w * 0.15} width={w * 0.7} y={y(v)} height={30 - y(v)} opacity={i === series.length - 1 ? 1 : 0.55} />;
                    })
                )}
            </svg>
            {node.caption && <div className="sk-surface__caption">{node.caption}</div>}
        </figure>
    );
}

function Table({ node, style }) {
    const fmt = useValueFormatter();
    const columns = node.columns || [];
    return (
        <div className="sk-surface__table-wrap" style={style}>
            <table className="sk-surface__table">
                <thead>
                    <tr>{columns.map(c => <th key={c.key} className={`sk-align--${c.align || 'start'}`}>{c.label}</th>)}</tr>
                </thead>
                <tbody>
                    {(node.rows || []).map((row, i) => (
                        <tr key={i}>
                            {columns.map(c => <td key={c.key} className={`sk-align--${c.align || 'start'}`}>{fmt(row[c.key], c.format)}</td>)}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function Badge({ node, style }) {
    return <span className={`sk-surface__badge${tone(node.tone)}`} style={style}>{node.label}</span>;
}

function Button({ node, ctx, style }) {
    const { t } = useTranslation();
    const [state, setState] = useState('idle'); // idle | confirm | busy | done | error
    const [error, setError] = useState(null);
    const action = ctx.actions[node.action];
    if (!action || !ctx.onAction) return null; // undeclared actions are refused, not drawn

    const run = async () => {
        setState('busy');
        setError(null);
        try {
            await ctx.onAction(action.id, node.input || {});
            setState('done');
            setTimeout(() => setState('idle'), 2500);
        } catch (err) {
            setError(err?.message || String(err));
            setState('error');
        }
    };
    const mustConfirm = action.danger || action.confirm;

    if (state === 'confirm') {
        return (
            <span className="sk-surface__confirm" style={style}>
                <span>{action.confirm || t('gui.surface.confirmAction', 'Run “{{title}}”?', { title: action.title })}</span>
                <button type="button" className={`sk-surface__button${action.danger ? ' sk-tone--bad' : ''}`} onClick={run}>
                    {node.label}
                </button>
                <button type="button" className="sk-surface__button sk-surface__button--ghost" onClick={() => setState('idle')}>
                    {t('gui.surface.cancel', 'Cancel')}
                </button>
            </span>
        );
    }
    return (
        <span className="sk-surface__action" style={style}>
            <button
                type="button"
                className={`sk-surface__button${tone(node.tone)}`}
                disabled={state === 'busy'}
                title={action.title}
                onClick={() => (mustConfirm ? setState('confirm') : run())}
            >
                {state === 'busy' ? t('gui.surface.working', 'Working…') : state === 'done' ? t('gui.surface.done', 'Done') : node.label}
            </button>
            {state === 'error' && <span className="sk-surface__caption sk-tone--bad">{error}</span>}
        </span>
    );
}

const INLINE_IMAGE = /^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$/;

function Image({ node, style }) {
    if (typeof node.src !== 'string' || !INLINE_IMAGE.test(node.src)) return null;
    return (
        <img
            className={`sk-surface__image sk-fit--${node.fit || 'contain'}`}
            src={node.src}
            alt={node.alt || ''}
            width={node.width}
            height={node.height}
            style={style}
        />
    );
}

function Divider({ style }) {
    return <hr className="sk-surface__divider" style={style} />;
}

function Empty({ node, style }) {
    return <div className="sk-surface__empty" style={style}>{node.message}</div>;
}

const NODES = {
    stack: Stack,
    grid: Grid,
    panel: Panel,
    desktop: Desktop,
    text: Text,
    stat: Stat,
    progress: Progress,
    list: List,
    keyvalue: KeyValue,
    chart: Chart,
    table: Table,
    badge: Badge,
    button: Button,
    image: Image,
    divider: Divider,
    empty: Empty,
};
