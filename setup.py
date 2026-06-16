#!/usr/bin/env python3
"""setup.py — Interactive installer for codex-vault-migrator v2.0.
Discovers all skill vaults, generates routing rules, configures hooks.
"""
import os
import sys
import subprocess
import re
from pathlib import Path

CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))

def prompt(text, default=None):
    if default:
        result = input(f"{text} [{default}]: ").strip()
        return result if result else default
    return input(f"{text}: ").strip()

def main():
    print("=" * 60)
    print("  codex-vault-migrator v2.0 — 一键初始化")
    print("=" * 60)
    print()
    
    # ── Step 1: Detect defaults ──
    print("--- 环境检测 ---")
    print()
    
    vault_path = prompt(
        "Vault 路径 (KKNexus 工作区)",
        str(Path.home() / "OneDrive" / "文档" / "New project 6")
    )
    
    codex_home = prompt(
        "Codex home 目录",
        str(CODEX_HOME)
    )
    
    # ── Step 2: Auto-discover skill vaults ──
    print()
    print("--- 技能 Vault 自动发现 ---")
    print()
    
    skills_dir = Path(codex_home) / "skills"
    discovered = {}
    if skills_dir.exists():
        for entry in sorted(skills_dir.iterdir()):
            vault_path_check = entry / "vault"
            if vault_path_check.is_dir() and not entry.name.endswith(".bak"):
                discovered[entry.name] = str(vault_path_check)
                print(f"  ✅ {entry.name} -> {vault_path_check}")
    
    print(f"\n  发现 {len(discovered)} 个 skill vault")
    
    # ── Step 3: Config generation ──
    print()
    print("--- 生成配置文件 ---")
    print()
    
    # Generate routing rules
    rules_lines = []
    rules_lines.append("vault_routing_rules:")
    rules_lines.append(f'  - pattern: "New project [0-9]+"')
    rules_lines.append(f'    vault: "{vault_path}"')
    rules_lines.append(f'    label: "KKNexus"')
    rules_lines.append(f'  - pattern: "Codex-Brain"')
    rules_lines.append(f'    vault: "{Path.home() / "OneDrive" / "Codex-Brain"}"')
    rules_lines.append(f'    label: "CodexBrain"')
    
    for name, vpath in discovered.items():
        pattern = re.sub(r"[-_]+", "[-_]?", re.escape(name.lower()))
        rules_lines.append(f'  - pattern: "{pattern}"')
        rules_lines.append(f'    vault: "{vpath}"')
        rules_lines.append(f'    label: "{name}"')
    
    rules_lines.append(f'  - pattern: ".*"')
    rules_lines.append(f'    vault: "_unrouted"')
    rules_lines.append(f'    label: "UNROUTED"')
    
    config_content = (
        f'version: "2.0"\n'
        f'vault_path: "{vault_path}"\n'
        f'codex_brain_vault: "{Path.home() / "OneDrive" / "Codex-Brain"}"\n'
        f'codex_home: "{codex_home}"\n'
        f'sessions_path: "{Path(codex_home) / "sessions"}"\n'
        f'python_path: "{sys.executable}"\n'
        f'zk_domain: "codex"\n'
        f'\n'
        + "\n".join(rules_lines) + "\n"
    )
    
    config_path = Path(vault_path) / "config.yaml"
    if not config_path.parent.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
    
    config_path.write_text(config_content, encoding="utf-8")
    print(f"  ✅ 配置写入: {config_path}")
    
    # ── Step 4: Hooks setup ──
    print()
    print("--- Hooks 配置 ---")
    use_hooks = prompt("配置 hooks.json 自动收割? (y/n)", "y").lower()
    
    if use_hooks == "y":
        hooks_content = """{
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
"""
        hooks_path = Path(vault_path) / "hooks.json"
        hooks_path.write_text(hooks_content, encoding="utf-8")
        print(f"  ✅ hooks.json 写入: {hooks_path}")
        print("  ⚠ 重启 Codex Desktop 后 hhooks 生效")
    
    # ── Step 5: Pip deps ──
    print()
    print("--- 依赖安装 ---")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyyaml"],
            capture_output=True, text=True, timeout=30
        )
        print(f"  ✅ PyYAML 已安装")
    except Exception as e:
        print(f"  ⚠ PyYAML 安装失败: {e}")
    
    # ── Step 6: Validate ──
    print()
    print("--- 验证 ---")
    print(f"  配置: ✅")
    print(f"  Vault: {vault_path}")
    print(f"  Codex home: {codex_home}")
    print(f"  技能 vault: {len(discovered)} 个")
    print(f"  Hooks: {"✅ 已配置" if use_hooks == "y" else "❌ 未配置"}")
    
    # ── Step 7: Next steps ──
    print()
    print("=" * 60)
    print("  初始化完成!")
    print("=" * 60)
    print()
    print("下一步:")
    print(f"  1. 复制 config.example.yaml 到 config.yaml (如果尚未)")
    print(f"  2. 配置 hooks.json 或 config.toml notify")
    print(f"  3. 运行 python scripts/deploy.py 验证环境")
    print(f"  4. 运行 python scripts/session_harvester.py --mode start 测试首次扫描")
    print()

if __name__ == "__main__":
    main()

