(function () {
  'use strict';

  function build() {
    var overlay = document.createElement('div');
    overlay.className = 'in-lightbox';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');

    var image = document.createElement('img');
    image.className = 'in-lightbox-image';
    image.alt = '';

    var previous = document.createElement('button');
    previous.type = 'button';
    previous.className = 'in-lightbox-nav in-lightbox-prev';
    previous.innerHTML = '&#10094;';

    var next = document.createElement('button');
    next.type = 'button';
    next.className = 'in-lightbox-nav in-lightbox-next';
    next.innerHTML = '&#10095;';

    var close = document.createElement('button');
    close.type = 'button';
    close.className = 'in-lightbox-close';
    close.innerHTML = '&times;';

    overlay.appendChild(image);
    overlay.appendChild(previous);
    overlay.appendChild(next);
    overlay.appendChild(close);
    document.body.appendChild(overlay);

    return { overlay: overlay, image: image, previous: previous, next: next, close: close };
  }

  function init() {
    var body = document.querySelector('.in-post-body');
    if (!body) {
      return;
    }
    var images = Array.prototype.slice.call(body.querySelectorAll('img'));
    if (images.length < 2) {
      return;
    }

    var ui = build();
    var index = 0;
    var opened = false;

    function show(next) {
      index = next;
      var source = images[index];
      ui.image.src = source.currentSrc || source.src;
      ui.image.alt = source.alt || '';
      ui.previous.hidden = index === 0;
      ui.next.hidden = index === images.length - 1;
    }

    function open(start) {
      opened = true;
      show(start);
      ui.overlay.classList.add('is-open');
      document.body.style.overflow = 'hidden';
      ui.close.focus();
    }

    function close() {
      opened = false;
      ui.overlay.classList.remove('is-open');
      document.body.style.overflow = '';
      ui.image.removeAttribute('src');
    }

    body.addEventListener('click', function (event) {
      var target = event.target;
      if (target.tagName !== 'IMG') {
        return;
      }
      event.preventDefault();
      open(images.indexOf(target));
    });

    ui.close.addEventListener('click', close);
    ui.overlay.addEventListener('click', function (event) {
      if (event.target === ui.overlay) {
        close();
      }
    });
    ui.previous.addEventListener('click', function () {
      show(index - 1);
    });
    ui.next.addEventListener('click', function () {
      show(index + 1);
    });

    document.addEventListener('keydown', function (event) {
      if (!opened) {
        return;
      }
      if (event.key === 'Escape') {
        close();
      } else if (event.key === 'ArrowLeft' && index > 0) {
        show(index - 1);
      } else if (event.key === 'ArrowRight' && index < images.length - 1) {
        show(index + 1);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();