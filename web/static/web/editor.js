/* The documentation editor: the page as it will look, with a toolbar at the top for headings, text styles, lists,
   links, tables, pictures and lines. What it writes is put in the form's hidden field when it is saved; the server
   keeps only safe HTML (web/markup.py). Pictures are uploaded to the documentation's files first. */
(function () {
  'use strict';

  function editor(root) {
    var area = root.querySelector('[contenteditable]');
    var field = root.querySelector('textarea[name=body]');
    var picker = root.querySelector('input[type=file]');
    var upload = root.dataset.upload;

    function run(command, value) { area.focus(); document.execCommand(command, false, value || null); }

    function insert(html) {
      area.focus();
      document.execCommand('insertHTML', false, html);
    }

    function table() {
      var rows = parseInt(prompt('How many rows (with the heading row)?', '3'), 10);
      var cols = parseInt(prompt('How many columns?', '3'), 10);
      if (!(rows > 0 && cols > 0 && rows <= 100 && cols <= 20)) return;
      var html = '<table><thead><tr>';
      for (var c = 0; c < cols; c++) html += '<th>Heading</th>';
      html += '</tr></thead><tbody>';
      for (var r = 1; r < rows; r++) {
        html += '<tr>';
        for (var d = 0; d < cols; d++) html += '<td><br></td>';
        html += '</tr>';
      }
      insert(html + '</tbody></table><p><br></p>');
    }

    function link() {
      var url = prompt('Link to (https://…):', 'https://');
      if (url && /^(https?:\/\/|mailto:|\/)/.test(url)) run('createLink', url);
    }

    var saved = null;   // where the picture goes: the selection is lost while the file is picked
    function picture() {
      var sel = window.getSelection();
      saved = sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
      picker.click();
    }

    picker.addEventListener('change', function () {
      if (!picker.files.length) return;
      var body = new FormData();
      Array.prototype.forEach.call(picker.files, function (f) { body.append('file', f); });
      body.append('csrfmiddlewaretoken', window.OSMIA_CSRF);
      fetch(upload, { method: 'POST', body: body, headers: { 'X-Requested-With': 'fetch' } })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          area.focus();
          if (saved) { var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(saved); }
          res.files.forEach(function (f) {
            insert(f.image ? '<img src="' + f.url + '" alt="">' : '<a href="' + f.url + '">📎 ' + f.name.replace(/</g, '&lt;') + '</a>');
          });
          picker.value = '';
        });
    });

    var actions = {
      p: function () { run('formatBlock', 'P'); }, h2: function () { run('formatBlock', 'H2'); },
      h3: function () { run('formatBlock', 'H3'); }, h4: function () { run('formatBlock', 'H4'); },
      bold: function () { run('bold'); }, italic: function () { run('italic'); }, underline: function () { run('underline'); },
      strike: function () { run('strikeThrough'); }, ul: function () { run('insertUnorderedList'); }, ol: function () { run('insertOrderedList'); },
      quote: function () { run('formatBlock', 'BLOCKQUOTE'); }, code: function () { run('formatBlock', 'PRE'); },
      link: link, unlink: function () { run('unlink'); }, table: table, picture: picture,
      hr: function () { insert('<hr><p><br></p>'); }, undo: function () { run('undo'); }, redo: function () { run('redo'); },
      clear: function () { run('removeFormat'); }
    };
    root.querySelectorAll('[data-do]').forEach(function (b) {
      b.addEventListener('mousedown', function (e) { e.preventDefault(); });   // keep the selection in the text
      b.addEventListener('click', function () { actions[b.dataset.do](); });
    });
    root.querySelector('select[data-block]').addEventListener('change', function (e) {
      actions[e.target.value](); e.target.value = '';
    });

    /* Table rows and columns: added after or taken away where the cursor is. */
    function cell() {
      var node = window.getSelection().anchorNode;
      while (node && node !== area) { if (node.nodeName === 'TD' || node.nodeName === 'TH') return node; node = node.parentNode; }
      return null;
    }
    root.querySelectorAll('[data-table]').forEach(function (b) {
      b.addEventListener('mousedown', function (e) { e.preventDefault(); });
      b.addEventListener('click', function () {
        var c = cell();
        if (!c) { alert('Put the cursor in a table first.'); return; }
        var row = c.parentNode, table = row.closest('table'), index = Array.prototype.indexOf.call(row.children, c);
        if (b.dataset.table === 'row') {
          var copy = row.cloneNode(true);
          Array.prototype.forEach.call(copy.children, function (x) { var td = document.createElement('td'); td.innerHTML = '<br>'; x.replaceWith(td); });
          (row.parentNode.nodeName === 'THEAD' ? table.querySelector('tbody') || table : row.parentNode).insertBefore(copy, row.parentNode.nodeName === 'THEAD' ? null : row.nextSibling);
        } else if (b.dataset.table === 'col') {
          table.querySelectorAll('tr').forEach(function (r) {
            var x = document.createElement(r.parentNode.nodeName === 'THEAD' ? 'th' : 'td'); x.innerHTML = '<br>';
            r.insertBefore(x, r.children[index + 1] || null);
          });
        } else if (b.dataset.table === 'delrow') {
          row.remove();
        } else if (b.dataset.table === 'delcol') {
          table.querySelectorAll('tr').forEach(function (r) { if (r.children[index]) r.children[index].remove(); });
        }
      });
    });

    root.closest('form').addEventListener('submit', function () { field.value = area.innerHTML; });
    window.addEventListener('beforeunload', function (e) {
      if (field.value !== area.innerHTML && !root.closest('form').dataset.sent) { e.preventDefault(); e.returnValue = ''; }
    });
    root.closest('form').addEventListener('submit', function () { root.closest('form').dataset.sent = '1'; });
    field.value = area.innerHTML;
  }

  document.querySelectorAll('.doc-edit').forEach(editor);
})();
