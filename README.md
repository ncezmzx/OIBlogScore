# OIBlogScore

**面向 OI / ICPC 技术博客的审查、修复与验证工具。** 技术正确性优先。文字修复应当让文章仍像原作者写的，而不是变成一篇新文章。

OIBlogScore 由九个 Agent Skills 和一个 Python CLI 组成。**Agent** 阅读文章、核验算法与证据；**CLI** 发现文件、追踪依赖、管理任务和缓存、保护写入并汇总报告。CLI 不调用模型、不执行文章附带代码，也不会自行宣布某个证明成立。

## 安装

需要 Python **3.8+** 与 Git，运行时无第三方 Python 依赖。Python 3.8 的旧 pip/setuptools 需先升级；Windows 建议设置 `PYTHONUTF8=1`。

```sh
git clone https://github.com/ncezmzx/OIBlogScore.git
cd OIBlogScore
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install .
mkdir -p "$HOME/.agents/skills"
cp -R skills/oi-* "$HOME/.agents/skills/"
```

安装路径因 Agent 宿主而异，见 [install.md](install.md)。常见问题：Windows `core.autocrlf=true` 会让 `repair` 按字节判 dirty 并在 `repair-run.json` 说明原因（这是保守拒绝，不是修复成功）；WSL/DrvFs 的 `core.fileMode=false` 会忽略可执行位；Git Bash 的 `/tmp` 需先转成原生路径；CLI 不在 PATH 时用 `PYTHONPATH=src python -m oiblogscore.cli`。

## 全仓库审查

在需要审查的 Git 仓库根目录运行：

```sh
# 建议将 .oiblogscore/ 加到目标仓库的 .git/info/exclude，避免误提交原稿备份。
oiblogscore scan .
oiblogscore audit . --full
```

让支持 Skills 的 Agent 调用 `oi-repository-audit`：按 `.oiblogscore/queue.json` 对文章及依赖执行审查，每项把 **证据** 连同任务票据传给 `oiblogscore submit . --result /path/to/result.json`。可并行审查，串行提交。没有 Agent 也可以人工提交同一格式。见 [工作流与结果示例](docs/audit-workflow.md)。

```sh
oiblogscore resume .                      # 恢复最近任务范围
oiblogscore audit . --incremental          # 按当前输入复用有效结果
oiblogscore audit . --path notes/ --type md --category dp --dimension proof
oiblogscore report .                       # 或 --json
```

Git 可见的 Markdown、MDX、LaTeX、HTML 会进入候选集。README、文档、疑似生成页、草稿、归档均会单独分类，默认不丢弃；用 `oiblogscore.json`（参见 [示例](config.example.json)）排除目录、补充依赖或配置审查规则文件。`COMPLETE` 不是「没有问题」：它表示配置范围已发现且没有已报告的缺失依赖、适用审查已处理、修复已验证，报告可能仍有 `FAIL` 或 `SUSPECTED`。

## 算法资料检索

在 OIBlogScore checkout 中用 `python tools/catalog.py find "李超线段树"` 查规范 ID，用 `refs li-chao` 查看来源及版本，用 `review li-chao` 读本地审查说明。收录上游原稿和许可说明均放在[独立的来源层](resources/algorithm-catalog/sources/README.md)，不受项目 MIT 许可重新授权；来源未核验与项目分析是不同状态。数据流为 **Source → Normalization → Crosswalk → Review Knowledge → Skill Retrieval**。可用 `variants shortest-paths` 区分实现和变体，`candidates` 查看尚未归类的来源；见 [Schema](docs/catalog-schema.md) 和[目录同步及验收](docs/catalog-maintenance.md)。

## 自动修复与回滚

```sh
oiblogscore repair . --mode safe --path notes/article.md
oiblogscore repair . --mode interactive    # 先看 Diff，再逐篇确认
oiblogscore verify .
oiblogscore resume .                      # 交给 Agent 重审受影响文章
oiblogscore rollback . --path notes/article.md
# 或 --edit-id ID，只撤销一项（ID 在报告和 journal 中）
```

`repair` 不带模式时只审查。Safe Repair 只处理少量明确且独立成段的编辑性短句；其他错字、格式问题和风格候选由 Agent 报告，不会任意改写。带公式、代码或术语的内容不会被改写。文件已被用户修改、暂存或是未跟踪文件时直接跳过。不会自动提交或推送。详见 [修复政策](docs/repair-policy.md)。

## Skills

| Skill | 职责 |
|---|---|
| [oi-blog-review](skills/oi-blog-review/SKILL.md) | 综合技术和语言审查 |
| [oi-proof-review](skills/oi-proof-review/SKILL.md) | 定理条件、推导、不变量和正确性 |
| [oi-complexity-review](skills/oi-complexity-review/SKILL.md) | 时间、空间、摊还界和实现开销 |
| [oi-code-review](skills/oi-code-review/SKILL.md) | 实现、模型一致性、边界和数值范围 |
| [oi-counterexample](skills/oi-counterexample/SKILL.md) | 构造、最小化和复核见证 |
| [oi-blog-score](skills/oi-blog-score/SKILL.md) | 严重性、审查覆盖和可解释评分 |
| [oi-repository-audit](skills/oi-repository-audit/SKILL.md) | 分发任务、全量、增量、定向和恢复 |
| [oi-blog-repair](skills/oi-blog-repair/SKILL.md) | 同作者风格参考、分类与克制修复 |
| [oi-repair-verify](skills/oi-repair-verify/SKILL.md) | 技术内容保护、验证、重审和回滚 |

## 开发与边界

- [架构](docs/architecture.md) · [工作流](docs/audit-workflow.md) · [修复政策](docs/repair-policy.md) · [报告字段](docs/report-format.md)
- [模块化算法知识库](resources/algorithm-catalog/README.md) · [样例审查](examples/dijkstra-review.md) · [贡献指南](CONTRIBUTING.md) · [系统审计记录](docs/system-audit.md)
- `python tools/check_quality.py` 与 `python -m unittest discover -s tests -v`；CI 矩阵配置为 Ubuntu/Windows 与 Python 3.8/3.12。
- 发现和依赖提取是启发式的，不解析所有生成器、动态引用、复杂 YAML/MDX 或所有构建依赖；请配置隐式依赖。技术结论依赖实际审查证据。文风统计只供参考，不自动生成替换句子。

受 [CPscore](https://github.com/SemsueZhang/CPscore) 的独立 Skills、共享 Reference 和可选确定性脚本架构启发。详见 [工程验收与覆盖范围](docs/engineering-quality.md)。项目原创软件和资料采用 MIT License；第三方收录内容沿用原许可。

Catalog 返回的是检索线索和分层证据，不是自动审查结论。`python tools/catalog.py find SAM --json` 可查看命中字段和相似条目；消歧后用 canonical ID 查 `refs` 和 `review`。`python tools/check_quality.py` 同时检查写作资源、Skills 和 Catalog 数据完整性，不认证算法证明。
