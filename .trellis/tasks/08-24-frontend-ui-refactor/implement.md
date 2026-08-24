# 全项目前端 UI 现代化重构实施计划 (Implementation Plan)

## 实施阶段 (Phases)

### 阶段 1: 全局设计 Token 与样式基础升级
- [x] 升级 `desktop/src/styles/globals.css` 与 `desktop/tailwind.config.js`。
  - 增加高级表面 tokens（`--bg-base`, `--bg-subtle`, `--bg-muted`, `--bg-elevated`, `--bg-card`）。
  - 优化边框与分割线 tokens（`--border-default`, `--border-strong`, `--border-subtle`）。
  - 优化主色调与状态色彩（Indigo 现代调色板、Emerald 成功色、Rose 危险色、Amber 警告色、Sky 提示色）。
  - 添加阴影（Subtle, Elevated, Popover）、毛玻璃 backdrop-blur 工具类、平滑过渡动效、定制纤细精致滚动条。

### 阶段 2: 应用外壳与全局组件重构
- [x] 重构 `desktop/src/components/Sidebar.tsx`
  - 升级品牌 Logo 容器与发光效果。
  - 重构导航条目（活动状态条、微交互、优雅 Tooltip、收起过渡动画）。
- [x] 重构 `desktop/src/components/TopBar.tsx`
  - 采用毛玻璃背景，优化页面标题/面包屑展示。
  - 升级分段式（Segmented Pill）主题切换器。
- [x] 重构 `desktop/src/components/StatusBar.tsx` 与 `desktop/src/components/ActivityPopover.tsx`
  - 状态栏增加连接状态呼吸灯、存储后端信息徽章、任务状态气泡。
  - 活动任务悬浮窗采用毛玻璃卡片、进度条与清晰的任务列表。
- [x] 重构 `desktop/src/components/BackendGate.tsx`
  - 升级连接中与离线错误卡片，带品牌呼吸动效与重试交互。

### 阶段 3: 对话页面与消息渲染体系重构
- [x] 重构 `desktop/src/components/SessionList.tsx`
  - 现代 "+ 新建对话" 渐变按钮、会话卡片悬浮效果、防误触删除体验。
- [x] 重构 `desktop/src/pages/ChatPage.tsx`
  - 欢迎界面 Hero 卡片与快捷提示词气泡。
  - 模式切换分段控制器（Auto / Quick / Deep）。
  - 悬浮卡片式 Composer 输入框、多图上传预览胶囊、拖拽高亮边框、快捷键提示。
- [x] 重构 `desktop/src/components/TurnView.tsx` 与 `desktop/src/components/MarkdownView.tsx`
  - 用户与助手消息气泡视觉分层。
  - 思考过程与规划步骤折叠展开卡片。
  - 工具调用卡片（带执行状态、高亮代码块、耗时徽章）。
  - 度量信息底栏精致 Pill 标签。

### 阶段 4: 知识库文件管理器与各类文件预览器重构
- [x] 重构 `desktop/src/components/library/FolderTree.tsx`
  - 顶部操作工具栏升级（新建、上传、同步、重解析）。
  - 彩色文件类型图标系统（PDF, MD, Code, Office, Image, Media, Binary）。
  - 悬浮操作菜单与加载中脉冲动效。
- [x] 重构 `desktop/src/components/library/MetaPanel.tsx`
  - 智能摘要卡片、动态标签胶囊云、关联相似知识推荐卡片。
- [x] 重构 `desktop/src/components/library/FileViewer.tsx` 及各类 viewers (`viewers/*`)
  - 顶部工具栏视觉优化，各类型查看器样式与内边距精修。
- [x] 重构 `desktop/src/components/library/Dialogs.tsx`
  - 模态弹窗毛玻璃背景、精致表单输入框与按钮。

### 阶段 5: 搜索中心页面重构
- [x] 重构 `desktop/src/pages/SearchPage.tsx`
  - 居中聚焦搜索框、快捷键标识、清空/加载动效。
  - 搜索结果卡片与面包屑路径、高亮匹配摘要与标签。

### 阶段 6: 设置页面与模型配置重构
- [x] 重构 `desktop/src/pages/SettingsPage.tsx` 与 `desktop/src/components/LlmProfileEditor.tsx`
  - 分区卡片式布局与功能图标。
  - 快速配置 / 预设服务商模板卡片选择器。
  - API Key 密码切换与状态指示徽章、单 Profile 连接测试反馈。
  - 高级配置折叠面板、WebDAV、检索索引、偏好设置卡片。

### 阶段 7: 帮助中心与关于页面重构
- [x] 重构 `desktop/src/pages/HelpPage.tsx`
  - 模块化指南卡片、配置参数速查表、快捷键列表。
- [x] 重构 `desktop/src/pages/AboutPage.tsx`
  - 品牌 Logo Hero、版本检查更新卡片、系统信息一键复制、精美外部链接。

### 阶段 8: 质量验证与构建检查
- [x] 运行 `npm run lint` 和 `npm run build`，确保无任何类型与构建错误。
- [x] 检查全站 Light / Dark 模式视觉效果与交互一致性。
