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
    return env.ASSETS.fetch(request);
  },
};
