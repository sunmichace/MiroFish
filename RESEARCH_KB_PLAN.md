# 研报观点知识库方案（基于 MiroFish 改造）

## 1. 目标

面向 `/hdd/project/Investment/32｜通用爬虫/32.1｜wisburg智堡/omni_exports/ai_article` 目录中的 12,066 篇研究报告 Markdown，建设一个可检索、可追溯、可做时间对比的知识库。

知识库核心内容分为四类：

- 事件 `Event`
- 数据 `Data / Observation`
- 观点 `Viewpoint`
- 对象 `Object`

目标查询能力：

1. 给每篇报告提取作者、机构、发布时间、核心事件、关键观点、关键数据。
2. 能按作者或机构检索历史观点。
3. 能围绕某个事件查看不同人的观点分布与时间变化。
4. 能把观点和证据、数据、原文出处关联起来，保证可回溯。

## 2. 数据源现状

### 2.1 基本情况

- 文件数量：12,066 篇 `.md`
- 文件格式：YAML front matter + 标准化正文
- 语言：中文为主，夹杂英文金融术语和 ticker
- 文件大小：900 字节 ~ 22KB，典型 5-10KB
- 时间跨度：2025-09 ~ 2026-01

### 2.2 Front Matter 字段（已清洗后）

所有文件均有 YAML front matter，清洗后包含：

| 字段 | 说明 | 覆盖率 |
|------|------|--------|
| `title` | 真正的报告标题（已从标签拼接中提取） | 100% |
| `original_title` | 原始标签拼接式标题 | 100% |
| `published` | 平台发布时间（ISO 8601） | 100% |
| `source_date` | 原始报告发布日期（从 `<source>` 标签提取） | 65% |
| `institution` | 发布机构中文名 | 100%（23 篇为话题标签，无法恢复） |
| `source_institution` | 机构英文缩写（GS/JPM/MS 等） | 88% |
| `author` | 作者人名 | 87%（752 篇为机构名已清除，150 篇原始为空） |
| `source` | wisburg 内部 ID | 100% |
| `kind` | 固定值 28（REPORT_FEED） | 100% |
| `detail_type` | 固定值 Report | 100% |
| `tags` | 主题标签列表（已从标题中补充） | 84%（原始 1,875 篇无 tags，现已补充） |
| `vip_visibility` | 可见性等级（1/3） | 100% |

### 2.3 正文结构

正文不是原始全文，而是 AI 生成的结构化摘要。所有文件以 `## Summary` 开头，包含以下标准化章节：

| 章节 | 覆盖率 | 说明 |
|------|--------|------|
| `### 主要观点` | 99.9% | 编号列表，每条含加粗核心论点 + 展开论述 |
| `### 事实依据` | 99.9% | 编号列表，支撑观点的事实和数据 |
| `### 陈述总结` | 99.9% | 1-3 段总结性文字 |
| `### 关键数据` | 99.5% | 带加粗标签的数据点列表 |
| `### 专业名词及重要事件` | 99.9% | 术语解释列表 |
| `### 推荐资产标的` | 59.5% | 交易建议（建仓/目标/止损） |

此外：

- 92% 的文件包含 `<source>` 标签（含机构英文缩写、作者名、发布日期）
- 约 43% 的文件包含图片链接（指向 wisburg CDN）

### 2.4 对证据层的影响

由于正文是摘要而非全文，"证据回溯"的精度受限：

- `quote_span` 只能指向摘要文本，不是原始报告原文
- 但摘要质量高、结构标准化，足以支撑观点和数据的提取与引用
- 建议在 Viewpoint/Observation 中保留 `source_quote` 字段，标注"引自摘要"

### 2.5 机构分布（Top 10）

| 机构 | 篇数 |
|------|------|
| 高盛 | 1,671 |
| 摩根大通 | 1,639 |
| 摩根士丹利 | 1,490 |
| 美银美林 | 1,339 |
| 瑞银 | 1,067 |
| 花旗 | 933 |
| 德意志银行 | 854 |
| 汇丰 | 791 |
| 巴克莱 | 712 |
| 野村 | 648 |

## 3. 对当前项目的判断

基于对 MiroFish 代码的逐文件审读，精确评估如下：

### 3.1 可直接复用

