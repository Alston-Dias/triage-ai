/**
 * preserveProxyRouting.js
 *
 * Some deployment proxies (e.g. solution3.demopersistent.com) route requests
 * to a specific backend container based on a query-string parameter such as
 * `?app=<uuid>`. The browser:
 *   • drops the query string when fetching sub-resources, and
 *   • removes the query string from the URL bar whenever client-side
 *     routing calls history.pushState('/some-route') without re-appending it.
 *
 * When that happens, a page reload sends the proxy a URL with no routing
 * param → 503. To survive reloads / bookmarks / shared links we keep the
 * routing params pinned to the URL bar at all times.
 *
 * IMPORTANT: this module must be imported BEFORE any router code so the
 * history methods are patched before React Router (or any other router)
 * grabs references to them.
 */

// Snapshot the params present on first load. We deliberately store a frozen
// copy: even if a future navigation strips them, we still know what to
// re-attach.
const INITIAL_SEARCH = (() => {
  try {
    return new URLSearchParams(window.location.search);
  } catch {
    return new URLSearchParams();
  }
})();

// Public read-only accessor used by lib/api.js to forward the same params
// onto outgoing /api/* requests and WebSocket upgrades.
export const INITIAL_QUERY = INITIAL_SEARCH;
export const getRoutingQueryString = () => {
  const s = INITIAL_SEARCH.toString();
  return s ? `?${s}` : '';
};

// If the initial URL had no routing params there is nothing to preserve.
if (INITIAL_SEARCH.toString()) {
  const ensureParams = (urlLike) => {
    if (urlLike == null) return urlLike;
    try {
      // history.pushState/replaceState accept absolute URLs, relative paths,
      // or even empty strings (means "current URL"). URL() handles all three
      // when given a base.
      const u = new URL(String(urlLike), window.location.href);

      // Only inject params for navigations that stay on the same origin.
      if (u.origin !== window.location.origin) return urlLike;

      let changed = false;
      INITIAL_SEARCH.forEach((value, key) => {
        if (!u.searchParams.has(key)) {
          u.searchParams.set(key, value);
          changed = true;
        }
      });
      if (!changed) return urlLike;
      // Return a same-origin relative form so the browser's URL bar stays clean.
      return `${u.pathname}${u.search}${u.hash}`;
    } catch {
      return urlLike;
    }
  };

  const wrap = (name) => {
    const original = window.history[name];
    if (typeof original !== 'function' || original.__proxyRoutingWrapped) return;
    const wrapped = function (state, title, url) {
      return original.call(this, state, title, ensureParams(url));
    };
    wrapped.__proxyRoutingWrapped = true;
    window.history[name] = wrapped;
  };
  wrap('pushState');
  wrap('replaceState');

  // If something (or the back/forward button) manages to land us on a URL
  // without the routing params, silently put them back.
  const reconcile = () => {
    const need = [];
    const current = new URLSearchParams(window.location.search);
    INITIAL_SEARCH.forEach((value, key) => {
      if (!current.has(key)) need.push([key, value]);
    });
    if (!need.length) return;
    need.forEach(([k, v]) => current.set(k, v));
    const newUrl = `${window.location.pathname}?${current.toString()}${window.location.hash}`;
    // replaceState here is already our wrapped version, which is a no-op for
    // params it would re-add; calling the original avoids any re-entry.
    window.history.replaceState(window.history.state, '', newUrl);
  };
  window.addEventListener('popstate', reconcile);
  // Run once on boot too — defends against scripts that mutated the URL
  // before this module loaded (e.g. analytics that strip query strings).
  reconcile();
}
