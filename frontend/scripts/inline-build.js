/* eslint-disable no-console */
/**
 * Post-build inliner.
 *
 * Why this exists
 * ---------------
 * Our deployment proxy routes requests using a `?app=<uuid>` query string.
 * The browser drops query strings when fetching sub-resources, so requests
 * like `/static/css/main.xxx.css` arrive at the proxy WITHOUT the routing
 * parameter and the proxy answers 503.
 *
 * To work around that we inline every local CSS/JS chunk produced by CRA
 * into `index.html`, leaving a single self-contained HTML document. The
 * only network request the browser must make to load the SPA is the
 * initial document — which always carries the proxy's `?app=<uuid>` and
 * therefore succeeds.
 *
 * This script ONLY inlines local `/static/...` assets. External URLs
 * (fonts.googleapis.com, posthog, emergent badge, etc.) are left alone.
 */

const fs = require('fs');
const path = require('path');

const BUILD_DIR = path.resolve(__dirname, '..', 'build');
const INDEX_HTML = path.join(BUILD_DIR, 'index.html');

function readBuildFile(publicPath) {
  // publicPath is what appears in href/src, e.g. "/static/css/main.abc.css"
  // Map "/static/..." -> "<BUILD_DIR>/static/..."
  if (!publicPath.startsWith('/')) return null;
  const onDisk = path.join(BUILD_DIR, publicPath.replace(/^\/+/, ''));
  if (!fs.existsSync(onDisk)) return null;
  return fs.readFileSync(onDisk, 'utf8');
}

function escapeForScriptTag(js) {
  // Prevent the browser from terminating our inline <script> block early
  // if the bundled code contains the literal characters `</script`.
  return js.replace(/<\/script/gi, '<\\/script');
}

function inlineCss(html) {
  // Match any <link ...> that has both rel="stylesheet" and href="...",
  // regardless of attribute order. We capture the full tag, then extract
  // the href on a successful rel match.
  const linkRe = /<link\b[^>]*>/gi;
  return html.replace(linkRe, (tag) => {
    if (!/\brel=["']stylesheet["']/i.test(tag)) return tag;
    const hrefMatch = tag.match(/\bhref=["']([^"']+)["']/i);
    if (!hrefMatch) return tag;
    const href = hrefMatch[1];
    if (!href.startsWith('/static/')) return tag; // leave external sheets alone
    const css = readBuildFile(href);
    if (css == null) {
      console.warn(`[inline-build] CSS not found on disk: ${href} (leaving link tag)`);
      return tag;
    }
    console.log(`[inline-build] inlined CSS  ${href} (${css.length} bytes)`);
    return `<style data-inlined-from="${href}">\n${css}\n</style>`;
  });
}

function inlineJs(html) {
  // Match: <script ... src="/static/js/...js" ...></script>
  // We collect each inlined script in order, replace the original tag with
  // a placeholder comment, then move all inlined scripts to just before
  // </body>. This preserves CRA's `defer` semantics (run after DOM parse).
  const scriptRe = /<script\b([^>]*)\bsrc=["']([^"']+)["']([^>]*)><\/script>/gi;
  const inlinedScripts = [];

  let processed = html.replace(scriptRe, (match, pre, src, post) => {
    if (!src.startsWith('/static/')) return match; // leave external scripts alone
    const js = readBuildFile(src);
    if (js == null) {
      console.warn(`[inline-build] JS not found on disk: ${src} (leaving script tag)`);
      return match;
    }
    // Preserve attributes other than src/defer/async (defer + async are
    // meaningless for inline scripts and we'll relocate the tag to the end
    // of <body> ourselves to mimic defer ordering).
    const attrs = `${pre} ${post}`
      .replace(/\bdefer(=["'][^"']*["'])?/gi, '')
      .replace(/\basync(=["'][^"']*["'])?/gi, '')
      .replace(/\s+/g, ' ')
      .trim();
    const attrStr = attrs ? ` ${attrs}` : '';
    console.log(`[inline-build] inlined JS   ${src} (${js.length} bytes) -> moved to end of <body>`);
    inlinedScripts.push(
      `<script data-inlined-from="${src}"${attrStr}>\n${escapeForScriptTag(js)}\n</script>`
    );
    return `<!-- inlined: ${src} -->`;
  });

  if (inlinedScripts.length) {
    const block = `\n${inlinedScripts.join('\n')}\n`;
    if (/<\/body>/i.test(processed)) {
      processed = processed.replace(/<\/body>/i, `${block}</body>`);
    } else {
      processed += block;
    }
  }
  return processed;
}

function main() {
  if (!fs.existsSync(INDEX_HTML)) {
    console.error(`[inline-build] ${INDEX_HTML} not found — did 'craco build' run?`);
    process.exit(1);
  }
  const original = fs.readFileSync(INDEX_HTML, 'utf8');
  let out = original;
  out = inlineCss(out);
  out = inlineJs(out);
  fs.writeFileSync(INDEX_HTML, out, 'utf8');

  const beforeKb = (Buffer.byteLength(original) / 1024).toFixed(1);
  const afterKb = (Buffer.byteLength(out) / 1024).toFixed(1);
  console.log(`[inline-build] index.html: ${beforeKb} KB -> ${afterKb} KB`);
}

main();
