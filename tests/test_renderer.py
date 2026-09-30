# -*- coding: utf-8 -*-
from pathlib import Path

from internote.config import load_config
from internote.constants import ICONS, get_i18n
from internote.renderer import Renderer

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = REPO_ROOT / "src" / "internote" / "templates"
HOME = "https://interset-wq.github.io/InterNote"

COUNTER_SCRIPTS = {
    "vercount": f"{HOME}/plugins/vercount.js",
    "busuanzi": f"{HOME}/plugins/busuanzi.js",
}


def base_context(**overrides):
    cfg = load_config(REPO_ROOT / "config.sample.toml")
    blog = cfg.context()
    blog.update(
        {
            "home_url": HOME,
            "blog_repo_url": "https://github.com/x/y",
            "prev_url": "disabled",
            "next_url": "disabled",
            "post_title": "Hello World",
            "post_url": "post/1.html",
            "description": "First post",
            "post_body": "<p>hi</p>",
            "comment_num": 0,
            "post_source_url": "https://github.com/x/y/issues/1",
            "highlight": 0,
            "style": "",
            "script": "",
            "head": "",
            "top": 0,
            "created_date": "2026-01-01",
            "date_label_color": "#d4a72c",
            "updated_date": "",
            "labels": ["daily"],
        }
    )
    post_list = overrides.pop("post_list", {})
    blog.update(overrides.pop("page", {}))
    blog.update(overrides)
    return {
        "blogBase": blog,
        "post_list": post_list,
        "i18n": get_i18n(blog["language"]),
        "IconList": ICONS,
    }


def render(name: str, ctx: dict) -> str:
    return Renderer(TEMPLATES).render(name, ctx)


def test_renders_j2_templates():
    html = render("post", base_context())
    assert "<!DOCTYPE html>" in html
    assert "Hello World" in html


def test_post_uses_giscus_not_utterances():
    ctx = base_context(
        giscus_repo="interset-wq/InterNote",
        giscus_repo_id="R_abc",
        giscus_category="General",
        giscus_category_id="DIC_xyz",
    )
    html = render("post", ctx)

    assert "https://giscus.app/client.js" in html
    assert 'data-repo="interset-wq/InterNote"' in html
    assert 'data-repo-id="R_abc"' in html
    assert 'data-category="General"' in html
    assert 'data-category-id="DIC_xyz"' in html
    assert 'data-mapping="pathname"' in html
    assert "utteranc.es" not in html


def test_post_giscus_lang_matches_site_language():
    giscus = dict(
        giscus_repo="interset-wq/InterNote",
        giscus_repo_id="R_abc",
        giscus_category="General",
        giscus_category_id="DIC_xyz",
    )

    html_cn = render("post", base_context(language="CN", **giscus))
    assert 'data-lang="zh-CN"' in html_cn

    html_en = render("post", base_context(language="EN", **giscus))
    assert 'data-lang="en"' in html_en


def _header(html: str) -> str:
    return html.split('id="header"')[1].split('id="content"')[0]


def _footer(html: str) -> str:
    return html.split('id="content"')[1]


def test_plist_moves_rss_and_github_to_footer():
    html = render("plist", base_context(post_source_url=""))

    footer = _footer(html)
    assert 'id="buttonRSS"' in footer
    assert f'href="{HOME}/rss.xml"' in footer
    assert 'id="buttonGH"' in footer
    assert 'href="https://github.com/x/y"' in footer

    header = _header(html)
    assert "buttonRSS" not in header
    assert "pathRSS" not in header


def test_post_moves_issue_link_to_footer():
    html = render("post", base_context())

    footer = _footer(html)
    assert 'id="buttonRSS"' in footer
    assert 'id="buttonGH"' in footer
    assert 'href="https://github.com/x/y/issues/1"' in footer

    assert "pathIssue" not in html
    assert 'id="buttonRSS"' not in _header(html)


def test_post_github_falls_back_to_repo_when_source_hidden():
    html = render("post", base_context(show_post_source=False))

    footer = _footer(html)
    assert 'href="https://github.com/x/y/issues/1"' not in footer
    assert 'href="https://github.com/x/y"' in footer


