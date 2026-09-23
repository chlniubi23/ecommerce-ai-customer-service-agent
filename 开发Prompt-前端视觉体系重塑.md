# 开发 Prompt：前端视觉体系重塑（Dark Premium 方向）

> 交付方式：将本文档整体交给一个新的开发对话执行。
> 项目根目录：`E-commerce Customer Service Agent/frontend/`。
> 技术栈：Next.js 15（App Router）+ React 19 + Tailwind CSS 3 + TypeScript strict。
> **核心红线：本次是纯视觉重塑，功能、交互逻辑、API 契约一律不改；`npm run build` 必须通过。**

---

## 一、目标

把当前"仿抖音商城风 + 三套配色打架"的前端，重塑为深色产品级（Dark Premium）视觉体系。
验收语境：观众打开首页 3 秒内感受到"这是一个有质感的 AI 产品"，并且**不改任何交互功能**。

项目本质：AI 客服 Agent 演示系统——视觉主角是 **AI 能力与实时业务数据**，不是商品流。

## 二、现状诊断（已代码实证，开发时对照处理）

| # | 问题 | 位置 |
| --- | --- | --- |
| V1 | 配色三套并存：tailwind `primary`=蓝色系、`globals.css` `--brand`=#ff2442 粉红、首页场景卡 8 种彩色渐变 | `tailwind.config.ts`、`app/globals.css` |
| V2 | 首页信息架构错位：仿抖音商城占 80% 版面，业务数据面板/AI 能力被埋角落 | `app/page.tsx`（190 行） |
| V3 | 组件类 `app-card/app-button/app-input/ai-soft-panel/ai-link/ai-price` 全部粉色定义，全站引用 | `globals.css` @layer components |
| V4 | 动效基础设施良好可直接复用：打字机、3D 数字人、消息入场、骨架屏、加载点、徽章弹 | `globals.css` 后半部分 |

## 三、设计语言（已锁定，不得自由发挥）

### 3.1 色彩 Token（唯一事实源，tailwind.config.ts 与 globals.css 同步）

```
背景基底:
  bg-base:      #0A0A0F   (页面底色)
  bg-surface:   #12121A   (卡片/面板)
  bg-elevated:  #1A1A26   (悬浮层/浮窗)
  border-line:  rgba(255,255,255,0.08)

文字:
  text-primary:   #F4F4F6
  text-secondary: #A1A1B0
  text-tertiary:  #6B6B7B

Accent（全站唯一主色，禁止第二种彩色）:
  accent:        #6366F1  (indigo-500)
  accent-hover:  #818CF8
  accent-glow:   rgba(99,102,241,0.35)
  accent-gradient: linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%)  (仅用于点睛：主按钮、数字人光环、核心数据)

功能色（仅状态提示，极小面积）:
  success: #34D399, warning: #FBBF24, danger: #F87171

价格/强调数字: 继承 text-primary，不再用品牌红
```

### 3.2 排版
- 页面标题：`font-black tracking-tight`，Hero 标题 5xl~7xl，副标题 text-secondary；
- 数据数字：等宽数字特性（`tabular-nums`），大号字重 black；
- 中文正文保持现有字体栈，微调行高（1.6）与字距。

### 3.3 材质与光效
- 卡片：`bg-surface` + 1px `border-line` + 极淡内阴影，**不用大圆角粉影**（圆角统一 12-16px）；
- 光效：仅三处——Hero 背景的单 accent 径向微光（opacity ≤ 0.15）、主按钮 hover 时的 `accent-glow` 光晕、数字人背后的 aura（复用现有 `.assistant-aura` 动画，颜色改 accent）；
- 毛玻璃仅用于浮窗/导航（`backdrop-blur` + 半透明 `bg-elevated`）。

### 3.4 图标
- 全站用 **lucide-react** 线性图标替代 emoji（允许新增此依赖，它是该栈标配）；
- 移除所有 emoji 图标（🔥⏰💰👑📦🚚⚠️ 等）；状态点保留 emoji 文字的地方改彩色圆点。

## 四、任务分解（按阶段执行，每阶段独立可验收）

### 阶段 P1：设计 Token 统一（先改地基）
1. `tailwind.config.ts`：theme.extend 写入第三节全部 token（colors / boxShadow / fontFamily 微调），删除旧的 blue primary 定义；
2. `globals.css`：`:root` 变量、`app-card/app-panel/app-input/app-button/app-button-secondary/ai-soft-panel/ai-link/ai-price` 全部按新 token 重写；body 背景改为 `bg-base` + 单 accent 径向微光；滚动条、骨架屏 shimmer 适配暗色；
3. 验收：全站构建通过，页面呈现为深色基底（此时各页面细节未打磨可接受）。

