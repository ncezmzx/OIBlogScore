# 2026-11-21 全系统修缮报告

本文件是本轮的完整工作报告。评测原始数据见 [2026-11-21 独立对照盲测](evaluation/2026-11-21/README.md)。报告只陈述实际执行的检查；NOT RUN 的项目没有用推测补齐。

## A. 执行摘要

### 基线

- 起始 HEAD：`376ea781ee6899031812c96aeb2f96585b39b196`（main，工作区干净）。
- 环境：Windows Python 3.14.7、3.12.10、3.8.10；WSL Ubuntu 22.04 Python 3.10.12；Git 2.55；MinGW g++ 8.1.0；WSL g++ 11.4.0。
- 初始门禁通过；77 项测试中 1 项失败、1 项跳过。失败项是测试夹具未隔离用户级 `core.autocrlf=true`，不是 CLI 实现缺陷；修复的是测试隔离，不是断言或实现。
- 初始 Catalog：1,014 来源、10 Provider、113 规范实体、323 上游候选、17 结构化 Review、2 Claims、47 verbatim。

### 本轮目标与实际完成

本轮优先处理会破坏用户数据、误报状态或虚高可信度的问题。实际完成：

- **工程安全**：前导 `/` Windows 路径逃逸、保留状态目录大小写变体、只读目标临时文件残留、锁所有权、缓存基线不可达、提交前输入复验、发现清单稳定性、缺失跟踪文件保留缓存、大小写/Unicode 路径冲突、零候选误判完成、WSL `core.fileMode=false` 误判、非 UTF-8/自动换行跳过诊断。
- **算法知识**：Lengauer–Tarjan 从支配树别名中拆出，新增 needs-review 实体与笔记；LCT、费用流、PAM 从 project-analysis 降为 needs-review；一般图匹配补齐范围与检查；修正 Knuth 复杂度索引错位、Beats 误用 counterexample、支配树简单路径论证缺句。
- **Catalog 证据**：移除含第三方论文证明摘录的 verbatim 副本；新增 verbatim pin 绑定、第三方出处标记门禁；修正两条 Codeforces 发布日期、33 条 `content_language`、未支撑的 `scope-inspected` 标记；收窄具体算法别名；`find` 默认不把未归并来源当规范实体。
- **Skills**：统一六态 verdict 语义（`NEEDS_CONTEXT` vs `NOT_CHECKED`）、proof 中“证明无效/命题为假”、counterexample 无发现不得 PASS、repair 整行白名单与 `--path`、verify 空结果不是通过、score 的 Major/Critical 上限与等级。
- **评测**：实现 `blind_eval.py prepare` 净化 bundle 与 manifest；修正引用指标、评分校验、UTF-8 输出；实际运行 25 题 Baseline/Catalog 双会话盲测、独立评分和主代理复核。结果见 G 节：**两条件 verdict 与证据均满分，未观察到判定收益**，属于饱和题集上的 null/ceiling 结果。
- **回归**：Windows 3.8/3.12/3.14 与 WSL 3.10 全量 95 项通过；wheel 3.12 离线安装、仓库外调用和完整修复/回滚工作流通过；Catalog 全部子命令通过。

### 最重要的风险与未解决事项

- 高风险数学结论仍保留 `needs-review`：LT 的半支配/eval 与平衡 link 界、一般图匹配的缩花完备性、LCT 的 access 摊还、混合 Beats、Knuth 决策单调性继承、费用流整体最优性、PAM 构造界。没有把它们升级为 `independently-verified`。
- 盲测只覆盖 25 道摘录，且当前模型两组都 25/25；没有人类盲评，主对照的模型后端/版本未被宿主暴露；不能据此宣称普遍提升。
- 3.11、macOS、Windows 长路径、真实 CI、五个上游的最终代码 dry-run 未在本轮执行；详见 C 节。
- 323 个上游候选仍未归类、304 条 `related` 仍是弱关联、30 条 Blog 未读正文、没有独立核验 Claim；这些是既定边界，不是本轮“已修复”。

## B. Git 与变更