| 模块 | 文件 | 说明 |
|------|------|------|
| Zep 客户端封装 | `graph_builder.py` | 图谱创建、批量入库、轮询、删除 |
| 分页检索 | `zep_paging.py` | 节点/边分页获取 + 重试 |
| 实体过滤 | `zep_entity_reader.py` | 按类型过滤、上下文增强 |
| 多策略检索 | `zep_tools.py` | `insight_forge`（子查询分解）、`panorama_search`（活跃/历史事实）、`quick_search` |
| 配置基础设施 | `config.py` | 环境变量、LLM/Zep 配置 |
| 编码回退 | `file_parser.py` | 多编码尝试读取 |
| 任务管理 | `models/task.py` | 异步任务状态追踪 |

### 3.2 可部分复用（需改造）

| 模块 | 文件 | 可用部分 | 需改造 |
|------|------|---------|--------|
| 文本分块 | `text_processor.py` | 基础分块框架 | 改为 section-aware 分块（按 `###` 章节切分） |
| 报告 Agent | `report_agent.py` | ReAct 循环、分段生成、进度追踪 | 替换所有 prompt（从仿真叙事改为研报分析） |
| 图谱数据导出 | `graph_builder.py:get_graph_data()` | 节点/边序列化含时间字段 | 增加 provenance 字段 |

### 3.3 需完全替换

| 模块 | 文件 | 原因 |
|------|------|------|
| 本体生成 | `ontology_generator.py` | 当前 prompt 锁定"社媒仿真"，强制 10 entity types + Person/Organization 兜底，不适合研报 KB |
| 仿真系统 | `simulation_*.py`, `oasis_*.py` | 与研报 KB 无关 |
| 图谱记忆更新 | `zep_graph_memory_updater.py` | 面向仿真 action 流，不适合文档入库 |

### 3.4 需新增

- Front matter 解析器（已有清洗脚本 `scripts/fix_research_md.py`）
- Section-aware 分块器（按 `###` 章节切分）
- 固定 schema 的 LLM 抽取器（事件/对象/观点/数据）
- 结构化存储层（SQLite 或 PostgreSQL）
- 归一化模块（事件/作者/机构消歧）
- 研报场景查询 API

## 4. 关键技术约束：Zep 限制

当前 MiroFish 使用 Zep Cloud 作为图谱后端。Zep 有以下硬限制：

| 约束 | 限制值 | 影响 |
|------|--------|------|
| 自定义 entity types | 最多 10 个 | 方案需要 6 种节点，勉强够用 |
| 自定义 edge types | 最多 10 个 | 方案设计了 15 种边，**超限** |
| 节点分页上限 | 代码硬编码 2,000 | 12,000 篇文档产生的节点量可能远超此限 |
| Episode 入库 | 每批 3 个 chunk + 1 秒间隔 | 12,000 篇 × ~10 chunks ≈ 40,000 批 ≈ 11+ 小时 |
| 本体属性类型 | 仅 `Optional[EntityText]` / `Optional[str]` | 无法表达数值、日期等强类型 |

### 4.1 边关系压缩方案（适配 Zep 10 边限制）

将原设计的 15 种边压缩为 10 种：

| 边类型 | 说明 | 合并策略 |
|--------|------|---------|
| `AUTHORED_BY` | Document → Object(Person) | 保留 |
| `PUBLISHED_BY` | Document → Object(Institution) | 保留 |
| `HAS_CONTENT` | Document → Viewpoint / Observation | 合并原 `HAS_VIEWPOINT` + `HAS_OBSERVATION` |
| `BY_AUTHOR` | Viewpoint → Object | 保留 |
| `ABOUT` | Viewpoint/Observation → Event/Object | 合并原 4 种 ABOUT 边，用属性区分 |
| `SUPPORTED_BY` | Viewpoint → Observation | 保留 |
| `OF_SERIES` | Observation → DataSeries | 保留 |
| `INVOLVES` | Event → Object | 保留 |
| `MENTIONS` | Document → Event/Object | 合并原 2 种 MENTIONS |
| `EVIDENCED_BY` | Viewpoint/Observation → EvidenceChunk | 合并原 2 种 SUPPORTS |

### 4.2 备选方案：引入本地图数据库

如果 POC 阶段验证 Zep 无法承载 12,000 篇文档的规模，建议：

- 主存储改用 Neo4j Community Edition 或 PostgreSQL + Apache AGE
- Zep 降级为可选的语义检索增强层
- 好处：无 entity/edge type 数量限制，支持 Cypher 查询，本地部署无 API 成本

