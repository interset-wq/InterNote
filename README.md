# InterNote

一个超轻量级的个人博客生成器，完全基于 `GitHub Pages`、`GitHub Issues` 和 `GitHub Actions`。
由 [Gmeek](https://github.com/Meekdai/Gmeek) 重构而来：写作流程不变（Issue 即文章），
工具链升级为 Python 3.14 + uv + pydantic + typer，评论系统迁移至 [giscus](https://giscus.app)。

- 不需要本地部署：写完 Issue，自动构建，自动发布
- UI 与 GitHub 同源，只引入 GitHub 原生 CSS：[primer.style](https://primer.style/css)
- 使用 `jinja2` 渲染 HTML，模板可自定义主题

## 特性

- 文章 URL 使用 Issue 编号：`post/42.html`；单页 Label（如 `about`）生成 `about.html`
- 评论：[giscus](https://giscus.app)（按 pathname 映射，`<template>` 懒加载，未配置时不渲染）
- 可选功能：文章目录（tocbot）、访问计数（vercount / busuanzi）、RSS 订阅（`rss.xml`）
- 站内搜索（按标题过滤 `post-list.json`）
- TOML 配置，pydantic 严格校验，`config.sample.toml` 为完整示例
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

## 本地开发

```bash
uv sync                                       # 安装依赖（Python 版本见 .python-version）
uv run internote <token> <owner/repo>          # 全局生成
uv run internote <token> <owner/repo> --issue-number 42   # 单篇重建
uv run pytest -q                               # 运行测试
```

输出：`dist/`（静态站点）、`sources/*.md`（源码备份）、`internote.json`（状态）、
`post-list.json`（搜索/列表数据，位于 `dist/` 内）。

## 配置说明

完整示例与逐键注释见 [`config.sample.toml`](config.sample.toml)，分组如下：

| 分组 | 说明 |
| --- | --- |
| `[site]` | 标题、头像、语言（CN/EN）、时区 `utc`、`version`（博客 workflow 检出的 InterNote 版本，`last` 为最新 tag） |
| `[theme]` | 明暗模式（`manual` 支持切换 / `fix` 固定）、年份标签配色、primer.css 地址 |
| `[layout]` | 分页数量、单页 Label、建站日期、备案号、底部文字、注入的 `head/style/script` 等 |
| `[nav]` | 附加导航图标（`exlink`）与自定义 SVG path（`icon_list`） |
| `[comments]` | 评论开关与评论数徽章颜色 |
| `[giscus]` | giscus 四项参数（在 [giscus.app](https://giscus.app) 生成；留空则不渲染评论区） |
| `[features]` | `toc` 文章目录、`visit_counter` 访问计数（`off` / `vercount` / `busuanzi`） |
| `[feed]` | RSS 摘要切分方式（`sentence` 或自定义字符） |

### 文章内配置（Issue 正文最后一行）

```text
## {"timestamp": 1700000000, "ogImage": "https://example.com/og.png", "style": "", "script": "", "head": ""}
```

- `timestamp`：覆盖文章时间（Unix 秒）
- `ogImage`：该文章的 OG 分享图
- `style` / `script` / `head`：单篇注入的 HTML 片段（在全局配置基础上追加）

## 与 Gmeek 的差异

- 评论：utteranc.es -> giscus；文章 URL：slug -> Issue 编号
- 配置：`config.json` -> `config.toml`（pydantic 校验，未知键报错）
- 产物：`docs/` -> `dist/`，`backup/` -> `sources/`，`blogBase.json` -> `internote.json`
- CLI：`internote <token> <repo> [--issue-number N]`（兼容 `--issue_number`）
- 工具链：uv + src 布局 + pytest 测试（`tests/`）

## 鸣谢

- [Gmeek](https://github.com/Meekdai/Gmeek) — 本项目的前身
- [jinja2](https://jinja.palletsprojects.com/)、[giscus](https://giscus.app)、[primer.style](https://primer.style/css)
- [gitblog](https://github.com/yihong0618/gitblog)

## License

见 [LICENSE](LICENSE)。请保留页面底部与 console 界面的版权信息
（`Powered by Internote • Based on Gmeek`），谢谢！
