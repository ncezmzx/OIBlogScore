# Catalog 维护、验收和适用边界

## 可重现范围

`tools/catalog.py stats` 是当前统计。来源范围按固定提交枚举：OI Wiki 收录 `docs` 下 12 个技术／竞赛分组的 Markdown，标题优先取 mkdocs 导航；cp-algorithms 收录 `src` 下分类技术页，排除顶层站点页。USACO Guide 为挑选的 13 个模块；Library Checker 为带标题的非样例题规格；KACTL 为技术分类的头文件。另有 5 篇博客（Codeforces 4、Universal OJ 1）、1 篇 AtCoder 官方题解、2 篇研究资料记录。许多记录只有来源元数据；不得将题库、头文件或导航页计为已核验数学专题。

本次保留 34 份原有完整专题，新增 6 份项目定向审稿条目（费用流、LCT、数位 DP、回文自动机、几何凸包、稀疏表）。例如“边分治”、“支配树”、“Beats”、“Knuth”和“广义 SAM”现在能查到有出处的资料，但其完整本地审查说明仍缺。其它来源候选未完全消歧；已建规范 ID 的别名必须唯一，未归并条目以来源路径作可追溯的发现 ID，不将同名算法误采为必然等价。待继续覆盖：复杂树分治的平衡假设、费用流强界及负环变体、完全动态连通性、全套几何鲁棒性证明、自动机与 DP 的组合模型。

## 同步：只生成候选，不修改工作树

```sh
# 从 sources/providers.json 取固定 SHA；clone 后确保该提交在本地。
python tools/sync_catalog.py cp-algorithms /path/to/cp-algorithms-checkout
python tools/sync_catalog.py cp-algorithms /path/to/cp-algorithms-checkout --output /tmp/cp-catalog-candidate
```

1. 支持 `oi-wiki`、`cp-algorithms`、`usaco-guide`、`library-checker`、`kactl`。工具读 Git 对象，不读上游工作树中的本地改动；不联网，不运行上游脚本。相同固定版本和政策生成相同字节。`--output` 只能是不存在的目录，不能重写旧快照。不要把输出目录指向现有 `sources/`。
2. 更新时用 `--providers` 提供另存的候选配置（修订 commit、日期及固定许可 URL）。脚本报告新增、删除、内容与元数据变化。许可声明字节变化时拒绝；须先实际复核许可再更新哈希。对于原样归档，如内容哈希变化，预览后逐篇核对许可、署名与第三方材料，再用 `--approvals` 传入人工审查的哈希文件。不能盲批新哈希。
3. 审查 staging 与 `sources/` 的差异后手动应用经批准的来源记录和原样文件；更新 ID 重命名的跨源关系，按变更相应移除旧归档。`knowledge/`、各算法正文和既有审稿协议从不由同步写入。
4. `python tools/check_quality.py` 校验许可、快照、链接形状、收录权限、内容完整性、来源追溯、别名和 Skill 检索契约。网络按需运行 `python tools/check_source_links.py --provider cp-algorithms --limit 0`，404/410 与超时、403、429、沙箱无网络分开，后者不能判定为死链接。离线 CI 不依赖远端网站响应。

## 审查和 Golden 语义

`tests/fixtures/catalog/golden.json` 保存可供 Agent 检查的对照：真实资料短句或博客贡献、合成正反主张、来源 ID、预期审查证据；`lazy.cpp` 是自写的有意错误对照。测试实际跑检索、出处和小型独立 oracle，并在可用时编译运行两种 C++ 实现；不调用 LLM，也不声称通过结构门禁就验证了上游定理。要测 Agent 能力，给 Agent 不包含 `expected` 的两侧主张与固定资料，要求分维度提供证据，再由人工对照期望；不要把期望预先暴露给待测 Agent。
