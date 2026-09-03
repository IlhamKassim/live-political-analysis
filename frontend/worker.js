// MyPolitik — Cloudflare Worker. Serves the static map app + a health probe.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    // force HTTPS + canonical apex host in one 301: plain-http hits (typed URLs,
    // old links) showed "Not secure", and the old www redirect kept the incoming
    // protocol, bouncing www visitors to http://
    if (url.protocol === "http:" || url.hostname.startsWith("www.")) {
      url.protocol = "https:";
      if (url.hostname.startsWith("www.")) url.hostname = url.hostname.slice(4);
      return Response.redirect(url.toString(), 301);
    }
    if (url.pathname === "/api/health") {
      return Response.json({ ok: true, app: "mypolitik", ts: Date.now() });
    }
    if (url.pathname === "/api/live/johor") {
      if (request.method === "PUT") {
        const expected = env.LIVE_PUBLISH_TOKEN;
        const supplied = request.headers.get("authorization")?.replace(/^Bearer\s+/i, "")
          || request.headers.get("x-live-publish-token");
        if (!expected || supplied !== expected) {
          return Response.json({ error: "unauthorized" }, { status: 401 });
        }
        if (!env.PRN_LIVE) {
          return Response.json({ error: "live store unavailable" }, { status: 503 });
        }
        let body;
        try {
          if (Number(request.headers.get("content-length") || 0) > 300000) throw new Error("payload too large");
          body = await request.json();
        } catch (_) {
          return Response.json({ error: "invalid live payload" }, { status: 400 });
        }
        if (!body || typeof body !== "object" || body.election !== "prn16-johor" || !body.seats || typeof body.seats !== "object") {
          return Response.json({ error: "invalid live payload" }, { status: 422 });
        }
        await env.PRN_LIVE.put("johor", JSON.stringify(body), { expirationTtl: 900 });
        return Response.json({ ok: true, updated: body.updated || null });
      }
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
        headers: { "cache-control": "public, max-age=5, stale-while-revalidate=15" },
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
