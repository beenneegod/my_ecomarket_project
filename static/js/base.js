// Base behaviors loaded after vendors. Keep inline JS to zero; use CSP nonces for the early theme only.
(function(){
  // AOS init with reduced-motion respect
  if (window.AOS) {
    try {
      AOS.init({
        disable: function(){
          return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        }
      });
    } catch(_) {}
  }

  // Drop suspend-transitions after first paint
  window.addEventListener('DOMContentLoaded', function(){
    setTimeout(function(){
      document.documentElement.classList.remove('suspend-transitions');
    }, 300);
  });

  // A11y: dropdown focus management (Bootstrap events)
  document.addEventListener('shown.bs.dropdown', function (e) {
    var toggle = e.target; // .dropdown-toggle
    var menu = toggle && toggle.nextElementSibling;
    if (menu) {
      var firstItem = menu.querySelector('.dropdown-item:not(.disabled)');
      if (firstItem) firstItem.focus();
    }
  });
  document.addEventListener('hidden.bs.dropdown', function (e) {
    var toggle = e.target; // return focus to button
    if (toggle && typeof toggle.focus === 'function') toggle.focus();
  });

  // Logout link without inline onclick
  document.addEventListener('click', function(e){
    var link = e.target.closest('.logout-button-bs');
    if (!link) return;
    e.preventDefault();
    var form = document.getElementById('logout-form');
    if (form) form.submit();
  });
})();
