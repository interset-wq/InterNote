/**
 * giscus comments, lazy-loaded.
 *
 * The giscus script ships inside an inert <template> in
 * components/comments.j2.html and is materialised only when the reader
 * approaches the section (IntersectionObserver, 300px margin; immediate
 * load when IntersectionObserver is unavailable). giscus.app is slow on
 * high-latency networks - loading it up front competed with the page's
 * own resources for no reason.
 */

(function () {
  'use strict';

  function currentMode() {
    return localStorage.getItem('internote_theme') || 'light';
  }

  function resolveTheme(mode) {
    if (mode === 'dark') return 'dark';
    if (mode === 'auto') return 'preferred_color_scheme';
    return 'light';
  }

  function setTheme(theme) {
    var frame = document.querySelector('.giscus-frame');
    if (!frame) return;
    frame.contentWindow.postMessage({ giscus: { setConfig: { theme: theme } } }, 'https://giscus.app');
  }

  function watchFrameTheme() {
    // Once the frame exists, sync it with the current theme.
    var timer = setInterval(function () {
      var frames = document.getElementsByClassName('giscus-frame');
      if (frames.length !== 1 || frames[0].style.height === '') return;
      clearInterval(timer);
      setTheme(resolveTheme(currentMode()));
    }, 200);

    new MutationObserver(function () {
      setTheme(resolveTheme(currentMode()));
    }).observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-color-mode']
    });
  }

  function materialise() {
    var holder = document.getElementById('comments');
    var tpl = document.getElementById('in-giscus-template');
    if (!holder || !tpl) return;
    var script = tpl.content.querySelector('script');
    if (!script) return;
    // load the frame directly in the visitor's theme - no light flash
    script.setAttribute('data-theme', resolveTheme(currentMode()));
    holder.appendChild(document.importNode(script, true));
    watchFrameTheme();
  }

  function init() {
    var holder = document.getElementById('comments');
    if (!holder) return;

    if (!('IntersectionObserver' in window)) {
      materialise();
      return;
    }
    var observer = new IntersectionObserver(function (entries) {
      if (!entries.some(function (e) { return e.isIntersecting; })) return;
      observer.disconnect();
      materialise();
    }, { rootMargin: '300px' });
    observer.observe(holder);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.giscusTheme = setTheme;
})();
