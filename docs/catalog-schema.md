# Catalog 数据契约

流向：**Source → Normalization → Crosswalk → Review Knowledge → Skill Retrieval**。同步只产出 Source 层候选，`tools/catalog_data.py` 组合视图，不把推导写回来源文件。

| 文件 | JSON 形状及主键 | 职责 |
|---|---|---|
| `index.json` | `{version:1,categories:{id:label},topics:[{id,title,category,aliases:[str],path}]}` | 34 篇深度 Markdown 的目录和既有 ID；不是上游快照，也不是所有算法实体的清单。 |
| `sources/providers.json` | `provider_id → {title,url,license,license_url,mode,retrieved,policy_url,permissions,terms,...}` | Git 来源另必须登记 `repository,revision,language,policy_path,policy_sha256`；Git SHA 40 位、内容/许可哈希 64 位小写十六进制。`permissions` 分 `copy,modify,redistribute`；`terms` 分 `commercial_use,attribution,share_alike`； `mode` 才是项目允准的收录方式，不用许可名称推断第三方附件权利。 |
| `sources/<provider>.json` | 来源对象数组 | 共用 `id,provider,title,url,authors,license,original_language,content_language,mode,modified,trust,retrieved,kind`。Git 记录另须 `path,revision,sha256,permalink,history`；只有原样收录须 `text_path`。字节、许可模式及固定网页路径通过门禁。 |
| `sources/curated.json` | 外部人工编目对象数组 | 共用字段外有 `published`（ISO 日期或 `null`）、`scope,review_use,metadata_status`；二级目录元数据须 `metadata_evidence`。作者和标题的出处不证明正文论点；日期未知保留 `null`。 |
| `sources/import-policy.json`、`approved-verbatim.json` | 分别是来源 → 路径/模块允许列表，以及收录相对路径 → SHA256 | 前者限定范围；后者批准具体字节；新版本每篇须重新审批，不因站点有许可就自动通过。 |
| `knowledge/crosswalk.json` | `[{id,aliases,sources:[{source,relation,basis}],title?,category?}]` | 已有深度专题沿用标题和分类；新实体提供两字段。不复制上游正文。 |
| `knowledge/triage-baseline.json` | `{revision,source_ids:[str]}` | 保存基线未归并来源集合用于可重复统计，不是当前待办队列；现状从 Crosswalk 派生。 |
| `knowledge/review.json` | `algorithm_id → {status,evidence,sources,model,preconditions,invariant,proof,complexity,witness,checks,related}` | 本地原创推导。`sources` 必须由对应实体引用；`related` 为存在的算法 ID。受限证明可用 `needs-review`，没有 `VERIFIED` 数值捷径。 |

## 身份和关联

- 规范 ID 为稳定的 ASCII kebab-case。保持既有 ID；新增前按标题、变体及别名查重。中英文别名规范化用 NFKC、casefold、合并空格；规范别名不可跨 ID 冲突。未归并来源源于发现，不替它伪造算法 ID。
- 来源 ID 是 `<provider>:<稳定上游相对路径或网站公开编号>`；不含 commit，修订通过独立字段维护。域名、Git 文件路径、固定版本和 permalink 要一致。USACO 模块 slug 来自上游 frontmatter；离线只验证模块类别及 slug 形状，仍需用固定 Git 对象重新同步复核。
- `exact` 是同一对象，`alias` 是同一定义的另一个名称，`implementation` 是具体实现，`variant` 带不同操作集、模型或实现策略，`related` 是背景、应用或仅部分涵盖，`unclassified` 不算归并。每条边需写依据。同一来源不能对多个算法做 `exact/alias` 身份声明；多个 `related` 边允许。多个条目共享一篇资料只是弱关联，`related` 命令另列 `shared_source`。
- 旧有宽泛关联按 `related` 迁移，直到逐条确认更强关系。`stats.triage.by_relation` 按基线来源去重，若一来源带多种关系，各子计数可能重叠；`identity_targets` 只数 对基线有 `exact/alias` 的规范实体。`review` 的分类互斥：一个 ID 有 Markdown 和新笔记时，优先显示笔记；`show` 仍读取旧 Markdown。
- `upstream-unreviewed` 指原文结论未独立核验。`project-analysis` 指作者独立写出限定范围的推导，不等于有人复核整个算法；`needs-review` 显式记录关键缺口。`indexed-from-secondary-directory` 只说明标题和作者可追溯到资料目录，不能证明原页面或数学正确性。
