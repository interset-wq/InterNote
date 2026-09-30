# InterNote 模板设计规范

## 命名规范

所有自定义 CSS class 统一使用 `in-` 前缀，避免与 Primer CSS 框架冲突。

### 前缀规则

| 前缀 | 用途 | 示例 |
|------|------|------|
| `in-site-` | 站点级布局组件 | `.in-site-header` `.in-site-main` `.in-site-footer` |
| `in-post-` | 文章相关组件 | `.in-post-title` `.in-post-meta` `.in-post-body` |
| `in-nav-` | 导航组件 | `.in-nav-btn` `.in-site-nav` |
| `in-badge` | 徽章/标签 | `.in-badge` |
| `in-comments-` | 评论组件 | `.in-comments-section` `.in-comments-toggle` |
| `in-post-list-` | 文章列表组件 | `.in-post-list-item` `.in-post-list-badges` |
| `in-pagination` | 分页组件 | `.in-pagination` `.in-disabled` |
| `in-search-` | 搜索组件 | `.in-search-form` `.in-search-input` |
| `in-tag-cloud` | 标签云 | `.in-tag-cloud` |
| `in-footer-` | 页脚组件 | `.in-footer-icons` `.in-footer-powered` |
| `in-` | 工具类 | `.in-animated-ellipsis` `.in-empty-state` |

### 完整 class 列表

#### 布局组件
- `.in-site-header` — 页面头部
- `.in-site-main` — 主内容区
- `.in-site-footer` — 页面底部
- `.in-site-branding` — 品牌区域（头像 + 标题）
- `.in-site-avatar` — 站点头像
- `.in-site-title` — 站点标题
- `.in-site-nav` — 导航栏
- `.in-nav-btn` — 导航按钮

#### 文章组件
- `.in-post-header` — 文章头部
- `.in-post-title` — 文章标题
- `.in-post-meta` — 文章元信息（日期、标签）
- `.in-post-body` — 文章正文
- `.in-post-footer-text` — 文章底部文字
- `.in-badge` — 徽章/标签

#### 评论组件
- `.in-comments-section` — 评论区
- `.in-comments-toggle` — 评论开关按钮
- `.in-comments-container` — 评论容器

#### 列表组件
- `.in-post-list` — 文章列表
- `.in-post-list-item` — 列表项
- `.in-post-list-title` — 列表项标题
- `.in-post-list-badges` — 列表项徽章组
- `.in-post-icon-0` / `.in-post-icon-1` — 列表项图标（置顶/普通）

#### 分页组件
- `.in-pagination` — 分页容器
- `.in-disabled` — 禁用状态

#### 搜索/标签组件
- `.in-page-title` — 页面标题
- `.in-search-form` — 搜索表单
- `.in-search-input` — 搜索输入框
- `.in-search-btn` — 搜索按钮
- `.in-tag-cloud` — 标签云
- `.in-empty-state` — 空状态提示

#### 页脚组件
- `.in-footer-icons` — 页脚图标行
- `.in-footer-line` — 页脚行
- `.in-footer-powered` — 页脚版权信息

#### 代码复制
- `.in-copy-feedback` — 复制反馈提示
- `.in-clipboard-wrapper` — 剪贴板包装器

#### 工具类
- `.in-animated-ellipsis` — 动画省略号
- `.in-empty-state` — 空状态

## 文件结构

```
templates/
├── base.j2.html              # 基础布局
├── post.j2.html              # 文章页
├── post-list.j2.html         # 文章列表页
├── tag.j2.html               # 标签搜索页
├── assets/
│   └── main.css              # 自定义样式（in- 前缀）
└── components/
    ├── header.j2.html        # 头部组件
    ├── footer.j2.html        # 底部组件
    ├── nav.j2.html           # 导航组件
    └── head-meta.j2.html     # Meta 标签
```

## CSS 架构

### 设计令牌（Design Tokens）

```css
:root {
  --in-max-width: 900px;
  --in-padding: 45px;
  --in-radius: 6px;
  --in-font-stack: ...;
  --in-color-text: ...;
  --in-color-bg: ...;
  --in-color-border: ...;
  --in-color-accent: ...;
  --in-color-muted: ...;
  --in-color-subtle: ...;
}
```

### 颜色系统

优先使用 Primer CSS 变量，回退到默认值：

```css
--in-color-text: var(--color-fg-default, #1f2328);
--in-color-bg: var(--color-canvas-default, #ffffff);
--in-color-border: var(--borderColor-muted, #d0d7de);
```

### 响应式断点

```css
@media (max-width: 600px) {
  :root { --in-padding: 16px; }
  /* 移动端适配 */
}
```

## 模板继承结构

```
base.j2.html
├── post.j2.html
├── post-list.j2.html
└── tag.j2.html
```

## 组件引用

```html
<!-- base.j2.html -->
{% include 'components/footer.j2.html' %}

<!-- post.j2.html / post-list.j2.html -->
{% include 'components/head-meta.j2.html' %}
```

## 插件

| 插件 | 用途 |
|------|------|
| `plugins/giscus.js` | Giscus 评论系统 |
| `plugins/tocbot.js` | 文章目录生成 |
| `plugins/vercount.js` | 访问量统计 |
| `plugins/busuanzi.js` | 访问量统计（备选） |
