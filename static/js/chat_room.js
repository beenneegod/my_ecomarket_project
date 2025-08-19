(function(){
  const root = document.getElementById('chat-root');
  if (!root) return;
  const messagesBox = document.getElementById('messages');
  const form = document.getElementById('sendForm');
  const inviteForm = document.getElementById('inviteForm');
  const attachmentsInput = document.getElementById('attachments');
  const attachmentsInfo = document.getElementById('attachmentsInfo');
  // Keep cumulative selection across multiple chooser uses
  let selectedFiles = [];
  // Create a small preview strip for images (no inline styles; CSS handles look)
  let attachmentsPreview = document.getElementById('attachmentsPreview');
  if (!attachmentsPreview && attachmentsInfo && attachmentsInfo.parentElement){
    attachmentsPreview = document.createElement('div');
    attachmentsPreview.id = 'attachmentsPreview';
    attachmentsPreview.className = 'chat-attachments-preview';
    attachmentsInfo.parentElement.appendChild(attachmentsPreview);
  }

  const roomId = parseInt(root.dataset.roomId, 10);
  const currentUsername = root.dataset.username || '';
  const messagesApi = root.dataset.messagesApi;
  const csrftoken = (document.querySelector('[name=csrfmiddlewaretoken]') || {}).value || '';

  let socket = null;
  let wsReady = false;
  let pollTimer = null;
  let lastId = null;
  const seenIds = new Set();
  const pendingByClientId = new Map();
  const SCROLL_STICKY_PX = 60; // threshold to consider user at bottom
  function isNearBottom(){
    if (!messagesBox) return true;
    const delta = messagesBox.scrollHeight - messagesBox.scrollTop - messagesBox.clientHeight;
    return delta <= SCROLL_STICKY_PX;
  }
  function scrollToBottom(){
    if (!messagesBox) return;
    messagesBox.scrollTop = messagesBox.scrollHeight;
  }

  // New messages bar (shown when not at bottom and new messages arrive)
  let newBar = document.getElementById('newMsgBar');
  if (!newBar && root){
    newBar = document.createElement('div');
    newBar.id = 'newMsgBar';
    newBar.className = 'alert alert-primary py-1 px-2 d-none';
    newBar.style.cursor = 'pointer';
    newBar.innerHTML = 'Nowe wiadomości: <strong><span id="newMsgCount">0</span></strong> — Na dół ⬇';
    // place right after messagesBox
    messagesBox.insertAdjacentElement('afterend', newBar);
  }
  let newCount = 0;
  function showNewBar(){ if (newBar) newBar.classList.remove('d-none'); }
  function hideNewBar(){ if (newBar) newBar.classList.add('d-none'); }
  function resetNewBar(){ newCount = 0; const span = newBar && newBar.querySelector('#newMsgCount'); if (span) span.textContent = '0'; hideNewBar(); }
  if (newBar){
    newBar.addEventListener('click', () => { scrollToBottom(); resetNewBar(); });
  }
  if (messagesBox){
  messagesBox.addEventListener('scroll', () => { if (isNearBottom()) { resetNewBar(); showScrollBtn(false); } else { showScrollBtn(true); } });
  }

  // Typing indicator
  let typingIndicator = document.getElementById('typingIndicator');
  if (!typingIndicator && messagesBox && messagesBox.parentElement){
    typingIndicator = document.createElement('div');
    typingIndicator.id = 'typingIndicator';
    typingIndicator.className = 'text-muted small mt-1';
    typingIndicator.style.minHeight = '1em';
    messagesBox.parentElement.appendChild(typingIndicator);
  }
  let typingHideTimer = null;
  function showTyping(name){
    if (!typingIndicator) return;
    typingIndicator.textContent = `${name} pisze…`;
    clearTimeout(typingHideTimer);
    typingHideTimer = setTimeout(() => { typingIndicator.textContent = ''; }, 2500);
  }
  function clearTyping(){ if (typingIndicator) typingIndicator.textContent = ''; }

  function renderMessage(m, opts){
    const animate = !opts || opts.animate !== false;
    if (m.id && seenIds.has(m.id)) {
      const existing = messagesBox.querySelector(`[data-id="${m.id}"] [data-text]`);
      if (existing && typeof m.text === 'string') existing.textContent = m.text;
      return;
    }
    // Reconcile optimistic message if client_id matches
    if (m.client_id && pendingByClientId.has(m.client_id)){
      const el = pendingByClientId.get(m.client_id);
      pendingByClientId.delete(m.client_id);
      if (m.id){ el.dataset.id = String(m.id); seenIds.add(m.id); lastId = m.id; }
      const txt = el.querySelector('[data-text]');
      if (txt && typeof m.text === 'string') txt.textContent = m.text;
      el.classList.remove('pending');
      // update header if needed
      const headerUser = el.querySelector('strong');
      if (headerUser && m.user) headerUser.textContent = m.user;
      const timeEl = el.querySelector('small');
      if (timeEl && m.created_at) timeEl.textContent = new Date(m.created_at).toLocaleTimeString();
      // ensure reply preview is present
      if (m.reply_to && !el.querySelector('.chat-reply')){
        const reply = document.createElement('div');
        reply.className = 'chat-reply small text-muted';
        reply.textContent = `${m.reply_to.user || ''}: ${m.reply_to.text || ''}`.trim();
        el.insertBefore(reply, el.querySelector('[data-text]'));
      }
      // ensure delete icon is present once server confirms permissions
      if (m.can_delete && m.id && !el.querySelector('[data-del]')){
        const delBtn = document.createElement('button');
        delBtn.type = 'button';
        delBtn.className = 'chat-delete-btn';
        delBtn.setAttribute('data-del', String(m.id));
        delBtn.setAttribute('title', 'Usuń wiadomość');
        delBtn.setAttribute('aria-label', 'Usuń wiadomość');
        delBtn.textContent = '×';
        el.appendChild(delBtn);
      }
      return;
    }
    const stick = isNearBottom();
  const el = document.createElement('div');
    el.className = 'chat-msg';
    if (animate) el.classList.add('enter');
    const time = new Date(m.created_at || Date.now()).toLocaleTimeString();

  const header = document.createElement('div');
    header.className = 'd-flex align-items-center gap-2';
    const userEl = document.createElement('strong');
    userEl.textContent = m.user || '—';
    header.appendChild(userEl);
    const timeEl = document.createElement('small');
    timeEl.className = 'text-muted';
    timeEl.textContent = time;
    header.appendChild(timeEl);
    if (m.can_delete && m.id){
      const delBtn = document.createElement('button');
      delBtn.type = 'button';
      delBtn.className = 'chat-delete-btn';
      delBtn.setAttribute('data-del', String(m.id));
      delBtn.setAttribute('title', 'Usuń wiadomość');
      delBtn.setAttribute('aria-label', 'Usuń wiadomość');
      delBtn.textContent = '×';
      el.appendChild(delBtn);
    }

    // Reply preview
    if (m.reply_to){
      const reply = document.createElement('div');
      reply.className = 'chat-reply small text-muted';
      reply.textContent = `${m.reply_to.user || ''}: ${m.reply_to.text || ''}`.trim();
      el.appendChild(reply);
    }

    const textWrap = document.createElement('div');
    if (m.id) textWrap.setAttribute('data-text', String(m.id));
    textWrap.textContent = m.text || '';

  el.appendChild(header);
  el.appendChild(textWrap);

    if (Array.isArray(m.attachments) && m.attachments.length){
      const att = document.createElement('div');
      att.className = 'mt-1 chat-attachments';
      m.attachments.forEach(a => {
        try {
          const isImg = /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(a.name || a.url || '');
          if (isImg){
            const aLink = document.createElement('a');
            aLink.href = a.url;
            aLink.className = 'chat-attach-thumb-link';
            aLink.setAttribute('data-image', '1');
            const img = document.createElement('img');
            img.src = a.url;
            img.alt = a.name || '';
            img.className = 'chat-attach-thumb';
            aLink.appendChild(img);
            att.appendChild(aLink);
          } else {
            const link = document.createElement('a');
            link.href = a.url;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.textContent = `📎 ${a.name}`;
            att.appendChild(link);
            att.appendChild(document.createTextNode(' '));
          }
        } catch(_) { /* ignore invalid attachment */ }
      });
      el.appendChild(att);
    }

    if (m.is_current_user || (m.user && m.user === currentUsername)) {
      el.classList.add('from-current-user');
    }
    // Reply button for other users' messages (hover-only icon)
    if ((!m.is_current_user) && (!m.user || m.user !== currentUsername) && m.id){
      const replyBtn = document.createElement('button');
      replyBtn.type = 'button';
      replyBtn.className = 'chat-reply-btn';
      replyBtn.setAttribute('data-reply', String(m.id));
      replyBtn.setAttribute('title', 'Odpowiedz');
      replyBtn.setAttribute('aria-label', 'Odpowiedz');
      replyBtn.textContent = '↩';
      el.appendChild(replyBtn);
    }
    if (m.id) {
      el.dataset.id = String(m.id);
      seenIds.add(m.id);
    }
  messagesBox.appendChild(el);
    if (animate){
      // Next frame remove the enter class to trigger transition
      requestAnimationFrame(() => { requestAnimationFrame(() => { el.classList.remove('enter'); }); });
    }
  if (stick) {
      scrollToBottom();
    } else {
      // Count new incoming messages only if not authored by current user
      if (!m.user || m.user !== currentUsername){
        newCount += 1;
        const span = newBar && newBar.querySelector('#newMsgCount');
        if (span) span.textContent = String(newCount);
        showNewBar();
      }
    }
    if (m.id) lastId = m.id;
  }

  async function pollOnce(){
    const qs = lastId ? ('?since_id=' + lastId) : '';
    try {
      const resp = await fetch(messagesApi + qs);
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.messages && data.messages.length){
        const isInitial = !lastId;
        data.messages.forEach(m => renderMessage(m, { animate: !isInitial }));
        if (isInitial) scrollToBottom();
      }
    } catch(_){ /* ignore */ }
  }

  function ensurePolling(){
    if (pollTimer || wsReady) return;
    pollTimer = setInterval(pollOnce, 3000);
    pollOnce();
  }
  function stopPolling(){ if (pollTimer){ clearInterval(pollTimer); pollTimer = null; } }

  function connectWS(){
    const scheme = (window.location.protocol === 'https:') ? 'wss' : 'ws';
    const wsUrl = `${scheme}://${window.location.host}/ws/chat/${roomId}/`;
    try { socket = new WebSocket(wsUrl); }
    catch(err){ ensurePolling(); return; }
  socket.onopen = () => { wsReady = true; stopPolling(); };
  socket.onclose = () => { wsReady = false; ensurePolling(); };
  socket.onerror = () => { wsReady = false; ensurePolling(); };
    socket.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
  if (data.type === 'history' && Array.isArray(data.messages)){
          data.messages.forEach(m => renderMessage(m, { animate: false }));
          scrollToBottom();
          showScrollBtn(false);
        } else if (data.type === 'message'){
          renderMessage(data, { animate: true });
        } else if (data.type === 'typing' && data.user && data.user !== currentUsername){
          showTyping(data.user);
        } else if (data.type === 'message_removed'){
            const wrap = messagesBox.querySelector(`[data-id="${data.id}"]`);
            if (wrap){ wrap.classList.add('removing'); setTimeout(() => { wrap.remove(); }, 180); }
        }
      } catch(err) { /* ignore */ }
    };
  }

  // Floating scroll-to-bottom button
  let scrollBtn = document.getElementById('chatScrollBottom');
  function ensureScrollBtn(){
    if (!messagesBox) return;
    if (!scrollBtn){
      scrollBtn = document.createElement('button');
      scrollBtn.id = 'chatScrollBottom';
      scrollBtn.type = 'button';
  scrollBtn.className = 'btn btn-sm btn-primary chat-scroll-bottom';
  scrollBtn.innerHTML = '⬇';
      messagesBox.appendChild(scrollBtn);
      scrollBtn.addEventListener('click', () => { scrollToBottom(); resetNewBar(); showScrollBtn(false); });
    }
  }
  function updateScrollBtnPos(){
    if (!messagesBox || !scrollBtn) return;
    const padding = 10;
    const btnRect = scrollBtn.getBoundingClientRect();
    // Position relative to scroll content top so it sticks to the visible bottom
    const top = messagesBox.scrollTop + messagesBox.clientHeight - btnRect.height - padding;
    scrollBtn.style.top = `${top}px`;
    scrollBtn.style.right = `${padding}px`;
  }
  function showScrollBtn(flag){ ensureScrollBtn(); if (!scrollBtn) return; scrollBtn.classList.toggle('is-visible', !!flag); updateScrollBtnPos(); }
  ensureScrollBtn();
  updateScrollBtnPos();
  window.addEventListener('resize', updateScrollBtnPos);
  if (messagesBox){ messagesBox.addEventListener('scroll', updateScrollBtnPos); }

  // Lightbox for image attachments
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
  messagesBox.addEventListener('click', (e) => {
    const link = e.target.closest('.chat-attach-thumb-link');
    if (!link) return;
    e.preventDefault();
    const bubble = e.target.closest('.chat-msg');
    if (!bubble) return;
    ensureLightbox();
    const items = Array.from(bubble.querySelectorAll('.chat-attach-thumb-link'));
    const list = items.map(a => ({ url: a.getAttribute('href') || '', alt: (a.querySelector('img')||{}).alt || '' }));
    const idx = Math.max(0, items.indexOf(link));
    lightbox.open(list, idx);
  });

  let lastSubmitAt = 0; // debounce duplicate sends
  // Reply state
  let replyingTo = null; // {id, user, text}
  function setReplying(to){
    replyingTo = to || null;
    let bar = document.getElementById('replyBar');
    if (replyingTo){
      if (!bar){
        bar = document.createElement('div');
        bar.id = 'replyBar';
        bar.className = 'reply-bar d-flex align-items-center gap-2';
        form.insertAdjacentElement('beforebegin', bar);
      }
      bar.innerHTML = `
        <span class="reply-icon" aria-hidden="true">↩</span>
        <span class="small text-muted">Odpowiedź na:</span>
        <strong>${replyingTo.user || ''}</strong>
        <span class="reply-excerpt text-truncate">${replyingTo.text || ''}</span>
        <button type="button" id="cancelReply" class="reply-close ms-auto" aria-label="Anuluj odpowiedź">×</button>`;
      bar.querySelector('#cancelReply').onclick = () => setReplying(null);
    } else if (bar){ bar.remove(); }
  }
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = form.querySelector('textarea, input[name="text"]');
    const text = (input && input.value || '').trim();
    const hasFiles = (attachmentsInput.files && attachmentsInput.files.length > 0);
    const submitBtn = form.querySelector('[type="submit"]') || form.querySelector('button');

    const now = Date.now();
    if (now - lastSubmitAt < 800) return; // prevent rapid double-submit
    lastSubmitAt = now;
    if (submitBtn) submitBtn.disabled = true;

  if (text && !hasFiles && wsReady && socket && socket.readyState === 1){
      // Optimistic echo
      const clientId = 'c' + Math.random().toString(36).slice(2, 10) + Date.now();
      const el = document.createElement('div');
      el.className = 'mb-2 chat-msg pending enter from-current-user';
      const header = document.createElement('div');
      header.className = 'd-flex align-items-center gap-2';
      const userEl = document.createElement('strong'); userEl.textContent = currentUsername || '—';
      const timeEl = document.createElement('small'); timeEl.className = 'text-muted'; timeEl.textContent = new Date().toLocaleTimeString();
      header.appendChild(userEl); header.appendChild(timeEl);
      if (replyingTo){
        const reply = document.createElement('div');
        reply.className = 'chat-reply small text-muted';
        reply.textContent = `${replyingTo.user || ''}: ${replyingTo.text || ''}`.trim();
        el.appendChild(reply);
      }
      const textWrap = document.createElement('div'); textWrap.setAttribute('data-text', clientId); textWrap.textContent = text;
      el.appendChild(header); el.appendChild(textWrap);
      messagesBox.appendChild(el);
      requestAnimationFrame(() => { requestAnimationFrame(() => { el.classList.remove('enter'); }); });
      pendingByClientId.set(clientId, el);
      scrollToBottom();
      // Send over WS with correlation id
      const payload = { action: 'send', text, client_id: clientId };
      if (replyingTo) payload.reply_to_id = replyingTo.id;
  socket.send(JSON.stringify(payload));
      form.reset();
      attachmentsInfo.textContent = '';
      attachmentsInput.value = '';
      if (attachmentsPreview) attachmentsPreview.innerHTML = '';
      setTimeout(() => { if (submitBtn) submitBtn.disabled = false; }, 150);
  setReplying(null);
      return;
    }

    try {
  const fd = new FormData(form);
      if (replyingTo) fd.append('reply_to', String(replyingTo.id));
      const resp = await fetch(form.action, { method: 'POST', body: fd, headers: { 'X-CSRFToken': csrftoken } });
      if (resp.ok){
        form.reset();
        attachmentsInfo.textContent = '';
        attachmentsInput.value = '';
  selectedFiles = [];
        if (attachmentsPreview) attachmentsPreview.innerHTML = '';
  // quick one-off refresh; keep polling only if WS is not connected
  pollOnce();
  if (!wsReady) ensurePolling();
        setReplying(null);
      } else {
        try {
          const err = await resp.json();
          const msgs = Array.isArray(err.errors) ? err.errors : (err.error ? [String(err.error)] : ['Błąd wysyłki wiadomości']);
          attachmentsInfo.textContent = msgs.join(' · ');
        } catch(_){
          attachmentsInfo.textContent = 'Błąd wysyłki wiadomości';
        }
      }
    } catch(_){ /* ignore */ }
    finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  });

  messagesBox.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-del]');
    if (!btn) return;
    const id = btn.getAttribute('data-del');
      const wrap = messagesBox.querySelector(`[data-id="${id}"]`);
      if (wrap){ wrap.classList.add('removing'); setTimeout(() => { wrap.remove(); }, 180); }
      try{
        await fetch(`/chat/api/messages/${id}/delete/`, { method: 'POST', headers: { 'X-CSRFToken': csrftoken } });
      } catch(_){ /* ignore */ }
  });

  // Explicit reply button click
  messagesBox.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-reply]');
    if (!btn) return;
    const id = btn.getAttribute('data-reply');
    const bubble = messagesBox.querySelector(`[data-id="${id}"]`);
    if (!bubble) return;
    const userEl = bubble.querySelector('strong');
    const textEl = bubble.querySelector('[data-text]');
    setReplying({ id: Number(id), user: (userEl && userEl.textContent) || '', text: (textEl && textEl.textContent) || '' });
    e.stopPropagation();
  });

  inviteForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(inviteForm);
    try{
      const resp = await fetch(inviteForm.action, { method: 'POST', body: fd, headers: { 'X-CSRFToken': csrftoken } });
      if (resp.ok){
        inviteForm.reset();
        // Could show a toast instead
      }
    } catch(_){ /* ignore */ }
  });

  function filesArray(){ return selectedFiles.length ? selectedFiles : Array.from(attachmentsInput.files || []); }
  function setFilesFromArray(arr){
    const dt = new DataTransfer();
    arr.forEach(f => dt.items.add(f));
    attachmentsInput.files = dt.files;
  }
  const MAX_PREVIEW = 6;
  const MAX_ATTACH = 10;
  const MAX_FILE_MB = 10; // must match server
  const MAX_TOTAL_MB = 40; // must match server
  function humanMB(bytes){ return Math.round(bytes / (1024*1024)); }
  function isAllowedType(file){
    const ct = file.type || '';
    return ct.startsWith('image/') || ct === 'application/pdf';
  }
  function renderPreview(){
    if (!attachmentsPreview) return;
    attachmentsPreview.innerHTML = '';
    const files = filesArray();
    files.slice(0, MAX_PREVIEW).forEach((f, idx) => {
      if (f.type && f.type.startsWith('image/')){
        const wrap = document.createElement('div');
        wrap.className = 'chat-attachments-item';
        wrap.setAttribute('data-name', f.name);
        wrap.setAttribute('data-lastmod', String(f.lastModified || 0));
        const img = document.createElement('img');
        img.alt = f.name;
        const url = URL.createObjectURL(f);
        img.src = url;
        img.onload = () => URL.revokeObjectURL(url);
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'chat-attachments-remove';
        btn.title = 'Usuń obraz';
        btn.textContent = '×';
        wrap.appendChild(img);
        wrap.appendChild(btn);
        attachmentsPreview.appendChild(wrap);
      }
    });
  }
  attachmentsInput.addEventListener('change', () => {
    let newly = Array.from(attachmentsInput.files || []);
    // Client-side filter: type and per-file size
    const errs = [];
    newly = newly.filter(f => {
      if (!isAllowedType(f)) { errs.push(`Niedozwolony typ: ${f.name}`); return false; }
      if ((f.size || 0) > MAX_FILE_MB * 1024 * 1024) { errs.push(`Za duży plik (> ${MAX_FILE_MB} MB): ${f.name}`); return false; }
      return true;
    });
    if (errs.length){ attachmentsInfo.textContent = errs.join(' · '); }
    // If nothing new and nothing previously selected
    if (!newly.length && !selectedFiles.length){
      attachmentsInfo.textContent = '';
      if (attachmentsPreview) attachmentsPreview.innerHTML = '';
      return;
    }
    // Merge old + new with de-dup (name + lastModified + size)
    const merged = [];
    const seen = new Set();
    const addUnique = (f) => {
      const key = `${f.name}::${f.lastModified || 0}::${f.size || 0}`;
      if (seen.has(key)) return;
      seen.add(key);
      merged.push(f);
    };
    selectedFiles.forEach(addUnique);
    newly.forEach(addUnique);
    // Cap to MAX_ATTACH and total size
    let total = 0;
    const capped = [];
    for (const f of merged){
      if (capped.length >= MAX_ATTACH) break;
      if (total + (f.size || 0) > MAX_TOTAL_MB * 1024 * 1024) { continue; }
      total += (f.size || 0);
      capped.push(f);
    }
    selectedFiles = capped;
    setFilesFromArray(selectedFiles);
    const count = selectedFiles.length;
    if (!count){
      attachmentsInfo.textContent = '';
      if (attachmentsPreview) attachmentsPreview.innerHTML = '';
      return;
    }
    if (count === 1) {
      attachmentsInfo.textContent = `Wybrano 1 plik: ${selectedFiles[0].name}`;
    } else {
      attachmentsInfo.textContent = `Wybrano ${count} plików (pierwsze ${MAX_PREVIEW} w podglądzie)`;
    }
    renderPreview();
  });
  if (attachmentsPreview){
    attachmentsPreview.addEventListener('click', (e) => {
      const btn = e.target.closest('.chat-attachments-remove');
      if (!btn) return;
      const wrap = btn.closest('.chat-attachments-item');
      if (!wrap) return;
      const name = wrap.getAttribute('data-name');
      const lastmod = parseInt(wrap.getAttribute('data-lastmod') || '0');
      selectedFiles = filesArray().filter(f => !(f.name === name && (f.lastModified || 0) === lastmod));
      setFilesFromArray(selectedFiles);
      const count = selectedFiles.length;
      if (!count) { attachmentsInfo.textContent = ''; }
      else if (count === 1) { attachmentsInfo.textContent = `Wybrano 1 plik: ${selectedFiles[0].name}`; }
      else { attachmentsInfo.textContent = `Wybrano ${count} plików (pierwsze ${MAX_PREVIEW} w podglądzie)`; }
      renderPreview();
    });
  }
  // Click to set reply target
  messagesBox.addEventListener('click', (e) => {
    const bubble = e.target.closest('.chat-msg');
    if (!bubble) return;
    if (e.target.closest('[data-del]') || e.target.closest('a')) return; // ignore clicks on delete/buttons/links
    const id = bubble.getAttribute('data-id');
    if (!id) return;
    const userEl = bubble.querySelector('strong');
    const textEl = bubble.querySelector('[data-text]');
    setReplying({ id: Number(id), user: (userEl && userEl.textContent) || '', text: (textEl && textEl.textContent) || '' });
  });
  form.addEventListener('reset', () => {
    attachmentsInfo.textContent = '';
    attachmentsInput.value = '';
    selectedFiles = [];
    if (attachmentsPreview) attachmentsPreview.innerHTML = '';
  });

  // Typing notifications via WebSocket (best-effort)
  const textInput = form.querySelector('textarea, input[name="text"]');
  let lastTypingSentAt = 0;
  let stopTypingTimer = null;
  function sendTyping(flag){
    if (!wsReady || !socket || socket.readyState !== 1) return;
    try { socket.send(JSON.stringify({ action: 'typing', typing: !!flag })); } catch(_){ /* ignore */ }
  }
  function scheduleStopTyping(){
    clearTimeout(stopTypingTimer);
    stopTypingTimer = setTimeout(() => sendTyping(false), 2000);
  }
  if (textInput){
    textInput.addEventListener('input', () => {
      const now = Date.now();
      if (now - lastTypingSentAt > 1500){
        sendTyping(true);
        lastTypingSentAt = now;
      }
      scheduleStopTyping();
    });
    textInput.addEventListener('blur', () => { sendTyping(false); });
  }

  // Kick off
  connectWS();
})();
