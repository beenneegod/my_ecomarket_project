(function(){
  function setToken(){
    var siteKey = (function(){
      try {
        var el = document.querySelector('script[src*="www.google.com/recaptcha/api.js?render="]');
        if (!el) return '';
        var m = el.src.match(/render=([^&]+)/);
        return m ? decodeURIComponent(m[1]) : '';
      } catch(e) { return ''; }
    })();
    if (!siteKey) return;
    if (!window.grecaptcha || !grecaptcha.execute) return;
    try {
      grecaptcha.ready(function(){
        grecaptcha.execute(siteKey, {action: 'contact'}).then(function(token){
          var el = document.getElementById('id_recaptcha_token');
          if (el) el.value = token;
        });
      });
    } catch (e) { /* no-op */ }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setToken);
  } else {
    setToken();
  }
  // Refresh token every 90 seconds
  setInterval(function(){
    try {
      setToken();
    } catch(e) {}
  }, 90000);
})();
