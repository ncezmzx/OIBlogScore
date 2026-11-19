# 仓库报告

`.oiblogscore/report.md` 是可读摘要；`report.json` 是完整记录。`manifest.json` 是快照加文件状态，`queue.json` 是最近范围内的待执行任务，`audit.json` 是缓存和票据，`repairs.json` 是包含完整原稿的私有日志。

- 顶层包含来源、分支、当前 commit、扫描时间、规则指纹、候选数、审完数、未审完数、已修复文件数、排除与发现判断、各级别和各 verdict 计数。工作树可能有未提交修改；文章哈希比 commit 更精确。
- 每篇有路径、格式、作者、分类原因、类别、内容及输入哈希、依赖和未解析关联、当前有效结论与最近有效审查时间、语言问题及修复计数。严重性统计按发现项，跨维度重复根因应由 Agent 去重。
- `repairs` 包含逐编辑 ID、位置、前后文本、理由、活动状态、Diff 和当时的验证结论；`verification` 是与当前文件的复验；`repair_run` 记录最近执行的跳过或拒绝。回滚保留历史日志。
- `unresolved` 列出审查发现、尚无结论的维度、发现告警和未解析引用。
- `completion.discovery` 只承诺完成配置范围的可见候选枚举；`completion.audit` 要求所有候选的六个维度均非 `NOT_CHECKED`；`completion.verification` 要求所有现有修复都通过验证（没有修复时为真）。三个均为真才是 `COMPLETE`。这不表示审查无错误，也不是正确性认证。`NOT_APPLICABLE` 必须有理由，`SUSPECTED` 表示已审但尚有疑点。
