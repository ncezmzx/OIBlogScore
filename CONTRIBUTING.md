# 贡献指南

建议先开 issue 给出最小文章、条件与可复核证据。提交前运行 `python -m pip install -e .` 和 `python -m unittest discover -s tests -v`。新增发现规则要测试误识别和失效路径；新增修复规则要证明是无技术语义的固定短句，并加入保留好文章、保护技术文本、保留原换行及回滚的回归测试。不要提交博客私稿、模型凭据、`.oiblogscore/` 或模型自评冒充审查证据。

新增算法专题时同改机器索引和类别入口；按专题的十个小节给出前提、反例、实现代价和出处，不贴通用模板段落。文档链接应保持在 Skill 包内，跨包共享资源通过可选 checkout 查询。提交前运行 `python tools/check_quality.py`；详见 [工程验收](docs/engineering-quality.md)。
