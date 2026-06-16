# codex-vault-migrator v2.0 Skill

## 触发条件

当用户表达以下意图时，激活本 Skill：
- "新设备" / "搬家" / "部署 setup" / "迁移 vault"
- "会话收割" / "知识收割" / "自动收割"
- "同步知识" / "跨设备同步"
- 检测到 ~/.codex/sessions/ 下有未处理的 JSONL 会话文件

## 架构

参见 README.md 中的四层架构图。

## 使用流程

### Phase A: 一键初始化
`ash
python setup.py
`

### Phase B: 配置 hooks
hooks.json 会在配置后自动触发每次工具调用后的知识收割。

### Phase C: 会话收割
`ash
python scripts/session_harvester.py --mode stop    # 收割最新会话
python scripts/session_harvester.py --mode start   # 扫描 48h 窗口
python scripts/session_harvester.py --mode test --file <path>  # 测试指定文件
`

### Phase D: 深度分析
`ash
python scripts/runner.py --full   # 全量分析流水线
`

## 已知故障

| 现象 | 根因 | 解法 |
|---|---|---|
| hooks.json 未触发 | Codex Desktop 未重启 | 重启 Codex Desktop |
| 收割无输出 | 会话中无 [DECISION:] / [ERROR:] 标注 | 正常行为，空会话自动跳过 |
| 路由到 _unrouted | cwd 未匹配任何路由规则 | 在 config.yaml 中新增路由条目 |
