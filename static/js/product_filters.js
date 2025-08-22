// Wire custom +/- spinner buttons for price inputs on the product list page
(function(){
    const container = document.querySelector('.product-filters');
    if(!container) return;

    function parseStep(input){
        const stepAttr = input.getAttribute('step');
        const step = stepAttr ? Number(stepAttr) : 1;
        return isFinite(step) && step > 0 ? step : 1;
    }
    function clamp(val, min, max){
        if(min != null && !isNaN(min)) val = Math.max(val, Number(min));
        if(max != null && !isNaN(max)) val = Math.min(val, Number(max));
        return val;
    }
    function format(input, value){
        const step = parseStep(input);
        // If step is fractional, keep up to 2 decimals; else integer
        const decimals = (String(step).includes('.') ? 2 : 0);
        return value.toFixed(decimals);
    }

    container.querySelectorAll('.number-field').forEach(field => {
        const input = field.querySelector('input[type="number"]');
        if(!input) return;
        const min = input.getAttribute('min');
        const max = input.getAttribute('max');

        const up = field.querySelector('.spinner-btn.up');
        const down = field.querySelector('.spinner-btn.down');
        const step = parseStep(input);

        function getCurrent(){
            const v = input.value.trim();
            if(v === '') return null;
            const n = Number(v.replace(',', '.'));
            return isNaN(n) ? null : n;
        }

        up && up.addEventListener('click', () => {
            const current = getCurrent();
            const next = (current == null ? (Number(min) || 0) : current) + step;
            const clamped = clamp(next, min, max);
            input.value = format(input, clamped);
            input.dispatchEvent(new Event('change', { bubbles: true }));
        });
        down && down.addEventListener('click', () => {
            const current = getCurrent();
            const next = (current == null ? (Number(min) || 0) : current) - step;
            const clamped = clamp(next, min, max);
            input.value = format(input, clamped);
            input.dispatchEvent(new Event('change', { bubbles: true }));
        });
    });

    // Pseudo-selects (support multiple instances: sort, min_rating, etc.)
    container.querySelectorAll('.pseudo-select').forEach(pseudo => {
        const name = pseudo.getAttribute('data-name');
        if(!name) return;
        const hidden = container.querySelector(`input[type="hidden"][name="${name}"]`);
        const toggle = pseudo.querySelector('.pseudo-select-toggle');
        const currentEl = pseudo.querySelector('.pseudo-current');
        const menu = pseudo.querySelector('.pseudo-select-menu');

        function open(){
            pseudo.classList.add('open');
            toggle.setAttribute('aria-expanded', 'true');
            menu.focus();
        }
        function close(){
            pseudo.classList.remove('open');
            toggle.setAttribute('aria-expanded', 'false');
        }
        function setValue(value, label){
            if(hidden) hidden.value = value;
            if(currentEl) currentEl.textContent = label;
            menu.querySelectorAll('li').forEach(li => li.classList.toggle('selected', li.dataset.value === value));
        }

        toggle?.addEventListener('click', () => {
            if(pseudo.classList.contains('open')) close(); else open();
        });
        menu?.addEventListener('click', (e) => {
            const li = e.target.closest('li[role="option"]');
            if(!li) return;
            setValue(li.dataset.value, li.textContent.trim());
            close();
        });
        document.addEventListener('click', (e) => {
            if(!pseudo.contains(e.target)) close();
        });
        menu?.addEventListener('keydown', (e) => {
            const items = Array.from(menu.querySelectorAll('li'));
            const idx = items.findIndex(li => li.classList.contains('selected'));
            if(e.key === 'Escape'){ close(); toggle.focus(); }
            else if(e.key === 'ArrowDown'){ e.preventDefault(); items[Math.min(idx+1, items.length-1)].focus?.(); }
            else if(e.key === 'ArrowUp'){ e.preventDefault(); items[Math.max(idx-1, 0)].focus?.(); }
            else if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); const el = document.activeElement.closest('li'); if(el){ setValue(el.dataset.value, el.textContent.trim()); close(); toggle.focus(); } }
        });
        // Make items focusable for keyboard
        menu?.querySelectorAll('li').forEach(li => li.tabIndex = 0);
    });
})();