## 5. 总体架构

采用五层结构：

### 5.1 文档层 `Document`

每篇 md 作为一篇独立文档，字段直接从清洗后的 front matter 解析：

- `doc_id`（使用 `source` 字段，即 wisburg ID）
- `title`（清洗后的真正标题）
- `original_title`（原始标签拼接式标题，用于全文检索）
- `published_at`（`published` 字段）
- `source_date`（原始报告发布日期，65% 覆盖）
- `author`（作者人名，87% 覆盖）
- `institution`（机构中文名）
- `source_institution`（机构英文缩写，88% 覆盖）
- `vip_visibility`
- `tags`（主题标签列表）
- `file_path`

这层完全不依赖 LLM，直接解析 front matter。

### 5.2 证据层 `EvidenceChunk`

由于正文是标准化摘要，建议按 `###` 章节切分而非固定字符数：

- `chunk_id`
- `doc_id`
- `chunk_index`
- `text`
- `section`（`主要观点` / `事实依据` / `关键数据` / `陈述总结` / `推荐资产标的` / `专业名词及重要事件`）
- `char_start`
- `char_end`

作用：

- 支持 GraphRAG
- 支持精确引用（到章节级别）
- 支持回溯观点和数据来自哪个章节

### 5.3 语义图层 `Graph`

图谱承载以下核心节点（6 种，在 Zep 10 个限制内）：

- `Document`
- `Object`（含子类型：Person / Institution / Company / CentralBank / Asset / CurrencyPair / Region）
- `Event`（含子类型：PolicyEvent / MacroEvent / MarketEvent / EarningsEvent）
- `Viewpoint`
- `Observation`
- `DataSeries`

边关系 10 种（见 4.1 节压缩方案）。

### 5.4 时间层 `Temporal`

所有可变知识都尽量带时间字段：

- `published_at`（平台发布时间）
- `source_date`（原始报告日期）
- `event_time`
- `observation_time` / `as_of_date`
- `valid_from` / `valid_to`
- `created_at`

### 5.5 数值层 `Structured Store`

真正需要做筛选、排序、聚合的数据放结构化表（SQLite / PostgreSQL），不强迫全部走图。

适合放表里的内容：

- 数值 `value_num`
- 文本值 `value_text`
- 单位 `unit`
- 时间 `as_of_date`
- 调查占比
- 估算值
- 阈值
- 方法说明 `method`

## 6. 固定知识 Schema

### 6.1 Document

表示一篇研究报告。

关键字段：

- `doc_id`（= wisburg source ID）
- `title`
- `original_title`
- `published_at`
- `source_date`
- `author_name`
- `institution_name`
- `source_institution`
- `detail_type`
- `vip_visibility`
- `tags`
- `file_path`

### 6.2 Object

统一表示"对象"。建议子类型：

- `Person`
- `Institution`
- `Company`
- `Government`
- `CentralBank`
- `Asset`
- `Region`
- `CurrencyPair`

关键字段：

- `object_id`
- `name`
- `object_type`
- `aliases`
- `country`
- `description`

### 6.3 Event

表示一个可被多人讨论、并且可做时间跟踪的事件。

建议子类型：

- `PolicyEvent`
- `MacroEvent`
- `MarketEvent`
- `EarningsEvent`
- `InterventionEvent`

关键字段：

- `event_id`
- `canonical_name`
- `event_type`
- `start_time`
- `end_time`
- `status`
- `aliases`
- `summary`

### 6.4 Viewpoint

表示"某人/某机构对某事件/对象的一个观点"。

关键字段：

- `viewpoint_id`
- `summary`
- `stance`
- `polarity`
- `confidence`
- `published_at`
- `source_doc_id`
- `author_object_id`
- `target_event_id`
- `source_quote`（标注"引自摘要"）
- `source_section`（来自哪个章节：主要观点 / 陈述总结）

其中：

- `stance` 适合表达支持/反对/谨慎/看多/看空/中性等
- `summary` 是对观点的一句结构化摘要
- `source_quote` 用于回溯摘要原文（非原始报告全文）

### 6.5 Observation

表示一条"结构化数据事实"，是本方案中最关键的数据节点。

不要把它简单理解为时序点。它可以表示：

- 等级
- 阈值
- 调查结果
- 估算值
- 存量值
- 规则/弹性估计

关键字段建议：

