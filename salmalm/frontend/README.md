# Frontend/UX Rules

## Files
- `templates.py` — All HTML/CSS/JS (single-file SPA, no build step)
- `web.py` — HTTP handler, routing, CSP headers, static assets

## Architecture
- Single-page app rendered as Python triple-quoted string in `templates.py`.
- No framework (React/Vue/etc). Pure vanilla JS with event delegation.
- `web.py` injects nonce into `<script>` tags at render time via `_html()`.

## CSP (Content Security Policy)
- `script-src 'nonce-{hex}'` — NO `unsafe-inline`. All scripts need nonce.
- `style-src 'self' 'unsafe-inline' fonts.googleapis.com fonts.gstatic.com`
- Inline `onclick`/`onchange`/`onkeydown` are **banned**. Use `data-action` attributes.
- Event delegation: single `document.addEventListener('click')` routes all actions.
- Programmatic `.onclick = function(){}` in JS is CSP-safe (not inline).

## JS in Python Strings — Critical
- templates.py uses `'''...'''` (triple single-quote).
- **All JS regex backslashes must be doubled**: `\\w`, `\\d`, `\\s`, `\\[`, `\\]`, etc.
- Single `\w` = Python invalid escape = **SyntaxError on Python 3.13+**.
- Use `\\x27` for single quotes inside JS strings (not `\'`).
- Test: `python -W error -c "from salmalm.templates import WEB_HTML"` must pass.

## Event Delegation Pattern
```js
document.addEventListener('click', function(e) {
  var el = e.target.closest('[data-action]');
  if (!el) return;
  var a = el.getAttribute('data-action');
  if (a === 'myAction') window.myFunction();
});
```

## Adding a New Button
1. Add HTML with `data-action="myAction"` (NO onclick).
2. Add handler in the `document.addEventListener('click')` block.
3. Define `window.myFunction` before the delegation block.

## Mobile
- `@media(max-width:700px)` for mobile-only rules.
- **Never touch `@media(max-width:900px)`** — breaks desktop layout.
- Mobile fixes go inside 700px media query only.

## Styling
- CSS variables for theming: `--bg`, `--text`, `--accent`, `--accent-dim`, etc.
- Dark theme = default. No pure black (#000) backgrounds — use `#181926`.
- No max-saturation neon. Keep colors muted.
- Inter font for body, pixel font (neodgm) optional for headers.
- Inline `style=` attributes are tolerated but prefer CSS classes when possible.

## PWA
- Service worker (`/sw.js`) only registers in standalone PWA mode.
- Don't register SW on mobile web browsers.
- Manifest at `/manifest.json`, icons at `/icon-192.svg` and `/icon-512.svg`.