- 起始 HEAD = 结束 HEAD = `376ea781ee6899031812c96aeb2f96585b39b196`；未创建 commit、未 push、未创建 PR。
- 工作区有未提交修改（本轮要求保留，不自动提交）：58 个已跟踪文件修改/删除，912 行增加、378 行删除；未跟踪 `docs/evaluation/`、`resources/algorithm-catalog/sources/verbatim-pin.json`、`tools/console.py`。
- 删除：`resources/algorithm-catalog/sources/upstream/cp-algorithms/dynamic_programming/knuth-optimization.md.txt`，因为它包含明确标注取自 F. Frances Yao 论文 Lemma 2.1 的整段证明，原样收录的许可边界无法证实。来源记录、permalink、sha256 和 review 引用保留，改为 external-index。其余文件没有删除。
- 用户数据：起始工作区干净；没有覆盖或清理用户未提交修改。盲测期间临时移出的 `tests/fixtures/blind/key.json` 与 `targets.json` 已恢复，`git diff` 对两者为空。
- 变更目的分组：
  - `src/oiblogscore/repository|discovery|audit|repair|reporting|cli.py`：数据安全、状态机、路径/锁/原子写、缓存与提交复验。
  - `resources/algorithm-catalog/**`：LT 实体、状态、来源、日期、语言、pin、别名。
  - `skills/oi-*`：九包 verdict/失败路径与修复边界。
  - `tools/**`、`tests/**`：评测隔离、指标、UTF-8、门禁与回归测试。
  - `docs/**`、`README.md`、`install.md`、`CONTRIBUTING.md`、`.github/workflows/test.yml`：文档与实际行为对齐、CI 强化。

## C. 工程验证

| 环境 | 质量门禁 | 全量测试 | 故障注入 | 安装验证 |
|---|---|---|---|---|
| Windows / Python 3.14.7 | PASS | 95 OK，2 skip | 见下 | NOT RUN（最终代码只用 3.12 重建轮子） |
| Windows / Python 3.12.10 | PASS | 95 OK，2 skip | 见下 | PASS：21 成员 wheel、全新 venv 离线装、checkout 外 CLI 与完整工作流 |
| Windows / Python 3.8.10 | PASS | 95 OK，2 skip | 见下 | NOT RUN（最终代码未重建 3.8 轮子；完成安装后全量测试） |
| WSL Ubuntu 22.04 / Python 3.10.12 | PASS | 95 OK，0 skip | 见下 | NOT RUN（Linux 源码运行；未建 Linux wheel） |
| Python 3.11 / Linux（NOT RUN：未安装；`py -3.11` 返回 103，不用 3.10/3.12 代替） | NOT RUN | NOT RUN | NOT RUN | NOT RUN |
| macOS（NOT RUN：无 macOS 执行器） | NOT RUN | NOT RUN | NOT RUN | NOT RUN |

补充：

- 2 个 Windows skip 是：`test_git_file_mode_false...`（NT 不暴露 Git fileMode 的临时代码位）与 `test_cpp_orientation_widening_and_ubsan_witness`（需要 Linux + libubsan）。WSL 中这两项均实际运行并通过；Windows 上 `lazy.cpp` 的普通 g++ 编译/运行通过，但 MinGW 缺少 `-lubsan`，UBSan 为 NOT RUN。
- 故障/边界回归实际覆盖：ENOSPC（fsync/replace 注入）、最终 journal 写入失败、损坏 pending、外部编辑、`HEAD` 已包含修复后的回滚、staged 文件、只读目标、锁被替换、第二进程锁冲突、`core.autocrlf=true`、`core.fileMode=false`、autocrlf/fileMode 诊断、大小写路径冲突、缺失跟踪文件、发现清单变化、提交后工作区变化、不可达缓存基线、零候选、保留状态变体、前导 `/` 路径。均由 `tests/test_workflow.py`、`tests/test_catalog_integrity.py` 执行。
- 安装后完整工作流（3.12 wheel）：scan、audit --full、六维 submit、report=COMPLETE、repair safe、verify、rollback、verify=[]，最终文件 SHA-256 与原始字节一致。
- Catalog：`check_quality.py`、`stats`、`find`、`show`、`refs`、`review`、`related`、`variants`、`candidates`、`search-sources`、`source`（含 `--text`）全部通过；新增 `prepare` 由测试和 CI 配置覆盖。
- 未执行：五个固定上游的最终代码 sync dry-run/staging（本轮没有对应 checkout；修改过的 pin/标记/输出路径逻辑由 fixture 测试覆盖，不能替代真实上游逐字节核验）、真实 GitHub Actions 执行、>260 字符长路径（本机 `LongPathsEnabled=0`，WinError 206）、Windows 文件占用/杀毒软件竞争压力测试。
- CI 配置：Ubuntu/Windows × 3.8/3.12；升级 pip/setuptools/wheel；wheel 构建后离线安装并从仓库外调用；门禁、stats、LT 检索、`prepare baseline`、unittest 失败注解。CI 结果需在推送后由实际运行证明，本轮没有远程运行。

