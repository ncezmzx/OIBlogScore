# 安装与卸载

从 checkout 运行 `python -m venv .venv`、激活虚拟环境，然后 `python -m pip install --upgrade pip setuptools wheel`，再 `python -m pip install .`。开发用 `python -m pip install -e .`；Python 3.8 自带的旧 pip/setuptools 可能不支持 pyproject editable，必须先升级。无需安装也可运行 `PYTHONPATH=src python -m oiblogscore.cli --help`（POSIX）。Windows PowerShell 激活命令是 `.venv\Scripts\Activate.ps1`。建议设置 `PYTHONUTF8=1`（PowerShell: `$env:PYTHONUTF8=1`），使中文、`²` 等字符在旧代码页控制台下不会中断工具的 JSON 输出。

## 常见环境问题

- **core.autocrlf**：Windows Git 默认 `core.autocrlf=true` 时，工作区 CRLF 与 HEAD blob 的 LF 字节不同。CLI 为保护作者修改会按字节判为 dirty，`repair` 跳过并在 `.oiblogscore/repair-run.json` 记录 `core.autocrlf=...`；这不是“修复成功”。需要自动修复时，在该仓库设置 `core.autocrlf=false` 并重新 checkout，或仅审查。不要用 Git 归一化结果替代字节核对。
- **core.fileMode=false**：WSL 的 DrvFs 等文件系统不保留可执行位；当仓库声明该配置时，CLI 忽略可执行位差异，不把 100644 文件误判为 dirty。
- **Windows 路径**：Git Bash 的 `/tmp/...` 不是原生 Python 路径；传给 `--result`、`--path` 前用 `cygpath -w` 转换。CLI 拒绝前导 `/`、盘符、UNC、`..`、`.git`、保留名和尾点/空格。
- **CLI 不在 PATH**：在 checkout 内用 `PYTHONPATH=src python -m oiblogscore.cli ...`；仍不可用时，按 Skill 的只读降级流程记录 `NOT_CHECKED`/`NEEDS_CONTEXT`，不要伪造机械校验。

按宿主配置复制完整 Skill 目录，例如 Codex `~/.agents/skills/`、Claude Code `~/.claude/skills/`，或放入项目级对应目录。仓库级编排应安装全部九个。保持 CLI 对 Agent 的 PATH 可见。各 Skill 的本地链接均封装在自身目录；技术 Skills 可选用共享算法库。给宿主提供 OIBlogScore checkout 路径，并在执行 CLI 的环境中设置 `OIBLOGSCORE_REFERENCE_ROOT=/absolute/path/to/OIBlogScore`，使其指纹包含该 checkout 的 `skills/` 与 `resources/`。不设环境变量且规则位于被审仓库外时，更新规则后递增目标仓库 `rule_version` 或全量重查。

升级时更新 checkout、重新安装 CLI 和覆盖 Skill 目录。卸载 CLI 用 `pip uninstall oiblogscore`；可以移除已安装的 Skill。**不要盲目删除 `.oiblogscore/`**：其中可能有唯一的修复备份和用于回滚的记录。


Wheel 只安装 Python CLI 与精确文字修复规则，不打包 Skills、Catalog 和上游正文。安装后可在 checkout 外运行 `oiblogscore --help`；目录检索从保存的可信 checkout 运行 `python tools/catalog.py stats`。不要把被审仓库的副本当作可信规则根。安装完成后可按 [可复跑工作流](docs/audit-workflow.md) 验证入口、队列及报告。

发布包验收可先运行 `python -m pip wheel --no-deps --wheel-dir wheelhouse .`，再从全新虚拟环境执行 `python -m pip install --no-index --find-links wheelhouse oiblogscore`。前者可能需要联网下载构建依赖，后者只需 wheel；editable 用于开发，不是 wheel 隔离验证。源码 checkout 单独提供 Catalog、Skill 和上游快照；不承诺 sdist 内包含这些编目资料。
