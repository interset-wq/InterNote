/**
 * giscus
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

  function init() {
    // Comments render immediately now; the script tag lives in the markup.
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

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.giscusTheme = setTheme;
})();
