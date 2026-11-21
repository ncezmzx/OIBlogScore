# 2026-11-21 独立 Agent 对照盲测

本目录保存一次小规模 pilot 的原始回答、评分和聚合结果。它是本轮基础设施与真实模型运行的证据，不是普遍能力结论。没有人类盲评者参与；评分来自一个独立 Qoder 会话加主代理逐项复核。

## 结论摘要

- 25 道题中两组都答对 25/25：18 个 FAIL 全部检出，0 误报，2 个 NOT_CHECKED 都正确弃答。按 verdict 计算的 precision、recall、F1、balanced accuracy 均为 1.0，FPR/FNR 为 0。
- 两组逐项证据准确率均为 25/25；无依据断言均为 0/25。
- Catalog 组额外给出 18 条来源引用：独立评分员判 18/18 语义支持；主代理复核判 17/18（A08 引用的“二维计算几何基础”不支撑 C++ `int` 减法溢出这一具体结论，自动指标也把该来源标为不属于 `convex-hull-geometry` 的允许来源）。因此引用指标按更保守的 17/18 记录。
- A25 逐目标评分两组都是 3/4：`knuth-window` PASS、`resort` FAIL、`unknown-preprocess` NOT_CHECKED 正确；`product-type` 期望为 CONDITIONAL，两组都写成 FAIL（都假定操作数为 `int`，没有明确保留“类型/范围未给”的条件）。scoped precision/recall/F1 均为 0.5，false-negative rate 0.5，correct abstention 1.0。
- 该题集对当前模型已经饱和：两组没有 discordant verdict，任何“Catalog 提升检出率/证据质量”的结论都得不到支持。可观察到的 Catalog 收益是来源可追溯性，而不是判定收益；且其中一条引用不支撑具体实现结论。
- 18/18 检出率的 95% Wilson 下界约 0.824；25/25 verdict 准确率的 95% Wilson 下界约 0.867。样本小且两端触顶，不能外推到其他模型、题目或算法。

## 条件

- **Baseline**：只有题面与指令；没有 OIBlogScore、Catalog、项目 Skills、仓库或外部检索条件。
- **Catalog**：同一批题面与相同指令骨架，额外得到一份净化的只读 OIBlogScore checkout（`tools/`、`resources/algorithm-catalog/`、`skills/`、`docs/`）；不含 `tests/`、答案键或 Git 元数据。允许运行 `python tools/catalog.py` 和阅读项目 Skills。
- 两个条件按 seed 7 生成同一题序；输出 schema 相同。

## 模型与运行记录

- **主对照**：两个独立的 Qoder Desktop 对话，均从本会话创建，继承同一保存模型与权限模式。创建接口没有返回具体 modelKey；应用默认模型是 Auto，无法核验后端模型版本或每次请求的实际路由。这是本 pilot 的主要方法学限制。
- **次要单组观察**：另有一次 Catalog 子代理运行（同样 25 行、同一 verdict 分布）。该次结果没有记录具体模型；失败的另一条 Baseline 子代理尝试曾在 API 错误中显示 DeepSeek V4.1，但不能据此推定这次 Catalog 运行使用同一模型。它没有对应的 Baseline 运行，因此不计入对照指标，只保存在 `catalog-answers-subagent-secondary.json` 供透明性检查。
- 会话创建于 2026-11-21T13:29:07Z 左右。Catalog 答案文件约 13:40Z 落盘，Baseline 约 13:44Z，独立评分标签约 14:05Z；宿主消息时间戳不可靠，以上是文件时间和轮次记录。
- 失败与重试：Baseline 子代理第一次触发输出上限，第二次遇到平台 `reasoning_effort` 错误；Baseline Qoder 会话首轮读取后失败，改为极小批次续跑成功。Catalog Qoder 会话一次完成。评分会话首轮读取后失败，改为 5 条一批续跑成功。失败轮次没有产生答案，未计入结果。
- Catalog 会话记录约 39 次工具调用（含一次失败 Bash）；Baseline 最终轮 26 次 Bash；评分最终轮 13 次 Bash。宿主没有向本任务暴露 token 计数。

## 隔离与残余风险

- 评测前把 `tests/fixtures/blind/key.json` 和 `targets.json` 移出工作区到随机临时目录；两个条件结束时才恢复。两个 bundle 都不含答案键；`prepare` 会拒绝包含 key/targets 的目录。
- Baseline bundle 只有 `cases.json`、`instruction.txt`、`manifest.json`；Catalog bundle 额外有净化 checkout。提示明确禁止读取 bundle 之外的文件、原始工作区、测试、答案键和网络。
- 残余风险：两个 Qoder 会话仍共享宿主工作区和文件系统；如果模型违反提示，技术上可以读取 bundle 之外的内容。没有观察到越权读取，Catalog 的满分也可由 Catalog 的审查笔记直接解释，但本 pilot 无法像容器/独立用户那样证明绝对隔离。评分会话知道每个 token 的 source_ids，可能据此猜条件；它被要求不推断条件。
- 没有人类盲评。独立评分会话不生成答案，但仍是 AI 评分；主代理复核发现并保留了一处与评分员不同的引用判断。任何“人类已盲评”的说法都不成立。

