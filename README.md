# InterNote

一个超轻量级的个人博客生成器，完全基于 `GitHub Pages`、`GitHub Issues` 和 `GitHub Actions`：
写作流程就是提 Issue，写完自动构建、自动发布，无需本地部署。

- 文章外观与 GitHub Issues 一致：内置 [Primer CSS](https://primer.style/css)（随包分发，无外部 CDN）
- 使用 `jinja2` 渲染 HTML，模板可自定义主题；明暗主题三态切换（亮 / 暗 / 跟随系统）
- 评论系统：[giscus](https://giscus.app)（基于 GitHub Discussions）

## 特性

- 文章 URL 使用 Issue 编号：`post/42.html`；单页 Label（如 `about`）生成 `about.html`
- 评论：[giscus](https://giscus.app)（按 pathname 映射，`<template>` 懒加载，未配置时不渲染）
- 文章目录（tocbot）默认开启；可选访问计数（`vercount` / `busuanzi`）、RSS 订阅（`rss.xml`）
- 站内搜索（按标题过滤 `post-list.json`）
- TOML 配置，pydantic 严格校验（未知键报错），`config.sample.toml` 为完整示例
- 每次构建更新仓库 `README.md` 的文章数 / 评论数 / 字数 / 时间统计（定时任务除外）

## 快速开始（博客仓库）

博客与生成器分两处存放：本仓库是生成器，博客仓库存放 Issue、配置和 workflow。

1. 【创建仓库】新建一个博客仓库（建议 `XXX.github.io`，`XXX` 为你的 GitHub 用户名）
2. 【添加配置】复制本仓库的 `config.sample.toml` 为博客仓库根目录的 `config.toml` 并修改
3. 【添加 workflow】复制本仓库的 `examples/blog-workflow.yml` 到博客仓库的 `.github/workflows/internote.yml`
4. 【启用 Pages】博客仓库 `Settings -> Pages -> Build and deployment -> Source` 选择 `GitHub Actions`
5. 【首次全局生成】Actions 页面手动运行 `build Internote -> Run workflow`
6. 【开始写作】新建 Issue，**必须**添加至少一个 Label，保存后自动构建，片刻后通过 Pages 地址访问

> 博客仓库会提交生成产物：`dist/`（站点）、`sources/`（Issue 源码备份）、
> `internote.json`（构建状态）、`README.md`（统计）。
> `.gitignore` 不要忽略这些路径。

### 构建触发

| 触发 | 行为 |
| --- | --- |
| Issue `opened` / `edited` | 增量重建该篇文章及列表页 |
| `schedule`（每天 0 16:00 UTC） | 全局重建 |
| `workflow_dispatch` | 手动全局重建（修改 `config.toml` 后执行一次） |

> blog workflow 总是检出 InterNote `main` 分支最新提交，本仓库的推送会影响线上博客的下一次构建。

## 本地开发

```bash
uv sync                                         # 安装依赖（Python 版本见 .python-version）
uv run internote <token> <owner/repo>           # 全局生成
uv run internote <token> <owner/repo> --issue-number 42   # 单篇重建
```

### 离线本地构建（fixture）

抓取一次线上数据（通过已登录的 `gh` CLI，同时预渲染 markdown），之后本地构建/单测零网络：

```bash
uv run python scripts/fetch_fixtures.py <owner/repo> -o tests/fixtures/<owner>__<name>.json
uv run internote - <owner/repo> --fixtures tests/fixtures/<owner>__<name>.json   # 无需 token
```

输出：`dist/`（静态站点）、`sources/*.md`（源码备份）、`internote.json`（状态）、
`post-list.json`（搜索/列表数据，位于 `dist/` 内）。

## 配置说明

完整示例与逐键注释见 [`config.sample.toml`](config.sample.toml)，分组如下：

| 分组 | 说明 |
| --- | --- |
| `[site]` | 标题、副标题、头像、语言（`CN` / `EN`）、时区 `utc`；`home_url` 留空自动推导 GitHub Pages 地址 |
| `[layout]` | 每页文章数 `posts_per_page`、单页标签 `single_labels`、建站日期 `start_date`、备案号 `icp`、底部文字 `footer_text`、源码链接 `show_source`、注入的 `head/style/script/index_script/index_style/all_head` |
| `[comments]` | 评论开关 `enabled`（还需配置 giscus 才会渲染评论区） |
| `[giscus]` | giscus 四项参数（在 [giscus.app](https://giscus.app) 生成；留空则不渲染评论区） |
| `[features]` | `visit_counter` 访问计数（`off` / `vercount` / `busuanzi`） |

主题无需配置：明暗切换内置（亮 / 暗 / 跟随系统三态循环），Primer CSS 与站点样式随包内置并复制到 `dist/assets/`。

### 文章 front matter（可选）

正文开头可用 `+++` 包裹一段 TOML，覆盖该文章的元信息：

````text
+++
title = "自定义标题"
description = "自定义摘要，用于 <meta description> 与分享卡片"
date = 2026-01-01T10:00:00+08:00
head = '<meta name="x" content="y">'
style = ".my-post { color: red; }"
script = "console.log('hi');"
draft = false
+++
正文从这里开始
````

| 字段 | 说明 |
| --- | --- |
| `title` | 覆盖 Issue 标题（列表页、文章页 `<title>`、RSS 均生效） |
| `description` | 覆盖自动摘要；缺省时取正文首个句号前的内容 |
| `date` | 覆盖文章时间；支持 TOML 日期时间、Unix 秒、ISO 8601 字符串 |
| `head` / `style` / `script` | 单篇注入的 HTML 片段，追加在 `[layout]` 同名配置之后。`style` 会被自动包进 `<style>`，`head` 与 `script` 需自行带标签 |
| `draft` | `true` 则该文章完全不发布：不生成页面，不进列表、标签页与 RSS |

说明：

- 用 `+++` 而非 `---`，因为 `---` 同时是 Markdown 水平线，放在正文开头会产生歧义；正文中间的 `---` 不受影响。
- **不支持 `labels`**：标签始终以 GitHub Issue 标签为准，搜索页、标签颜色与单页路由都依赖它。
- 字段拼错或 TOML 语法错误会**直接让构建失败**并报出 Issue 编号，不会静默忽略。
- `head` / `style` / `script` 会原样注入页面，仅在完全信任 Issue 作者时使用。
