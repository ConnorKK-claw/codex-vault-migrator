---
name: codex-vault-migrator
version: 1.0.0
description: |
  Cross-device Codex-Brain vault migration and deployment skill.
  Guides the user through the complete process of setting up a new device
  with OneDrive-synced vault, Directory Junctions, and all skill dependencies.
---

# codex-vault-migrator — 跨设备 Codex-Brain Vault 迁移

## 触发条件

当用户表达以下意图时，激活本 Skill：
- "新设备" / "搬家" / "部署 setup" / "迁移 vault"
- "换了新电脑，要配 Codex-Brain"
- 检测到 `~\.codex\skills\` 下缺少指向 `OneDrive\Codex-Brain\02-技能-vaults` 的 Junction

## 架构概览

```
OneDrive 云端
    │
    ├── Codex-Brain\               ← vault：技能知识库 + 系统配置 + 记忆（双向同步）
    └── 文档\New project N\        ← CLI 工作区：txtai 索引 + 本地记忆（双向同步）

本地设备（每台独立）
    ├── ~\.codex\config.toml       ← 模型配置、API 地址（不同步）
    ├── ~\.codex\skills\{name}     ← Junction → OneDrive\Codex-Brain\02-技能-vaults\{name}
    ├── D:\CCX\                    ← 本地 API 代理（不同步）
    └── ~\.cc-switch\              ← CC-Switch 缓存（不同步）
```

## 使用流程

### Phase A: 环境准备（引导用户操作）

执行 `scripts\deploy-checklist.ps1` 检查环境，逐项验证：

1. 确认 Windows 11/10
2. 确认 OneDrive 已登录并 vault 同步完成
3. 确认 Node.js ≥ v18、Python ≥ 3.10
4. 确认 PowerShell 执行策略可用
5. 确认管理员权限或 mklink 替代方案

对每一项，如果缺失则输出修复命令。

### Phase B: 自动化部署（引导执行）

6. 引导用户以管理员身份运行 vault 中的部署脚本：
   ```powershell
   Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$env:USERPROFILE\OneDrive\Codex-Brain\00-系统配置\codex-brain-deploy-v5.ps1`""
   ```

7. 如需补建 Junction，提供 mklink 命令模板：
   ```cmd
   mklink /J "C:\Users\%USERNAME%\.codex\skills\技能名" "C:\Users\%USERNAME%\OneDrive\Codex-Brain\02-技能-vaults\技能名"
   ```

### Phase C: 依赖安装（引导执行）

8. Python 依赖：`pip install txtai`
9. npm 依赖：`cmd /c "cd /d \"%USERPROFILE%\.codex\skills\imap-smtp-email\" && npm install"`

### Phase D: 应用配置（引导操作）

10. Codex Desktop 添加项目：`OneDrive\Codex-Brain` + `OneDrive\文档\New project N`
11. Obsidian 打开 vault：`OneDrive\Codex-Brain`

### Phase E: 验收

12. 运行验收脚本 `scripts\deploy-checklist.ps1`，输出最终状态

## 已知故障

| 现象 | 根因 | 解法 |
|---|---|---|
| 脚本报非管理员 | Codex 子进程无管理员令牌 | 手动 `Start-Process -Verb RunAs`；或降级用 `mklink /J` |
| 文件访问超时 | OneDrive Files On-Demand 占位符 | `attrib +U "路径" /S` 强制下载 |
| 脚本无法运行 | PowerShell 执行策略 Restricted | 加 `-ExecutionPolicy Bypass` 参数 |
| npm 报错 | npm.ps1 被策略拦截 | 用 `cmd /c npm` 或 `npm.cmd` |
| Obsidian 卡死 | 15,000+ 文件索引 | 等同步完成，关不必要插件 |

## 同步范围

| 内容 | 跨设备同步 | 说明 |
|---|---|---|
| `OneDrive\Codex-Brain\` | ✅ 双向同步 | vault 核心 |
| `OneDrive\文档\New project N\` | ✅ 双向同步 | CLI 工作区（Documents 重定向到 OneDrive） |
| `~\.codex\*` (config, sessions, auth) | ❌ 本机独有 | 每台设备独立 |
| `D:\CCX\` | ❌ 本机独有 | 代理服务 |
| 定时任务 | ❌ 本机独有 | schtasks / crontab |
| Obsidian 个性化设置 | ❌ 本机独有 | `%APPDATA%\Obsidian\` |
