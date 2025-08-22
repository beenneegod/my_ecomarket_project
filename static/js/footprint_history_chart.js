(function(){
  // Minimal, dependency-free line chart tailored for CSP: external file only, no inline scripts/styles.
  function renderChart(container, points){
    // Normalize and filter points
    const data = (points || [])
      .map(p => ({ t: new Date(p.date), v: Number(p.value) || 0 }))
      .filter(p => p.t.toString() !== 'Invalid Date')
      .sort((a,b) => a.t - b.t);

    // Guard
    if (!data.length) {
      container.innerHTML = '<div class="text-muted">Brak danych do wyświetlenia wykresu.</div>';
      return;
    }

    // Create canvas
    const dpr = window.devicePixelRatio || 1;
    const width = container.clientWidth || 600;
    const height = container.clientHeight || 260;
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    container.innerHTML = '';
    container.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    // Padding for axes
  const pad = { left: 40, right: 48, top: 12, bottom: 28 };
    const plotW = Math.max(10, width - pad.left - pad.right);
    const plotH = Math.max(10, height - pad.top - pad.bottom);

    // Compute scales
    const minT = data[0].t.getTime();
    const maxT = data[data.length - 1].t.getTime();
    const minV = Math.min(...data.map(p => p.v));
    const maxV = Math.max(...data.map(p => p.v));
    const vPad = (maxV - minV) * 0.1 || 1;
    const yMin = Math.max(0, Math.floor((minV - vPad)));
    const yMax = Math.ceil((maxV + vPad));

    const xScale = t => pad.left + (plotW * (t - minT)) / ((maxT - minT) || 1);
    const yScale = v => pad.top + plotH - (plotH * (v - yMin)) / ((yMax - yMin) || 1);

    // Determine theme (light/dark) via data-theme on html or body class if available
    const root = document.documentElement;
    const isDark = (root.getAttribute('data-theme') === 'dark') || document.body.classList.contains('dark-mode');
    const axisColor = isDark ? '#9099a5' : '#6c757d';
    const gridColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';
    const lineColor = isDark ? '#6dd47e' : '#1b9e3e';
    const pointColor = isDark ? '#a8e6b0' : '#2ecc71';

    // Background (transparent to blend)
    // Gridlines (horizontal 4 lines)
    ctx.lineWidth = 1;
    ctx.strokeStyle = gridColor;
    ctx.beginPath();
    const gridLines = 4;
    for (let i=0; i<=gridLines; i++){
      const y = pad.top + (plotH * i) / gridLines;
      ctx.moveTo(pad.left, y);
      ctx.lineTo(pad.left + plotW, y);
    }
    ctx.stroke();

    // Axes
    ctx.strokeStyle = axisColor;
    ctx.beginPath();
    // Y axis
    ctx.moveTo(pad.left, pad.top);
    ctx.lineTo(pad.left, pad.top + plotH);
    // X axis
    ctx.moveTo(pad.left, pad.top + plotH);
    ctx.lineTo(pad.left + plotW, pad.top + plotH);
    ctx.stroke();

    // Labels (y min/max)
    ctx.fillStyle = axisColor;
    ctx.font = '12px system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, sans-serif';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.fillText(String(yMin), pad.left - 6, yScale(yMin));
    ctx.fillText(String(yMax), pad.left - 6, yScale(yMax));

  // X labels: first and last date (align to edges so they don't clip)
  ctx.textBaseline = 'top';
  const fmt = new Intl.DateTimeFormat('pl-PL', { year: 'numeric', month: 'short' });
  ctx.textAlign = 'left';
  ctx.fillText(fmt.format(new Date(minT)), pad.left, pad.top + plotH + 6);
  ctx.textAlign = 'right';
  ctx.fillText(fmt.format(new Date(maxT)), pad.left + plotW, pad.top + plotH + 6);

    // Line
    ctx.lineWidth = 2;
    ctx.strokeStyle = lineColor;
    ctx.beginPath();
    data.forEach((p, idx) => {
      const x = xScale(p.t.getTime());
      const y = yScale(p.v);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Points
    ctx.fillStyle = pointColor;
    data.forEach(p => {
      const x = xScale(p.t.getTime());
      const y = yScale(p.v);
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  function init(){
    const el = document.getElementById('footprint-history-chart');
    if (!el) return;
    let points = [];
    try {
      const raw = el.getAttribute('data-points') || '[]';
      points = JSON.parse(raw);
    } catch(e){ points = []; }
    renderChart(el, points);

    // Handle resize
    let raf = null;
    const onResize = () => {
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => renderChart(el, points));
    };
    window.addEventListener('resize', onResize);

    // Optional: re-render on theme change if your code toggles data-theme
    const observer = new MutationObserver(() => renderChart(el, points));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
