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
})();
