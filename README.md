# codex-vault-migrator

跨设备 Codex-Brain vault 迁移与部署 Skill。

将一个已配置好的 OneDrive 同步知识库（vault）自动部署到新设备上，无需手动重建目录链接（Junction）和安装各项依赖。

## 适用场景

- 你在一台电脑上积累了 Codex 技能知识库（vault），换了一台新电脑
- 你的 vault 存放在 OneDrive 中，已登录同一 Microsoft 账号但尚未配置本地运行环境
- 你想把整个 Codex 工作环境从一台设备完整复制到另一台设备

## 核心架构

```
OneDrive 云端
    │
    ├── Codex-Brain/              ← vault（技能知识库，双向同步）
    └── 文档/New project N/       ← CLI 工作区（txtai 索引，双向同步）

本地设备（每台独立）
    ├── ~/.codex/config.toml      ← 模型配置、API 地址（不同步）
    ├── ~/.codex/skills/{name}    ← Junction → OneDrive/Codex-Brain/02-技能-vaults/{name}
    ├── ~/.codex/sessions/        ← Codex 会话历史（不同步）
    └── D:/CCX/                   ← 本地 API 代理（不同步）
```

## 前置条件

| # | 条件 | 验收方式 | 说明 |
|---|---|---|---|
| 1 | Windows 11 或 10 | `(Get-CimInstance Win32_OperatingSystem).Caption` | Directory Junction 是 NTFS 功能 |
| 2 | OneDrive 已登录同一账号 | `Get-Process OneDrive` | 确保 vault 数据可访问 |
| 3 | Vault 已同步到本地 | `Test-Path "$env:USERPROFILE\OneDrive\Codex-Brain\02-技能-vaults"` 为 `True` | 部署脚本的验证锚点 |
| 4 | PowerShell 5.1+ | `$PSVersionTable.PSVersion` | 脚本依赖 .NET API 创建 Junction |
| 5 | Node.js ≥ 18 | `node --version` → `v18.x.x+` | npm 依赖安装 |
| 6 | Python ≥ 3.10 | `python --version` → `Python 3.x.x+` | txtai 等 AI 依赖 |

## 使用方法

### 通过 Codex Desktop/CLI 安装

在 Codex 对话中输入：

```
帮我安装这个 skill：https://github.com/ConnorKK-claw/codex-vault-migrator
```

Codex 会自动克隆仓库到 `~/.codex/skills/codex-vault-migrator/` 并激活。

### 手动安装

```powershell
git clone https://github.com/ConnorKK-claw/codex-vault-migrator.git "$env:USERPROFILE\.codex\skills\codex-vault-migrator"
```

### 运行验收脚本

```powershell
Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$env:USERPROFILE\.codex\skills\codex-vault-migrator\scripts\deploy-checklist.ps1`""
```

脚本输出 12 项检查结果，通过数 ≥ 11 即表示环境就绪。

### 部署流程概要

| 阶段 | 操作 | 自动化程度 |
|---|---|---|
| 环境准备 | 安装 Obsidian / Node.js / Python | 人工操作 |
| Vault 同步 | 登录 OneDrive，等待同步完成 | 人工操作 |
| 自动化部署 | 运行 vault 中的部署脚本 | Skill 提供命令 |
| 依赖安装 | `pip install txtai` / `npm install` | Skill 代为执行 |
| 应用配置 | Codex Desktop 添加项目、Obsidian 打开 vault | 人工操作 |

## 同步范围

| 内容 | 跨设备同步 |
|---|---|
| `OneDrive/Codex-Brain/`（vault） | ✅ 双向同步 |
| `OneDrive/文档/New project N/`（CLI 工作区） | ✅ 双向同步（Documents 已重定向到 OneDrive） |
| `~/.codex/config.toml`（模型配置） | ❌ 本机独有 |
| `~/.codex/sessions/`（会话历史） | ❌ 本机独有 |
| `~/.codex/skills/{name}`（Junction 链接） | ❌ 链接本机独有，指向的 vault 内容已同步 |
| 系统定时任务（schtasks / crontab） | ❌ 本机独有 |
| API 代理服务（CCX） | ❌ 本机独有 |

## 已知故障

| 现象 | 根因 | 解法 |
|---|---|---|
| 脚本报"未以管理员身份运行" | Codex 子进程不继承管理员令牌 | 使用 `Start-Process -Verb RunAs` 手动提权；或降级使用 `mklink /J` |
| 文件访问超时 | OneDrive Files On-Demand 占位符未下载 | `attrib +U "路径" /S` 强制提前下载 |
| 脚本无法运行 | PowerShell 执行策略 Restricted | 加 `-ExecutionPolicy Bypass` 参数 |
| npm install 报错 | npm.ps1 被 PowerShell 执行策略拦截 | 使用 `cmd /c npm` 或 `npm.cmd` |
| Obsidian 首次加载卡死 | 海量文件索引 + OneDrive 占位符阻塞 | 等待同步完成，关闭不必要插件，清除 workspace 缓存 |

## 项目结构

```
codex-vault-migrator/
├── SKILL.md                       ← 使用引导（Codex 读取入口）
├── _meta.json                     ← 技能元数据
├── scripts/
│   └── deploy-checklist.ps1       ← 12 项环境验收脚本
└── assets/                        ← 预留资源
```

## 许可证

MIT