- `observation_id`
- `observation_type`
- `metric_name`
- `subject`
- `value_num`
- `value_text`
- `unit`
- `as_of_date`
- `method`
- `qualifier`
- `source_doc_id`
- `source_quote`
- `source_section`（通常来自 `关键数据` 或 `事实依据` 章节）

建议的 `observation_type`：

- `level`
- `threshold`
- `estimate`
- `survey_stat`
- `stock`
- `flow`
- `ratio`
- `scenario_rule`

### 6.6 DataSeries

表示真正可长期观测的序列概念。

例如：

- `USDJPY`
- `Japan_FX_Reserves`
- `BOJ_Policy_Rate`

关键字段：

- `series_id`
- `name`
- `frequency`
- `unit`
- `subject`
- `description`

## 7. 边关系设计

核心边 10 种（已适配 Zep 限制）：

- `Document AUTHORED_BY Object(Person)`
- `Document PUBLISHED_BY Object(Institution)`
- `Document HAS_CONTENT Viewpoint / Observation`
- `Viewpoint BY_AUTHOR Object`
- `Viewpoint / Observation ABOUT Event / Object`（用属性 `target_type` 区分）
- `Viewpoint SUPPORTED_BY Observation`
- `Observation OF_SERIES DataSeries`
- `Event INVOLVES Object`
- `Document MENTIONS Event / Object`（用属性 `target_type` 区分）
- `Viewpoint / Observation EVIDENCED_BY EvidenceChunk`

这样能够支持：

- 从人找观点
- 从事件找多方观点
- 从观点追证据和数据
- 从数据回溯具体文档和作者

## 8. "关键数据"怎么处理

示例（来自实际文件 `### 关键数据` 章节）：

- 干预警报级别：4级（共5级）
- 美元/日元关键水平：161.95
- 每100亿美元干预 -> 汇率下降 1.8% / 2.2%
- 干预资金规模：1870亿美元
- 42.5% 受访者预计在 162 左右发生干预
- 外汇储备总额：1.2 万亿美元

这些都不应强行压成普通时序点，而应入库为 `Observation`。

建议拆法：

### 8.1 等级型

- `metric_name = intervention_alert_level`
- `observation_type = level`
- `value_num = 4`
- `qualifier = 5级体系`

### 8.2 阈值型

- `metric_name = usd_jpy_key_level`
- `observation_type = threshold`
- `value_num = 161.95`

### 8.3 规则/弹性型

- `metric_name = usd_jpy_intervention_effect`
- `observation_type = scenario_rule`
- `value_text = 每100亿美元干预 -> -1.8%`
- `method = 日度数据`

再建第二条：

- `value_text = 每100亿美元干预 -> -2.2%`
- `method = 日内高频数据`

### 8.4 存量型

- `metric_name = intervention_capacity_usd`
- `observation_type = stock`
- `value_num = 1870`
- `unit = 亿美元`

### 8.5 调查统计型

- `metric_name = expected_intervention_level_share`
- `observation_type = survey_stat`
- `value_num = 42.5`
- `unit = percent`
- `qualifier = 预计162左右发生干预`

### 8.6 时间点存量

- `metric_name = fx_reserve_total`
- `observation_type = stock`
- `value_num = 1.2`
- `unit = trillion_usd`
- `as_of_date = 2025-12-31`

## 9. 入库流程

建议分为 6 步。

### 第 1 步：解析 Front Matter + Section 切分

直接从清洗后的 front matter 解析 Document 元数据（不需要 LLM）：

- `title`、`published`、`source_date`、`institution`、`author`、`tags` 等
- 同时按 `###` 章节切分正文，生成 EvidenceChunk

已有工具：`scripts/fix_research_md.py`（数据清洗已完成）

### 第 2 步：事件 / 对象 / 观点 / 数据抽取

针对每篇文档的特定章节，用固定 prompt + 固定输出 schema 抽取：

| 抽取目标 | 输入章节 | 输出 |
|---------|---------|------|
| Event | 主要观点 + 专业名词及重要事件 | `events.json` |
| Object | 主要观点 + 推荐资产标的 | `objects.json` |
| Viewpoint | 主要观点 + 陈述总结 | `viewpoints.json` |
| Observation | 关键数据 + 事实依据 | `observations.json` |

成本估算（12,066 篇）：

