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
