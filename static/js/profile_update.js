(function(){
  'use strict';
  function ready(fn){
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
    else fn();
  }
  ready(function(){
    var input = document.querySelector('.avatar-field .js-avatar-input');
    var fileNameField = document.getElementById('avatar-filename');
    var previewImg = document.querySelector('img[alt="Twój awatar"]');
    var clearBtn = document.getElementById('avatar-clear-btn');
    var clearFlag = document.getElementById('avatar-clear-flag');
    var defaultAvatarUrl = (previewImg && previewImg.getAttribute('data-default-avatar-url')) || null;
    if(!input) return;
    function update(){
      var file = input.files && input.files[0];
      if (fileNameField) fileNameField.textContent = file ? file.name : 'Nie wybrano pliku';
      if (file && previewImg){
        try {
          var url = URL.createObjectURL(file);
          previewImg.src = url;
          previewImg.onload = function(){ try { URL.revokeObjectURL(url); } catch(_){} };
        } catch(_){ }
      } else if (!file && defaultAvatarUrl && previewImg){
        // If input was cleared programmatically, reset preview
        previewImg.src = defaultAvatarUrl;
      }
      // If a file is chosen, make sure clear flag is off
      if (file && clearFlag) clearFlag.checked = false;
    }
    input.addEventListener('change', update);
    input.addEventListener('input', update);

    if (clearBtn) {
      clearBtn.addEventListener('click', function(){
        if (clearFlag) {
          clearFlag.checked = true;
          clearFlag.value = '1';
        }
        try { input.value = ''; } catch(_) {}
        if (fileNameField) fileNameField.textContent = 'Nie wybrano pliku';
        if (previewImg && defaultAvatarUrl) previewImg.src = defaultAvatarUrl;
      });
    }
  });
})();
