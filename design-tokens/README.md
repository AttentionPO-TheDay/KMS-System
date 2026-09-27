# design-tokens

KMS 5 个前端共用的设计令牌与基础样式层。

## 为什么需要它

此前 5 个前端各自维护一套暗色主题，品牌色与背景值互不相同：

| 应用 | 原主色 / 背景 | 原实现 |
|---|---|---|
| `kms-user/front` | `#00e5ff` / `#050507` | `src/styles.css` + `kms-official-theme.scss` |
| `kms-generate/front` | `#0099ff` / `#050507` | `kms-official-theme.scss` |
| `kms-updatedel/front` | `#0099ff` / `#050507` | `kms-official-theme.scss` |
| `kms-acceptance/front` | `#00f2fe` / `#020617` | `src/style.css` |
| `kms-distribute/.../web` | Element 默认 | `src/theme/**` + tailwind |

且 `kms-official-theme.scss` 在 3 个应用中逐字节重复，靠 58 处 `!important` 硬压 Element 样式。
本目录把颜色、间距、圆角、阴影收敛为**唯一真源**，并改用 Element 官方 CSS 变量驱动。

> **2026-09-26 注**：上表是**收敛之前**的状态，保留作设计依据的历史说明。
> 其中 `kms-generate/front` 与 `kms-distribute/.../web` 两个前端**已随代码清理删除**，
> 现在引用本目录的是 **3 个前端**（`kms-user`、`kms-updatedel`、`kms-acceptance`）。

## 目录结构

```
design-tokens/
├── tokens.scss         # 唯一真源：颜色 / 间距 / 圆角 / 阴影 / 字体 / 动效
├── base.scss           # reset + 排版基线 + 通用布局类（.kms-card 等）
├── element-light.scss  # Element Plus 浅色适配（CSS 变量优先，最小化选择器覆盖）
└── README.md
```

## 接入方式

1. 在应用 `vite.config.js` 增加别名：

```js
resolve: {
  alias: {
    '@': path.resolve(__dirname, './src'),
    '@tokens': path.resolve(__dirname, '../../design-tokens')
  }
}
```

2. 在入口 SCSS 中按顺序引入：

```scss
@import '@tokens/tokens';
@import '@tokens/base';
@import '@tokens/element-light';
```

3. 组件内一律使用令牌，不再写字面颜色值：

```scss
.my-panel {
  background: var(--kms-surface-1);
  border: 1px solid var(--kms-border);
  border-radius: var(--kms-radius);
  color: var(--kms-text-primary);
}
```

## 命名约定

- `--kms-surface-page` / `-1` / `-2` / `-3`：背景层次，数字越大越"深"（用于区块区分）
- `--kms-text-primary` / `-secondary` / `-tertiary` / `-disabled`：文本层级
- `--kms-brand` / `-fill` / `-text` / `-hover` / `-active` / `-subtle` / `-border`：品牌主色族
- `--kms-success|warning|danger|info` 及各自 `-strong` / `-subtle` / `-border`：状态色
- `--kms-space-*`、`--kms-radius-*`、`--kms-shadow-*`：间距 / 圆角 / 阴影

语义层**不出现 `dark` / `light` 字样**，便于后续引入其他主题而不改名。

## 按用途取色（重要，避免踩对比度问题）

同一族颜色有多个变体，**必须按用途取用**：

| 用途 | 取哪个令牌 | 原因 |
|---|---|---|
| 图标、装饰、渐变 | `--kms-brand` / `--kms-success` 等**明亮色** | 不承载文字，明亮更醒目 |
| 按钮等**有白字压在上面**的填充 | `--kms-brand-fill` | 白字压明亮主色仅 4.1，压 fill 为 5.76（达 WCAG AA） |
| 链接、正文文字 | `--kms-brand-text` | 明亮主色压白底仅 4.1，text 变体为 5.76 |
| 状态色**作为浅底上的文字** | `--kms-<state>-strong` | 明亮状态色压各自浅底实测 2.4~3.3，均不达标；strong 为 5.0+ |
| 状态色的浅色底 | `--kms-<state>-subtle` | 背景，不承载文字 |
| 浅底上的描边 | `--kms-<state>-border` | 边框 |

实测对比度（修正后，全部达 WCAG AA 正文标准 4.5）：

| 配对 | 对比度 |
|---|---|
| 正文 / 白卡片 | 15.78 |
| 次要文本 / 白卡片 | 5.45 |
| 三级文本 / 页面底 | 4.59 |
| 链接色 / 白卡片 | 5.76 |
| 白字 / 品牌按钮 | 5.76 |
| 成功文字 / 成功浅底 | 5.04 |
| 警告文字 / 警告浅底 | 5.58 |
| 危险文字 / 危险浅底 | 6.67 |
| 信息文字 / 信息浅底 | 5.13 |

> 注意：CSS 变量无法用于 ECharts（canvas 渲染）。图表配色见各仪表盘页内的
> `CHART_COLORS` 字面量常量，改品牌色时需同步该处。

## 改色指引

改品牌色只需修改 `tokens.scss` 中的 `--kms-brand` 族（含 `-fill` / `-text` 变体），
再同步 `element-light.scss` 里 `--el-color-primary-light-3/5/7/8` 的中间梯度
（Element 需要 5 级浅色梯度，无法由单一变量推导），
以及用到图表的页面里的 `CHART_COLORS`。

## 注意事项

- `base.scss` **不**覆盖 Element 组件外观，避免与 `element-light.scss` 职责重叠。
- `element-light.scss` 中仅保留 1 处 `!important`（`.el-card` 阴影），
  原因是 Element Plus 卡片默认阴影较重且通过内联变量无法下调；其余全部走 CSS 变量。
- 旧文件 `assets/styles/kms-official-theme.scss` 已改为引用本目录，不再保存颜色字面值。