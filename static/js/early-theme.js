// Early theme application to avoid FOUC; must load before CSS/paint. Kept minimal and CSP-safe as external script.
(function(){
  try {
    var root = document.documentElement;
    var stored = localStorage.getItem('theme');
    if (stored === 'dark') root.classList.add('dark-mode');
    else if (stored === 'light') root.classList.add('light-mode');
    else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) root.classList.add('dark-mode');
    // Pre-suspend transitions to avoid flicker during initial paint
    root.classList.add('suspend-transitions');
  } catch (e) {}
})();