### 阶段 P2：首页重塑（视觉主战场）
`app/page.tsx` 重构为以下结构（数据接口调用方式不变）：
1. **Hero 区**：深色底 + 单 accent 微光；左列大标题（参考："一句话，AI 帮你把售后办完"之类的产品主张，允许文案微调但禁止电商促销口吻）+ 副标题 + 2 个 CTA（主按钮 accent-gradient"立即对话"唤起浮窗、次按钮描边"逛商城"）；右列数字人展示（复用 3D 浮动动画 + accent aura 光环 + 下方悬浮"对话预览气泡"展示 1-2 条真实 Agent 能力样例，如"退款已提交，单号 RF_DEMO_002"）；
2. **能力 Bento 网格**（6 格不同尺寸）：查订单/追物流/退款售后/投诉升级/知识问答/转人工——每格 = lucide 图标 + 一句话价值 + 真实数据点缀（如"今日已处理 N 单"从 dashboard API 取）；hover 时 1px accent 边框渐显 + 轻微上浮；
3. **实时业务数据带**（全宽深色面板）：商品/订单/退款/投诉 4 个大数字（tabular-nums、入场时数字滚动动画，可用 requestAnimationFrame 纯 JS 实现，不引入计数库）+ 工具调用成功率 mini 条形（真实 metrics 数据）；
4. **商品区降级**：保留但改为"精选商品"小卡片流（暗色卡片、价格不再品牌红），放在 Bento 之后；
5. 验收：首页首屏无商城促销感，AI 与数据为视觉 C 位；数据来源与现有 API 完全一致。

### 阶段 P3：全站换肤（风格一致性）
`SiteShell.tsx`（导航：深色毛玻璃顶栏）、`/products`、`/products/[id]`、`/orders`、`/orders/[id]`、`/profile`、`/after-sales`、`/complaints`、`/metrics`、`/knowledge-base`、`/login`、`/register` 逐页检查：
- 背景/卡片/按钮/输入框/表格/状态徽章全部落到新 token；
- 状态徽章（订单/退款/投诉状态）用"彩色圆点 + 文字"方案（成功绿点、进行黄点、异常红点、默认灰点），禁止彩色渐变徽章；
- `/metrics` 页面图表适配暗色（如用 CSS 绘制的条形图改 bg-elevated 底 + accent 条）；
- 验收：13 个路由全部暗色一致、无粉色残留（grep `#ff2442`、`pink-` 应为 0 匹配）。

### 阶段 P4：AI 浮窗视觉升级（只改样式，不改交互）
`components/chat/FloatingAIAssistant.tsx`（1427 行）**只动 className 与内联样式，不改任何状态/事件/API 逻辑**：
- 面板：暗色毛玻璃 `bg-elevated/90 backdrop-blur-xl` + border-line；消息气泡：用户气泡 accent 底色、AI 气泡 bg-surface；
- 确认卡片/数据卡片/Trace 时间线：适配暗色（确认卡按钮 accent）；
- 快捷场景卡：8 种彩色渐变 → 统一 `bg-surface` + hover accent 边框；
- 验收：聊天、SSE 流式、确认卡、订单选择抽屉、主动事件提醒全部功能正常。

### 阶段 P5：动效打磨（克制，不做花活）
- 页面区块入场：`opacity 0→1, translateY 16px→0`，stagger 80ms，只用 CSS（复用现有动画模式）；
- 数字滚动（P2-3）、Hero 微光缓慢漂移（60s 周期，opacity 不超标）；
- 保留并尊重 `prefers-reduced-motion` 已有媒体查询，新动画一律加入该查询；
- 验收：Lighthouse 无动画性能警告级问题（60fps 目标，transform/opacity only）。

## 五、执行约束（红线）

1. **功能零破坏**：不改 services/、types/（除图标类型）、API 契约、路由结构、浮窗交互逻辑、上下文组装（buildContextPrompt 一行不许动）；
2. `npm run build` 每阶段结束必须跑通；**不允许** 为了样式改任何后端接口；
3. 依赖仅允许新增 `lucide-react`；禁止引入 UI 框架（shadcn/MUI/AntD）或动画库（framer-motion）——纯 CSS/Tailwind 实现；
4. 数字人 PNG 与商品 SVG 资产继续用现有 `public/` 资源，`next/image` 加载方式不变；
5. 移动端/窄屏不回归（浮窗、Bento 网格需响应式：Bento 在 md 以下退化为单列）;
6. 文案仅允许 Hero 区与 CTA 微调（产品口吻，禁止促销口吻）；其他页面文案不动；
7. 每阶段一个 git commit，message 注明 P1~P5；
8. 完成前 grep 自检：`#ff2442`、`#fff7fa`、`pink-`、`from-pink` 等粉色痕迹为 0。

## 六、验证标准

1. `npm run build` 通过，13 个路由全部可访问无运行时报错；
2. 视觉对比：首页/Bento/数据带/浮窗前后截图对比附入交付报告；
3. 功能回归清单（手动逐项）：登录 → 详情页唤起助手 → 聊天（流式）→ 触发退款确认卡 → 确认提交 → 订单列表/详情数据正确 → metrics 页数据展示 → knowledge-base 上传组件可用；
4. 暗色一致性：无粉色残留（grep 自检输出附报告）；表单/表格/弹层文字对比度可读（text-secondary 以上用于正文）；
5. 交付报告包含：改动文件清单（按 P1-P5 分组）、token 对照表（旧值→新值）、前后截图对比、功能回归清单逐项勾选结果。
