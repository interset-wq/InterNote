(function () {
  'use strict';

  // Floating action buttons (bottom-right) for post pages: TOC overlay,
  // scroll to top, scroll to bottom. Only rendered below 1250px, where the
  // sidebar TOC collapses into the top of the article and is useless for
  // navigation while reading. The TOC overlay reuses the #in-toc markup
  // that toc.js already built.
  function init() {
    var fab = document.getElementById('in-fab');
    if (!fab) {
      return;
    }
    // Desktop keeps the sidebar TOC untouched: no floating stack there
    // (CSS hides .in-fab anyway) and #in-toc must stay in the article.
    if (window.matchMedia('(min-width: 1250px)').matches) {
      return;
    }
    var tocRoot = document.getElementById('in-toc');
    // No post body (or no headings -> toc.js removed #in-toc): keep only
    // the scroll buttons; without #in-toc there is nothing to toggle.
    if (!tocRoot) {
      var tocBtn = fab.querySelector('.in-fab-btn-toc');
      if (tocBtn) {
        tocBtn.parentNode.removeChild(tocBtn);
      }
    }

    function button(className, iconName, label, onClick) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'in-fab-btn ' + className;
      btn.setAttribute('aria-label', label);
      btn.title = label;
      btn.addEventListener('click', onClick);
      var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', '0 0 16 16');
      svg.setAttribute('width', '18');
      svg.setAttribute('height', '18');
      svg.setAttribute('aria-hidden', 'true');
      // no .octicon class here (that would pull Primer's fill rule via a
      // class this svg does not carry) - set it directly so the glyph
      // follows the button colour instead of the default black, which
      // vanished on the dark-mode button background
      svg.setAttribute('fill', 'currentColor');
      var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('fill-rule', 'evenodd');
      path.setAttribute('d', (window.icons || {})[iconName] || '');
      svg.appendChild(path);
      btn.appendChild(svg);
      return btn;
    }

    if (tocRoot) {
      var overlay = document.createElement('div');
      overlay.className = 'in-fab-toc-overlay';
      overlay.hidden = true;
      // toc.js populated #in-toc with title + list + its own Top button.
      // Move the whole panel into the overlay so scroll-spy keeps working;
      // clicking any link closes the overlay.
      overlay.appendChild(tocRoot);
      document.body.appendChild(overlay);
      overlay.addEventListener('click', function (event) {
        if (event.target === overlay || event.target.closest('.in-toc-link')) {
          overlay.hidden = true;
        }
      });
      fab.appendChild(
        button('in-fab-btn-toc', 'bars', fab.dataset.tocTitle || 'Contents', function () {
          overlay.hidden = !overlay.hidden;
        })
      );
    }

    var topBtn = button(
      'in-fab-btn-top',
      'arrow-up',
      fab.dataset.topTitle || 'Top',
      function () {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    );
    var bottomBtn = button(
      'in-fab-btn-bottom',
      'arrow-down',
      fab.dataset.bottomTitle || 'Bottom',
      function () {
        window.scrollTo({
          top: document.documentElement.scrollHeight,
          behavior: 'smooth'
        });
      }
    );
    fab.appendChild(topBtn);
    fab.appendChild(bottomBtn);

    // Disable the button that does nothing: top is useless at the top,
    // bottom at the bottom. Disabled instead of hidden - the stack never
    // reflows and every button keeps its place.
    var pending = false;
    function update() {
      pending = false;
      var top = window.scrollY;
      var max =
        document.documentElement.scrollHeight - window.innerHeight;
      topBtn.disabled = top < 80;
      bottomBtn.disabled = top > max - 80;
    }
    window.addEventListener(
      'scroll',
      function () {
        if (!pending) {
          pending = true;
          window.requestAnimationFrame(update);
        }
      },
      { passive: true }
    );
    update();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
