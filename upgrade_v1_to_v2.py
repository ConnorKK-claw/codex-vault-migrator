#!/usr/bin/env python3
"""upgrade_v1_to_v2.py — Migrate from v1.0 to v2.0.
Handles: config migration, dep installation, heartbeat format migration.
"""
import os
import sys
import shutil
from pathlib import Path

def main():
    project_root = Path(os.path.dirname(os.path.abspath(__file__)))
    print("=" * 50)
    print("  codex-vault-migrator v1.0 → v2.0 升级")
    print("=" * 50)
    print()
    
    # Step 1: Detect v1.0
    ps1_path = project_root / "scripts" / "legacy" / "deploy-checklist.ps1"
    if not ps1_path.exists():
        ps1_path = project_root / "scripts" / "deploy-checklist.ps1"
    
    if ps1_path.exists():
        print("  ✅ 检测到 v1.0 安装 (deploy-checklist.ps1 存在)")
    else:
        print("  ⚠ 未检测到 v1.0 文件，可能是全新安装")
    
    # Step 2: Check config
    config_path = project_root / "config.yaml"
    if not config_path.exists():
        print("  ⚠ 未找到 config.yaml (新安装需要先运行 setup.py)")
        yn = input("  继续? (y/n): ").lower()
        if yn != "y":
            print("  取消升级")
            return
    
    # Step 3: Migrate heartbeat format (old: {sid: size} → new: {sid:size: timestamp})
    vault_path = None
    try:
        sys.path.insert(0, str(project_root / "scripts"))
        from config import load_config
        cfg = load_config()
        vault_path = cfg.get("vault_path", "")
    except Exception as e:
        print(f"  ⚠ 配置加载失败: {e}")
        vault_path = input("  输入 vault 路径: ").strip()
    
    if vault_path and os.path.exists(vault_path):
        heartbeat_path = os.path.join(vault_path, "heartbeat.md")
        if os.path.exists(heartbeat_path):
            _migrate_heartbeat(heartbeat_path)
    
    # Step 4: Install deps
    print()
    print("--- 安装依赖 ---")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyyaml"],
            capture_output=True, text=True, timeout=30
        )
        print("  ✅ PyYAML 已安装")
    except Exception as e:
        print(f"  ⚠ PyYAML 安装失败: {e}")
    
    # Step 5: Validate
    print()
    print("--- 验证 ---")
    v2_files = [
        "scripts/session_harvester.py",
        "scripts/deploy.py",
        "scripts/notify_dispatcher.py",
        "setup.py",
        "hooks.json",
    ]
    for f in v2_files:
        fp = project_root / f
        if fp.exists():
            print(f"  ✅ {f}")
        else:
            print(f"  ⚠ {f} 缺失")
    
    print()
    print("=" * 50)
    print("  升级完成!")
    print("=" * 50)
    print("  v2.0 新增文件: hooks.json, setup.py, scripts/session_harvester.py, ...")
    print("  v1.0 保留文件: scripts/deploy-checklist.ps1 (legacy/)")
    print("  如需回滚: python rollback-v2.py")
    print()

def _migrate_heartbeat(heartbeat_path):
    """Migrate old processed_sessions format to new composite key format."""
    import yaml
    from datetime import datetime
    
    try:
        with open(heartbeat_path, "r", encoding="utf-8") as f:
            content = f.read()
        parts = content.split("---", 2)
        if len(parts) < 3:
            return
        fm = yaml.safe_load(parts[1]) or {}
        old_processed = fm.get("processed_sessions", {})
        
        # Check if already migrated
        first_key = next(iter(old_processed.keys()), "")
        if ":" in first_key:
            print("  ✅ heartbeat 格式已是最新 (复合键)")
            return
        
        # Migrate: {sid: size} → {sid:size: timestamp}
        new_processed = {}
        for sid, size in old_processed.items():
            key = f"{sid}:{size}"
            new_processed[key] = datetime.now().isoformat()
        
        fm["processed_sessions"] = new_processed
        fm["migrated_at"] = datetime.now().isoformat()
        fm["migration_version"] = "2.0"
        
        fm_yaml = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
        body = parts[2] if len(parts) > 2 else "\n"
        new_content = f"---\n{fm_yaml}---\n{body}"
        
        tmp = heartbeat_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(new_content)
        os.replace(tmp, heartbeat_path)
        print(f"  ✅ heartbeat 格式已迁移 (复合键)")
    except Exception as e:
        print(f"  ⚠ heartbeat 迁移失败: {e}")

if __name__ == "__main__":
    import subprocess
    main()
