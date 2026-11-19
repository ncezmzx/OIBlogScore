# 安装与卸载

从 checkout 运行 `python -m venv .venv`、激活虚拟环境，然后 `python -m pip install .`。开发用 `python -m pip install -e .`；无需安装也可运行 `PYTHONPATH=src python -m oiblogscore.cli --help`（POSIX）。Windows PowerShell 激活命令是 `.venv\Scripts\Activate.ps1`。

按宿主配置复制完整 Skill 目录，例如 Codex `~/.agents/skills/`、Claude Code `~/.claude/skills/`，或放入项目级对应目录。仓库级编排应安装全部九个。保持 CLI 对 Agent 的 PATH 可见。各 Skill 的本地链接均封装在自身目录；技术 Skills 可选用共享算法库。给宿主提供 OIBlogScore checkout 路径，并在执行 CLI 的环境中设置 `OIBLOGSCORE_REFERENCE_ROOT=/absolute/path/to/OIBlogScore`，使其指纹包含该 checkout 的 `skills/` 与 `resources/`。不设环境变量且规则位于被审仓库外时，更新规则后递增目标仓库 `rule_version` 或全量重查。

升级时更新 checkout、重新安装 CLI 和覆盖 Skill 目录。卸载 CLI 用 `pip uninstall oiblogscore`；可以移除已安装的 Skill。**不要盲目删除 `.oiblogscore/`**：其中可能有唯一的修复备份和用于回滚的记录。
