// Temporarily suppress transitions/animations on tab visibility changes to prevent flicker
(function(){
  const root = document.documentElement;
  let clearTimer = null;

  function addSuspend(){
    root.classList.add('suspend-transitions');
  }
  function removeSuspendAfter(ms){
    if (clearTimer) {
      clearTimeout(clearTimer);
      clearTimer = null;
    }
    clearTimer = setTimeout(() => {
      root.classList.remove('suspend-transitions');
      clearTimer = null;
    }, ms);
  }

  // Keep transitions disabled while tab is hidden, re-enable with delay on return
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      addSuspend();
    } else if (document.visibilityState === 'visible') {
      removeSuspendAfter(350);
    }
  });

  // Also handle window focus/blur
  window.addEventListener('blur', addSuspend);
  window.addEventListener('focus', () => removeSuspendAfter(350));

  // Handle BFCache restores (pageshow with persisted)
  window.addEventListener('pageshow', (e) => {
    if (e.persisted) {
      addSuspend();
      removeSuspendAfter(350);
    }
  });

  // On initial load while styles hydrate
  window.addEventListener('load', () => removeSuspendAfter(200));
})();