- 输入：每篇 ~4K tokens（摘要文本）
- 输出：每篇 ~2K tokens（结构化 JSON）
- 总计：~72M tokens
- 按 GPT-4o-mini 价格约 $10-15，按 Claude Haiku 约 $18-25

### 第 3 步：归一化与去重

关键工作：

- 同一作者名归一化（front matter `author` 已是较干净的人名）
- 同一机构名归一化（`institution` + `source_institution` 双字段可交叉验证）
- 同一事件别名归一化
- 同一货币对、同一指标归一化

例如：

- "日元购买干预" / "日元干预" / "外汇干预" → 同一 canonical event

阶段一建议用简单规则（字符串相似度 + 别名表），阶段三再引入 LLM 辅助消歧。

### 第 4 步：写入图谱与结构化表

建议双写：

- 写入图谱（Zep 或 Neo4j）：语义关系
- 写入结构化表（SQLite / PostgreSQL）：Document、Observation 的数值/时间/筛选字段

### 第 5 步：建立检索层

检索分两类：

- 图检索：查关系、查主题、查跨文档连接（复用 `zep_tools.py` 的 `insight_forge` / `panorama_search`）
- 结构化检索：查数值、查时间、查作者、查事件（SQL 查询）

### 第 6 步：问答与报告

复用 `report_agent.py` 的 ReAct 框架，替换 prompt 为研报分析场景：

- 工具集：图检索 + SQL 查询 + 文档原文读取
- 输出：结构化分析报告

## 10. 查询能力设计

### 10.1 查询作者历史观点

查询意图：

- `Goto 历史上关于日元干预的观点有哪些？`

底层路径：

- `Person -> Viewpoint -> Document`
- 再按 `published_at` 排序

### 10.2 查询事件上的多方观点

查询意图：

- `围绕日元购买干预，各家机构观点分别是什么？`

底层路径：

- `Event -> Viewpoint -> Person / Institution`

### 10.3 查询观点变化

查询意图：

- `某作者对日本央行干预的判断是如何变化的？`

底层路径：

- 固定 `author + event`
- 拉出所有 `Viewpoint`
- 按时间排序
- 比较 `summary / stance / supporting observations`

### 10.4 查询某观点引用的数据

查询意图：

- `这条观点背后的关键数据有哪些？`

底层路径：

- `Viewpoint -> Observation -> Document / EvidenceChunk`

## 11. 分阶段实施建议

### 阶段一：最小可用版本（POC，50-100 篇）

目标：

- 验证 Zep 单图谱容量和抽取质量
- 解析 front matter → 生成 `Document`
- 从 `<source>` 标签 + front matter 生成 `Person / Institution`
- 用固定 prompt 从 `主要观点` 章节抽取 `Event / Viewpoint`
- 支持按作者查观点

关键验证点：

- Zep 能否承载 50 篇文档产生的节点/边量？
- 抽取的 Event/Viewpoint 质量是否满足查询需求？
- 如果 Zep 不够 → 阶段二直接切换到 Neo4j

### 阶段二：加入数据层 + 结构化存储

目标：

- 从 `关键数据` / `事实依据` 章节抽取 `Observation`
- 建立 SQLite/PostgreSQL 结构化表
- 支持观点 → 数据 → 原文回溯
- 扩展到全量 12,066 篇

### 阶段三：加入时间演化能力

目标：

- 事件归一化（LLM 辅助消歧）
- 观点时间轴
- 事件上的多方观点变化分析

### 阶段四：加入高质量问答与报告

目标：

- 基于 GraphRAG + Structured Query 的混合问答
- 自动生成"作者观点演进报告"
- 自动生成"事件多方观点对比报告"
- 改造前端为研报知识库 UI

## 12. 最终结论

这个知识库方案最合适的形态，不是纯文档 RAG，也不是纯时序图节点 RAG，而是：

**固定 schema 的研究报告知识图谱 + 结构化 Observation 数据层 + 证据级文档分块检索。**

一句话总结：

- `事件 / 对象 / 观点` 主要放图谱
- `关键数据` 主要放 Observation + 结构化表
- `原文证据` 保留在 chunk 层（注意：是摘要级证据，非原始全文）
- `问答和总结` 用 GraphRAG + ReportAgent 完成

核心风险：Zep 的 10 entity/edge type 限制和节点容量上限。建议阶段一用 50-100 篇做 POC 验证，如不满足则尽早切换到本地图数据库。
