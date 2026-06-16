# codex-vault-migrator v2.0

跨设备 Codex-Brain vault 迁移、部署与会话知识收割系统。

## v2.0 新增功能

- **会话知识自动收割**：通过 hooks.json (PostToolUse) 或 
otify (turn-ended) 自动从 Codex 会话中提取 [DECISION:] / [ERROR:] 标注
- **多 Vault 路由**：可配置正则路由表，按会话工作目录自动分配到对应 skill 的知识库
- **分析管道**：6 个 Python 脚本组成的完整分析流水线（备份 → 关键词筛选 → 规则维护 → 报告 → 索引编译）
- **幂等收割**：session_id:file_size 复合键防止重复写入
- **一键初始化**：setup.py 自动发现全部 11+ 个 skill vault 并生成路由规则
- **跨平台**：核心逻辑从 PowerShell 迁移为 Python，支持 Windows/macOS/Linux

## 快速安装

`ash
git clone https://github.com/ConnorKK-claw/codex-vault-migrator.git
cd codex-vault-migrator
pip install pyyaml
python setup.py
`

## License

MIT
