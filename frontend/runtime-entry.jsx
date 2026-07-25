// Runtime-ESM entry for ServerKit's no-rebuild loader (panel plan 25).
//
// Same exports as index.js, but the CSS is imported as a STRING (?inline) and
// injected at module load, so the single dist/index.mjs the panel blob-imports
// carries its own styles — no separate .css asset the runtime loader wouldn't
// fetch. Shared libs (react, react-router-dom) are externalized by vite.config
// and resolved to the panel's singletons via its import map.
import css from './styles/server-gui.css?inline';
import ServerGuiLauncher from './components/ServerGuiLauncher.jsx';

if (typeof document !== 'undefined' && !document.getElementById('serverkit-gui-styles')) {
    const style = document.createElement('style');
    style.id = 'serverkit-gui-styles';
    style.textContent = css;
    document.head.appendChild(style);
}

export default ServerGuiLauncher;
export { default as ServerGuiTab } from './components/ServerGui.jsx';
