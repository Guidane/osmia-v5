/* Files cards: files added by picking them or dropping them on the card, a picture made the preview (★), a file
   deleted (✕). The server draws the card again after each; making a preview reloads the page, which shows it. */
(function () {
  'use strict';

  function send(card, url, body, reload) {
    body = body || new FormData();
    body.append('csrfmiddlewaretoken', window.OSMIA_CSRF);
    card.classList.add('busy');
    fetch(url, { method: 'POST', body: body, headers: { 'X-Files-Card': '1' }, credentials: 'same-origin' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        if (reload) { window.location.reload(); return; }
        var holder = document.createElement('div');
        holder.innerHTML = html.trim();
        card.replaceWith(holder.firstElementChild);
      })
      .catch(function () { card.classList.remove('busy'); alert('That did not work.'); });
  }
  function upload(card, files) {
    if (!files || !files.length) return;
    var body = new FormData();
    Array.prototype.forEach.call(files, function (f) { body.append('file', f); });
    send(card, card.dataset.files, body, !document.querySelector('.main-image') && Array.prototype.some.call(files, function (f) {
      return /^image\//.test(f.type);
    }));
  }
  function cardAt(target) { return target && target.closest ? target.closest('.files-card') : null; }
  function carriesFiles(ev) { return ev.dataTransfer && Array.prototype.indexOf.call(ev.dataTransfer.types, 'Files') >= 0; }

  document.addEventListener('change', function (ev) {
    if (ev.target.matches('.files-card [data-pick]')) upload(cardAt(ev.target), ev.target.files);
  });
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest('.files-card [data-post]');
    if (!b) return;
    ev.preventDefault();
    if (b.dataset.ask && !confirm(b.dataset.ask)) return;
    send(cardAt(b), b.dataset.post, null, b.hasAttribute('data-reload'));
  });
  ['dragenter', 'dragover'].forEach(function (type) {
    document.addEventListener(type, function (ev) {
      var card = cardAt(ev.target);
      if (card && carriesFiles(ev)) { ev.preventDefault(); card.classList.add('dropping'); }
    });
  });
  document.addEventListener('dragleave', function (ev) {
    var card = cardAt(ev.target);
    if (card && !card.contains(ev.relatedTarget)) card.classList.remove('dropping');
  });
  document.addEventListener('drop', function (ev) {
    var card = cardAt(ev.target);
    if (!card || !carriesFiles(ev)) return;
    ev.preventDefault();
    card.classList.remove('dropping');
    upload(card, ev.dataTransfer.files);
  });
})();