## D. 算法审查

高风险专题的结论只按实际核验范围使用；没有新增 `independently-verified`。测试/小图 oracle 不等于全称证明。

| 专题 | 证明/复杂度现状 | 独立 oracle / 反例挑战 | 状态 |
|---|---|---|---|
| Lengauer–Tarjan | 记录 semi/link-eval/bucket/idom 修正契约；未证半支配引理、compress 正确性、bucket 完备性；简单 link-eval O((V+E)log V) 与平衡 link O((V+E)α) 不混用 | 既有删点可达 oracle（全 4 点图、固定 seed 9 点图）；审计子代理另跑 5–9 点随机/重边/自环；未验证平衡 link 生产界 | `needs-review` |
| 支配树迭代集合算法 | 迭代交前驱集合，V−1 轮；严格支配点全序，补了“拼接重复点删回路” | 小图/删点 oracle；不是 LT | `project-analysis` |
| 一般图最大基数匹配 | 只证增广翻转与奇环收缩义务；缩花/展开、LCA、嵌套花、带权界未证；常见 O(V³)/O(VE) 不当作本笔记上界 | 全部 1024 个五点简单图枚举匹配/增广路；未测 Blossom 实现 | `needs-review` |
| Link-Cut Tree | rev/cut/link 契约；未证 access 全局摊还，明确 O(r+k) 非 n 的界 | 协议/见证；无独立 LCT 实现 | `needs-review` |
| Segment Tree Beats（chmin+sum） | 势能/部分覆盖 +1/强制下推界；不迁移到 add/chmax；混合 add 只保留合法反例 | 小例；无混合模型完整证明 | `project-analysis`（仅 chmin 局限） |
| Knuth 优化 | 只证双侧单调后的候选区间与望远镜求和；最优决策单调性继承仍缺 | n≤6 全/随机对朴素区间 DP；平局约定有测试 | `needs-review` |
| 费用流 | 只证势与 Dijkstra 可继续使用；整体最优性/无负环证书未证 | 小见证；无完整最优性证明 | `needs-review` |
| 回文自动机 | 节点数、计数传播；构造链接下降/series link 界未证 | 反例/见证；无构造摊还证明 | `needs-review` |
| 离线动态连通性 | 时间线段树 + 回滚 DSU，只覆盖离线任意加删；不声称在线 | 协议/见证；无在线实现 | `project-analysis` |
| Trie 广义 SAM / 分隔符 SAM | 只证存在性；不证计数/不同文档数/Trie 版构造 | 225 对二元短文档子串集合 | `project-analysis`（限定范围） |
| CDQ、整体二分、Slope Trick、树形 DP、数位 DP、边分治、FPT/多项式/凸包/Sparse Table 等 | 各自限定模型；检查平局、边界、势能、位宽 | 既有枚举/对拍/见证 | 未发现新反例，保持各自声明范围 |

本轮算法审计实际运行（由独立审计子代理完成，主代理复核了 oracle 定义与代码）：LT 5–9 点约 2 万随机图与删点 oracle 无差异；Knuth n≤6 与朴素 DP 一致；Beats/PAM/SAM/Slope Trick 见证通过。仍未证明的内容不因这些运行升级状态。

