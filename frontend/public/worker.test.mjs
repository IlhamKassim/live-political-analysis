// Unit tests for frontend/worker.js parameterized live endpoints — run with `node --test`.
import { test } from "node:test";
import assert from "node:assert/strict";
import worker from "../worker.js";

class MemoryKV {
  constructor(initial = {}) {
    this.store = new Map(Object.entries(initial));
  }
  async get(key, opts) {
    const val = this.store.get(key);
    if (val === undefined) return null;
    if (opts && opts.type === "json") return JSON.parse(val);
    return val;
  }
  async put(key, val) {
    this.store.set(key, typeof val === "string" ? val : JSON.stringify(val));
  }
}

function makeEnv(kvStore, token = "test-token") {
  return {
    PRN_LIVE: kvStore,
    LIVE_PUBLISH_TOKEN: token,
    ASSETS: {
      fetch: async (input) => {
        const urlStr = typeof input === "string" ? input : (input.url || input.href || input.toString());
        const u = new URL(urlStr);
        if (u.pathname === "/data/live-johor.json" || u.pathname === "/data/live-prn16-johor.json") {
          return new Response(JSON.stringify({
            phase: "final",
            election: "prn16-johor",
            seats: { "1_N.01": { status: "official", coalition: "BN" } }
          }), { status: 200, headers: { "Content-Type": "application/json" } });
        }
        return new Response("Not found", { status: 404 });
      }
    }
  };
}

test("worker: GET /api/health probe", async () => {
  const req = new Request("https://mypolitik.xyz/api/health");
  const resp = await worker.fetch(req, makeEnv(new MemoryKV()));
  assert.equal(resp.status, 200);
  const data = await resp.json();
  assert.equal(data.ok, true);
  assert.equal(data.app, "mypolitik");
});

test("worker: GET /api/live/johor falls back to baked asset when KV empty", async () => {
  const req = new Request("https://mypolitik.xyz/api/live/johor");
  const resp = await worker.fetch(req, makeEnv(new MemoryKV()));
  assert.equal(resp.status, 200);
  const data = await resp.json();
  assert.equal(data.phase, "final");
  assert.equal(data.election, "prn16-johor");
  assert.ok(data.seats["1_N.01"]);
});

test("worker: GET /api/live/prn16-johor falls back to asset with suffix match", async () => {
  const req = new Request("https://mypolitik.xyz/api/live/prn16-johor");
  const resp = await worker.fetch(req, makeEnv(new MemoryKV()));
  assert.equal(resp.status, 200);
  const data = await resp.json();
  assert.equal(data.phase, "final");
  assert.equal(data.election, "prn16-johor");
});

test("worker: GET /api/live/<unknown> returns campaign default", async () => {
  const req = new Request("https://mypolitik.xyz/api/live/prn17-melaka");
  const resp = await worker.fetch(req, makeEnv(new MemoryKV()));
  assert.equal(resp.status, 200);
  const data = await resp.json();
  assert.equal(data.phase, "campaign");
  assert.equal(data.election, "prn17-melaka");
});

test("worker: GET /api/live/:electionId echoes an allowed Origin in CORS headers", async () => {
  // Step 5 (ADR 0013): the main site now fetches this cross-origin from
  // politikku.my, so the response needs an explicit allow-list match, not
  // just a working fetch.
  const req = new Request("https://politikku.ilhamkassim2003.workers.dev/api/live/prn17-melaka", {
    headers: { origin: "https://politikku.my" },
  });
  const resp = await worker.fetch(req, makeEnv(new MemoryKV()));
  assert.equal(resp.status, 200);
  assert.equal(resp.headers.get("access-control-allow-origin"), "https://politikku.my");
  assert.equal(resp.headers.get("vary"), "origin");
});

test("worker: GET /api/live/:electionId omits CORS headers for a disallowed Origin", async () => {
  const req = new Request("https://politikku.ilhamkassim2003.workers.dev/api/live/prn17-melaka", {
    headers: { origin: "https://evil.example" },
  });
  const resp = await worker.fetch(req, makeEnv(new MemoryKV()));
  assert.equal(resp.status, 200);
  assert.equal(resp.headers.get("access-control-allow-origin"), null);
});

test("worker: PUT /api/live/:electionId rejects unauthorized requests", async () => {
  const kv = new MemoryKV();
  const env = makeEnv(kv, "secret-key");
  const req = new Request("https://mypolitik.xyz/api/live/prn16-johor", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ election: "prn16-johor", seats: {} }),
  });
  const resp = await worker.fetch(req, env);
  assert.equal(resp.status, 401);
  const data = await resp.json();
  assert.equal(data.error, "unauthorized");
});

test("worker: PUT /api/live/:electionId rejects mismatched election payload", async () => {
  const kv = new MemoryKV();
  const env = makeEnv(kv, "secret-key");
  const req = new Request("https://mypolitik.xyz/api/live/prn17-sarawak", {
    method: "PUT",
    headers: {
      "Authorization": "Bearer secret-key",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ election: "prn16-johor", seats: {} }),
  });
  const resp = await worker.fetch(req, env);
  assert.equal(resp.status, 422);
  const data = await resp.json();
  assert.equal(data.error, "invalid live payload");
});

test("worker: PUT /api/live/:electionId updates KV and serves on subsequent GET", async () => {
  const kv = new MemoryKV();
  const env = makeEnv(kv, "secret-key");
  const payload = {
    election: "prn17-melaka",
    phase: "live",
    updated: "2026-11-20T20:00:00+08:00",
    seats: { "4_N.01": { status: "won", coalition: "BN" } }
  };
  const putReq = new Request("https://mypolitik.xyz/api/live/prn17-melaka", {
    method: "PUT",
    headers: {
      "Authorization": "Bearer secret-key",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const putResp = await worker.fetch(putReq, env);
  assert.equal(putResp.status, 200);
  const putData = await putResp.json();
  assert.equal(putData.ok, true);

  // Now GET /api/live/prn17-melaka should return the updated KV state
  const getReq = new Request("https://mypolitik.xyz/api/live/prn17-melaka");
  const getResp = await worker.fetch(getReq, env);
  assert.equal(getResp.status, 200);
  const getData = await getResp.json();
  assert.equal(getData.phase, "live");
  assert.equal(getData.election, "prn17-melaka");
  assert.equal(getData.seats["4_N.01"].status, "won");
});

test("worker: legacy PUT /api/live/johor accepts prn16-johor payload and syncs aliases", async () => {
  const kv = new MemoryKV();
  const env = makeEnv(kv, "secret-key");
  const payload = {
    election: "prn16-johor",
    phase: "live",
    updated: "2026-07-11T21:00:00+08:00",
    seats: { "1_N.01": { status: "won", coalition: "BN" } }
  };
  const putReq = new Request("https://mypolitik.xyz/api/live/johor", {
    method: "PUT",
    headers: {
      "X-Live-Publish-Token": "secret-key",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const putResp = await worker.fetch(putReq, env);
  assert.equal(putResp.status, 200);

  // Both /api/live/johor and /api/live/prn16-johor should read this
  const getReq1 = new Request("https://mypolitik.xyz/api/live/johor");
  const getResp1 = await worker.fetch(getReq1, env);
  const data1 = await getResp1.json();
  assert.equal(data1.phase, "live");
  assert.equal(data1.seats["1_N.01"].status, "won");

  const getReq2 = new Request("https://mypolitik.xyz/api/live/prn16-johor");
  const getResp2 = await worker.fetch(getReq2, env);
  const data2 = await getResp2.json();
  assert.equal(data2.phase, "live");
  assert.equal(data2.seats["1_N.01"].status, "won");
});
