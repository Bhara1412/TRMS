(() => {
  const button = document.querySelector('.menu-toggle');
  const sidebar = document.querySelector('.sidebar');
  if (!button || !sidebar) return;
  const close = () => { document.body.classList.remove('menu-open'); button.setAttribute('aria-expanded', 'false'); button.setAttribute('aria-label', 'Open navigation'); };
  button.addEventListener('click', () => {
    const open = document.body.classList.toggle('menu-open');
    button.setAttribute('aria-expanded', String(open));
    button.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
    if (open) sidebar.querySelector('a').focus();
  });
  document.querySelector('[data-close-menu]').addEventListener('click', close);
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && document.body.classList.contains('menu-open')) { close(); button.focus(); } });
  sidebar.addEventListener('keydown', event => {
    if (!document.body.classList.contains('menu-open') || event.key !== 'Tab') return;
    const links = sidebar.querySelectorAll('a, button');
    if (event.shiftKey && document.activeElement === links[0]) { event.preventDefault(); links[links.length - 1].focus(); }
    if (!event.shiftKey && document.activeElement === links[links.length - 1]) { event.preventDefault(); links[0].focus(); }
  });
  window.matchMedia('(min-width: 901px)').addEventListener('change', close);
})();
