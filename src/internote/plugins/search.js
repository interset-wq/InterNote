(function () {
  'use strict';

  // Local search: the whole index is a static JSON file written by the
  // generator (dist/search-index.json) and fetched once. Matching is a plain
  // case-insensitive substring test on title and labels; a date fragment in
  // the query filters by the post date instead.
  //
  // Matches are highlighted by splitting the raw text on the matched term and
  // wrapping the pieces in <mark> nodes created with createElement —
  // innerHTML is never used, so nothing an index contains can become markup.

  var DEBOUNCE_MS = 60;
  var MAX_HITS = 8;
  var SCRIPT_ID = 'internote-search';

  // A date fragment such as "2024", "2024-0" or "2024-05-1" filters on the
  // post date; everything else in the term still matches title/labels.
  var DATE_RE = /\d{4}(?:-\d{0,2}){0,2}/;

  var script = document.getElementById(SCRIPT_ID);
  if (!script) {
    return;
  }

  var indexUrl = script.dataset.indexUrl;
  if (!indexUrl) {
    return;
  }

  var labels = {
    noResults: script.dataset.noResults || 'No results for'
  };

  // ---------------------------------------------------------------- overlay

  var overlay = null;
  var input = null;
  var list = null;
  var status = null;
  var cursor = 0;
  var debounce = 0;
  var seq = 0;
  var lastFocus = null;
  var index = null; // array of {title, labels, date, url}, null until loaded
  var indexPromise = null;

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) {
      node.className = cls;
    }
    if (text !== undefined) {
      node.textContent = text;
    }
    return node;
  }

  // Wraps every case-insensitive occurrence of `term` in `value` with <mark>.
  // Text nodes only; innerHTML is never used.
  function appendHighlighted(parent, value, term) {
    if (!value) {
      return;
    }
    var text = String(value);
    if (!term) {
      parent.appendChild(document.createTextNode(text));
      return;
    }
    var lower = text.toLowerCase();
    var needle = term.toLowerCase();
    var at = 0;
    var hit = lower.indexOf(needle);
    while (hit !== -1) {
      if (hit > at) {
        parent.appendChild(document.createTextNode(text.slice(at, hit)));
      }
      parent.appendChild(el('mark', 'in-search-hit-mark', text.slice(hit, hit + needle.length)));
      at = hit + needle.length;
      hit = lower.indexOf(needle, at);
    }
    if (at < text.length) {
      parent.appendChild(document.createTextNode(text.slice(at)));
    }
  }

  function build() {
    overlay = el('div', 'in-search-overlay');
    overlay.hidden = true;

    var panel = el('div', 'in-search-panel');
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-label', script.dataset.placeholder || 'Search');

    var head = el('div', 'in-search-head');
    // Same pattern tag.j2.html uses for its post glyph: draw the Octicons
    // path from window.icons rather than inlining a second icon.
    var glyph = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    glyph.setAttribute('class', 'octicon in-search-head-icon');
    glyph.setAttribute('width', '16');
    glyph.setAttribute('height', '16');
    glyph.setAttribute('aria-hidden', 'true');
    var glyphPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    glyphPath.setAttribute('d', (window.icons || {}).search || '');
    glyphPath.setAttribute('fill-rule', 'evenodd');
    glyph.appendChild(glyphPath);
    head.appendChild(glyph);

    input = el('input', 'in-search-modal-input');
    input.type = 'search';
    input.autocomplete = 'off';
    input.spellcheck = false;
    input.placeholder = script.dataset.placeholder || '';
    input.setAttribute('aria-label', script.dataset.placeholder || 'Search');
    input.setAttribute('aria-controls', 'in-search-results');
    head.appendChild(input);

    list = el('ul', 'in-search-results');
    list.id = 'in-search-results';
    list.setAttribute('role', 'listbox');

    var foot = el('div', 'in-search-foot');
    status = el('span', 'in-search-status');
    foot.appendChild(status);

    panel.appendChild(head);
    panel.appendChild(list);
    panel.appendChild(foot);
    overlay.appendChild(panel);
    document.body.appendChild(overlay);
  }

  // ---------------------------------------------------------------- results

  function clearResults() {
    while (list.firstChild) {
      list.removeChild(list.firstChild);
    }
    cursor = 0;
  }

  function renderEmpty(message) {
    clearResults();
    // No placeholder when there is nothing to say: an empty <li> would still
    // occupy its padded height and read as a blank band under the input.
    if (!message) {
      return;
    }
    var empty = el('li', 'in-search-empty', message);
    empty.setAttribute('role', 'presentation');
    list.appendChild(empty);
  }

  function renderHits(results) {
    clearResults();

    if (!results.length) {
      renderEmpty(input.value ? labels.noResults + ' "' + input.value + '"' : '');
      status.textContent = '';
      return;
    }

    var term = lastTerm;
    results.forEach(function (record, index) {
      var item = el('li', 'in-search-hit');
      item.setAttribute('role', 'option');
      item.id = 'in-search-hit-' + index;
      item.setAttribute('aria-selected', index === 0 ? 'true' : 'false');

      var link = el('a', 'in-search-hit-link');
      link.href = record.url;

      var title = el('span', 'in-search-hit-title');
      appendHighlighted(title, record.title, term.title);
      link.appendChild(title);

      var badges = el('span', 'in-search-hit-labels');
      (record.labels || []).forEach(function (label) {
        badges.appendChild(el('span', 'in-badge in-search-hit-label', label));
      });
      link.appendChild(badges);

      var date = el('span', 'in-search-hit-snippet', record.date || '');
      link.appendChild(date);

      item.appendChild(link);
      item.addEventListener('click', function () {
        close();
      });
      list.appendChild(item);
    });

    var total = results.length;
    status.textContent = total > MAX_HITS ? MAX_HITS + ' / ' + total : String(total);
    select(0);
  }

  function select(next) {
    var items = list.querySelectorAll('.in-search-hit');
    if (!items.length) {
      return;
    }
    cursor = (next + items.length) % items.length;
    for (var i = 0; i < items.length; i++) {
      var active = i === cursor;
      items[i].classList.toggle('is-active', active);
      items[i].setAttribute('aria-selected', active ? 'true' : 'false');
    }
    items[cursor].scrollIntoView({ block: 'nearest' });
    input.setAttribute('aria-activedescendant', items[cursor].id);
  }

  // ----------------------------------------------------------------- query

  // The parts of the term that drove the current result set, so the highlight
  // pass uses the same text the match did.
  var lastTerm = { text: '', title: '' };

  function loadIndex() {
    if (indexPromise) {
      return indexPromise;
    }
    indexPromise = fetch(indexUrl)
      .then(function (response) {
        if (!response.ok) {
          throw new Error('HTTP ' + response.status);
        }
        return response.json();
      })
      .then(function (data) {
        // The file is shared with the tag page: {label_colors, posts}.
        var posts = data && Array.isArray(data.posts) ? data.posts : [];
        index = posts;
        return index;
      })
      .catch(function (error) {
        // A failed fetch must not poison later retries: drop the promise so
        // the next keystroke fetches again.
        indexPromise = null;
        throw error;
      });
    return indexPromise;
  }

  function matchRecord(record, rest, datePrefix) {
    if (datePrefix && String(record.date || '').indexOf(datePrefix) !== 0) {
      return false;
    }
    if (!rest) {
      return true;
    }
    var needle = rest.toLowerCase();
    if (String(record.title || '').toLowerCase().indexOf(needle) !== -1) {
      lastTerm.title = rest;
      return true;
    }
    var labelsList = record.labels || [];
    for (var i = 0; i < labelsList.length; i++) {
      if (String(labelsList[i]).toLowerCase().indexOf(needle) !== -1) {
        return true;
      }
    }
    return false;
  }

  function searchLocal(term) {
    var mine = ++seq;
    loadIndex()
      .then(function (records) {
        if (mine !== seq) {
          return;
        }
        var dateMatch = term.match(DATE_RE);
        var datePrefix = dateMatch ? dateMatch[0] : '';
        // The date fragment only filters; the remainder matches text.
        var rest = datePrefix ? term.replace(datePrefix, '').trim() : term;
        lastTerm = { text: term, title: rest };

        var scored = [];
        for (var i = 0; i < records.length; i++) {
          if (matchRecord(records[i], rest, datePrefix)) {
            scored.push(records[i]);
          }
        }
        // Newest first; the generator writes dates as YYYY-MM-DD, so a
        // string compare is a chronological compare.
        scored.sort(function (a, b) {
          return String(b.date || '') < String(a.date || '') ? -1 : 1;
        });
        renderHits(scored.slice(0, MAX_HITS));
      })
      .catch(function (error) {
        if (mine !== seq) {
          return;
        }
        renderEmpty(String(error && error.message ? error.message : error));
        status.textContent = '';
      });
  }

  function onInput() {
    window.clearTimeout(debounce);
    var term = input.value.trim();
    if (!term) {
      seq++;
      renderEmpty('');
      status.textContent = '';
      return;
    }
    debounce = window.setTimeout(function () {
      searchLocal(term);
    }, DEBOUNCE_MS);
  }

  // ------------------------------------------------------------ open/close

  function open() {
    lastFocus = document.activeElement;
    overlay.hidden = false;
    document.documentElement.classList.add('in-search-open-page');
    renderEmpty('');
    loadIndex(); // warm the cache while the dialog is still empty
    input.focus();
    input.select();
  }

  function close() {
    overlay.hidden = true;
    document.documentElement.classList.remove('in-search-open-page');
    window.clearTimeout(debounce);
    seq++;
    if (lastFocus && lastFocus.focus) {
      lastFocus.focus();
    }
  }

  function isOpen() {
    return !overlay.hidden;
  }

  function onKeydown(event) {
    // Escape, arrows and Enter stay: they operate the dialog once it is open
    // and are never advertised. There is deliberately no global shortcut, so
    // the handler returns immediately while the dialog is closed.
    if (!isOpen()) {
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      select(cursor + 1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      select(cursor - 1);
    } else if (event.key === 'Enter') {
      var active = list.querySelector('.in-search-hit.is-active a');
      if (active) {
        event.preventDefault();
        window.location.href = active.href;
      }
    }
  }

  function init() {
    build();

    input.addEventListener('input', onInput);
    overlay.addEventListener('mousedown', function (event) {
      // Only a click on the backdrop itself dismisses, so a drag that ends
      // outside a result does not close the dialog.
      if (event.target === overlay) {
        close();
      }
    });

    var opener = document.getElementById('in-search-open');
    if (opener) {
      opener.addEventListener('click', function () {
        if (isOpen()) {
          close();
        } else {
          open();
        }
      });
    }

    document.addEventListener('keydown', onKeydown);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
