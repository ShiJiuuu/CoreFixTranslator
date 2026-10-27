# PDF翻译与排版重建技术方案

# PDF 翻译与排版重建技术方案

面向自研 PDF 翻译软件的工程落地文档。目标：让译文排版达到"视觉等价"于原文档，而非像素级还原。

---

## 0. 三条铁律

在写任何代码之前先确立，它们决定了系统能力的上限。

| # | 原则 | 说明 |
| --- | --- | --- |
| 1 | 中间表示必须是**带几何信息的文档树** | 纯文本流 IR 会永久丢失排版能力，后期无法补救 |
| 2 | 排版目标是**视觉等价**，不是像素还原 | 强行像素还原必然产生挤压与空洞，得不偿失 |
| 3 | 所有排版参数必须**可配置、可测量、可回退** | 每个自适应决策都要能退化到保守默认值 |

---

## 1. 总体架构

```
源 PDF
  → [1] 版面解析    抽取字符级坐标 + 文本 + 图像位置
  → [2] 结构重建    阅读顺序重排 + 块类型判定 + 标题层级
  → [3] 译文注入    术语表 + 上下文 + 占位保护 + 并行翻译
  → [4] 排版重建    自适应字号行距 + 表格重排 + 规则引擎
  → [5] 渲染输出    HTML 中枢 → PDF / DOCX / 对照表
```

各模块之间全部通过 IR 传递，**禁止模块间直接传递纯文本**。

---

## 2. 中间表示（IR）

### 2.1 数据结构

```ts
interface BBox { x0: number; y0: number; x1: number; y1: number }  // 单位 pt

interface Span {
  text: string
  font: {
    family: string
    size: number          // pt
    weight: number        // 400 / 700
    italic: boolean
    color: string         // hex
  }
}

type BlockType =
  | 'heading' | 'paragraph' | 'listItem'
  | 'table' | 'figure' | 'caption'
  | 'footnote' | 'header' | 'footer'
  | 'code' | 'formula' | 'pageNumber'

interface Block {
  id: string
  type: BlockType
  bbox: BBox
  pageIndex: number
  readingOrder: number      // 全文档唯一序号
  level?: number            // heading 层级，1 起
  spans: Span[]
  sourceText: string
  targetText?: string
  // 排版控制位
  keepWithNext?: boolean    // 破题控制：不与下块分页
  noReflow?: boolean        // 该块不做自适应（如图片、公式）
  colSpan?: number          // 分栏归属，用于跨栏判断
  style?: BlockStyle        // 译文排版后的最终样式
}

interface Page {
  index: number
  width: number
  height: number
  margin: { top: number; right: number; bottom: number; left: number }
  blocks: Block[]
  images: ImageRef[]
}

interface Doc {
  pages: Page[]
  lang: string
  title?: string
  glossary: GlossaryEntry[]
}

interface BlockStyle {
  fontFamilyCJK: string
  fontFamilyLatin: string
  fontSize: number
  lineHeight: number
  align: 'left' | 'right' | 'center' | 'justify'
  spaceBefore: number
  spaceAfter: number
}
```

### 2.2 五个关键字段

| 字段 | 作用 | 丢失后果 |
| --- | --- | --- |
| `bbox` | 坐标定位 | 无法保留版式 |
| `type` | 语义类型 | 标题被当正文排版 |
| `level` | 层级关系 | 无法生成目录与样式继承 |
| `readingOrder` | 阅读顺序 | 双栏文档输出乱序 |
| `spans` | 样式片段 | 字体字号统一化，观感崩坏 |

---

## 3. 模块一：版面解析

### 3.1 文本型 PDF

- **必须抽取到字符级 bbox**，行级不够（无法做精确断行与混合样式处理）
- 推荐库：PyMuPDF(fitz)、pdfplumber、PDFBox
- 必提取项：字符 bbox、字体名、字号、颜色、加粗斜体、页面尺寸

**核心陷阱**：PDF 内部文本流顺序 ≠ 视觉阅读顺序。PDF 按内容生成顺序存储，双栏、带侧栏、带文本框的文档直接抽取会得到交错乱序文本。

