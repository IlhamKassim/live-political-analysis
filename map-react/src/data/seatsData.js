import defaultSeats from "./sampleSeats.json";

/**
 * Fetches seat data from runtime static files or remote fallback.
 * Returns an array of seat records formatted with result and mp data.
 */
export async function loadSeatsData() {
  try {
    const [seatsRes, ge15Res, polsRes] = await Promise.all([
      fetch("/data/seats-parlimen.json").catch(() => null),
      fetch("/data/results-ge15.json").catch(() => null),
      fetch("/data/politicians.json").catch(() => null),
    ]);

    if (!seatsRes?.ok || !ge15Res?.ok || !polsRes?.ok) {
      console.warn("Using bundled real seat snapshot for pilot (local fetch returned non-200)");
      return defaultSeats;
    }

    const [parlimenData, ge15Data, polsData] = await Promise.all([
      seatsRes.json(),
      ge15Res.json(),
      polsRes.json(),
    ]);

    const seatsMap = new Map();
    for (const s of parlimenData.seats || []) {
      seatsMap.set(s.code, s);
    }

    const testCodes = [
      "P.003", // Arau (PN, Perlis, with photo)
      "P.015", // Sungai Petani (PH, Kedah, with photo)
      "P.021", // Kota Bharu (PN/PAS, Kelantan, with photo)
      "P.044", // Permatang Pauh (PN, Penang, monogram)
      "P.075", // Bagan Datuk (BN, Perak, ultra-marginal, with photo)
      "P.102", // Bangi (PH, Selangor, with photo)
      "P.104", // Subang (PH, Selangor, with photo)
      "P.121", // Lembah Pantai (PH, KL, with photo)
      "P.147", // Parit Sulong (BN, Johor, with photo)
      "P.197", // Kota Samarahan (GPS, Sarawak, monogram)
    ];

    const mps = polsData.mps || {};

    return testCodes.map((code) => {
      const s = seatsMap.get(code) || {};
      const r = ge15Data[code] || {};
      const mp = mps[code] || {};
      return {
        code,
        name: s.name || r.name,
        state: s.state || r.state,
        result: r,
        mp,
      };
    });
  } catch (err) {
    console.warn("loadSeatsData error, falling back to bundled real seat snapshot:", err);
    return defaultSeats;
  }
}

export { defaultSeats };