## E. Catalog

当前 `stats`：

- 1,014 来源、10 Provider、968 external-index、46 verbatim；114 规范实体、323 上游候选。
- Crosswalk：11 exact、1 alias、1 implementation、22 variant、304 related；triage 固定样本 360 条中 37 已关联、323 待处理、6 个 identity target。
- Review：32 local-reference、12 project-analysis、6 needs-review、387 sources-only；18 结构化笔记；2 Claims；0 `independently-verified`。
- 30 Blog、2 Editorial、2 Paper；50 个规范实体有本地知识，8 个有身份来源。

本轮处理：

- **第三方材料**：移除 Knuth 页原样副本；新增 `THIRD_PARTY` 标记门禁与 sync 拒绝；`approved-verbatim.json` 46 条，`import-policy` 与磁盘文件一致。不能据此对所有来源做法律确权。
- **pin/批准**：新增 `sources/verbatim-pin.json`，绑定 cp-algorithms 的 revision/policy_sha256；门禁拒绝未绑定 pin；sync 换 pin 时同步写 pin，旧批准不能隐式复用。
- **身份**：LT 不再作为支配树别名，新增 `lengauer-tarjan` 实体（两个 related 来源 + needs-review 笔记）；移除 shortest-paths/max-flow/matching 的 Dijkstra/Bellman-Ford/Dinic/Hopcroft–Karp 别名；suffix-tree 的 cp Ukkonen 教程从 implementation 改为 related；KACTL 头文件仍是唯一 LCT implementation。
- **检索边界**：`find` 默认排除未归并候选（`--include-candidates` 可选）；文本 `refs`/`variants` 增加固定 revision 与 sha256 前缀；`source_view` 的 `redistribution_policy` 改为记录自身的 mode，另保留 provider policy。
- **元数据**：Codeforces 105658 日期由 2022-08-25 修正为 2022-08-05，47821 由 2016-09-24 修正为 2016-10-17（实际查询 Codeforces API 的 creationTimeSeconds）；33 条 curated `content_language` 从 zh 改为原文 en/ja；移除没有审阅人/日期的 `scope-inspected` 标记。
- **门禁**：legacy topic 必须 path/category/id 一致；第三方标记拒绝；pin 绑定；find 候选隔离；sync 输出必须在 checkout 外（fixture 测试）。
- **链接检查**：DOI/出版商重定向改为 `redirected` 状态，不再等同 unreachable；新增 `--allow-redirect-host` 与 `--permalinks`；本轮未做真实网络全量探测。

未解决：323 个候选未归类；304 条 related 只是可追溯线索；cp-algorithms 等 Git 源 `authors` 为空（显示时回退为 provider contributors，仍不能等同于逐页署名）；30 条 Blog 未标记正文已读；2 条 Claim 均非独立核验；许可判断不是法律意见。

## F. 九个 Skills

| Skill | 结论 | 本轮修改/剩余限制 |
|---|---|---|
| `oi-blog-review` | 有限可用 | 六维名称/六态表；缺少材料改 `NEEDS_CONTEXT` 并列缺项，未完成本维才 `NOT_CHECKED`。仍依赖 Agent 实际读材料。 |
| `oi-proof-review` | 可用 | 明确区分“证明无效/命题为假”；ledger 支持 `NEEDS_CONTEXT`/`NOT_APPLICABLE`；交付状态统一。结构检查器不验语义。 |
| `oi-complexity-review` | 可用 | 有效但不紧的界可 PASS 并注明；错误上界 FAIL/Major；缺模型/实现 NEEDS_CONTEXT。 |
| `oi-code-review` | 可用 | 增加重复点/重边/重复测试数据；无代码 NOT_APPLICABLE，引用实现缺失 NEEDS_CONTEXT；静态检查不等于执行。 |
| `oi-counterexample` | 可用 | 找到反例是命题 FAIL 见证；有界搜索无结果只能 NOT_CHECKED，不得给 PASS。 |
| `oi-blog-score` | 有限可用 | Major 上限 74、Critical 上限 49；SUSPECTED 半分成不能绕过；等级 A/B/C/D；说明分数是 Agent 报告，CLI 不验证数值。 |
| `oi-repository-audit` | 可用 | 六态表、CLI/PYTHONPATH 降级、Windows `/tmp` 转原生路径、COMPLETE 非正确性。 |
| `oi-blog-repair` | 有限可用 | 改为整行白名单；safe 建议显式 `--path`；报告 dirty/非 UTF-8/拒绝；不把段落级语义当授权。 |
| `oi-repair-verify` | 有限可用 | verify 空结果是 no-op 不是通过；检查 repair-run 状态；CLI 缺失时 NOT_CHECKED；不能替代技术重审。 |

