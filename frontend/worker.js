// PolitikKu — Cloudflare Worker. Serves the static map app + a health probe.
//
// Step 5 of the PolitikKu x mypolitik merge (ADR 0013): the main site now
// lives on GitHub Pages (politikku.my), not this Worker, so the live-mode
// GET below is a cross-origin fetch from the browser and needs an explicit
// CORS allow-list — echoing back a matched Origin, never a wildcard, since
// a wildcard would also authorize any other site to read live results
// through a visitor's browser.
const ALLOWED_LIVE_ORIGINS = new Set([
  "https://politikku.my",
  "https://www.politikku.my",
  "http://localhost:4178", // frontend/dev-server.py's default port
]);

function liveCorsHeaders(request) {
  const origin = request.headers.get("origin");
  if (!origin || !ALLOWED_LIVE_ORIGINS.has(origin)) return {};
  return { "access-control-allow-origin": origin, vary: "origin" };
}

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
      return Response.json({ ok: true, app: "politikku", ts: Date.now() });
    }
    const liveMatch = url.pathname.match(/^\/api\/live\/([a-zA-Z0-9_-]+)$/);
    if (liveMatch) {
      const electionId = liveMatch[1];
      const kvStore = env.LIVE_ELECTIONS || env.PRN_LIVE;
      if (request.method === "PUT") {
        const expected = env.LIVE_PUBLISH_TOKEN;
        const supplied = request.headers.get("authorization")?.replace(/^Bearer\s+/i, "")
          || request.headers.get("x-live-publish-token");
        if (!expected || supplied !== expected) {
          return Response.json({ error: "unauthorized" }, { status: 401 });
        }
        if (!kvStore) {
          return Response.json({ error: "live store unavailable" }, { status: 503 });
        }
        let body;
        try {
          if (Number(request.headers.get("content-length") || 0) > 300000) throw new Error("payload too large");
          body = await request.json();
        } catch (_) {
          return Response.json({ error: "invalid live payload" }, { status: 400 });
        }
        const matchesElection = body && typeof body === "object" && (
          body.election === electionId ||
          (electionId === "johor" && body.election === "prn16-johor") ||
          (typeof body.election === "string" && body.election.endsWith(`-${electionId}`))
        );
        if (!matchesElection || !body.seats || typeof body.seats !== "object") {
          return Response.json({ error: "invalid live payload" }, { status: 422 });
        }
        await kvStore.put(electionId, JSON.stringify(body), { expirationTtl: 900 });
        if (electionId === "prn16-johor") {
          try { await kvStore.put("johor", JSON.stringify(body), { expirationTtl: 900 }); } catch (_) {}
        } else if (electionId === "johor") {
          try { await kvStore.put("prn16-johor", JSON.stringify(body), { expirationTtl: 900 }); } catch (_) {}
        }
        return Response.json({ ok: true, updated: body.updated || null });
      }
      // Live state for electionId, in preference order:
      // 1. KV (binding LIVE_ELECTIONS / PRN_LIVE, key electionId)
      // 2. Baked asset /data/live-<electionId>.json (or /data/live-<suffix>.json fallback)
      // 3. Campaign default
      let live = null;
      try {
        if (kvStore) {
          live = await kvStore.get(electionId, { type: "json" });
          if (!live && electionId === "johor") {
            live = await kvStore.get("prn16-johor", { type: "json" });
          } else if (!live && electionId === "prn16-johor") {
            live = await kvStore.get("johor", { type: "json" });
          }
        }
      } catch (_) {}
      if (!live && env.ASSETS) {
        const candidatePaths = [`/data/live-${electionId}.json`];
        if (electionId.includes("-")) {
          const suffix = electionId.split("-").slice(1).join("-");
          candidatePaths.push(`/data/live-${suffix}.json`);
        }
        if (electionId === "johor") {
          candidatePaths.push("/data/live-prn16-johor.json");
        }
        for (const p of candidatePaths) {
          try {
            const a = await env.ASSETS.fetch(new URL(p, url.origin));
            if (a.ok) {
              live = await a.json();
              break;
            }
          } catch (_) {}
        }
      }
      return Response.json(live || { phase: "campaign", election: electionId }, {
        headers: {
          "cache-control": "public, max-age=5, stale-while-revalidate=15",
          ...liveCorsHeaders(request),
        },
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
