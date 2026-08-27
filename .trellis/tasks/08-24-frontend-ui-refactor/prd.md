# 全项目前端页面 UI 现代化重构 (PRD)

## 1. 目标与定位 (Goal & Vision)
基于 `ui-design-system` 技能，参考 **Apple HIG**（空间排版、精致质感）、**Google Material 3**（色彩层次、动效规范）、**Linear / Vercel**（极简现代、克制高级），对 Library 本地知识库的整个前端页面（React + Tailwind + Vite）进行系统级的 UI 现代化重构与视觉体验升级。

- **克制的奢华**：统一的设计 Token 体系，避免粗糙与过时模式，营造极具质感的现代桌面级应用体验。
- **高阶视觉质感**：细腻的 Frosted Glass (Backdrop Blur) 毛玻璃效果、微层次多阶阴影、精致的微边框（1px elevated border）、平滑过渡动画。
- **极致的可用性与一致性**：全站统一的组件交互规范（Hover / Active / Focus-visible / Loading / Empty 状态），多端明暗主题（Light / Dark）无缝适配。

---

## 2. 需求范围 (Scope & Requirements)

### R1. 全局设计系统与 Token 体系升级
- 升级 `globals.css` 与 `tailwind.config.js`，建立严谨的 Design Tokens：
  - 表面层级（Base / Subtle / Muted / Elevated / Overlay / Glass）
  - 文本与图标层级（Foreground Base / Muted / Subtle / Accent）
  - 状态色系（Success / Danger / Warning / Info）
  - 阴影与微边框（Elevation Shadows, Subtle Borders）
  - 交互与动效（Easing Curves, Micro-transitions, Skeleton Shimmer, Smooth Spring-like effects）
  - 统一定制纤细精致的现代滚动条。

### R2. 应用外壳与全局导航 (App Shell & Navigation)
- **Sidebar**: 升级 Brand Logo 与发光图标、精致的导航条目（带 active 指示条、流畅 hover 背景）、收起/展开平滑过渡、底部版本号与状态标识。
- **TopBar**: 采用毛玻璃背景 (`backdrop-blur-md`)、动态页面标题与面包屑、精细化分段控制（Segmented Pill）主题切换器（Light/System/Dark）。
- **StatusBar & ActivityPopover**: 底部状态栏增加实时在线/离线呼吸灯状态指示点、存储后端徽章、活动任务悬浮卡片（带任务进度条、状态徽章与毛玻璃卡片）。
- **BackendGate**: 现代化的断线重连与全屏加载态，带有渐变 Logo 呼吸动效与优雅的重试交互。

### R3. 对话工作台页面 (Chat Page & Turn Components)
- **Welcome Hero**: 精致的欢迎界面，内置功能卡片与快捷提问建议气泡（Prompt Suggestion Chips）。
- **Session List**: 现代高质感 "+ 新建对话" 渐变按钮、会话卡片悬浮效果、相对时间格式化、删除操作防误触气泡。
- **Mode Selector**: Auto / Quick / Deep 模式切换器升级为现代胶囊分段组件，配合高质感图标与 Tooltip 说明。
- **Composer 输入区**: 悬浮卡片设计，支持多图附件缩略图预览胶囊、拖拽上传高亮边框、快捷键提示徽章与精致发送按钮。
- **TurnView & MarkdownView**:
  - 用户消息与 AI 助手回答的高级气泡与排版优化。
  - 思考过程 (Thinking) 与 计划进度 (Plan) 可折叠手风琴面板，流畅展开。
  - 工具调用卡片 (Tool Calls)：区分执行中、成功、失败状态，提供语法高亮参数预览与展开查看。
  - 丰富 Markdown 渲染：表格、代码块一键复制与语言标签、高亮引用来源（Citations）与联动定位。
  - 单轮度量数据底栏（Token 消耗、缓存命中率、耗时等）以精致 Pill 形式呈现。

### R4. 知识库管理与文件预览 (Library Explorer & Viewers)
- **FolderTree**:
  - 现代化操作工具栏（新建文件夹、上传文件、WebDAV 同步、重新解析），图标与按钮统一风格。
  - 树形节点优化：依据文件类型（PDF、Markdown、Office、代码、图片等）区分精美彩色文件图标，入库中任务带脉冲动画，悬浮快捷操作。
  - 侧边栏宽度拖拽分割条提供流畅的 hover 激活指示线。
- **MetaPanel**: 抽屉卡片面板，包含文件基本信息、AI 智能摘要卡片、标签云（带动态添加/删除交互）、相关推荐文件列表（带相似度评分条）。
- **FileViewer**: 顶部文件信息条、各类专业预览器（Markdown、Image、PDF、Office 文档、代码与文本、Email、Epub、Binary）视觉与布局全面精修。
- **Dialogs**: 模态弹窗（新建文件夹、文件上传、WebDAV 配置等）统一毛玻璃背景、精致表单输入框与主次操作按钮。

### R5. 搜索中心页面 (Search Page)
- 搜索栏升级为居中聚焦的大气搜索框，带快捷键提示徽章（`/`）、加载微动效。
- 搜索结果卡片：高亮匹配摘要、文件路径导航条、标签徽章、相关度指示器。
- 优化的空搜索与无结果引导态。

### R6. 设置与模型配置页面 (Settings & LLM Configuration)
- 分区卡片式布局：视觉分组明确，提供清晰的标题与说明。
- 快速配置 / 服务商预设模板（OpenAI、Anthropic、DeepSeek、通义千问、Kimi、Ollama 等）卡片选择器，一键预填。
- 默认配置表单：API Key 明暗显示切换、已配置/未配置状态徽章、单 profile 连接测试（带测试中动画与成功/失败结果提示）。
- 高级配置折叠面板、WebDAV 同步、检索与索引配置、偏好设置、服务器状态诊断卡片。

### R7. 帮助中心与关于页面 (Help & About Pages)
- **HelpPage**: 结构化的配置参考表格（Key-Value 对齐、默认值徽章）、快捷键速查表、功能特性指引卡片。
- **AboutPage**: Logo Hero 卡片、版本号状态、检查更新交互卡片、系统信息一键复制、外部链接精致悬浮卡片、隐私保证。

---

## 3. 验收标准 (Acceptance Criteria)
- [ ] 全站所有页面（Chat, Library, Search, Settings, Help, About）UI 完成全面升级，达到现代化大厂/Pinterest 级高级简约美学。
- [ ] 浅色（Light）与深色（Dark）模式下所有组件色彩对比度合规（WCAG AA），无生硬断层。
- [ ] 所有交互状态（Hover, Active, Focus, Loading, Empty, Disabled）完整且动效流畅自然。
- [ ] 前端 TypeScript 编译（`npm run lint`）与 Vite 构建（`npm run build`）100% 成功通过。