跨包问题：Catalog 检索契约在 7 个 Skill 中按包内自包含要求重复，不是共享文件；各包输出仍是人工/自由文本，只有 `oi-repository-audit` 直接给 submit JSON；score、counterexample、A/B/C/D 没有统一机器转换。它们已在本轮文档中说明，不是隐藏能力。

## G. 真实 Agent 对照盲测

完整记录、原始回答和评分见 [评测目录](evaluation/2026-11-21/README.md)。摘要：

- 25 题（18 FAIL、5 PASS、2 NOT_CHECKED），seed 7 同序；Baseline 只有题面/指令，Catalog 有净化只读 OIBlogScore checkout。
- 两个独立 Qoder 会话从同一会话创建，继承同一保存模型与权限模式；宿主未返回具体 modelKey，应用默认是 Auto，无法核验后端版本/路由。另有一次 Catalog 子代理运行（跨 harness；该次结果未记录具体模型；失败的一条 Baseline 子代理尝试曾在 API 错误中显示 DeepSeek V4.1），没有对应 Baseline，单独保存、不合并。
- **verdict**：两组都 25/25；18/18 检出、0 误报、F1=1.0；2/2 正确弃答。18/18 的 95% Wilson 下界约 0.824，25/25 的约 0.867。该样本对模型已饱和，没有 discordant verdict。
- **证据**：两组 25/25 evidence accurate、0 unsupported claim。
- **引用**：Baseline 按条件无引用，rate 为 null；Catalog 自动 ID 命中 15/16=0.9375；独立评分员判 18/18 语义支持；主代理复核判 17/18（A08 的“二维计算几何基础”不支撑 C++ int 减法溢出这一具体结论，自动指标也把该来源标为不在 `convex-hull-geometry` 允许列表）。最终采用较保守的 17/18，并保留分歧记录。
- **A25 逐目标**：两组都是 3/4；`knuth-window` PASS、`resort` FAIL、`unknown-preprocess` NOT_CHECKED 正确；`product-type` 期望 CONDITIONAL，两组都写成 FAIL；scoped precision/recall/F1 均 0.5，correct abstention 1.0。Catalog 的 target citation 只有 `knuth-window` 获直接支撑（1/4）。
- **未测**：severity accuracy、duplicate issue rate、全题集 multi-defect coverage；输出 schema 和答案键没有相应字段，不伪造。
- **隔离**：私有 key/targets 在评测期间移出工作区；bundle 不含 tests/key；提示禁止越界。残余风险是两个 Qoder 会话共享宿主文件系统，无法像容器那样证明绝对隔离；Catalog 满分也可由 Catalog 审查笔记直接解释。没有人类盲评；独立 AI 评分 + 主代理复核不能替代人类判断。
- **结论**：本轮实际运行了对照，但结果是 null/ceiling；可观察到的 Catalog 收益是来源可追溯性，不是判定或证据质量提升；且引用存在一处语义不支撑。不能据此宣称 OIBlogScore 普遍提升 Agent 能力。

## H. 未解决问题

### Critical

无已知仍存的 Critical 数据破坏问题。原 Critical/High 候选（Windows 前导路径逃逸、保留状态大小写变体、第三方 verbatim）已修复或移除。盲测隔离的共享工作区风险属于评测方法风险，不是用户数据破坏。

### High

