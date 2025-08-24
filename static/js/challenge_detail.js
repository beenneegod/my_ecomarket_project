// Updates filename preview for proof_file input on the challenge detail page.
(function(){
  function updatePreview(input){
    var targetId = input.getAttribute('data-filename-target') || 'proof-filename';
    var span = document.getElementById(targetId);
    if (!span) return;
    var files = input.files;
    var defaultText = span.getAttribute('data-default-text') || 'Nie wybrano pliku';
    var filename = null;
    if (files && files.length > 0) {
      filename = files.length === 1 ? files[0].name : (files.length + ' pliki');
    } else if (typeof input.value === 'string' && input.value) {
      // Some browsers expose a fake path like C:\\fakepath\\filename.ext
      var v = input.value;
      var parts = v.split('\\');
      filename = parts[parts.length - 1];
      if (!filename) {
        parts = v.split('/');
        filename = parts[parts.length - 1];
      }
    }
    span.textContent = filename || defaultText;
  }

  document.addEventListener('change', function(e){
    if (e.target && e.target.classList && e.target.classList.contains('js-proof-input')) {
      updatePreview(e.target);
    }
  }, false);

  document.addEventListener('input', function(e){
    if (e.target && e.target.classList && e.target.classList.contains('js-proof-input')) {
      updatePreview(e.target);
    }
  }, false);

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function(){
      var el = document.querySelector('.js-proof-input');
      if (el) updatePreview(el);
    });
  } else {
    var el = document.querySelector('.js-proof-input');
    if (el) updatePreview(el);
  }
})();
