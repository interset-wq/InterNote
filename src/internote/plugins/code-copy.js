/**
 * Copy buttons on code blocks.
 *
 * Rewrites each <pre><code> into a positioned wrapper carrying a
 * <clipboard-copy> element (a Primer web component). The copy/check
 * glyphs are swapped on click, which is why these two icons have to be
 * available at runtime rather than rendered by the template.
 */
(function () {
  'use strict';

  var SELECTORS = ['pre.notranslate > code.notranslate', 'div.highlight > pre.notranslate'];

  function wrapCode(html) {
    return (
      '<pre class="notranslate"><code class="notranslate">' + html + '</code></pre>' +
      '<div class="clipboard-container position-absolute right-0 top-0">' +
      '<clipboard-copy class="ClipboardButton btn m-2 p-0" role="button" style="display: inherit;">' +
      '<svg height="16" width="16" class="octicon octicon-copy m-2"><path d="' + window.icons.copy + '"></path></svg>' +
      '<svg height="16" width="16" class="octicon octicon-check m-2 d-none"><path d="' + window.icons.check + '"></path></svg>' +
      '</clipboard-copy>' +
      '<div class="in-copy-feedback">Copied!</div>' +
      '</div>'
    );
  }

  function rewrite(selector) {
    var isHighlight = selector.indexOf('highlight') !== -1;
    document.querySelectorAll(selector).forEach(function (codeElement) {
      var wrapper = document.createElement('div');
      wrapper.className = 'in-code-block';
      wrapper.innerHTML = wrapCode(codeElement.innerHTML);

      var pre = codeElement.parentElement;
      if (isHighlight) {
        pre.parentElement.insertBefore(wrapper, pre.nextSibling);
        pre.parentElement.removeChild(pre);
      } else {
        pre.parentElement.replaceChild(wrapper, pre);
      }
    });
  }

  function copyText(text) {
    var area = document.createElement('textarea');
    area.value = text;
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    document.body.removeChild(area);
  }

  function bind() {
    var visible = null;

    document.querySelectorAll('clipboard-copy').forEach(function (button) {
      button.addEventListener('click', function () {
        copyText(button.closest('.in-code-block').innerText);

        var copyIcon = button.querySelector('.octicon-copy');
        var checkIcon = button.querySelector('.octicon-check');
        var feedback = button.nextElementSibling;

        if (visible && visible !== feedback) {
          visible.style.display = 'none';
        }
        visible = feedback;

        copyIcon.classList.add('d-none');
        checkIcon.classList.remove('d-none');
        feedback.style.display = 'block';
        button.style.borderColor = 'var(--color-success-fg)';

        setTimeout(function () {
          copyIcon.classList.remove('d-none');
          checkIcon.classList.add('d-none');
          feedback.style.display = 'none';
          button.style.borderColor = '';
        }, 2000);
      });
    });
  }

  function init() {
    SELECTORS.forEach(rewrite);
    bind();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();