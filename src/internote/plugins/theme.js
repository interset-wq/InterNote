/**
 * Light / dark / auto theme switching.
 *
 * The mode lives in localStorage under internote_theme. The resolved
 * colour mode is mirrored onto <html data-color-mode>, which Primer keys
 * its dark palette off. giscus.js watches the same attribute.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'internote_theme';

  var MODES = {
    dark: { colorMode: 'dark', icon: 'moon', accent: '#00f0ff', giscus: 'dark' },
    light: { colorMode: 'light', icon: 'sun', accent: '#ff5000', giscus: 'light' },
    auto: { colorMode: null, icon: 'sync', accent: '', giscus: 'preferred_color_scheme' }
  };

  function stored() {
    return localStorage.getItem(STORAGE_KEY) || 'light';
  }

  function prefersDark() {
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  }

  function resolve(mode) {
    return mode === 'auto' ? (prefersDark() ? 'dark' : 'light') : mode;
  }

  function apply(mode) {
    var conf = MODES[mode];
    document.documentElement.setAttribute('data-color-mode', resolve(mode));

    var button = document.getElementById('themeSwitch');
    if (button) {
      button.setAttribute('d', window.icons[conf.icon]);
      if (button.parentNode) {
        button.parentNode.style.color = conf.accent;
      }
    }
    if (window.giscusTheme) {
      window.giscusTheme(conf.giscus);
    }
  }

  // exposed for the inline onclick="InternoteTheme.cycle()" handler
  function cycle() {
    var current = stored();
    var next = current === 'light' ? 'dark' : current === 'dark' ? 'auto' : 'light';
    localStorage.setItem(STORAGE_KEY, next);
    apply(next);
  }

  window.InternoteTheme = { apply: apply, cycle: cycle };

  function init() {
    if (document.getElementById('themeSwitch')) {
      apply(stored());
    }
    if (window.matchMedia) {
      var media = window.matchMedia('(prefers-color-scheme: dark)');
      var onChange = function () {
        if (stored() === 'auto') {
          apply('auto');
        }
      };
      if (media.addEventListener) {
        media.addEventListener('change', onChange);
      } else if (media.addListener) {
        media.addListener(onChange);
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();