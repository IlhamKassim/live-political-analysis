// Presentation only. Map, filters, sources, sharing and routes use /app/app.js.
const copy = {
  en: {
    eyebrow: 'MALAYSIA / SEAT EXPLORER',
    heading: 'Explore the\nSeat map.',
    description: 'Choose a state on the map, or search for a Seat and explore its record.',
    search: 'Find a Seat',
    filters: 'SEAT LAYER / COLOUR BY',
    honesty: 'Election results are records. A Projection is an estimate. Follow the sources to see the difference.',
    sources: 'Data & sources ↗',
    tool: 'The Seat map',
    mobileFilters: 'Layers & colours ↗',
  },
  ms: {
    eyebrow: 'MALAYSIA / PETA KERUSI',
    heading: 'Terokai\npeta kerusi.',
    description: 'Pilih negeri pada peta, atau cari kerusi dan terokai rekodnya.',
    search: 'Cari kerusi',
    filters: 'LAPISAN KERUSI / WARNA MENGIKUT',
    honesty: 'Keputusan pilihan raya ialah rekod. Unjuran ialah anggaran. Rujuk sumber untuk memahami perbezaannya.',
    sources: 'Data & sumber ↗',
    tool: 'Peta kerusi',
    mobileFilters: 'Lapisan & warna ↗',
  },
};
const root = document.documentElement;
const panel = document.getElementById('panel');
const theme = document.querySelector('meta[name="theme-color"]');
const mobileNav = document.createElement('nav');
mobileNav.className = 'obs-mobile-nav';
const navSources = [...document.querySelectorAll('.sb-nav .sb-item')];
for (const source of navSources) {
  const link = document.createElement('a');
  link.href = source.getAttribute('href') || '/app/';
  link.dataset.obsNav = source.id;
  link.addEventListener('click', event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    document.getElementById('mobile-menu-btn').click();
    source.click();
  });
  mobileNav.append(link);
}
document.getElementById('mobile-menu').append(mobileNav);
document.getElementById('obs-mobile-filters').addEventListener('click', event => {
  event.stopPropagation();
  document.getElementById('mobile-menu-btn').click();
  document.querySelector('#menu-map-controls button')?.focus();
});
function translate() {
  const words = copy[root.lang] || copy.en;
  document.querySelector('.obs-home').setAttribute('aria-label', root.lang === 'ms' ? 'Laman utama PolitikKu' : 'PolitikKu home');
  mobileNav.setAttribute('aria-label', root.lang === 'ms' ? 'Navigasi' : 'Navigation');
  for (const link of mobileNav.children) {
    const source = document.getElementById(link.dataset.obsNav);
    link.textContent = source.querySelector('.sb-label').textContent + ' ↗';
    link.setAttribute('aria-label', source.getAttribute('aria-label'));
  }
  document.querySelectorAll('[data-obs]').forEach(node => {
    node.textContent = words[node.dataset.obs];
  });
}
function alignTheme() {
  if (theme.content !== '#101e23') theme.content = '#101e23';
}
function updateLayout() {
  document.body.classList.toggle('obs-overview', panel.classList.contains('empty'));
}
new MutationObserver(translate).observe(root, { attributes: true, attributeFilter: ['lang'] });
new MutationObserver(alignTheme).observe(theme, { attributes: true, attributeFilter: ['content'] });
new MutationObserver(updateLayout).observe(panel, { attributes: true, attributeFilter: ['class'] });
document.getElementById('obs-sources').addEventListener('click', () => document.getElementById('sb-about').click());
translate();
alignTheme();
updateLayout();
