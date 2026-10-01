(function () {
  'use strict';

  // Algolia returns highlighted fragments wrapped in these sentinels. They are
  // split on and turned into <mark> nodes rather than assigned via innerHTML,
  // so nothing a post contains can ever become markup in the dialog.
  var MARK_OPEN = '\u0001';
  var MARK_CLOSE = '\u0002';

  var DEBOUNCE_MS = 140;
  var HITS_PER_PAGE = 8;
  var SCRIPT_ID = 'internote-search';

  var script = document.getElementById(SCRIPT_ID);
  if (!script) {
    return;
  }

  var appId = script.dataset.appId;
  var apiKey = script.dataset.apiKey;
  var indexName = script.dataset.index;
  if (!appId || !apiKey || !indexName) {
    return;
  }

  var labels = {
    noResults: script.dataset.noResults || 'No results for'
  };

  var endpoint =
    'https://' +
    appId +
    '-dsn.algolia.net/1/indexes/' +
    encodeURIComponent(indexName) +
    '/query';

  // ---------------------------------------------------------------- overlay

  var overlay = null;
  var input = null;
  var list = null;
  var status = null;
  var cursor = 0;
  var debounce = 0;
  var seq = 0;
  var lastFocus = null;

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

  // Turns Algolia's MARK_OPEN/MARK_CLOSE sentinels into <mark> elements.
  // Text nodes only; innerHTML is never used.
  function appendHighlighted(parent, value) {
    if (!value) {
      return;
    }
    var parts = String(value).split(MARK_OPEN);
    for (var i = 0; i < parts.length; i++) {
      var chunk = parts[i];
      if (chunk === '') {
        continue;
      }
      var pieces = chunk.split(MARK_CLOSE);
      parent.appendChild(document.createTextNode(pieces[0]));
      for (var j = 1; j < pieces.length; j++) {
        if (pieces[j - 1]) {
          parent.appendChild(el('mark', 'in-search-hit-mark', pieces[j - 1]));
        }
        parent.appendChild(document.createTextNode(pieces[j]));
      }
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
    // The Algolia logo is a condition of the free tier, so it is rendered
    // unconditionally rather than behind a flag.
    var credit = el('a', 'in-search-credit', 'Search by Algolia');
    credit.href = 'https://www.algolia.com/';
    credit.target = '_blank';
    credit.rel = 'noopener';
    foot.appendChild(status);
    foot.appendChild(credit);

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

  function snippetFor(hit) {
    var snippet = hit._snippetResult && hit._snippetResult.body;
    if (snippet && snippet.value) {
      return snippet.value;
    }
    return hit.body || '';
  }

  function renderHits(results, nbHits) {
    clearResults();

    if (!results.length) {
      renderEmpty(input.value ? labels.noResults + ' "' + input.value + '"' : '');
      status.textContent = '';
      return;
    }

    results.forEach(function (hit, index) {
      var item = el('li', 'in-search-hit');
      item.setAttribute('role', 'option');
      item.id = 'in-search-hit-' + index;
      item.setAttribute('aria-selected', index === 0 ? 'true' : 'false');

      var link = el('a', 'in-search-hit-link');
      link.href = hit.url;

      var title = el('span', 'in-search-hit-title');
      appendHighlighted(
        title,
        hit._highlightResult && hit._highlightResult.title
          ? hit._highlightResult.title.value
          : hit.title
      );
      link.appendChild(title);

      var badges = el('span', 'in-search-hit-labels');
      (hit.labels || []).forEach(function (label) {
        badges.appendChild(el('span', 'in-badge in-search-hit-label', label));
      });
      link.appendChild(badges);

      var snippet = el('span', 'in-search-hit-snippet');
      appendHighlighted(snippet, snippetFor(hit));
      link.appendChild(snippet);

      item.appendChild(link);
      item.addEventListener('click', function () {
        close();
      });
      list.appendChild(item);
    });

    var total = typeof nbHits === 'number' ? nbHits : results.length;
    status.textContent =
      total > results.length
        ? results.length + ' / ' + total
        : String(results.length);
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

  function query(term) {
    var mine = ++seq;
    var body = {
      query: term,
      hitsPerPage: HITS_PER_PAGE,
      attributesToHighlight: ['title'],
      attributesToSnippet: ['body:25'],
      highlightPreTag: MARK_OPEN,
      highlightPostTag: MARK_CLOSE
    };

    return fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Algolia-Application-Id': appId,
        'X-Algolia-API-Key': apiKey
      },
      body: JSON.stringify(body)
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error('HTTP ' + response.status);
        }
        return response.json();
      })
      .then(function (data) {
        // A slow earlier request must not overwrite a newer one.
        if (mine !== seq) {
          return;
        }
        renderHits(data.hits || [], data.nbHits);
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
      query(term);
    }, DEBOUNCE_MS);
  }

  // ------------------------------------------------------------ open/close

  function open() {
    lastFocus = document.activeElement;
    overlay.hidden = false;
    document.documentElement.classList.add('in-search-open-page');
    renderEmpty('');
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