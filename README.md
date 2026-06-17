# Codex Vault Migrator (v2.0)

跨设备 Codex-Brain vault 迁移、部署与会话知识自动收割系统。

将 Codex Desktop 会话中的决策、错误、原则自动提取并路由至对应 skill vault，经由 OneDrive 实现跨设备知识同步，构建持续学习的知识管理系统。

---

## v2.0 新增特性

### 核心能力

| 特性 | 说明 |
|---|---|
| **自动知识收割** | 每次 Codex 工具调用结束后，自动从会话 JSONL 中提取 `[DECISION:]`、`[ERROR:]`、`[SESSION_SUMMARY]` 标注，写入目标 vault |
| **多 vault 路由** | 基于可配置的正则规则，按会话原始工作目录（cwd）自动路由至对应技能 vault。支持 11+ 个 skill 知识库 |
| **增量同步与幂等** | `session_id:file_size` 复合键确保同一会话不会被重复收割，无论触发多少次 |
| **跨平台部署** | Windows / macOS / Linux 统一支持。核心逻辑全部使用 Python，消除 PowerShell 执行策略限制 |
| **一键安装** | `setup.py` 交互式安装器自动发现 `~/.codex/skills/` 下所有含 `vault/` 的 skill，生成完整路由规则 |

### 系统架构

```
Codex Desktop 会话
    │ hooks.json: PostToolUse (匹配 shell 类工具后触发)
    ▼
scripts/session_harvester.py
    ├─ ① 提取 session_meta（固定原始 cwd，防 skill 嵌套路由错乱）
    ├─ ② 正则解析 [DECISION:] / [ERROR:] / [SESSION_SUMMARY]
    ├─ ③ resolve_target_vault() 按路由规则写入目标 vault
    │     ~/.codex/skills/{name}/vault/knowledge/zk-codex-*
    │     ~/.codex/skills/{name}/vault/journal/YYYY-MM-DD.md
    └─ ④ 标记已处理（heartbeat.md 复合键）
    │
    ▼ (可选)
scripts/runner.py --full  (每日全量分析管道)
    ├─ backup.py    → 增量备份会话
    ├─ analyzer.py  → 关键词筛选 + 启发式根因分析
    ├─ maintainer.py → 规则生命周期管理
    ├─ reporter.py  → 学习叙事周报
    └─ compiler.py  → 索引重建 (unified_index.py + index.lock 防并发)
    │
    ▼
OneDrive 同步 → 跨设备知识可用
```

### 配置示例

```yaml
# config.yaml — vault_routing_rules 片段
vault_routing_rules:
  # 通用知识路由：会话在 KKNexus 或 Codex-Brain 工作区中
  - pattern: "New project [0-9]+"
    vault: "%CODEX_HOME%/skills/equity-incentive/vault"
    label: "equity-incentive"
  - pattern: "Codex-Brain"
    vault: "%CODEX_HOME%/skills/equity-incentive/vault"
    label: "equity-incentive"

  # 技能专用路由：cwd 包含技能名称时写入对应 vault
  - pattern: "equity[-_]?incentive"
    vault: "%CODEX_HOME%/skills/equity-incentive/vault"
    label: "equity-incentive"
  - pattern: "tax[-_]?compliance"
    vault: "%CODEX_HOME%/skills/tax-compliance-expert/vault"
    label: "tax-compliance-expert"
  - pattern: "financial[-_]?analysis"
    vault: "%CODEX_HOME%/skills/financial-analysis/vault"
    label: "financial-analysis"
  - pattern: "hk[-_]?ipo"
    vault: "%CODEX_HOME%/skills/hk-ipo/vault"
    label: "hk-ipo"
  - pattern: "a[-_]?share[-_]?research"
    vault: "%CODEX_HOME%/skills/a-share-research/vault"
    label: "a-share-research"
  - pattern: "engineering[-_]?practices"
    vault: "%CODEX_HOME%/skills/engineering-practices/vault"
    label: "engineering-practices"
  - pattern: "ima[-_]?knowledge"
    vault: "%CODEX_HOME%/skills/ima-knowledge/vault"
    label: "ima-knowledge"

  # 默认降级：未匹配规则的会话，知识不丢失
  - pattern: ".*"
    vault: "_unrouted"
    label: "UNROUTED"
```

---

## 安装

### 前置条件

| 条件 | 最低版本 | 验收方式 |
|---|---|---|
| Python | ≥ 3.10 | `python --version` |
| Codex Desktop | 任意版本 | 确保 `~/.codex/sessions/` 存在 |
| OneDrive | 已登录 | 确保 vault 可跨设备同步 |
| (Windows) NTFS | — | Directory Junction 功能 |

### 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/ConnorKK-claw/codex-vault-migrator.git
cd codex-vault-migrator

# 2. 安装依赖
pip install pyyaml

# 3. 一键初始化（自动发现所有 skill vault、生成路由规则、配置 options）
python setup.py

# 4. 将 hooks.json 放置于 Codex Desktop 项目工作区根目录
#    如 ~/OneDrive/文档/New project 6/hooks.json
#    或 ~/OneDrive/Codex-Brain/hooks.json

# 5. 重启 Codex Desktop 完成集成
```

---


> ⚠️ **重要：notify 单槽限制**：如果 `~/.codex/config.toml` 中已有 `notify` 配置（如 `computer-use.exe` 占用），
> 需创建链式调度 bat 脚本：先执行原程序，再执行 `notify_dispatcher.py`。详见故障排除章节。

### 配置 AGENTS.md 标注输出

Codex Agent 不会自动输出 `[DECISION:]` / `[ERROR:]` 标记。**必须**在项目的 `AGENTS.md` 中添加以下指令：

```markdown
## 会话知识收割协议

