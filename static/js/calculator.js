(function(){
  function enhanceSelect(select){
    if(select.dataset.enhanced) return;
    select.dataset.enhanced = '1';

    const wrapper = document.createElement('div');
    wrapper.className = 'custom-select';

    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'custom-select-trigger';
    trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-haspopup', 'listbox');

    const labelSpan = document.createElement('span');
    const caret = document.createElement('span');
    caret.className = 'caret';

    const menu = document.createElement('div');
    menu.className = 'custom-select-menu';
    menu.setAttribute('role', 'listbox');

    function getSelectedText(){
      const opt = select.options[select.selectedIndex];
      return opt ? opt.text : '';
    }

    function updateTrigger(){
      labelSpan.textContent = getSelectedText() || select.getAttribute('placeholder') || '';
      // reflect invalid state
      if(select.classList.contains('is-invalid')){
        trigger.classList.add('is-invalid');
      } else {
        trigger.classList.remove('is-invalid');
      }
    }

    function closeMenu(){
      wrapper.classList.remove('open');
      trigger.setAttribute('aria-expanded','false');
    }

    function openMenu(){
      wrapper.classList.add('open');
      trigger.setAttribute('aria-expanded','true');
      // focus selected option if present
      const current = menu.querySelector('.custom-select-option[aria-selected="true"]');
      const target = current || menu.querySelector('.custom-select-option');
      if(target){ target.focus({preventScroll:true}); }
    }

    function toggleMenu(){
      if(wrapper.classList.contains('open')) closeMenu(); else openMenu();
    }

    // Build options
    Array.from(select.options).forEach(function(opt){
      const item = document.createElement('div');
      item.className = 'custom-select-option';
      item.setAttribute('role','option');
      item.setAttribute('tabindex','-1');
      item.dataset.value = opt.value;
      item.textContent = opt.text;
      if(opt.disabled){ item.setAttribute('aria-disabled','true'); item.style.opacity = '0.6'; }
      if(opt.selected){ item.setAttribute('aria-selected','true'); }
      item.addEventListener('click', function(e){
        if(opt.disabled) return;
        select.value = opt.value;
        select.dispatchEvent(new Event('change', {bubbles:true}));
        menu.querySelectorAll('.custom-select-option[aria-selected="true"]').forEach(function(n){ n.setAttribute('aria-selected','false'); });
        item.setAttribute('aria-selected','true');
        updateTrigger();
        closeMenu();
        trigger.focus();
      });
      item.addEventListener('keydown', function(e){
        const focusables = Array.from(menu.querySelectorAll('.custom-select-option'));
        const idx = focusables.indexOf(document.activeElement);
        if(e.key === 'ArrowDown'){
          e.preventDefault();
          const next = focusables[Math.min(idx+1, focusables.length-1)];
          if(next) next.focus();
        } else if(e.key === 'ArrowUp'){
          e.preventDefault();
          const prev = focusables[Math.max(idx-1, 0)];
          if(prev) prev.focus();
        } else if(e.key === 'Enter' || e.key === ' '){
          e.preventDefault();
          item.click();
        } else if(e.key === 'Escape'){
          e.preventDefault();
          closeMenu();
          trigger.focus();
        }
      });
      menu.appendChild(item);
    });

    trigger.appendChild(labelSpan);
    trigger.appendChild(caret);
    updateTrigger();

    trigger.addEventListener('click', function(){ toggleMenu(); });
    trigger.addEventListener('keydown', function(e){
      if(e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' '){
        e.preventDefault();
        openMenu();
      }
    });

    // Keep native select for form submission but visually hide it
    select.classList.add('native-select-visually-hidden');

    // Sync when native select changes (e.g., by validation or code)
  select.addEventListener('change', function(){
      const value = select.value;
      menu.querySelectorAll('.custom-select-option').forEach(function(n){
        n.setAttribute('aria-selected', n.dataset.value === value ? 'true' : 'false');
      });
      updateTrigger();
    });
  // also observe class changes (e.g., server-side errors rendered on load)
  const mo = new MutationObserver(function(){ updateTrigger(); });
  mo.observe(select, { attributes:true, attributeFilter:['class'] });

    // Insert DOM
    select.parentNode.insertBefore(wrapper, select);
    wrapper.appendChild(trigger);
    wrapper.appendChild(menu);
    wrapper.appendChild(select);

    // Close on outside click
    document.addEventListener('click', function(e){
      if(!wrapper.contains(e.target)) closeMenu();
    });
  }

  function initCalculatorCustomSelects(){
    const container = document.querySelector('.calculator-page');
    if(!container) return;
    const selects = container.querySelectorAll('select.form-select');
    selects.forEach(enhanceSelect);
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', initCalculatorCustomSelects);
  } else {
    initCalculatorCustomSelects();
  }
})();
