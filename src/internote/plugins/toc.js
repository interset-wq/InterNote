(function () {
  'use strict';

  var HEADINGS = 'h1, h2, h3, h4, h5, h6';
  var ACTIVE_OFFSET = 130;

  function slugify(text, used) {
    var base = text
      .trim()
      .toLowerCase()
      .replace(/\s+/g, '-')
      .replace(/[^\p{L}\p{N}-]/gu, '');
    if (!base) {
      base = 'section';
    }
    var slug = base;
    var suffix = 2;
    while (used[slug]) {
      slug = base + '-' + suffix;
      suffix += 1;
    }
    used[slug] = true;
    return slug;
  }

  function collectHeadings(body) {
    var used = Object.create(null);
    var headings = Array.prototype.slice.call(body.querySelectorAll(HEADINGS));
    return headings
      .filter(function (heading) {
        if (heading.textContent.trim() === '') {
          return false;
        }
        // Posts that demo markdown headings (e.g. a syntax cheat sheet)
        // would otherwise inject one TOC entry per demo heading; such
        // demos are wrapped in <div class="in-toc-skip"> by the author.
        return !heading.closest('.in-toc-skip');
      })
      .map(function (heading) {
        if (!heading.id) {
          heading.id = slugify(heading.textContent, used);
        } else {
          used[heading.id] = true;
        }
        return {
          level: Number(heading.tagName.charAt(1)),
          id: heading.id,
          text: heading.textContent.trim(),
          el: heading
        };
      });
  }

  function toTree(items) {
    var root = { level: 0, children: [] };
    var stack = [root];
    items.forEach(function (item) {
      var node = { level: item.level, item: item, children: [] };
      while (stack.length > 1 && stack[stack.length - 1].level >= item.level) {
        stack.pop();
      }
      stack[stack.length - 1].children.push(node);
      stack.push(node);
    });
    return root.children;
  }

  function renderList(nodes, links) {
    var list = document.createElement('ul');
    list.className = 'in-toc-list';
    nodes.forEach(function (node) {
      var item = document.createElement('li');
      item.className = 'in-toc-item';

      var link = document.createElement('a');
      link.className = 'in-toc-link';
      link.href = '#' + node.item.id;
      link.textContent = node.item.text;
      link.addEventListener('click', function () {
        setActive(link);
      });
      links.push(link);
      item.appendChild(link);

      if (node.children.length) {
        item.appendChild(renderList(node.children, links));
      }
      list.appendChild(item);
    });
    return list;
  }

  function setActive(link) {
    var active = link.classList.contains('is-active');
    if (active) {
      return;
    }
    var siblings = link.closest('.in-toc').querySelectorAll('.in-toc-link.is-active');
    Array.prototype.forEach.call(siblings, function (node) {
      node.classList.remove('is-active');
    });
    link.classList.add('is-active');
  }

  function trackActive(headings, links) {
    var byId = Object.create(null);
    links.forEach(function (link) {
      byId[link.getAttribute('href').slice(1)] = link;
    });

    var pending = false;
    function update() {
      pending = false;
      var current = null;
      headings.forEach(function (heading) {
        if (heading.el.getBoundingClientRect().top - ACTIVE_OFFSET <= 0) {
          current = heading.id;
        }
      });
      if (!current) {
        return;
      }
      var link = byId[current];
      if (link) {
        setActive(link);
      }
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

  function padForLastHeading(headings) {
    var last = headings[headings.length - 1];
    if (!last) {
      return;
    }
    var docTop = last.el.getBoundingClientRect().top + window.scrollY;
    var needed = docTop - ACTIVE_OFFSET - (document.documentElement.scrollHeight - window.innerHeight);
    if (needed <= 0) {
      return;
    }
    var spacer = document.createElement('div');
    spacer.style.height = needed + 'px';
    document.body.appendChild(spacer);
  }

  function init() {
    var root = document.getElementById('in-toc');
    if (!root) {
      return;
    }
    var body = document.querySelector('.in-post-body');
    if (!body) {
      return;
    }

    var headings = collectHeadings(body);
    if (!headings.length) {
      root.parentNode.removeChild(root);
      return;
    }

    var title = document.createElement('div');
    title.className = 'in-toc-title';
    title.textContent = root.dataset.tocTitle || 'Contents';
    root.appendChild(title);

    var links = [];
    root.appendChild(renderList(toTree(headings), links));

    var top = document.createElement('button');
    top.type = 'button';
    top.className = 'in-toc-top';
    top.textContent = root.dataset.tocTop || 'Top';
    top.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
    root.appendChild(top);

    root.classList.add('is-ready');
    padForLastHeading(headings);
    trackActive(headings, links);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();