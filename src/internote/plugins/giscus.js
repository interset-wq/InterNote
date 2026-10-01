/**
 * giscus
 */

(function () {
  'use strict';

  var config = {
    repo: '{{ site.giscus_repo }}',
    repoId: '{{ site.giscus_repo_id }}',
    category: '{{ site.giscus_category }}',
    categoryId: '{{ site.giscus_category_id }}',
    mapping: 'pathname',
    strict: '0',
    reactionsEnabled: '1',
    emitMetadata: '0',
    inputPosition: 'bottom',
    theme: 'light',
    lang: '{{ site.language | lower | replace("cn", "zh-CN") | replace("en", "en") }}',
  };

  function getTheme() {
    var t = localStorage.getItem('internote_theme') || 'light';
    if (t === 'dark') return 'dark';
    if (t === 'auto') return 'preferred_color_scheme';
    return 'light';
  }

  function setTheme(theme) {
    var iframe = document.getElementsByClassName('giscus-frame')[0];
    if (iframe) {
      iframe.contentWindow.postMessage(
        { giscus: { setConfig: { theme: theme } } },
        'https://giscus.app'
      );
    }
  }

  function loadGiscus() {
    var cm = document.getElementById('comments');
    if (!cm) return;

    var tpl = document.getElementById('giscusTemplate');
    if (!tpl) return;

    var script = tpl.content.firstElementChild.cloneNode(true);
    script.setAttribute('data-theme', getTheme());
    cm.appendChild(script);

    var timer = setInterval(function () {
      var frame = document.getElementsByClassName('giscus-frame');
      if (frame.length === 1 && frame[0].style.height !== '') {
        clearInterval(timer);
        var btn = document.getElementById('cmButton');
        if (btn) btn.style.display = 'none';
        setTheme(getTheme());
        console.log('giscus Load OK');
      }
    }, 200);
  }

  function openComments() {
    var btn = document.getElementById('cmButton');
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML = 'loading<span class="animated-ellipsis"></span>';
    loadGiscus();
  }

  function init() {
    var btn = document.getElementById('cmButton');
    if (btn) {
      btn.addEventListener('click', openComments);
    }

    var themeSwitch = document.getElementById('themeSwitch');
    if (themeSwitch) {
      var observer = new MutationObserver(function () {
        setTheme(getTheme());
      });
      observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['data-color-mode'],
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.giscusTheme = setTheme;
  window.openComments = openComments;
})();