**解法**：XY-cut 递归切分算法

```
function xyCut(blocks, page):
    // 1. 尝试沿水平方向找最大空白间隙 → 切分为上下两段
    // 2. 对每段尝试沿垂直方向找最大空白间隙 → 切分为左右两段
    // 3. 递归，直到块不可再分
    // 4. 按切分顺序输出 readingOrder
    // 注意：间隙阈值需按字符平均高度动态计算，不能写死
```

补充规则：

- 分栏数由垂直切分结果推断
- 跨栏块（如通栏标题）由 bbox 宽度 \> 单栏宽度判定
- 页眉页脚由纵向位置 + 跨页文本重复度判定

### 3.2 扫描件

- OCR 后必须接**版面分析**，不能只做文字识别
- 推荐：PaddleOCR PP-Structure、LayoutLMv3、DiT
- 输出需映射到同一套 Block 结构，使下游模块无感知

| 环节 | 方案 | 说明 |
| --- | --- | --- |
| 图像预处理 | 去倾斜、去噪、二值化 | 显著提升 OCR 准确率 |
| 文字识别 | PaddleOCR / Tesseract 5 | 中文优先 PaddleOCR |
| 版面分析 | PP-Structure / LayoutLMv3 | 输出区域类型与坐标 |
| 表格还原 | 线框检测（lattice） | 扫描件表格高优先 |

---

## 4. 模块二：结构重建

### 4.1 块类型判定

采用**规则打底 + 模型兜底**，冲突时规则优先（保证可解释与可调试）。

**规则层特征**

| 特征 | 用途 |
| --- | --- |
| 字号聚类 | 正文基准字号 = 出现频次最高的字号；大于基准的候选为标题 |
| 字体加粗 | 标题强信号 |
| 编号正则 | `第[一二三]章`、`1.`、`1.1.2`、`A.` 判定层级 |
| 纵向位置 | 页首 → 页眉/标题；页尾 → 页脚/脚注 |
| 行长比例 | 短行 + 居中 → 标题强信号 |
| 行间距 | 段前段后间距异常 → 标题或分隔 |

**标题层级**：字号降序聚类 + 编号正则双重验证，取一致结果；不一致时以编号为准。

**模型层**：LayoutLMv3 / DiT 微调做 block 分类，用于规则覆盖不到的复杂版面。

### 4.2 后处理

- **跨页段落合并**：页尾块以连字符结尾或首行缩进缺失 → 与上页末块合并
- **跨栏处理**：按 `colSpan` 字段归入正确栏位
- **表格识别**：有线条用 lattice 算法，无线条用文本对齐（stream）算法
- **图注判定**：位于图片下方、字号小于正文、以"图 X"或"Figure X"开头

---

## 5. 模块三：译文注入

### 5.1 翻译粒度

**以 Block 为粒度**，不要按行、按页或按字符数切分。

- 按行：破坏语义完整性
- 按页：上下文窗口过大，长文档质量下降
- 按 Block：粒度适中，且天然对齐排版单元

### 5.2 上下文与一致性

```
// 携带前序译文，保证连贯与代词指代正确
context = last N blocks 的 (sourceText, targetText) 对
```

- 建议 N = 1\~2，过多会拖慢且收益递减
- 并发翻译后按 `readingOrder` 回填，**不要按返回顺序拼接**

### 5.3 术语表

三阶段：

1. **术语抽取**：全文 TF-IDF + 领域词表 + 大写缩写识别
2. **建表**：`glossary: [{ source, target, doNotTranslate }]`
3. **双重约束**：
   - 翻译前注入 prompt 约束
   - 翻译后做强制替换校验（防止模型不遵守）

### 5.4 占位保护

以下元素翻译前替换为占位符，译后还原：

```
公式、代码、URL、邮箱、数字与单位、专有名词、文件路径、图表引用编号
```

用不可见或极特殊 token（如 `⟪PH_0⟫`）避免与正文冲突。

### 5.5 缓存

对 `sourceText` 做哈希缓存，重复段落（常见于合同、模板文档）直接复用译文。

---

## 6. 模块四：排版重建（核心）

