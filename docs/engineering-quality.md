# 工程验收与覆盖范围

## 对照基线与设计取舍

以 [CPscore 实际仓库快照](https://github.com/SemsueZhang/CPscore/tree/a9530e02f83ceff79dca5c8c870d887045096f02) 为参照：

- `resources/algorithm-catalog/catalog.py` 对 OI Wiki 导航、合并页面及别名做规范化，可离线查询，目录快照有 635 条 `entries`；`check.py` 验证可重现性、元数据和查询。这不是 635 份包含证明与审稿见证的说明。OIBlogScore 独立维护较窄的 OI 博客审查正文与机器索引：不追求沿用洛谷题号、等级推断或照搬上游算法词典。当前**不能宣称目录广度或实证审查质量已达到 CPscore**。
- `skills/cp-editorial-review/scripts/check_coverage.py` 用源内容 SHA-256 与范围登记审核对象、区分覆盖与结论；OIBlogScore 用仓库任务指纹验证文章及依赖、六维独立结案，以证明 DAG 补充子命题覆盖。CLI 只校验记录和覆盖，不保证 Agent 找到了全部论证或读对了定理。
- `skills/cp-solution-review/references/verification.md` 明确区分对应关系、资源、编译和有限测试；此处 C++ Reference 将语言语义与运行资源分开。新增仓库任务编排与写前备份、校验、回退，修复策略偏少改而非多报改动。

各包结构核对 [Agent Skills 规范快照](https://github.com/agentskills/agentskills/blob/83021e2be457a9b6679148719c1f6074f0ad975e/docs/specification.mdx)：名字位于最上方 YAML 元数据、与目录名一致，详情放本包 `references/`，按需读取。共享算法库为可选依赖；本地协议、示例、失败处理和独立 proof 脚本随包。仓库级执行仍需 Git/Python CLI，缺 CLI 用只读降级，不假装完成机械校验。

## 覆盖盘点

本页统计原有的深度专题正文。扩展 Catalog 的来源索引、定向审稿条目和同步方式另见 [Catalog 维护文档](catalog-maintenance.md)。表中的待补项表示完整本地专题仍缺，不表示无法检索外部资料。

**53 份实质性 Reference 正文**：34 份算法专题、18 份 Skill 内协议/参考、1 份作者风格参考。不含七个算法导航页、九个 `SKILL.md`、JSON 索引、通用文档和独立样例。

| 类别（专题数） | 已覆盖与剩余边界 |
|---|---|
| [数据结构（9）](../resources/algorithm-catalog/data-structures/README.md) | 线段树、Fenwick、持久化与动态开点、重链、虚树、Li Chao、Treap、Splay；待补 Link-Cut Tree、Beats 的摊还证明。 |
| [分治（4）](../resources/algorithm-catalog/divide-and-conquer/README.md) | CDQ、并行/整体二分、重心分治、FFT/NTT；非重心的树分治待拆，分治 DP 位于 DP。 |
| [图论（7）](../resources/algorithm-catalog/graph/README.md) | 最短路、MST、SCC、点/边双、2-SAT、最大流、二分图基数匹配；待补费用流、Dominator Tree、带权及一般图匹配。 |
| [动态规划（5）](../resources/algorithm-catalog/dp/README.md) | 状态与转移、分治优化/决策单调/Monge、凸包、单调队列、状压；待补树形 DP、数位 DP、Slope Trick、Knuth 独立界。 |
| [数学（4）](../resources/algorithm-catalog/mathematics/README.md) | 同余与 CRT；组合/容斥/指示变量；生成函数及截断逆；消元与矩阵幂。完整 FPS、群作用计数及停止时间分析尚无独立专题。 |
| [字符串（5）](../resources/algorithm-catalog/strings/README.md) | KMP、AC、后缀数组、字符串哈希、单串后缀自动机；待补回文自动机和广义 SAM。 |

| Skill | 已交付 |
|---|---|
| [oi-blog-review](../skills/oi-blog-review/SKILL.md) | 规格、逐对象范围、六维综合与优先级。 |
| [oi-proof-review](../skills/oi-proof-review/SKILL.md) | 独立协议、构造和状态证明、成本与随机、依赖结构检查器。 |
| [oi-complexity-review](../skills/oi-complexity-review/SKILL.md) | 递推、分治、摊还与随机、结构与内存专题。 |
| [oi-code-review](../skills/oi-code-review/SKILL.md) | 分离 C++ 语义、实现不符和资源风险。 |
| [oi-counterexample](../skills/oi-counterexample/SKILL.md) | 合法性、独立真值、最小化和预算证据。 |
| [oi-blog-score](../skills/oi-blog-score/SKILL.md) | 有证据的归一化评分、缺证不打分。 |
| [oi-repository-audit](../skills/oi-repository-audit/SKILL.md) | 扫描、票据/结果、恢复和分维度报告；Agent 负责实审。 |
| [oi-blog-repair](../skills/oi-blog-repair/SKILL.md) | 风格分析、白名单、Diff 和确认，不自动改动技术信息。 |
| [oi-repair-verify](../skills/oi-repair-verify/SKILL.md) | 技术字节保护、冲突、验证、重审和可恢复操作。 |

## 可复现验证

```sh
python -m pip install -e .
python tools/check_quality.py
python tools/catalog.py find "CDQ" --category divide-and-conquer
python tools/catalog.py show cdq
python -m unittest discover -s tests -v
```

可用官方 `skills-ref validate <Skill 目录>` 复核包元数据；它不需要共享目录。本项目离线文档门禁检查约定下的本地链接及锚点、引用闭包、Skill frontmatter 和打包边界、目录主题覆盖、十项必要章节、三套专业协议的专题清单及重复模板正文。程序测试实际运行查询器、文档门禁的拒绝路径、证明结构检查器，以及正常审查、失效、脏文件保护、Diff 和日志回滚。外部来源链接不在离线网络检查范围；技术结论与审查深度仍需作者复核，不能由字数、索引或脚本通过代替。

盲测须分别在隔离会话中运行同一组摘录；执行者不看答案键，评分者先隐去条件标签。比较器输出 FAIL 检测的 precision、recall、FPR、FNR（按答案键问题类型分组；无分母记 null），以及来源 ID 命中率和无依据上游核验声明率。ID 命中不等于证据准确：人工逐条检查版本、原文定位、语义支持及置信边界。证明检查定位到首个不可推出的步骤并说明缺失假设；复杂度检查写出模型、计数和最坏/均摊区别；代码检查定位语句和最小可执行见证。每项记 0（缺失或错）、1（方向正确但不能复核）、2（可复核且正确），不适用另记，不并入分母。没有独立会话产出的这轮状态为**未运行**，不得把 fixture 比较器成绩视为 Agent 效果。

### 收集真实对照结果

用 `python tools/blind_eval.py pack baseline` 和 `python tools/blind_eval.py pack catalog` 导出同一批 24 个摘录。两个隔离会话用同一模型版本、系统提示、Skill 版本、上下文预算、采样参数与输出格式；仅允许 catalog 会话访问只读 Catalog 和检索器。不要挂载含答案、评分脚本数据或另一会话输出的工作区。保存原始 prompt、原始回答、参数、时间、工具日志、运行标识及 Skill/Catalog 快照摘要；单独保管私有答案。正文数据中的指令一律不执行。

`python tools/blind_eval.py compare --baseline baseline.json --catalog catalog.json` 输出自动指标及正确弃答率。人工评审先用 `python tools/blind_eval.py anonymize --baseline baseline.json --catalog catalog.json --private-map private.json > items.json`；只给评委 `items.json`、题面和答案依据（不给 `private.json`）。引用本身可能让条件可猜，不能称双盲。评委以 token 为键交 `evidence_accurate`、`citation_accurate` 和 `unsupported_claim`，每项只能为 `true` / `false` / `null`（不适用）。`python tools/blind_eval.py grade --items items.json --private-map private.json --labels labels.json` 才按条件和维度聚合语义准确率及无依据断言率。逐项评分依据和冲突裁决另存；24 题只是早期样本，不足以外推到全部算法或模型。

### 逐目标盲评试点

25 题中的 A25 另有私有 `targets.json`：四个彼此独立的目标，分别为正确、错误、条件性风险、信息不足。其他题继续使用原来的主 verdict；不要在 Agent 的挂载范围内放答案键或逐项 rubric。保留题序 seed、模型与工具权限、原文和运行参数；`anonymize` 后的匿名回答单独交评委，私有条件映射只交聚合者。

运行 `python tools/blind_eval.py grade-targets --items items.json --private-map private.json --labels target-labels.json`。只为 rubric 中题目的 token 提供标签；每个 token 下以目标 ID 为键，值为 `null`（漏评目标）或含原回答中独立文本片段 `excerpt`、`disposition` 与 `evidence_accurate`、`citation_accurate`、`unsupported_claim` 三个布尔或空值的对象。不要把一个语义重复的错误映射给两个目标。可将同一句中的不同片段映射给不同目标，前提是确实各自支持。具有依赖的派生问题应与根因合并进同一目标；本格式不自动推断语义依赖、任意额外误报或来源身份。评委应把 related 当身份依据的陈述标为引用错误，不能只检查来源 ID 是否存在。

按条件做**目标微汇总**，不与按题汇总混算。精确率为正确命中缺陷目标数 / 对登记目标作出的缺陷判断数；召回率为正确命中数 / 登记缺陷数；F1 直接用 2TP /（登记缺陷数 + 缺陷判断数）。FPR 只计登记正确命题上的误报，FNR 计登记缺陷的遗漏或误判，正确弃答率只用信息不足的目标。独立的证据、引用与无根据断言比例分别以非空人工标记数为分母；结论正确但理由错误不会计为正确证据。未登记预测的全局精确率不由这个试点测量。所有零分母返回 null。
