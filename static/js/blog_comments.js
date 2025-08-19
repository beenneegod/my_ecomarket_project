(function(){
  'use strict';

  function init(){
    // Clear #comments-section hash to avoid native jumps
    if (window.location.hash === '#comments-section') {
      try { history.replaceState(null, '', window.location.pathname + window.location.search); } catch (_) {}
    }

    var form = document.querySelector('form.comment-form');
    var commentsList = document.getElementById('comments-list');
    var commentsCount = document.getElementById('comments-count');
    var submitBtn = document.getElementById('comment-submit-btn');
    var noComments = document.getElementById('no-comments-placeholder');
    var errorBox = document.getElementById('comment-form-error');

    // Choose image UX
    var hiddenInput = document.querySelector('.js-comment-image-input');
    var chooseBtn = document.getElementById('btn-choose-comment-image');
    var fileNameField = document.getElementById('comment-image-filename');
    if (chooseBtn && hiddenInput) {
      chooseBtn.addEventListener('click', function(){ hiddenInput.click(); });
    }
    if (hiddenInput) {
      hiddenInput.addEventListener('change', function(){
        var file = hiddenInput.files && hiddenInput.files[0];
        if (fileNameField) fileNameField.textContent = file ? file.name : 'Nie wybrano pliku';
      });
    }

  if (!commentsList) return;
  // No hover preloading to avoid excess repaints on mouse move

    // Improve modal experience: prevent thumbnail clicks while modal open and smooth image reveal
    document.addEventListener('shown.bs.modal', function(e){
      var modal = e.target;
      if (!modal || !modal.id || modal.id.indexOf('imageModal-') !== 0) return;
      document.body.classList.add('image-modal-open');
      var box = modal.querySelector('.modal-body .zoom-image');
      if (box){
        void box.offsetHeight;
        box.style.transition = 'opacity .12s ease-out';
        box.style.opacity = '1';
      }
    });
    document.addEventListener('hidden.bs.modal', function(e){
      var modal = e.target;
      if (!modal || !modal.id || modal.id.indexOf('imageModal-') !== 0) return;
      document.body.classList.remove('image-modal-open');
      var box = modal.querySelector('.modal-body .zoom-image');
      if (box){
        box.style.opacity = '0';
        // keep transition as is; next show will set it again if needed
      }
    });

    // Highlight user's ratings if present
    document.querySelectorAll('.comment-rating[data-user-rating]').forEach(function(cr){
      var uv = parseInt(cr.getAttribute('data-user-rating'));
      if (!uv) return;
      cr.querySelectorAll('.rating-star').forEach(function(s){
        var v = parseInt(s.getAttribute('data-value'));
        s.classList.toggle('text-warning', v <= uv);
        s.classList.toggle('text-secondary', v > uv);
      });
    });

  if (form) form.addEventListener('submit', function(e){
      e.preventDefault();
      e.stopPropagation();
      if (submitBtn) submitBtn.disabled = true;
      if (errorBox) { errorBox.style.display = 'none'; errorBox.textContent = ''; }

      var formData = new FormData(form);
      var url = form.getAttribute('action') || (window.location.pathname + window.location.search);
      var beforeTopAbs = commentsList.getBoundingClientRect().top + window.scrollY;

      fetch(url, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        body: formData
      }).then(function(res){
        return res.json().then(function(data){ return { res: res, data: data }; });
      }).then(function(payload){
        var res = payload.res, data = payload.data;
        if (!res.ok || !data.ok) {
          var msg = (data && (data.error || (data.errors && (data.errors.body && data.errors.body[0]) || (data.errors && data.errors.image && data.errors.image[0])))) || 'Nie udało się dodać komentarza.';
          if (errorBox) { errorBox.textContent = msg; errorBox.style.display = ''; }
          return;
        }
        var wrapper = document.createElement('div');
        wrapper.innerHTML = data.html;
        var node = wrapper.firstElementChild;
        if (noComments) { try { noComments.remove(); } catch(_) {} }
        commentsList.prepend(node);
        var afterTopAbs = commentsList.getBoundingClientRect().top + window.scrollY;
        window.scrollBy({ top: (afterTopAbs - beforeTopAbs), left: 0, behavior: 'auto' });
        commentsCount.textContent = data.count;
        form.reset();
        if (fileNameField) fileNameField.textContent = 'Nie wybrano pliku';
      }).catch(function(err){
        try { console.error('Błąd wysyłania komentarza:', err); } catch(_) {}
        if (errorBox) { errorBox.textContent = 'Wystąpił błąd sieci. Spróbuj ponownie.'; errorBox.style.display = ''; }
      }).finally(function(){
        if (submitBtn) submitBtn.disabled = false;
      });
  });

    // Lightbox for blog comment images (reuse chat lightbox CSS/UX)
    let lightbox = null; let lightboxImg = null; let lightboxPrev = null; let lightboxNext = null; let lightboxClose = null; let lightboxList = []; let lightboxIndex = 0;
    function ensureLightbox(){
      if (lightbox) return;
      lightbox = document.createElement('div');
      lightbox.id = 'chatLightbox';
      lightbox.className = 'chat-lightbox';
      lightbox.innerHTML = `
        <div class="chat-lightbox-backdrop" role="button" aria-label="Zamknij"></div>
        <div class="chat-lightbox-content" role="dialog" aria-modal="true">
          <button class="chat-lightbox-close" aria-label="Zamknij">×</button>
          <button class="chat-lightbox-nav chat-lightbox-prev" aria-label="Poprzednie">‹</button>
          <img class="chat-lightbox-img" alt="" />
          <button class="chat-lightbox-nav chat-lightbox-next" aria-label="Następne">›</button>
        </div>`;
      document.body.appendChild(lightbox);
      lightboxImg = lightbox.querySelector('.chat-lightbox-img');
      lightboxPrev = lightbox.querySelector('.chat-lightbox-prev');
      lightboxNext = lightbox.querySelector('.chat-lightbox-next');
      lightboxClose = lightbox.querySelector('.chat-lightbox-close');
      const backdrop = lightbox.querySelector('.chat-lightbox-backdrop');
      const close = () => { lightbox.classList.remove('is-open'); document.removeEventListener('keydown', onKey); };
      const onKey = (e) => {
        if (e.key === 'Escape') close();
        else if (e.key === 'ArrowLeft') showIndex(lightboxIndex - 1);
        else if (e.key === 'ArrowRight') showIndex(lightboxIndex + 1);
      };
      lightboxPrev.addEventListener('click', () => showIndex(lightboxIndex - 1));
      lightboxNext.addEventListener('click', () => showIndex(lightboxIndex + 1));
      lightboxClose.addEventListener('click', close);
      backdrop.addEventListener('click', close);
      lightbox.addEventListener('click', (e) => { if (e.target === lightbox) close(); });
      function showIndex(idx){
        if (!lightboxList.length) return;
        lightboxIndex = (idx + lightboxList.length) % lightboxList.length;
        const { url, alt } = lightboxList[lightboxIndex];
        lightboxImg.src = url; lightboxImg.alt = alt || '';
      }
      lightbox.showIndex = showIndex;
      lightbox.open = (list, start) => {
        lightboxList = list || [];
        lightboxIndex = start || 0;
        lightbox.classList.add('is-open');
        lightbox.showIndex(lightboxIndex);
        document.addEventListener('keydown', onKey);
      };
      lightbox.close = close;
    }

    commentsList.addEventListener('click', function(e){
      const link = e.target.closest('.chat-attach-thumb-link');
      if (!link) return;
      e.preventDefault();
      const wrap = e.target.closest('.comment');
      if (!wrap) return;
      ensureLightbox();
      const items = Array.from(wrap.querySelectorAll('.chat-attach-thumb-link'));
      const list = items.map(a => ({ url: a.getAttribute('href') || '', alt: (a.querySelector('img')||{}).alt || '' }));
      const idx = Math.max(0, items.indexOf(link));
      lightbox.open(list, idx);
    });

    // Rating stars handler (delegate to comments list)
    commentsList.addEventListener('click', function(ev){
      var t = ev.target;
      if (!t.classList || !t.classList.contains('rating-star')) return;
      ev.preventDefault();
      var container = t.closest('.comment-rating');
      if (!container) return;
      var commentId = container.getAttribute('data-comment-id');
      if (container.getAttribute('data-disabled') === '1') {
        // Optionally, brief hint
        return;
      }
      var value = parseInt(t.getAttribute('data-value')); 
      if (!commentId || !value) return;
      // Prevent rating own comment by UI if identifiable: assume parent .comment has data-author-id? Not guaranteed; rely on server validation.

      // Optimistic UI: light up stars up to value
      var stars = container.querySelectorAll('.rating-star');
      stars.forEach(function(s){
        var v = parseInt(s.getAttribute('data-value'));
        s.classList.toggle('text-warning', v <= value);
        s.classList.toggle('text-secondary', v > value);
      });

  var rateUrl = container.getAttribute('data-rate-url');
  if (!rateUrl) return;
      var csrf = getCsrfToken();
      fetch(rateUrl, {
        method: 'POST',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'Content-Type': 'application/json',
          'X-CSRFToken': csrf || ''
        },
        body: JSON.stringify({ value: value })
      }).then(function(res){
        return res.json().then(function(data){ return { res: res, data: data }; });
      }).then(function(payload){
        var res = payload.res, data = payload.data;
        if (!res.ok || !data.ok) {
          // revert UI? For now, just log; server enforces and returns error message.
          try { console.warn('Rating failed:', data && (data.error || res.status)); } catch(_) {}
          // revert to previous user rating, if any
          var prev = parseInt(container.getAttribute('data-user-rating')) || 0;
          stars.forEach(function(s){
            var v = parseInt(s.getAttribute('data-value'));
            s.classList.toggle('text-warning', v <= prev);
            s.classList.toggle('text-secondary', v > prev);
          });
          return;
        }
        // Update average/count text
        var meta = container.querySelector('.rating-meta');
        if (meta) {
          meta.textContent = '(Śr: ' + (data.average != null ? data.average.toFixed ? data.average.toFixed(1) : data.average : '0.0') + ', głosów: ' + (data.count || 0) + ')';
        }
        container.setAttribute('data-user-rating', String(value));
      }).catch(function(err){
        try { console.error('Błąd wysyłania oceny:', err); } catch(_) {}
        // revert to previous user rating on network error
        var prev = parseInt(container.getAttribute('data-user-rating')) || 0;
        stars.forEach(function(s){
          var v = parseInt(s.getAttribute('data-value'));
          s.classList.toggle('text-warning', v <= prev);
          s.classList.toggle('text-secondary', v > prev);
        });
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

// CSRF helper copied from Django docs
function getCookie(name){
  var cookieValue = null;
  if (document.cookie && document.cookie !== ''){
    var cookies = document.cookie.split(';');
    for (var i = 0; i < cookies.length; i++){
      var cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')){
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

function getCsrfToken(){
  // Prefer hidden input (works even if CSRF cookie is HttpOnly)
  var inp = document.querySelector('input[name="csrfmiddlewaretoken"]');
  if (inp && inp.value) return inp.value;
  // Fallback to cookie
  return getCookie('csrftoken');
}
