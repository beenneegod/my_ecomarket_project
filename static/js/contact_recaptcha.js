(function(){
  var submitting = false;

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

  // Ensure token exists before submit; fetch then submit
  document.addEventListener('submit', function(ev){
    var form = ev.target;
    if (!(form && form.tagName === 'FORM')) return;
    // Only for contact form (has our hidden input)
    var tokenEl = form.querySelector('#id_recaptcha_token');
    if (!tokenEl) return;
    if (submitting) return; // avoid loop

    var token = tokenEl.value && tokenEl.value.trim();
    if (token) return; // ok

    ev.preventDefault();
    var siteKey = (function(){
      try {
        var el = document.querySelector('script[src*="www.google.com/recaptcha/api.js?render="]');
        if (!el) return '';
        var m = el.src.match(/render=([^&]+)/);
        return m ? decodeURIComponent(m[1]) : '';
      } catch(e) { return ''; }
    })();
    if (!siteKey || !window.grecaptcha || !grecaptcha.execute) {
      // give up gracefully; let server decide
      submitting = true;
      form.submit();
      return;
    }
    grecaptcha.ready(function(){
      grecaptcha.execute(siteKey, {action: 'contact'}).then(function(newToken){
        tokenEl.value = newToken || '';
        submitting = true;
        form.submit();
      }).catch(function(){
        submitting = true;
        form.submit();
      });
    });
  }, true);
})();
