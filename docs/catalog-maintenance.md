# Catalog 维护、验收和适用边界

## 可重现范围

运行 `python tools/catalog.py stats` 获取当前来源、审稿状态和归并统计。数据契约见 [Catalog Schema](catalog-schema.md)。目录保留原有 34 篇 Markdown 和 6 篇定向分析；新笔记扩展前提、不变量、推导、复杂度和见证。`needs-review` 明确标记 Knuth 的最优决策单调性定理及一般图匹配的缩花完备性尚未在本项目全证；其它推导只在其声明范围内使用。

## 归并流程

`python tools/catalog.py candidates` 列出固定基线仍待核对的来源。读来源的实际模型、状态及复杂度后，与现有规范 ID 对照；不要把一个页面作为多个条目的身份声明。已确认或有弱关联的条目用 `candidates --all` 查看，明确区分 `related` 和 `exact`。不要把旧的一般关联迁移为已人工验证的等价。

博客编目优先记录可追溯的作者与原地址，再写一个具体审稿问题。若只核对了公开二级目录，把它记作二级来源，不把项目补充的问题描述成博客已证明的结论。正文核对、数学复核是后续步骤。

## 同步：只生成候选，不修改工作树

```sh
# 从 sources/providers.json 取固定 SHA；clone 后确保该提交在本地。
python tools/sync_catalog.py cp-algorithms /path/to/cp-algorithms-checkout
python tools/sync_catalog.py cp-algorithms /path/to/cp-algorithms-checkout --output /tmp/cp-catalog-candidate
```

1. 支持 `oi-wiki`、`cp-algorithms`、`usaco-guide`、`library-checker`、`kactl`。工具读 Git 对象，不读上游工作树中的本地改动；不联网，不运行上游脚本。相同固定版本和政策生成相同字节。`--output` 只能是不存在的目录，不能重写旧快照。不要把输出目录指向现有 `sources/`。
2. 更新时用 `--providers` 提供另存的候选配置（修订 commit、日期及固定许可 URL）。脚本报告新增、删除、内容与元数据变化。许可声明字节变化时拒绝；不能经候选 `--providers` 更换许可摘要。先走独立人工许可审查及政策变更。cp-algorithms 每次换 pin 都需要显式传入 `--approvals`，不论是否存在内容变化；有变化时对照提交逐篇核对许可、署名与第三方材料再生成新摘要。不能盲批新哈希。
3. 审查 staging 与 `sources/` 的差异后手动应用经批准的来源记录和原样文件；更新 ID 重命名的跨源关系，按变更相应移除旧归档。`knowledge/`、各算法正文和既有审稿协议从不由同步写入。
4. `python tools/check_quality.py` 校验许可、快照、链接形状、收录权限、内容完整性、来源追溯、别名和 Skill 检索契约。网络按需运行 `python tools/check_source_links.py --provider cp-algorithms --limit 0`，404/410 与超时、403、429、沙箱无网络分开，后者不能判定为死链接。离线 CI 不依赖远端网站响应。

## 审查和 Golden 语义

`tests/fixtures/catalog/golden.json` 保存可供 Agent 检查的对照：真实资料短句或博客贡献、合成正反主张、来源 ID、预期审查证据；`lazy.cpp` 是自写的有意错误对照。测试实际跑检索、出处和小型独立 oracle，并在可用时编译运行两种 C++ 实现；不调用 LLM，也不声称通过结构门禁就验证了上游定理。要测 Agent 能力，给 Agent 不包含 `expected` 的两侧主张与固定资料，要求分维度提供证据，再由人工对照期望；不要把期望预先暴露给待测 Agent。

## Agent 对照盲测

```sh
python tools/blind_eval.py pack baseline > /tmp/baseline-cases.json
python tools/blind_eval.py pack catalog > /tmp/catalog-cases.json
python tools/blind_eval.py compare --baseline /tmp/baseline-answers.json --catalog /tmp/catalog-answers.json
```

使用同一模型、指令骨架、预算，两次隔离运行；baseline 不提供仓库、Catalog 或工具，Catalog 条件提供工具和其快照，但两边均不交付答案文件。保存原始响应及模型和变量。比较器输出问题检出率、误报率、遗漏类型、可疑引用、无根据的核验声明；引用是否能支撑某条结论、reason 是否正确仍由盲评者审读。本轮只运行工具和合成响应验证，**未执行真实 Agent 对照评测**。

同步默认只输出计划。它读取固定 Git commit，先检查当前 Source/Knowledge，再在临时副本叠加候选快照并重跑这些检查。删除只报告；`possible_renames` 是一对一相同摘要的提示，不是迁移依据。删除若影响 Crosswalk、Review 或固定分流样本，必须人工处理引用，不能通过 `--output` 绕过。申请候选 pin 时不允许顺带更换 Provider 身份或许可配置；verbatim 批准及许可文件仍需人工核验。`--output` 必须是 Catalog 以外尚不存在的目录；输出供审阅，不会覆盖仓库内容。应用后再运行完整 `python tools/check_quality.py`（还包括 Markdown、文档和 Skills）。

变更 cp-algorithms pin 时，候选 `--approvals` 必须是 `{ "revision": "新提交", "policy_sha256": "现行许可摘要", "files": { "相对篇目": "sha256" } }`；旧版裸哈希表不接受为新 pin 的显式批准。批准不是签名，也不认证批准者。输出清单最后写；仅在命令成功退出后审阅 staging，不使用失败遗留的目录。
