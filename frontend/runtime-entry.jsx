// Runtime-ESM entry for ServerKit's no-rebuild loader (panel plan 25).
//
// Same exports as index.js, but the CSS is imported as a STRING (?inline) and
// injected at module load, so the single dist/index.mjs the panel blob-imports
// carries its own styles — no separate .css asset the runtime loader wouldn't
// fetch. Shared libs (react, react-router-dom) are externalized by vite.config
// and resolved to the panel's singletons via its import map.
import css from './styles/server-gui.css?inline';
import ServerGuiLauncher from './components/ServerGuiLauncher.jsx';

// Translations. Registered against the PANEL's i18next singleton (shared via
// its vendor import map), additively and under this extension's own
// `gui` namespace — never init() or changeLanguage(), which the panel
// owns and which would reconfigure or switch the language everywhere.
//
// The English bundle is generated from the inline t('key', 'English')
// defaults, so a key with no bundle still renders its default. More locales
// drop in beside en.json with one addResourceBundle line each.
import i18next from 'i18next';
import en from './locales/en.json';

for (const [language, bundle] of Object.entries({ en })) {
    i18next.addResourceBundle(language, 'translation', bundle, true, false);
}


if (typeof document !== 'undefined' && !document.getElementById('serverkit-gui-styles')) {
    const style = document.createElement('style');
    style.id = 'serverkit-gui-styles';
    style.textContent = css;
    document.head.appendChild(style);
}

export default ServerGuiLauncher;
export { default as ServerGuiTab } from './components/ServerGui.jsx';