def test_post_without_comments_hides_giscus():
    ctx = base_context(need_comment=False)
    html = render("post", ctx)
    assert "giscus.app" not in html
    assert 'id="cmButton"' not in html


def test_post_toc_plugin_injected_when_enabled():
    html = render("post", base_context(toc=True))
    assert f"{HOME}/plugins/tocbot.js" in html


def test_post_toc_plugin_absent_when_disabled():
    html = render("post", base_context(toc=False))
    assert "tocbot.js" not in html


def test_post_meta_row():
    html = render(
        "post",
        base_context(
            created_date="2026-01-01",
            date_label_color="#d4a72c",
            updated_date="2026-03-15",
            labels=["daily"],
            label_color_dict={"daily": "#0969da"},
        ),
    )
    assert 'class="postMeta"' in html
    assert "LabelTime" in html
    assert "2026-01-01" in html
    assert "LabelUpdated" in html
    assert "2026-03-15" in html
    assert f'{HOME}/tag.html#daily' in html
    assert "#0969da" in html


def test_post_meta_hides_update_when_same_date():
    html = render(
        "post",
        base_context(
            created_date="2026-01-01",
            date_label_color="#d4a72c",
            updated_date="2026-01-01",
            labels=["daily"],
        ),
    )
    assert 'class="postMeta"' in html
    assert "LabelUpdated" not in html


def test_visit_counter_vercount():
    html = render("post", base_context(visit_counter="vercount"))
    assert COUNTER_SCRIPTS["vercount"] in html
    assert COUNTER_SCRIPTS["busuanzi"] not in html


def test_visit_counter_busuanzi():
    html = render("post", base_context(visit_counter="busuanzi"))
    assert COUNTER_SCRIPTS["busuanzi"] in html
    assert COUNTER_SCRIPTS["vercount"] not in html


def test_visit_counter_off():
    html = render("post", base_context(visit_counter="off"))
    assert "vercount.js" not in html
    assert "busuanzi.js" not in html


def test_footer_attribution():
    html = render("post", base_context())
    assert "Powered by" in html
    assert "Internote" in html
    assert "Based on" in html
    assert "Gmeek" in html
    assert "meekdai.com/Gmeek.html" not in html


def test_console_branding():
    html = render("post", base_context())
    assert "Internote last" in html  # config site.version = "last"
    assert "Based on Gmeek" in html


def test_plist_renders_posts():
    ctx = base_context(
        page={},
        post_list={
            "P1": {
                "post_title": "First",
                "post_url": "post/1.html",
                "labels": ["daily"],
                "comment_num": 2,
                "top": 1,
                "created_date": "2026-01-01",
                "date_label_color": "#0969da",
            }
        },
    )
    html = render("plist", ctx)
    assert "First" in html
    assert "post/1.html" in html
    assert "2026-01-01" in html


def test_theme_switch_syncs_giscus():
    ctx = base_context(
        giscus_repo="interset-wq/InterNote",
        giscus_repo_id="R_abc",
        giscus_category="General",
        giscus_category_id="DIC_xyz",
    )
    html = render("post", ctx)
    assert "giscus" in html
    assert "setConfig" in html
    assert "https://giscus.app" in html


def test_footer_icons_row_separate_from_poweredby_row():
    html = render("post", base_context())

    footer = _footer(html)
    icons_row = footer.split('id="footer2"')[1].split('id="footer3"')[0]
    powered_row = footer.split('id="footer3"')[1]

    assert 'id="buttonRSS"' in icons_row
    assert 'id="buttonGH"' in icons_row
    assert "Powered by" not in icons_row
    assert "Powered by" in powered_row
    assert "2026" not in powered_row


def test_theme_switch_button_uniform_across_pages():
    for name in ("plist", "post", "tag"):
        header = _header(render(name, base_context()))
        assert 'onclick="modeSwitch()"' in header, name
        assert header.count('id="themeSwitch"') == 1, name


def test_giscus_theme_function_defined_once_in_base():
    src = (
        REPO_ROOT / "src" / "internote" / "templates" / "base.j2.html"
    ).read_text(encoding="utf-8")
    assert src.count("function giscusTheme") == 1