每次会话结束时输出以下内容：

```markdown
[SESSION_SUMMARY]
projects: [<project-slug>]
primary: <project-slug>
decisions:
  - <one-line summary>
    context: <why this choice>
errors:
  - type: <error-type>
    resolution: <how fixed>
[/SESSION_SUMMARY]
```

行内标注：

```
[DECISION: <一句话总结> | context: <为什么>]
[ERROR: type=<错误类型> | resolution=<怎么修的>]
```
```

将以上内容追加到 `~/.codex/AGENTS.md`（全局）或项目工作区的 `AGENTS.md` 中。否则 harvester 会持续输出 "提取到 0 条知识"。
## 使用方式

### 手动触发

```bash
# 收割最新会话（stop 模式）
python scripts/session_harvester.py --mode stop

# 扫描过去 48 小时内未处理的会话（start 模式）
python scripts/session_harvester.py --mode start

# 测试模式：在指定文件中检查提取效果
python scripts/session_harvester.py --mode test --file "~/.codex/sessions/2026/06/15/rollout-xxx.jsonl"
```

### 自动钩子

`hooks.json` 中的 `PostToolUse` 配置会在每次匹配到 shell 类工具执行后自动触发收割：

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "bash|command|execute|run|powershell",
        "hooks": [
          {
            "type": "command",
            "command": "python scripts/session_harvester.py --mode stop"
          }
        ]
      }
    ]
  }
}
```

### 每日全量分析

通过系统定时任务（Task Scheduler / crontab）调用每日深度分析管道：

```bash
# 全量 5 步分析：backup → analyze → maintain → report → compile
python scripts/runner.py --full

# 仅索引编译（适合已有分析结果的快速刷新）
python scripts/runner.py --step compile
```

---

## 测试

```bash
python -m unittest tests.test_harvester -v
```

覆盖 **16 个测试用例**，包括：

| 测试组 | 用例数 | 覆盖场景 |
|---|---|---|
| 会话元数据提取 | 3 | 正常 / 空 / 无 session_meta |
| 决策提取 | 3 | 正常 / 空会话 / skill 嵌套 |
| 错误提取 | 2 | 正常 / skill 嵌套 |
| 会话摘要提取 | 2 | 正常 / 空 |
| 幂等性 | 1 | `session_id:file_size` 复合键防重复 |
| vault 路由 | 3 | KKNexus / skill vault / UNROUTED fallback |
| 自动发现 | 2 | 真实 skill vault 扫描 / 路由规则生成 |

---

## 回滚

若需从 v2.0 回滚到 v1.0：

```bash
python rollback-v2.py
```

回滚操作：
- **删除** v2.0 新增文件：`hooks.json`、`setup.py`、`config.yaml`、`scripts/session_harvester.py`、`scripts/deploy.py`、`scripts/notify_dispatcher.py`、`upgrade_v1_to_v2.py`、`rollback-v2.py`、`tests/`
- **保留** v1.0 文件：`scripts/legacy/deploy-checklist.ps1`
- **标记** 已收割的 `zk-codex-*` 知识节点为 `status: expired`（知识不丢失，仅标记为不再维护）
- **恢复** `_meta.json` 版本号为 `1.0.0`

---

## v1.0 功能（历史）

v1.0 是一个轻量级环境检查工具，用于在全新 Windows 设备上快速验收 Codex-Brain vault 部署条件：

| 功能 | 说明 |
|---|---|
| **12 项环境检查** | 操作系统 / OneDrive / vault 同步 / Node.js / Python / txtai / Junction 完整性 / API 代理 / config.toml / npm 依赖 / Obsidian vault / mcp.json |
| **部署脚本** | `scripts/deploy-checklist.ps1`（Windows PowerShell 独占） |
| **平台支持** | Windows 11/10 独占 |
| **功能范围** | 仅检查不修复，输出 ✅/❌/⚠️ 状态报告 |

v1.0 的 `deploy-checklist.ps1` 已保留在 `scripts/legacy/` 目录中，可通过 `rollback-v2.py` 完整恢复。

---

## License

MIT

## 故障排除

### hooks 列表为空
- 确认 `hooks.json` 已复制到 Codex Desktop **项目工作区根目录**（如 `New project 6/hooks.json`）
- 重启 Codex Desktop 使其识别 hooks 文件
- 当前 Codex Desktop 的 `hooks.json` 机制可能需要特定版本支持

### 提取到 0 条知识
- 检查 `~/.codex/AGENTS.md` 是否包含「会话知识收割协议」中的标注输出指令
- 运行 `python scripts/session_harvester.py --mode test --file "~/.codex/sessions/2026/06/*/*.jsonl"` 验证提取逻辑
- 确认 config.yaml 中 `vault_path` 指向正确的工作区

### notify 已被占用
- 如果 `config.toml` 的 `notify` 已绑定其他程序（如 `computer-use.exe`）
- 创建 `turn_ended.bat` 链式调度器：同时执行原程序和 `notify_dispatcher.py`
- 将 `config.toml` 的 `notify` 指向该 bat 文件
- 参见 [notify 桥接说明](#安装)

### 会话路径不匹配
- 确认 `config.yaml` 中 `sessions_path` 留空（自动使用 `~/.codex/sessions/`）
- Codex 默认会话路径：`~/.codex/sessions/YYYY/MM/DD/*.jsonl`

