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
    if(!input) return;
    function update(){
      var file = input.files && input.files[0];
      if (fileNameField) fileNameField.textContent = file ? file.name : 'Nie wybrano pliku';
      if (file && previewImg){
        try {
          var url = URL.createObjectURL(file);
          previewImg.src = url;
          previewImg.onload = function(){ try { URL.revokeObjectURL(url); } catch(_){} };
        } catch(_){}
      }
    }
    input.addEventListener('change', update);
    input.addEventListener('input', update);
  });
})();
