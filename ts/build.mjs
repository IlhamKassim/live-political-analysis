// Bundles src/lookup.ts to a single ES module, matching this repo's other
// PolitikKu output: generated, not committed (see .gitignore), written
// straight into public/ the same way the Python pages are.
import * as esbuild from "esbuild";

await esbuild.build({
  entryPoints: ["src/lookup.ts"],
  bundle: true,
  minify: true,
  sourcemap: true,
  format: "esm",
  target: "es2020",
  outfile: "../public/politikku/lookup.js",
});

console.log("Wrote ../public/politikku/lookup.js");
