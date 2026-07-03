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
    return env.ASSETS.fetch(request);
  },
};