| 问题 | 影响 | 为什么未解决 | 下一步证据 | 阻塞发布 |
|---|---|---|---|---|
| LT、一般图匹配、LCT、混合 Beats、Knuth 继承、费用流最优性、PAM 构造界未全证 | 不能把这些结论当作已核验数学事实 | 需要完整引理/势能/摊还证明，超出本轮可安全完成的范围 | 独立审稿人给出的完整证明、平衡 link/缩花实现和更广 oracle | 否；已保持 needs-review |
| 无 `independently-verified` Claim | 知识库不能宣称独立核验 | 没有独立签名/复核人 | 逐条 reviewer、日期、可复现 verification | 否；诚实边界 |
| 盲测无人类评审、主对照模型后端未暴露、样本饱和 | 不能证明 Agent 能力提升 | 平台模型路由/人类资源限制 | 固定显式 modelKey、双人盲评、更大且非饱和题集 | 否；已报告 null 结果 |
| 3.11、macOS、长路径、真实 CI、五个上游最终 dry-run 未运行 | 跨版本/跨平台/上游同步覆盖不完整 | 环境与 checkout 不可用 | 对应解释器、macOS runner、启用长路径、固定上游 checkout | 否；NOT RUN 已标注 |
| 323 候选/304 related/30 Blog 未深化 | 知识覆盖与来源身份仍有限 | 需要逐条人工核验 | 来源级 review 与正文阅读记录 | 否 |

### Medium

- `core.autocrlf=true` 时 repair 按字节判 dirty 并跳过；已给出可操作 detail，但默认 Windows Git 配置下自动修复仍会停摆。需要用户设 `core.autocrlf=false` 或只审查。
- `find` 的索引 aliases 仍是检索名，不是严格身份关系；已移除最明显的具体算法别名，但 `kruskal`、`高斯消元` 等仍作为检索名保留。
- 18 条结构化 Review 中 12 条 project-analysis、6 条 needs-review；其证明范围不等同于 Markdown 专题。
- `check_source_links` 的 redirect/permalinks 代码未做真实网络全量验证；DOI 出版商 allowlist 仍由用户显式提供。
- sync 输出现在拒绝 checkout 内目录，但真实上游 dry-run 未在本轮重跑。
- 评分/严重性/重复 issue 没有机器字段；score Skill 的分数不能由 CLI 验证。
- targeted audit 对范围外已失效结果的清理策略仍会删除旧缓存；报告只显示当前 NOT_CHECKED。旧结论已失效，不构成有效结果丢失，但历史证据不保留。
- 多进程只验证了锁互斥与所有权，没有做高并发/杀进程/网络文件系统压力。

### Low

- `pyproject.toml` 的 `license = {text="MIT"}` 在新 setuptools 中已弃用；保留是为 Python 3.8 兼容。
- `.gitattributes` 没有全局 `text=auto eol=lf`；规则指纹会随 checkout EOL 变化，可能造成跨机器缓存差异。
- `authors` 为空的 Git 源在显示时回退为 provider contributors；不是逐页个人署名。
- 真实 CI 未在本轮触发；Windows 杀毒/文件占用、8.3 短名、>260 长路径未实测。

## I. 最终结论

**`PASS WITH LIMITATIONS`**

本轮完成了工程安全修复、Catalog 证据边界修复、九个 Skill 的可执行性修复、Windows/Linux 多版本全量回归、安装后 CLI 工作流验证，以及一次真实模型的双条件盲测。主要目标（让工具更可靠、让证据边界更诚实、让评测可复现）已完成。

但必须明确限制：高风险数学结论仍按 `needs-review` 保留；盲测是 25 题饱和 pilot，两条件都 25/25，未显示判定或证据收益，且无人类盲评、主对照模型后端未暴露；Python 3.11/macOS/长路径/真实 CI/最终上游 dry-run 未运行；Catalog 仍有大量未归类和弱关联来源。因此本结论不表示 OIBlogScore 已被证明普遍提升 Agent 审查能力，也不表示任何 needs-review 命题已被证明。后续若要升级为 `PASS`，至少需要固定显式模型与人类双盲评审、非饱和且更大的题集、完成高风险证明的独立核验，以及在真实 CI/上游环境重跑安装与同步验证。
