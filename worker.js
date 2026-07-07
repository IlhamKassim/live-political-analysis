// MyPolitik — Cloudflare Worker. Serves the static map app + a health probe.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    // canonical host: send www.* → the apex (301), so mypolitik.xyz is the one true URL
    if (url.hostname.startsWith("www.")) {
      url.hostname = url.hostname.slice(4);
      return Response.redirect(url.toString(), 301);
    }
    if (url.pathname === "/api/health") {
      return Response.json({ ok: true, app: "mypolitik", ts: Date.now() });
    }
    if (url.pathname === "/api/live/johor") {
      // PRN16 Johor live state, in preference order:
      // 1. KV (binding PRN_LIVE, key "johor") — instant no-deploy publishing, if bound;
      // 2. the baked asset /data/live-johor.json — the poller republishes it via a
      //    ~15s `wrangler deploy` each cycle (works with the deploy-scoped token);
      // 3. campaign default.
      let live = null;
      try {
        if (env.PRN_LIVE) live = await env.PRN_LIVE.get("johor", { type: "json" });
      } catch (_) {}
      if (!live) {
        try {
          const a = await env.ASSETS.fetch(new URL("/data/live-johor.json", url.origin));
          if (a.ok) live = await a.json();
        } catch (_) {}
      }
      return Response.json(live || { phase: "campaign" }, {
        headers: { "cache-control": "public, max-age=45" },
      });
    }
    // Never let the edge/browser serve a stale HTML entry: the document is tiny and
    // carries the versioned (?v=N) asset URLs, so keeping it fresh means a deploy is
    // always picked up on the next load (fixes "it hasn't changed" after a deploy).
    // Versioned JS/CSS keep their default cacheability — the ?v= bump busts those.
    const resp = await env.ASSETS.fetch(request);
    if ((resp.headers.get("content-type") || "").includes("text/html")) {
      const headers = new Headers(resp.headers);
      headers.set("cache-control", "no-store");
      return new Response(resp.body, { status: resp.status, statusText: resp.statusText, headers });
    }
    return resp;
  },
};