## 指标

自动指标（`compare.json`）：

| 指标 | Baseline | Catalog |
|---|---:|---:|
| Verdict correct | 25/25 | 25/25 |
| Detection (FAIL cases) | 18/18 = 1.0 | 18/18 = 1.0 |
| False positives | 0 | 0 |
| FPR / FNR | 0 / 0 | 0 / 0 |
| Defect precision / recall / F1 | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 |
| Balanced accuracy | 1.0 | 1.0 |
| Correct abstention | 2/2 = 1.0 | 2/2 = 1.0 |
| Citation ID match | N/A | 15/16 = 0.9375 |
| Unsupported upstream-verification claims | 0/25 | 0/25 |

语义指标（独立评分员 `grade-grader.json`，主代理复核 `grade-main-review.json`）：

| 指标 | Baseline | Catalog |
|---|---:|---:|
| Evidence accurate | 25/25 = 1.0 | 25/25 = 1.0 |
| Citation accurate | N/A (无引用) | 独立 18/18；主代理复核 17/18 |
| Unsupported claim | 0/25 | 0/25 |

逐维度 verdict 计数：algorithm 9、proof 7、complexity 6、code 3；两条件在这些维度上的 verdict 都正确。

A25 逐目标（`target-grade-grader.json`；主代理复核的目标正确性一致）：

| 指标 | Baseline | Catalog |
|---|---:|---:|
| Target accuracy | 3/4 = 0.75 | 3/4 = 0.75 |
| Scoped precision / recall / F1 | 0.5 / 0.5 / 0.5 | 0.5 / 0.5 / 0.5 |
| Scoped FNR / FPR | 0.5 / 0 | 0.5 / 0 |
| Correct abstention | 1/1 = 1.0 | 1/1 = 1.0 |
| Target evidence accurate | 4/4 | 4/4 |
| Target citation accurate | N/A | 1/4 (仅 `knuth-window` 有直接支撑) |
| Target unsupported claim | 0/4 | 0/4 |

`product-type` 两组的 disposition 都是 FAIL，而期望是 CONDITIONAL：答案指出了类型问题，但没有保留“操作数类型/范围未给，不能断言所有实现都溢出”的限制。这是两组共享的精度缺口，不是 Catalog 带来的收益。

## 未测量项

- **Severity accuracy**：pilot 的输出 schema 没有 severity 字段，答案键也没有逐题严重性标注；不伪造该指标。
- **Duplicate issue rate**：每题只有一个 verdict/reason，没有逐 issue 结构；A25 的重复片段由 `grade-targets` 拒绝，但不足以计算全局重复率。
- **Multi-defect coverage**：仅在 A25 的四个目标上测得 3/4；不是全题集的多缺陷覆盖。
- **人工盲评**：没有人类评审资源；独立 AI 评分不能替代。

## 文件

- [baseline-answers.json](baseline-answers.json) · [catalog-answers.json](catalog-answers.json)
- [catalog-answers-subagent-secondary.json](catalog-answers-subagent-secondary.json)（不同 harness 的次要单组观察，不与主对照合并）
- [compare.json](compare.json)（自动 verdict 指标）
- [grade-grader.json](grade-grader.json) · [grade-main-review.json](grade-main-review.json)
- [target-grade-grader.json](target-grade-grader.json) · [target-grade-main-review.json](target-grade-main-review.json)
- [grader-labels.json](grader-labels.json) · [grader-target-labels.json](grader-target-labels.json)
- [main-review-labels.json](main-review-labels.json) · [main-review-target-labels.json](main-review-target-labels.json)
- [anonymized-items.json](anonymized-items.json)（无 condition 标签；私有映射未发布）
- [manifest-baseline.json](manifest-baseline.json) · [manifest-catalog.json](manifest-catalog.json)
- [prepare-baseline.json](prepare-baseline.json) · [prepare-catalog.json](prepare-catalog.json)
- [instruction-baseline.txt](instruction-baseline.txt) · [instruction-catalog.txt](instruction-catalog.txt) · [cases.json](cases.json)

私有条件映射 `private-map.json` 没有发布；它只用于把 token 标签聚合到两个条件。Condition-labeled 原始回答仍在两个 answers 文件中。

## 复现

```sh
python tools/blind_eval.py prepare baseline /tmp/blind-baseline --seed 7
python tools/blind_eval.py prepare catalog /tmp/blind-catalog --seed 7
python tools/blind_eval.py compare --baseline baseline-answers.json --catalog catalog-answers.json
python tools/blind_eval.py anonymize --baseline baseline-answers.json --catalog catalog-answers.json --private-map private-map.json > items.json
python tools/blind_eval.py grade --items items.json --private-map private-map.json --labels grader-labels.json
python tools/blind_eval.py grade-targets --items items.json --private-map private-map.json --labels grader-target-labels.json
```

`prepare` 会在 bundle manifest 中记录 cases/instruction/Catalog/工具摘要；bundle 内含 `cases.json`、`instruction.txt` 和净化 `repo/`（Catalog 条件）。`/tmp` 示例在 Windows 下应换成原生临时目录。
