// Entry point — bundled by esbuild to public/politikku/lookup.js and
// loaded via <script type="module"> from politikku_shell.py's render_shell.

import { mountAllLookups } from "./dom";

mountAllLookups();