### 6.1 三种成品模式

| 模式 | 几何信息 | 适用场景 | 成本 |
| --- | --- | --- | --- |
| 保留版式 | 完整使用 | 合同、论文、对外材料 | 高 |
| 中英对照 | 转表格承载 | 校对、学习 | 中 |
| 纯译文 | 丢弃，仅保留结构 | 内部阅读、二次编辑 | 低 |

### 6.2 自适应字号算法

```
function fitBlock(block, targetBox, baseStyle):
    size = baseStyle.fontSize
    lineHeight = baseStyle.lineHeight

    for i in 1..MAX_ITER:            // MAX_ITER = 3
        h = measureText(             // 真实渲染测量，非估算
              block.targetText,
              font = baseStyle.fontFamilyCJK,
              size = size,
              maxWidth = targetBox.width
        )
        total = h + spaceBefore + spaceAfter

        if abs(total - targetBox.height) <= TOL:   // TOL = 5%
            break

        if total > targetBox.height:
            // 先调行距，行距到极限再调字号
            if lineHeight > MIN_LINE_HEIGHT:
                lineHeight = max(lineHeight - LINE_STEP, MIN_LINE_HEIGHT)
            else:
                size = max(size - SIZE_STEP, MIN_SIZE)
                if size <= MIN_SIZE:
                    block.overflow = true          // 触底，标记溢出
                    break
        else:
            if lineHeight < MAX_LINE_HEIGHT:
                lineHeight = min(lineHeight + LINE_STEP, MAX_LINE_HEIGHT)
            else:
                size = min(size + SIZE_STEP, MAX_SIZE)

    block.style = { ...baseStyle, fontSize: size, lineHeight: lineHeight }
    return block.style
```

**参数建议**

| 参数 | 建议值 | 理由 |
| --- | --- | --- |
| `MIN_SIZE` | 8pt | 低于此值中文不可读 |
| `MAX_SIZE` | 14pt | 高于此值破坏版面统一 |
| `MIN_LINE_HEIGHT` | 1.15 | 过密影响阅读 |
| `MAX_LINE_HEIGHT` | 1.8 | 过疏占位过多 |
| `TOL` | 5% | 视觉不可分辨 |
| `MAX_ITER` | 3 | 3 轮未收敛说明该块不适合自适应 |

**触底策略**：不要无限缩小字号。触底后标记 `overflow`，由上层决定是让相邻块让位、还是允许轻微溢出。

### 6.3 表格排版

- 单元格内独立执行换行与行高计算
- 列宽按中英文加权：中文字符宽 ≈ 1.0 em，英文字符宽 ≈ 0.5 em，混合内容按字符类型累加
- 表格整体超宽时的降级顺序：缩小表内字号 → 压缩单元格内边距 → 允许横向溢出并标记

### 6.4 排版规则引擎

做成可配置规则集，支持开关与优先级。

| 规则 | 说明 |
| --- | --- |
| 中英混排间距 | 中文与拉丁字符/数字间插入 1/4 em 空格，英文单词间不插 |
| 标点全半角 | 中文语境用全角「，。；：」；英文内容保留半角 |
| 避头尾 | CJK 行首禁则：行首不能出现 `。，、）」》；行尾不能出现`（「\` |
| 孤行寡行 | 段落末行不独占页首，首行不独占页尾 |
| 破题控制 | 标题与紧跟的首段不分页（`keepWithNext`） |
| 字体分离 | 中文字体与西文字体分开指定，构建 fallback 链 |
| 数字与单位 | 数字与单位之间不换行 |

---

## 7. 模块五：渲染输出

### 7.1 推荐架构：HTML 为排版中枢

```
排版重建 → HTML + CSS（Paged Media）→ 各格式分发
                                      ├→ PDF（WeasyPrint / Paged.js + Playwright）
                                      ├→ DOCX（pandoc / 自研 OOXML 直写）
                                      └→ 对照表（HTML table 直出）
