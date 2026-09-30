function loadResource(type, attributes, callback) {
    var element;
    if (type === 'script') {
        element = document.createElement('script');
        element.src = attributes.src;
        element.onload = callback;
    } else if (type === 'link') {
        element = document.createElement('link');
        element.rel = attributes.rel;
        element.href = attributes.href;
    } else if (type === 'style') {
        element = document.createElement('style');
        element.rel = 'stylesheet';
        element.appendChild(document.createTextNode(attributes.css));
    }
    document.head.appendChild(element);
}

function createTOC() {
    var tocElement = document.createElement('div');
    tocElement.className = 'toc';
    var contentContainer = document.getElementById('content');
    if (contentContainer.firstChild) {
        contentContainer.insertBefore(tocElement, contentContainer.firstChild);
    } else {
        contentContainer.appendChild(tocElement);
    }
}

document.addEventListener("DOMContentLoaded", function() {
    const headings = document.querySelectorAll('.markdown-body h1, .markdown-body h2, .markdown-body h3, .markdown-body h4, .markdown-body h5, .markdown-body h6');
    if (headings.length > 0) {
        createTOC();
        var css = '.toc {position:fixed;top:130px;left:50%;transform: translateX(50%) translateX(300px);width:200px;padding-left:30px;}@media (max-width: 1249px) {.toc{position:static;top:auto;left:auto;transform:none;padding:10px;margin-bottom:20px;background-color:var(--color-open-muted);}}';
        loadResource('style', {css: css});

        loadResource('script', { src: 'https://cdnjs.cloudflare.com/ajax/libs/tocbot/4.27.4/tocbot.min.js' }, function() {
            tocbot.init({
                tocSelector: '.toc',
                contentSelector: '.markdown-body',
                headingSelector: 'h1, h2, h3, h4, h5, h6',
                scrollSmooth: true,
                scrollSmoothOffset: -10,
                headingsOffset: 10,
            });
        });

        loadResource('link', { rel: 'stylesheet', href: 'https://cdnjs.cloudflare.com/ajax/libs/tocbot/4.27.4/tocbot.css' });
    }
    headings.forEach((heading) => {
        if (!heading.id) {
            heading.id = heading.textContent.trim().replace(/\s+/g, '-');
        }
    });

    var lastHeading = headings[headings.length - 1];
    if (lastHeading) {
        var maxScroll = document.documentElement.scrollHeight - document.documentElement.clientHeight;
        var target = lastHeading.getBoundingClientRect().top + window.scrollY - 20;
        var need = target - maxScroll;
        if (maxScroll > 0 && need > 0) {
            var footerPlaceholder = document.createElement('div');
            footerPlaceholder.style.height = need + 'px';
            document.body.appendChild(footerPlaceholder);
        }
    }
    console.log("\n %c Internote tocbot plugin • Based on Gmeek https://github.com/Meekdai/Gmeek \n","padding:5px 0;background:#C333D0;color:#fff");
});
