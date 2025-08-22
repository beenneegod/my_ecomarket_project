// Product detail rating interactions (CSP-safe, no inline JS)
(function(){
  var rating = document.querySelector('.product-rating');
  if (!rating) return;
  var userLoggedIn = (rating.getAttribute('data-auth') === '1');

  function getCookie(name){
    var m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }

  function setStars(value){
    var stars = rating.querySelectorAll('.rating-star');
    stars.forEach(function(s){
      var v = parseInt(s.getAttribute('data-value'));
      s.classList.toggle('text-warning', v <= value);
      s.classList.toggle('text-secondary', v > value);
    });
  }

  rating.addEventListener('click', function(ev){
    var t = ev.target;
    if (t && t.nodeType !== 1) { t = t.parentElement; }
    var btn = t && t.closest ? t.closest('.rating-star') : null;
    if (!btn) return;
    ev.preventDefault();

    if (!userLoggedIn) {
      // Basic prompt without SweetAlert (CSP-safe)
      var go = confirm('Zaloguj się, aby ocenić produkt. Przejść do logowania?');
      if (go) {
        window.location.href = (document.querySelector('a[href$="/login/"]') && document.querySelector('a[href$="/login/"]').href) || '/accounts/login/';
      }
      return;
    }

    var value = parseInt(btn.getAttribute('data-value'));
    if (!value) return;

    // Optimistic
    setStars(value);

    var url = rating.getAttribute('data-rate-url');
    var formData = new FormData();
    formData.append('value', String(value));
    var csrf = (document.querySelector('[name=csrfmiddlewaretoken]')||{}).value || getCookie('csrftoken') || '';
    if (csrf) formData.append('csrfmiddlewaretoken', csrf);

    fetch(url, { method: 'POST', body: formData, headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrf }, credentials: 'same-origin' })
      .then(function(res){
        var ct = res.headers.get('content-type') || '';
        if (ct.includes('application/json')) return res.json().then(function(d){ return {res: res, data: d};});
        return { res: res, data: { ok: false, error: 'Non-JSON response', status: res.status } };
      })
      .then(function(payload){
        var d = payload.data;
        if (!payload.res.ok || !d.ok) {
          // revert
          var prev = parseInt(rating.getAttribute('data-user-rating')) || 0;
          setStars(prev);
          if (payload.res && payload.res.status === 403) {
            alert('Błąd CSRF (403). Odśwież stronę i spróbuj ponownie.');
          }
          return;
        }
        var meta = rating.querySelector('.rating-meta');
        if (meta) meta.textContent = '(Śr: ' + (d.average != null ? Number(d.average).toFixed(1) : '0.0') + ', głosów: ' + (d.count || 0) + ')';
        rating.setAttribute('data-user-rating', String(value));
      })
      .catch(function(){
        var prev = parseInt(rating.getAttribute('data-user-rating')) || 0;
        setStars(prev);
        alert('Nie udało się wysłać oceny. Sprawdź połączenie.');
      });
  });
})();
