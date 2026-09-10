(() => {
 const button = document.querySelector('.site-header .menu-toggle');
 const nav = document.querySelector('.site-header .nav-links');
 if (!button || !nav) return;
 const close = () => {
   nav.classList.remove('is-open');
   button.setAttribute('aria-expanded', 'false');
 };
 button.addEventListener('click', () => {
   const open = button.getAttribute('aria-expanded') !== 'true';
   nav.classList.toggle('is-open', open);
   button.setAttribute('aria-expanded', String(open));
 });
 nav.addEventListener('click', event => { if (event.target.closest('a')) close(); });
 document.addEventListener('keydown', event => {
   if (event.key === 'Escape' && button.getAttribute('aria-expanded') === 'true') {
     close(); button.focus();
   }
 });
})();
