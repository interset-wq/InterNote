/* Client-side mermaid rendering, on demand.
 *
 * The GitHub /markdown API only syntax-highlights ```mermaid fences
 * (div.highlight-source-mermaid > pre.notranslate); it never returns
 * SVG. When such a block is present, this plugin pulls mermaid.js from
 * the CDN once and turns each block's code text into an inline diagram.
 * Pages without mermaid blocks never download the library.
 *
 * Zero-dependency IIFE like every other plugin here; the library itself
 * is the one sanctioned CDN exception (user decision).
 */
(function () {
  'use strict';

  var MERMAID_CDN =
    'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
  var blocks = Array.prototype.slice.call(
    document.querySelectorAll('.highlight-source-mermaid pre.notranslate')
  );
  if (!blocks.length) {
    return;
  }

  var themeButton = document.getElementById('in-theme-toggle');
  // mermaid's own themes; 'dark' follows the site's dark mode, 'neutral'
  // reads closest to GitHub's light rendering.
  function currentTheme() {
    return document.documentElement.getAttribute('data-color-mode') === 'dark'
      ? 'dark'
      : 'neutral';
  }

  function wrap(block, svg) {
    var box = document.createElement('div');
    box.className = 'in-mermaid';
    box.innerHTML = svg;
    block.replaceWith(box);
  }

  function fail(block) {
    // Leave the source visible: the highlighted code block is the
    // graceful fallback, just add a hint.
    block.closest('.highlight').classList.add('in-mermaid-failed');
  }

  function renderAll(mermaid) {
    blocks.forEach(function (block) {
      var source = block.textContent;
      try {
        mermaid.render('in-mermaid-' + (block._id || Math.random().toString(36).slice(2)),
          source).then(function (result) {
            wrap(block, result.svg);
          }).catch(function () { fail(block); });
      } catch (err) {
        fail(block);
      }
    });
  }

  function loadLibrary(then) {
    // dynamic import of the ESM build; cached after the first call
    import(MERMAID_CDN).then(function (mod) {
      var mermaid = mod.default;
      mermaid.initialize({
        startOnLoad: false,
        theme: currentTheme(),
        // page fonts instead of mermaid defaults
        fontFamily: 'inherit',
        securityLevel: 'strict',
      });
      then(mermaid);
    }).catch(function () {
      blocks.forEach(fail);
    });
  }

  // Re-render on theme switch: drop the rendered diagrams and rebuild
  // from the kept sources.
  var sources = blocks.map(function (block) { return block.textContent; });
  document.addEventListener('click', function (event) {
    if (themeButton && event.target.closest && event.target.closest('#in-theme-toggle')) {
      var boxes = document.querySelectorAll('.in-mermaid');
      if (!boxes.length) return;
      // simplest correct path: reload sources by re-fetching the module
      // is unnecessary - re-render from cached sources
      import(MERMAID_CDN).then(function (mod) {
        mod.default.initialize({ startOnLoad: false, theme: currentTheme(), fontFamily: 'inherit', securityLevel: 'strict' });
        boxes.forEach(function (box, i) {
          var holder = document.createElement('pre');
          holder.className = 'notranslate';
          holder.textContent = sources[i];
          mod.default.render('in-mermaid-re-' + i, sources[i]).then(function (result) {
            box.innerHTML = result.svg;
          });
        });
      });
    }
  });

  loadLibrary(renderAll);
})();
