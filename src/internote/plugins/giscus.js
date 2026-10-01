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

  function loadGiscus() {
    var container = document.getElementById('comments');
    var template = document.getElementById('giscusTemplate');
    if (!container || !template) return;

    var script = template.content.firstElementChild.cloneNode(true);
    script.setAttribute('data-theme', resolveTheme(currentMode()));
    container.appendChild(script);

    var timer = setInterval(function () {
      var frames = document.getElementsByClassName('giscus-frame');
      if (frames.length !== 1 || frames[0].style.height === '') return;
      clearInterval(timer);
      var button = document.getElementById('cmButton');
      if (button) button.hidden = true;
      setTheme(resolveTheme(currentMode()));
    }, 200);
  }

  function openComments() {
    var button = document.getElementById('cmButton');
    if (!button) return;
    button.disabled = true;
    button.innerHTML = 'loading<span class="in-animated-ellipsis"></span>';
    loadGiscus();
  }

  function init() {
    var button = document.getElementById('cmButton');
    if (button) button.addEventListener('click', openComments);

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
