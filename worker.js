// Peta YB — Cloudflare Worker. Serves the static map app + a health probe.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/health") {
      return Response.json({ ok: true, app: "politics", ts: Date.now() });
    }
    return env.ASSETS.fetch(request);
  },
};
