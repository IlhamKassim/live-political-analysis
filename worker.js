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
      // PRN16 Johor live state. On polling night a poller PUTs the derived results
      // into KV (binding PRN_LIVE, key "johor") — phase flips campaign→live→final
      // without a deploy. Until the binding/key exists, serve the campaign default.
      let live = null;
      try {
        if (env.PRN_LIVE) live = await env.PRN_LIVE.get("johor", { type: "json" });
      } catch (_) {}
      return Response.json(live || { phase: "campaign" }, {
        headers: { "cache-control": "public, max-age=60" },
      });
    }
    return env.ASSETS.fetch(request);
  },
};
