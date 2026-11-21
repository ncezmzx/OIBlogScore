# 算法审查知识库

**Source → Normalization → Crosswalk → Review Knowledge → Skill Retrieval**。详细字段、ID 和许可策略见[数据契约](../../docs/catalog-schema.md)。三层分开维护：

1. **来源**：[来源许可、原稿与版本](sources/README.md)；不把来源文本当作审稿规则。
2. **算法身份**：[本地深度专题索引](index.json)与[跨源对照](knowledge/crosswalk.json)；中文、英文及缩写统一到 ID。尚未人工合并的题目/教程不靠文件名强行判等；其中 OI Wiki 和 cp-algorithms 的未归并技术页可作为 `upstream-candidate` 检索。
3. **审查知识**：[项目自行推导的定向检查](knowledge/review.json)及下方原有 34 份正文。`sources-only` 表示没有本地审查分析；`project-analysis` 是自行推导，不等于第三方所有结论已核实。区分来源陈述与适用于本文的推导、可重复见证。遇到不同资料冲突时登记来源 ID、变体和争议，不从条数投票确认结论。

原有深度审稿专题按类别：

- [数据结构](data-structures/README.md)
- [分治](divide-and-conquer/README.md)
- [图论](graph/README.md)
- [动态规划](dp/README.md)
- [数学](mathematics/README.md)
- [字符串](strings/README.md)

扩展类别（计算几何、搜索、基础／贪心／构造、随机化、交互等）可用命令查询，不代表已补齐本地审查协议：

```sh
python tools/catalog.py find '树链剖分'
python tools/catalog.py find --category geometry --limit 0
python tools/catalog.py refs min-cost-flow --json
python tools/catalog.py review min-cost-flow
python tools/catalog.py related min-cost-flow
python tools/catalog.py variants shortest-paths
python tools/catalog.py candidates
python tools/catalog.py search-sources 'potentials' --kind blog --author is-this-fft --provider codeforces --tag min-cost-flow
python tools/catalog.py source cp-algorithms:graph/dijkstra.md --text
python tools/catalog.py stats
```

所有查询离线进行。`find` 的精确规范别名优先；关键词可以命中关联资料标题。`refs` 返回全部**已关联**来源，不承诺覆盖互联网。`related` 分别标识人工交叉引用和共享来源形成的弱关联。`--limit 0` 取消结果截断。来源记录有公开访问地址；固定提交是同步、溯源和核对版本的依据。详见[维护与验收](../../docs/catalog-maintenance.md)。

检索时，`index.json` 只描述本地 Markdown；`tools/catalog.py` 会校验后合成 Source、Crosswalk、Review 和本地条目。`find` 默认保留部分匹配和来源标题线索；先排精确 ID、别名、标题，再排部分匹配。`find --json` 给出 `matching_fields` 和 `ambiguous_exact`，`--exact` 只保留精确命中而不强制选一个。候选不是等价映射；未映射的来源仍可经 `search-sources` 找到。指定独立数据目录时把 `--root` 放在子命令之前。
