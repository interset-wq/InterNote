(function () {
  'use strict';

  var SOURCES = {
    busuanzi: 'https://busuanzi.ibruce.info/busuanzi/2.3/busuanzi.pure.mini.js',
    vercount: 'https://vercount.one/js'
  };

  function insert(target, markup, position) {
    if (!target) {
      return null;
    }
    var holder = document.createElement('div');
    holder.innerHTML = markup;
    var node = holder.firstElementChild;
    if (position === 'afterend') {
      target.insertAdjacentElement('afterend', node);
    } else {
      target.appendChild(node);
    }
    return node;
  }

  function init() {
    var script = document.getElementById('visit-counter');
    if (!script) {
      return;
    }
    var source = SOURCES[script.dataset.counter];
    if (!source) {
      return;
    }

    var pageLabel = script.dataset.pageLabel || 'Page views';
    var siteLabel = script.dataset.siteLabel || 'Site views';

    insert(
      document.querySelector('.in-post-body'),
      '<span class="in-counter" id="busuanzi_container_page_pv" hidden>' +
        pageLabel +
        ' <span id="busuanzi_value_page_pv"></span></span>',
      'afterend'
    );

    insert(
      document.getElementById('run-days'),
      '<span class="in-counter" id="busuanzi_container_site_pv" hidden>' +
        siteLabel +
        ' <span id="busuanzi_value_site_pv"></span></span>',
      'afterend'
    );

    var remote = document.createElement('script');
    remote.src = source;
    remote.async = true;
    document.head.appendChild(remote);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();