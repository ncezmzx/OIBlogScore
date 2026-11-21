# 证明依赖记录与检查器

先读 [证明协议](protocol.md)。可以保存下列 JSON（字符串依据应替换为实际核验结果）。边 `depends_on` 从命题指向其依赖。用 `python scripts/check_ledger.py path.json` 执行（从该 Skill 根目录；见[检查器](../scripts/check_ledger.py)）。退出 0 代表结构合法且目标的可达前提没有未解决或失败节点；退出 1 表示记录结构合法但有阻塞；退出 2 表示形状、引用或依赖无效。不检查证据语义，不向仓库自动提交结论。

```json
{
  "targets": ["equivalence"],
  "claims": [
    {"id":"forward", "location":"note.md:4", "direction":"forward", "status":"PASS", "evidence":"偶数写为 2k，因此除以 2 余数为 0。", "depends_on":[]},
    {"id":"reverse", "location":"note.md:5", "direction":"reverse", "status":"PASS", "evidence":"余数为 0，由带余除法 n=2q，所以 n 偶。", "depends_on":[]},
    {"id":"equivalence", "location":"note.md:3", "direction":"equivalence", "status":"PASS", "evidence":"整数域两个蕴含均成立。", "depends_on":["forward","reverse"]}
  ]
}
```

允许方向 `statement`、`forward`、`reverse`、`equivalence`；状态 `PASS`、`SUSPECTED`、`NOT_CHECKED`、`FAIL`、`NEEDS_CONTEXT`、`NOT_APPLICABLE`。等价节点必须直接登记且仅登记一个正向和一个反向依赖，允许另有 `statement` 依赖。把合法性和条件写入依据，未读的预备引理应显式登记为 `NOT_CHECKED`，缺题面/依赖用 `NEEDS_CONTEXT`，确实不适用用 `NOT_APPLICABLE`；不得删除依赖以获得成功退出。
