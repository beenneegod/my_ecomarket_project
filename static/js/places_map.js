(function(){
  if (!window.L) return; // Leaflet must be loaded
  const mapEl = document.getElementById('map');
  if (!mapEl) return;
  const cfg = {
    placesApi: mapEl.getAttribute('data-places-api'),
    placeDetailApi: mapEl.getAttribute('data-place-detail-api'),
    addReviewUrl: mapEl.getAttribute('data-add-review-url'),
    voteReviewUp: mapEl.getAttribute('data-vote-review-up'),
    voteReviewDown: mapEl.getAttribute('data-vote-review-down'),
  };

  const map = L.map('map').setView([52.2297, 21.0122], 6); // Poland
  // Use an inline SVG marker (data: URI) so CSP doesn't block icons and no CDN is required
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="25" height="41" viewBox="0 0 25 41">\
<path d="M12.5 0C5.596 0 0 5.596 0 12.5C0 21.9 12.5 41 12.5 41C12.5 41 25 21.9 25 12.5C25 5.596 19.404 0 12.5 0Z" fill="#2a8f4a"/>\
<circle cx="12.5" cy="12.5" r="5.5" fill="#ffffff"/></svg>';
  const defaultIcon = L.icon({
    iconUrl: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg),
    iconRetinaUrl: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg),
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    tooltipAnchor: [16, -28]
  });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);

  // Cluster group for markers
  const cluster = (window.L && L.markerClusterGroup) ? L.markerClusterGroup({
    showCoverageOnHover: false,
    maxClusterRadius: 48
  }) : null;
  if (cluster) map.addLayer(cluster);

  const markers = [];
  let radiusCircle = null;

  function clearMarkers() {
    markers.forEach(m => {
      if (cluster) { cluster.removeLayer(m); }
      else { map.removeLayer(m); }
    });
    markers.length = 0;
    if (radiusCircle) { map.removeLayer(radiusCircle); radiusCircle = null; }
  }

  function fitToMarkers() {
    if (markers.length === 0) return;
    const group = L.featureGroup(markers);
    map.fitBounds(group.getBounds().pad(0.15));
  }

  async function loadPlaces(params) {
    const url = new URL(cfg.placesApi, window.location.origin);
    if (params.city) url.searchParams.set('city', params.city);
    (params.categories || []).forEach(cat => url.searchParams.append('category', cat));
    if (params.center_lat && params.center_lng && params.radius_km) {
      url.searchParams.set('center_lat', params.center_lat);
      url.searchParams.set('center_lng', params.center_lng);
      url.searchParams.set('radius_km', params.radius_km);
    }
    const resp = await fetch(url.toString());
    const data = await resp.json();
    clearMarkers();
    data.results.forEach(p => {
      const marker = L.marker([p.lat, p.lng], { icon: defaultIcon });
      if (cluster) cluster.addLayer(marker); else marker.addTo(map);
      const title = p.name + (p.city ? `, ${p.city}` : '');
      const addr = p.address ? `<div><small>${p.address}</small></div>` : '';
      const rating = p.reviews_count ? `<div class="mt-1"><span class="badge bg-primary">${p.average_rating} / 5</span> <small>(${p.reviews_count} opinii)</small></div>` : '<div class="mt-1 text-muted"><small>Brak ocen</small></div>';
      const detailsBtn = `<button class="btn btn-sm btn-outline-primary mt-2" data-place-id="${p.id}">Opinie (${p.reviews_count || 0})</button>`;
      marker.bindPopup(`<strong>${title}</strong>${addr}${rating}<div class="popup-actions">${detailsBtn}</div>`);
      marker.on('popupopen', () => {
        const btn = document.querySelector('.leaflet-popup .popup-actions button[data-place-id="' + p.id + '"]');
        if (btn) {
          btn.addEventListener('click', async () => {
            const baseUrl = cfg.placeDetailApi.replace('/0/', `/${p.id}/`);
            const PER = 4;
            let currentPage = 1;
            let totalReviews = 0;
            let d = { reviews: [], average_rating: 0, reviews_count: 0 };

            async function fetchPage(page){
              const u = new URL(baseUrl, window.location.origin);
              u.searchParams.set('page', String(page));
              u.searchParams.set('per', String(PER));
              const r = await fetch(u.toString());
              return r.json();
            }
            function reviewItem(rv){
              const upUrl = cfg.voteReviewUp.replace('/0/', `/${rv.id}/`);
              const downUrl = cfg.voteReviewDown.replace('/0/', `/${rv.id}/`);
              return `<div class="review-item border-top pt-2 mt-2" data-review-id="${rv.id}"><div><strong>${rv.user}</strong> — ${rv.rating}/5</div><small class="text-muted">${new Date(rv.created_at).toLocaleString()}</small><div class="mt-1">${rv.comment || ''}</div><div class="review-actions d-flex gap-2 mt-1"><button class="btn btn-sm btn-outline-primary btn-tight" data-vote="up" data-url="${upUrl}">Pomocny (<span data-helpful>${rv.helpful}</span>)</button><button class="btn btn-sm btn-outline-secondary btn-tight" data-vote="down" data-url="${downUrl}">Niepomocny (<span data-nothelp>${rv.not_helpful}</span>)</button></div></div>`;
            }
            function renderPopup(){
              const loaded = d.reviews.length;
              const remaining = Math.max(0, totalReviews - loaded);
              const more = remaining > 0 ? `<button class="btn btn-sm btn-outline-primary w-100 mt-2" data-more>Pokaż więcej (${remaining})</button>` : '';
              const reviewsHtml = loaded ? `<div class="reviews-scroll">${d.reviews.map(reviewItem).join('')}</div>` : '<div class="mt-2 text-muted">Brak komentarzy</div>';
              const content = `<strong>${title}</strong>${addr}<div class="mt-1"><span class="badge bg-primary">${d.average_rating} / 5</span> <small>(${totalReviews} opinii)</small></div>` + reviewsHtml + more + `<div class="mt-2"><a class="btn btn-sm btn-primary text-white w-100" href="${cfg.addReviewUrl.replace('/0/', `/${p.id}/`)}">Dodaj opinię</a></div>`;
              marker.getPopup().setContent(content).update();
              const popupEl = document.querySelector('.leaflet-popup');
              if (popupEl && !popupEl.dataset.voteBound){
                popupEl.addEventListener('click', async (evt) => {
                  const vbtn = evt.target.closest('[data-vote]');
                  if (vbtn){
                    evt.preventDefault();
                    const url = vbtn.getAttribute('data-url');
                    try{
                      const csrftoken = (document.querySelector('[name=csrfmiddlewaretoken]') || {}).value || '';
                      const resp = await fetch(url, { method: 'POST', headers: { 'X-CSRFToken': csrftoken } });
                      if (resp.ok){
                        const js = await resp.json();
                        const reviewEl = vbtn.closest('[data-review-id]');
                        if (reviewEl){
                          const upSpan = reviewEl.querySelector('[data-helpful]');
                          const downSpan = reviewEl.querySelector('[data-nothelp]');
                          if (upSpan && typeof js.helpful === 'number') upSpan.textContent = String(js.helpful);
                          if (downSpan && typeof js.not_helpful === 'number') downSpan.textContent = String(js.not_helpful);
                        }
                      }
                    } catch(_) { /* ignore */ }
                  }
                  const moreBtn = evt.target.closest('[data-more]');
                  if (moreBtn){
                    evt.preventDefault();
                    currentPage += 1;
                    try{
                      const next = await fetchPage(currentPage);
                      d.reviews = d.reviews.concat(next.reviews || []);
                      totalReviews = next.reviews_count || totalReviews;
                      renderPopup();
                    } catch(_) { /* ignore */ }
                  }
                });
                popupEl.dataset.voteBound = '1';
              }
            }
            try{
              const first = await fetchPage(currentPage);
              d.reviews = first.reviews || [];
              d.average_rating = first.average_rating || 0;
              totalReviews = first.reviews_count || 0;
              renderPopup();
            } catch(_) { /* ignore */ }
          }, { once: true });
        }
      });
      markers.push(marker);
    });
    fitToMarkers();
  }

  function gatherParams() {
    const city = document.getElementById('citySelect').value || '';
    const categories = Array.from(document.querySelectorAll('.category-input:checked')).map(el => el.value);
    return { city, categories };
  }

  function applyParamsToControls(params) {
    if (params.city) {
      const sel = document.getElementById('citySelect');
      const opt = Array.from(sel.options).find(o => o.value === params.city);
      if (opt) sel.value = params.city;
    }
    if (params.categories && params.categories.length) {
      params.categories.forEach(val => {
        const cb = document.getElementById(`cat-${val}`);
        if (cb) cb.checked = true;
      });
    }
    if (params.radius_km) {
      document.getElementById('radiusInput').value = params.radius_km;
    }
  }

  function updateUrl(params) {
    const url = new URL(window.location.href);
    url.search = '';
    if (params.city) url.searchParams.set('city', params.city);
    (params.categories || []).forEach(cat => url.searchParams.append('category', cat));
    if (params.center_lat && params.center_lng && params.radius_km) {
      url.searchParams.set('center_lat', params.center_lat);
      url.searchParams.set('center_lng', params.center_lng);
      url.searchParams.set('radius_km', params.radius_km);
    }
    history.replaceState(null, '', url.toString());
  }

  // Enhance native select to themed custom dropdown (no external deps)
  function enhanceCitySelect(){
    const sel = document.getElementById('citySelect');
    if (!sel || sel.dataset.enhanced) return;
    sel.dataset.enhanced = '1';
    // Wrapper
    const wrap = document.createElement('div');
    wrap.className = 'custom-select';
    sel.parentElement.insertBefore(wrap, sel);
    // Hide original but keep in DOM for form/ARIA
    sel.classList.add('custom-select-hidden');
    wrap.appendChild(sel);
    // Trigger button
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'custom-select-trigger';
    btn.setAttribute('aria-haspopup', 'listbox');
    btn.setAttribute('aria-expanded', 'false');
    btn.textContent = sel.options[sel.selectedIndex]?.text || sel.options[0]?.text || '';
    wrap.appendChild(btn);
    // Menu list
    const menu = document.createElement('div');
    menu.className = 'custom-select-menu';
    menu.setAttribute('role', 'listbox');
    wrap.appendChild(menu);
    Array.from(sel.options).forEach((opt, idx) => {
      const it = document.createElement('button');
      it.type = 'button';
      it.className = 'custom-select-option';
      it.setAttribute('role', 'option');
      it.dataset.value = opt.value;
      it.textContent = opt.text;
      if (idx === sel.selectedIndex) it.classList.add('is-selected');
      it.addEventListener('click', () => {
        // Update native select and fire change
        sel.value = opt.value;
        btn.textContent = opt.text;
        menu.querySelectorAll('.custom-select-option').forEach(o => o.classList.remove('is-selected'));
        it.classList.add('is-selected');
        btn.setAttribute('aria-expanded', 'false');
        menu.classList.remove('is-open');
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      });
      menu.appendChild(it);
    });
    function toggle(){
      const open = menu.classList.toggle('is-open');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
    btn.addEventListener('click', toggle);
    document.addEventListener('click', (e) => {
      if (!wrap.contains(e.target)) { menu.classList.remove('is-open'); btn.setAttribute('aria-expanded', 'false'); }
    });
    // Keep in sync when code updates select (e.g., applyParamsToControls)
    sel.addEventListener('change', () => {
      const opt = sel.options[sel.selectedIndex];
      if (opt) btn.textContent = opt.text;
      menu.querySelectorAll('.custom-select-option').forEach(o => o.classList.toggle('is-selected', o.dataset.value === sel.value));
    });
  }

  enhanceCitySelect();
  document.getElementById('citySelect').addEventListener('change', () => {
    const p = gatherParams();
    updateUrl(p);
    loadPlaces(p);
  });
  document.querySelectorAll('.category-input').forEach(el => {
    el.addEventListener('change', () => {
      const p = gatherParams();
      updateUrl(p);
      loadPlaces(p);
    });
  });

  document.getElementById('locateBtn').addEventListener('click', () => {
    if (!navigator.geolocation) {
      alert('Geolokalizacja nie jest obsługiwana przez Twoją przeglądarkę.');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords;
        const radius_km = parseFloat(document.getElementById('radiusInput').value) || 10;
        const base = gatherParams();
        map.setView([latitude, longitude], 12);
        if (radiusCircle) { map.removeLayer(radiusCircle); }
        radiusCircle = L.circle([latitude, longitude], {
          radius: radius_km * 1000,
          color: '#198754',
          weight: 1,
          fillColor: '#198754',
          fillOpacity: 0.08,
        }).addTo(map);
        const p = { ...base, center_lat: latitude, center_lng: longitude, radius_km };
        updateUrl(p);
        loadPlaces(p);
      },
      (err) => {
        console.warn('Błąd geolokalizacji', err);
        alert('Nie udało się ustalić lokalizacji.');
      },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 }
    );
  });

  const initUrl = new URL(window.location.href);
  const init = {
    city: initUrl.searchParams.get('city') || '',
    categories: initUrl.searchParams.getAll('category'),
    center_lat: initUrl.searchParams.get('center_lat') || null,
    center_lng: initUrl.searchParams.get('center_lng') || null,
    radius_km: initUrl.searchParams.get('radius_km') || null,
  };
  applyParamsToControls(init);
  if (init.center_lat && init.center_lng && init.radius_km) {
    if (radiusCircle) { map.removeLayer(radiusCircle); }
    radiusCircle = L.circle([parseFloat(init.center_lat), parseFloat(init.center_lng)], {
      radius: parseFloat(init.radius_km) * 1000,
      color: '#198754',
      weight: 1,
      fillColor: '#198754',
      fillOpacity: 0.08,
    }).addTo(map);
    map.setView([parseFloat(init.center_lat), parseFloat(init.center_lng)], 12);
  }
  updateUrl(init);
  loadPlaces(init);
})();
