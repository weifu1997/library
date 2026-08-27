# 全项目前端 UI 现代化重构设计方案 (Design Specification)

## 1. 设计系统 (Design Tokens & Theme Architecture)

### 1.1 色彩与表面 (Surfaces & Colors)
- **Light Theme**:
  - `--bg-base`: `255 255 255` (纯净底色)
  - `--bg-subtle`: `248 249 251` (柔和次表面)
  - `--bg-muted`: `241 243 246` (组件底色/输入框/卡片浅底)
  - `--bg-elevated`: `255 255 255` (悬浮卡片/弹窗/下拉菜单)
  - `--border-default`: `226 232 240` (微边框，slate-200)
  - `--border-strong`: `203 213 225` (交互边框，slate-300)
  - `--accent`: `79 70 229` (Indigo 600)
  - `--accent-fg`: `255 255 255`
  - `--accent-subtle`: `238 242 255` (Indigo 50)
  - `--accent-hover`: `67 56 202` (Indigo 700)
- **Dark Theme**:
  - `--bg-base`: `10 11 14` (深度暗黑，slate-950+zinc-950 混合质感)
  - `--bg-subtle`: `15 17 21` (侧栏与次级背景)
  - `--bg-muted`: `22 25 31` (组件底色/卡片底色)
  - `--bg-elevated`: `27 31 39` (悬浮卡片/弹窗)
  - `--border-default`: `35 41 51` (精致暗色微边框)
  - `--border-strong`: `51 60 74` (高亮暗色边框)
  - `--accent`: `99 102 241` (Indigo 500)
  - `--accent-fg`: `255 255 255`
  - `--accent-subtle`: `30 27 75` (深邃暗紫背景)
  - `--accent-hover`: `129 140 248` (Indigo 400)

### 1.2 阴影与微质感 (Shadows & Micro-Textures)
- `shadow-subtle`: `0 1px 2px 0 rgba(0, 0, 0, 0.03)`
- `shadow-elevated`: `0 4px 16px -2px rgba(0, 0, 0, 0.06), 0 2px 6px -1px rgba(0, 0, 0, 0.03)`
- `shadow-popover`: `0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.05)`
- `backdrop-blur-glass`: `backdrop-filter: blur(12px) saturate(180%)`

### 1.3 字体排版与图标规范
- 中西文混合排版：SF Pro, Inter, system-ui, "PingFang SC", "Microsoft YaHei", sans-serif.
- 等宽代码字体：JetBrains Mono, Fira Code, Menlo, monospace.
- 字重与层级比例：
  - H1: 22px / 1.35 / font-semibold / tracking-tight
  - H2: 17px / 1.4 / font-semibold
  - H3: 15px / 1.45 / font-medium
  - Body: 14px / 1.55 / font-normal
  - Small / Caption: 12px / 1.45 / font-medium

---

## 2. 组件重构设计

### 2.1 App Shell
- **Sidebar**:
  - 渐变立体 Logo 容器，提升品牌视觉辨识度。
  - 导航条目：带左侧或胶囊高亮背景，平滑的 Icon 缩放与颜色过渡。
- **TopBar**:
  - `backdrop-blur-md` 磨砂玻璃质感，当前页面 Title / Breadcrumb 显示。
  - Segmented Theme Pill 切换器，带平滑阴影与图标高亮。
- **StatusBar & ActivityPopover**:
  - 绿色/红色网络状态指示点（带呼吸动效）。
  - 活动任务统计卡片，带进度条、取消/重试按钮和任务耗时。
- **BackendGate**:
  - 现代化 Logo 呼吸灯、连接重试状态提示卡片。

### 2.2 对话工作台 (Chat & Conversations)
- **SessionList**: 现代扁平卡片，hover 时显示删除按钮，选中状态带左侧 Indigo 强调指示条。
- **Composer**: 悬浮卡片式输入容器，支持多图附件预览胶囊（带关闭动画）、模式切换胶囊选择器、输入框自适应扩展高度。
- **TurnView**:
  - 消息气泡区分：用户消息更紧凑优雅，助手回复 Markdown 呈现细腻行距与优雅代码块。
  - 思考过程 (Thinking) 与 规划 (Plan) 的折叠收起动画。
  - 工具调用卡片 (Tool Calls) 带有状态图标（绿勾/红叉/旋转）、语法高亮参数展开与耗时展示。

### 2.3 知识库管理器 (Library & Viewers)
- **FolderTree**:
  - 现代化图标库：按文件后缀（`.pdf`, `.md`, `.docx`, `.xlsx`, `.py`, `.png` 等）显示精美的彩色图标。
  - 操作栏与搜索快速筛选、清晰的层级折叠树、右键/悬浮操作菜单。
- **FileViewer**:
  - 统一的顶部工具栏（文件名、类型 Tag、大小、下载、外部打开、全屏/关闭）。
  - 各类文件预览器（PDF, Office, Markdown, Image, Code, Email, Epub）背景与内边距精修。
- **MetaPanel**:
  - 优雅卡片分区：智能摘要、彩色标签云（带创建/删除交互）、关联知识相似度条形图。
- **Dialogs**:
  - 统一毛玻璃遮罩、圆角卡片、平滑缩放进入动画（`zoom-in-95`）。

### 2.4 搜索中心 (Search Page)
- 居中大气搜索框，带有渐变边框聚焦高亮、实时清除与 loading 状态。
- 搜索结果卡片：标题高亮、路径导航、高亮内容摘录（Highlight snippet）、标签徽章。

### 2.5 设置页面 (Settings Page)
- 分区卡片导航，每个设置分组带有专属图标和副标题。
- 预设大模型服务商（OpenAI, Anthropic, DeepSeek, 通义千问, Kimi, Ollama 本地等）网格卡片一键选择。
- API Key 安全掩码切换、单模型连接测试反馈条、高级配置按需折叠。

### 2.6 帮助中心与关于 (Help & About)
- 现代化网格卡片展示系统特性、按分类排列的配置参数字典、快捷键矩阵。
- 关于页面：版本检查状态、更新动态、一键复制诊断信息、项目链接卡片。
