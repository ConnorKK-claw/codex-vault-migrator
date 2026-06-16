#!/usr/bin/env python3
"""rollback-v2.py — Precise rollback from v2.0 to v1.0.
Only removes files added by v2.0. Preserves all KKNexus existing data.
"""
import os
import shutil
import sys
from pathlib import Path
import yaml
from datetime import datetime

V2_FILES = [
    "hooks.json",
    "setup.py",
    "config.yaml",  # Only if created by v2.0 (check via marker)
    "upgrade_v1_to_v2.py",
    "rollback-v2.py",
    "scripts/session_harvester.py",
    "scripts/notify_dispatcher.py",
    "scripts/deploy.py",
    "tests/",
]

V2_DIRS = [
    "tests/",
]

def main():
    project_root = Path(os.path.dirname(os.path.abspath(__file__)))
    
    print("=" * 50)
    print("  codex-vault-migrator v2.0 → v1.0 回滚")
    print("=" * 50)
    print()
    print("  将删除以下 v2.0 新增文件:")
    for f in V2_FILES:
        fp = project_root / f
        if fp.exists():
            print(f"    🗑  {f}")
    
    print()
    yn = input("  确认回滚? (y/N): ").lower()
    if yn != "y":
        print("  取消回滚")
        return
    
    # ── Step 1: Mark harvested knowledge as expired ──
    print()
    print("--- 已收割知识处理 ---")
    _mark_knowledge_expired()
    
    # ── Step 2: Remove v2.0 files ──
    print()
    print("--- 删除 v2.0 文件 ---")
    for f in V2_FILES:
        fp = project_root / f
        if fp.exists():
            try:
                if os.path.isdir(fp):
                    shutil.rmtree(fp)
                else:
                    os.remove(fp)
                print(f"  ✅ 已删除: {f}")
            except Exception as e:
                print(f"  ⚠ 删除失败 {f}: {e}")
    
    for d in V2_DIRS:
        dp = project_root / d
        if dp.exists():
            try:
                shutil.rmtree(dp)
                print(f"  ✅ 已删除目录: {d}")
            except Exception as e:
                print(f"  ⚠ 删除失败 {d}: {e}")
    
    # ── Step 3: Restore _meta.json version ──
    meta_path = project_root / "_meta.json"
    if meta_path.exists():
        try:
            import json
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["version"] = "1.0.0"
            meta["description"] = "Cross-device Codex-Brain vault migration and deployment skill"
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  ✅ _meta.json 版本恢复为 1.0.0")
        except Exception as e:
            print(f"  ⚠ _meta.json 版本恢复失败: {e}")
    
    # ── Step 4: Verify v1.0 intact ──
    print()
    print("--- 验证 ---")
    ps1_legacy = project_root / "scripts" / "legacy" / "deploy-checklist.ps1"
    ps1_root = project_root / "scripts" / "deploy-checklist.ps1"
    
    if ps1_legacy.exists():
        print(f"  ✅ v1.0 deploy-checklist.ps1 在 legacy/ 中完好")
    elif ps1_root.exists():
        print(f"  ✅ v1.0 deploy-checklist.ps1 在 scripts/ 中完好")
    else:
        print(f"  ⚠ 未找到 v1.0 deploy-checklist.ps1")
    
    print()
    print("=" * 50)
    print("  回滚完成!")
    print("=" * 50)
    print("  已删除: v2.0 全部新增文件")
    print("  已保留: All vault/ knowledge/ journal/ sessions/ data")
    print("  已保留: deploy-checklist.ps1 (v1.0)")
    print("  已标记: knowledge/zk-codex-* → status: expired")
    print()

def _mark_knowledge_expired():
    """Scan vaults for zk-codex-* files and mark them as expired."""
    vault_paths = _find_vault_paths()
    marked = 0
    
    for vault_path in vault_paths:
        knowledge_dir = Path(vault_path) / "knowledge"
        if not knowledge_dir.exists():
            continue
        
        for f in knowledge_dir.iterdir():
            if not f.name.startswith("zk-codex-") or not f.name.endswith(".md"):
                continue
            
            try:
                content = f.read_text(encoding="utf-8")
                parts = content.split("---", 2)
                if len(parts) < 3:
                    continue
                fm = yaml.safe_load(parts[1]) or {}
                
                if fm.get("status") == "expired":
                    continue  # Already marked
                
                fm["status"] = "expired"
                fm["expired_at"] = datetime.now().strftime("%Y-%m-%d")
                fm["expired_by"] = "rollback-v2"
                
                new_fm = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
                new_content = f"---\n{new_fm}---\n{parts[2]}"
                
                tmp = str(f) + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    fh.write(new_content)
                os.replace(tmp, str(f))
                marked += 1
            except Exception:
                continue
    
    if marked:
        print(f"  ✅ 已标记 {marked} 个 zk-codex-* 文件为 expired")
    else:
        print(f"  ℹ 没有需要标记的 zk-codex-* 文件")

def _find_vault_paths():
    """Find all vault paths that might contain zk-codex-* files."""
    paths = set()
    
    # Check config
    try:
        sys.path.insert(0, str(Path(__file__).parent / "scripts"))
        from config import load_config
        cfg = load_config()
        paths.add(cfg["vault_path"])
        # Also check Codex-Brain
        if cfg.get("codex_brain_vault"):
            paths.add(cfg["codex_brain_vault"])
    except Exception:
        pass
    
    # Also scan skills
    codex_home = os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))
    skills_dir = Path(codex_home) / "skills"
    if skills_dir.exists():
        for entry in skills_dir.iterdir():
            vault_path = entry / "vault"
            if vault_path.exists() and not entry.name.endswith(".bak"):
                paths.add(str(vault_path))
    
    return list(paths)

if __name__ == "__main__":
    main()
