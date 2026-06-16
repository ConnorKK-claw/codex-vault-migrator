"""Step 5 (adapted): Compile -> vault/knowledge/ + vault/templates/ + index rebuild.
v2.0 adaptation: routes index rebuild to KKNexus unified_index.py with lock file.
"""
import os
import yaml
import subprocess
from datetime import datetime

RULES_START = "<!-- COMPILED:RULES_START -->"
RULES_END = "<!-- COMPILED:RULES_END -->"
PROJECTS_START = "<!-- COMPILED:PROJECTS_START -->"
PROJECTS_END = "<!-- COMPILED:PROJECTS_END -->"
INDEX_LOCK = ".index.lock"

def run(cfg, dry_run=False, step_results=None):
    vault = cfg.get("vault_path", "")
    claude_md_path = cfg.get("claude_md_path", "")
    results = {"rules_compiled": 0, "projects_compiled": 0, "dirty": False}
    
    # ── Part A: CLAUDE.md compilation (optional, Claude Code only) ──
    if claude_md_path and os.path.exists(claude_md_path):
        try:
            with open(claude_md_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            markers_ok = all(m in content for m in [RULES_START, RULES_END, PROJECTS_START, PROJECTS_END])
            if markers_ok:
                rules_text = compile_rules_section(vault)
                projects_text = compile_projects_section(vault)
                new_content = replace_block(content, RULES_START, RULES_END, rules_text)
                new_content = replace_block(new_content, PROJECTS_START, PROJECTS_END, projects_text)
                
                if not dry_run:
                    tmp_path = claude_md_path + ".tmp"
                    with open(tmp_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    os.replace(tmp_path, claude_md_path)
                
                results["rules_compiled"] = rules_text.count("\n")
                results["projects_compiled"] = projects_text.count("\n")
        except Exception as e:
            results["claude_md_error"] = str(e)
    
    # ── Part B: Index rebuild (KKNexus unified_index.py) ──
    if vault:
        rebuild_indexes(vault, dry_run)
    
    return results


def rebuild_indexes(vault_path, dry_run=False):
    """Rebuild KKNexus unified_index.py safely with lock file."""
    lock_file = os.path.join(vault_path, INDEX_LOCK)
    
    # Check lock
    if os.path.exists(lock_file):
        try:
            mtime = os.path.getmtime(lock_file)
            if (datetime.now().timestamp() - mtime) > 3600:
                os.remove(lock_file)  # Stale lock (> 1 hour)
            else:
                print("  ⚠ Index rebuild already in progress, skipping")
                return
        except OSError:
            pass
    
    if dry_run:
        print("  [dry-run] Would rebuild indexes")
        return
    
    try:
        # Write lock
        with open(lock_file, "w") as f:
            f.write(datetime.now().isoformat())
        
        # Try KKNexus unified_index.py
        script_dir = os.path.join(vault_path, "scripts")
        unified_idx = os.path.join(script_dir, "unified_index.py")
        build_idx = os.path.join(script_dir, "build_index.py")
        
        if os.path.exists(unified_idx):
            result = subprocess.run(
                [sys.executable, unified_idx, "--refresh"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                print(f"  Index rebuild: unified_index.py OK")
            else:
                print(f"  WARNING: unified_index.py: {result.stderr[:200]}")
        elif os.path.exists(build_idx):
            result = subprocess.run(
                [sys.executable, build_idx, vault_path],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                print(f"  Index rebuild: build_index.py OK")
            else:
                print(f"  WARNING: build_index.py: {result.stderr[:200]}")
        else:
            print("  ⚠ No index script found (unified_index.py or build_index.py), skipping rebuild")
    except subprocess.TimeoutExpired:
        print("  WARNING: Index rebuild timed out")
    except Exception as e:
        print(f"  WARNING: Index rebuild failed: {e}")
    finally:
        # Release lock
        try:
            if os.path.exists(lock_file):
                os.remove(lock_file)
        except OSError:
            pass


def compile_rules_section(vault):
    rules_dir = os.path.join(vault, "00-Rules") if vault else ""
    if not rules_dir or not os.path.exists(rules_dir):
        return "| Rule ID | Title | Category | Applies To | Status |\n|---------|-------|----------|------------|--------|"
    
    lines = ["| Rule ID | Title | Category | Applies To | Status |",
             "|---------|-------|----------|------------|--------|"]
    
    for f in sorted(os.listdir(rules_dir)):
        if not f.endswith(".md") or f.startswith("_"):
            continue
        fp = os.path.join(rules_dir, f)
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                content = fh.read()
            fm = yaml.safe_load(content.split("---")[1])
            if fm.get("status") in ("active", "beta"):
                rule_id = fm.get("rule_id", "?")
                title = fm.get("title", "?")
                category = fm.get("category", "?")
                applies = ", ".join(fm.get("applies_to", []))
                status = fm.get("status", "?")
                lines.append(f"| {rule_id} | {title} | {category} | {applies} | {status} |")
        except (yaml.YAMLError, IndexError):
            continue
    
    return "\n".join(lines)


def compile_projects_section(vault):
    projects_dir = os.path.join(vault, "01-Projects") if vault else ""
    if not projects_dir or not os.path.exists(projects_dir):
        return "| Project | Decisions | Pitfalls | Last Session |\n|---------|-----------|----------|-------------|"
    
    lines = ["| Project | Decisions | Pitfalls | Last Session |",
             "|---------|-----------|----------|-------------|"]
    
    for proj in sorted(os.listdir(projects_dir)):
        proj_path = os.path.join(projects_dir, proj)
        if not os.path.isdir(proj_path):
            continue
        decisions_path = os.path.join(proj_path, "Memory", "decisions.md")
        pitfalls_path = os.path.join(proj_path, "Memory", "pitfalls.md")
        sessions_dir = os.path.join(proj_path, "Memory", "sessions")
        
        n_decisions = count_items(decisions_path, "decisions")
        n_pitfalls = count_items(pitfalls_path, "pitfalls")
        last_session = get_latest_session(sessions_dir)
        
        lines.append(f"| {proj} | {n_decisions} | {n_pitfalls} | {last_session} |")
    
    return "\n".join(lines)


def replace_block(content, start_marker, end_marker, new_content):
    before = content.split(start_marker)[0]
    after = content.split(end_marker)[1]
    return before + start_marker + "\n" + new_content + "\n" + end_marker + after


def count_items(path, key):
    if not os.path.exists(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        fm = yaml.safe_load(content.split("---")[1])
        return len(fm.get(key, [])) if isinstance(fm, dict) else 0
    except (yaml.YAMLError, IndexError, AttributeError):
        return 0


def get_latest_session(sessions_dir):
    if not os.path.exists(sessions_dir):
        return "-"
    files = [f for f in os.listdir(sessions_dir) if f.endswith(".md") and not f.startswith("_")]
    return sorted(files)[-1][:10] if files else "-"