```

**为什么用 HTML 做中枢**：CSS 的排版表达能力（分页控制、避头尾、孤行寡行、字体 fallback）远超 DOCX API 与直接 PDF 绘制，且一份排版结果可分发多种格式。

### 7.2 各格式注意点

| 格式 | 关键注意事项 |
| --- | --- |
| PDF | 必须嵌入中文字体子集，否则跨设备显示异常 |
| DOCX | 精确定位困难，需用文本框或表格承载；样式尽量用 Word 内置样式名 |
| 对照表 | 用表格天然保证行对齐，禁用浮动定位 |

### 7.3 保留版式模式的坐标落地

- 绝对定位块：CSS `position: absolute` + `pt` 单位（1pt = 1/72 inch）
- 页面容器：`@page { size: A4; margin: ... }`
- 分页控制：`break-before` / `break-inside: avoid` / `orphans` / `widows`

---

## 8. 避坑清单

| # | 坑 | 后果 | 对策 |
| --- | --- | --- | --- |
| 1 | IR 用纯文本流 | 排版能力永久丢失 | 上 IR 前先定数据结构 |
| 2 | 信任 PDF 文本流顺序 | 双栏文档乱序 | XY-cut 重排 |
| 3 | 死守原坐标 | 挤压或空洞 | 自适应 + 视觉等价目标 |
| 4 | 用固定膨胀系数 | 文体一变就崩 | 真实渲染测量 |
| 5 | 逐句翻译 | 上下文断裂、指代错误 | Block 粒度 + 前序上下文 |
| 6 | 无术语表 | 同一术语多种译法 | 术语抽取 + 前后双重约束 |
| 7 | 扫描件跳过预处理 | OCR 错误放大进译文 | 去倾斜去噪必做 |
| 8 | 表格跨页 | 表格断裂、表头丢失 | 表头重复 + 断页保护 |

---

## 9. 评测与验证

### 9.1 自动指标

| 维度 | 指标 | 目标 |
| --- | --- | --- |
| 版面还原 | Block IoU | \> 0.85 |
| 阅读顺序 | Kendall's tau | \> 0.90 |
| 排版质量 | 溢出率 | \< 3% |
| 排版质量 | 字号越界率 | \< 1% |
| 排版质量 | 孤行寡行率 | \< 2% |
| 译文一致 | 术语一致率 | \> 98% |

### 9.2 人工抽查清单（每批抽 20 页）

- [ ] 双栏文档阅读顺序正确
- [ ] 标题层级与样式正确
- [ ] 跨页表格表头重复
- [ ] 图注与图片未分离
- [ ] 脚注编号连续且与正文对应
- [ ] 页眉页脚位置正确
- [ ] 中英混排间距一致
- [ ] 标点全半角无混用
- [ ] 术语全文一致
- [ ] 目录页码正确

---

## 10. 建议实施顺序

| 阶段 | 目标 | 交付物 |
| --- | --- | --- |
| Phase 1 | 打通最小闭环：文本型 PDF → 纯译文 DOCX | IR 定义 + 解析 + 翻译 + 简单排版 |
| Phase 2 | 补结构判定与规则引擎 | 标题层级、表格、中英混排规则 |
| Phase 3 | 做保留版式模式 | 自适应算法 + HTML 中枢 + PDF 输出 |
| Phase 4 | 扩展扫描件与对照模式 | OCR 版面分析 + 对照排版 |

**不要一开始做保留版式。** Phase 1 先把 IR 和纯译文跑通，因为 IR 是所有模式的地基；在 IR 不稳定的情况下做自适应排版，会浪费大量时间调试本不该存在的问题。

---

## 11. 技术选型参考

| 环节 | 首选 | 备选 |
| --- | --- | --- |
| PDF 解析 | PyMuPDF (fitz) | pdfplumber / PDFBox |
| OCR + 版面 | PaddleOCR PP-Structure | Tesseract 5 + LayoutLMv3 |
| 表格还原 | Camelot (lattice) | pdfplumber / Tabula |
| 排版中枢 | HTML + CSS Paged Media | — |
| HTML → PDF | WeasyPrint | Paged.js + Playwright |
| HTML → DOCX | pandoc | 自研 OOXML 直写 |
| 文本测量 | 浏览器 measure API | 自建字形宽度缓存表 |
