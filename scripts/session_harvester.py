#!/usr/bin/env python3
"""
Session Harvester v2.0 — Codex-adapted.
Triggered by hooks.json (PostToolUse) or notify (turn-ended).

Extracts [DECISION:], [ERROR:], [SESSION_SUMMARY] from Codex session JSONL files
and routes them to the appropriate skill vault based on configurable regex rules.

Design principles:
- Never loses data: all writes are atomic (.tmp → rename)
- Never crashes: every step has try/except
- Works without proxy: no network calls in harvest phase
- Idempotent: session_id + file_size composite key prevents duplicates
- Multi-vault: resolves target vault from session_meta.cwd using regex routing table
- Safe for skill nesting: always reads original cwd from session_meta, not runtime cwd
"""
import os
import sys
import re
import json
import yaml
import shutil
import hashlib
import argparse
import glob as glob_mod
from datetime import datetime, timezone, timedelta
from config import load_config, resolve_target_vault

# ── Configuration defaults (overridden by config.yaml) ──────────
VAULT_PATH = None          # resolved from config
CODEX_HOME = None          # resolved from config
SESSIONS_PATH = None       # resolved from config
ZK_DOMAIN = "codex"        # Zettelkasten domain for harvested knowledge

# Local timezone (China Standard Time)
CST = timezone(timedelta(hours=8))


# ── Main ───────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Session Harvester v2.0 (Codex)")
    parser.add_argument("--mode", choices=["stop", "start", "test"], default="stop",
                       help="stop: harvest latest transcript. "
                            "start: scan for unprocessed transcripts (48h window). "
                            "test: run on a specific file (for testing).")
    parser.add_argument("--file", help="Specific JSONL file to process (for --mode test)")
    args = parser.parse_args()

    # Load config
    global VAULT_PATH, CODEX_HOME, SESSIONS_PATH
    try:
        cfg = load_config()
    except FileNotFoundError as e:
        print(f"[harvester] ERROR: {e}")
        return 1
    
    VAULT_PATH = cfg["vault_path"]
    CODEX_HOME = cfg.get("codex_home", os.path.expanduser("~/.codex"))
    SESSIONS_PATH = cfg.get("sessions_path", os.path.join(CODEX_HOME, "sessions"))

    if args.mode == "start":
        return start_mode(cfg)
    elif args.mode == "test":
        if not args.file:
            print("[harvester] ERROR: --file required for --mode test")
            return 1
        return test_mode(cfg, args.file)
    else:
        return stop_mode(cfg)


def stop_mode(cfg):
    """Stop hook: harvest the latest transcript, then trigger incremental scanner."""
    transcript_path = find_latest_transcript()
    if not transcript_path:
        print("[harvester] No transcript found — nothing to harvest")
        return 0
    
    result = process_transcript(cfg, transcript_path)
    if result:
        run_scanner_incremental(cfg)
    return 0


def start_mode(cfg):
    """SessionStart hook: find unprocessed transcripts in 48h window."""
    processed = load_processed_sessions(cfg)
    candidates = find_recent_transcripts(processed, hours=48)
    
    if not candidates:
        print("[harvester:start] No unprocessed transcripts found")
        return 0
    
    print(f"[harvester:start] Found {len(candidates)} unprocessed transcript(s)")
    harvested = 0
    for tp in candidates:
        if process_transcript(cfg, tp):
            harvested += 1
    print(f"[harvester:start] Harvested {harvested}/{len(candidates)} transcripts")
    return 0


def test_mode(cfg, filepath):
    """Test mode: run harvest on a specific file, print verbose output."""
    print(f"[harvester:test] Testing on: {filepath}")
    if not os.path.exists(filepath):
        print(f"  ERROR: File not found: {filepath}")
        return 1
    
    # Read and parse metadata
    content = read_transcript(filepath)
    meta = extract_session_meta(content)
    print(f"  Session ID: {meta.get("id", "unknown")}")
    print(f"  Original cwd: {meta.get("cwd", "unknown")}")
    
    # Resolve vault
    target_vault, label = resolve_target_vault(cfg, meta.get("cwd", ""))
    print(f"  Routed vault: {target_vault} ({label})")
    
    # Extract annotations
    decisions = extract_decisions(content)
    errors = extract_errors(content)
    summary = extract_session_summary(content)
    print(f"  Found: {len(decisions)} decisions, {len(errors)} errors, {"1 summary" if summary else "no summary"}")
    
    # Show first few
    for d in decisions[:3]:
        print(f"    [DECISION] {d.get("text", "")[:80]}")
    for e in errors[:3]:
        print(f"    [ERROR] {e.get("type", "")}: {e.get("resolution", "")[:60]}")
    
    result = process_transcript(cfg, filepath)
    print(f"  Result: {"Harvested" if result else "Nothing to write"}")
    return 0


def process_transcript(cfg, transcript_path):
    """Harvest a single transcript: extract knowledge, route to vault, write.
    
    Key safety: reads original cwd from session_meta (not runtime cwd)
    to prevent skill-nesting routing errors.
    """
    print(f"[harvester] Processing: {transcript_path}")
    
    content = read_transcript(transcript_path)
    if not content:
        print(f"[harvester] WARNING: Empty or unreadable transcript, skipping")
        return False
    
    # Extract session metadata once, lock cwd for routing
    meta = extract_session_meta(content)
    session_id = meta.get("id", generate_session_id(transcript_path))
    original_cwd = meta.get("cwd", "")
    date_str = meta.get("timestamp", datetime.now(CST).strftime("%Y-%m-%d"))[:10]
    
    # Resolve target vault from original cwd
    target_vault, vault_label = resolve_target_vault(cfg, original_cwd)
    
    # Check idempotency (composite key: session_id + file_size)
    file_size = os.path.getsize(transcript_path)
    heartbeat_path = os.path.join(
        target_vault if vault_label != "UNROUTED" else cfg["vault_path"],
        "heartbeat.md"
    )
    if is_already_processed(heartbeat_path, session_id, file_size):
        print(f"[harvester] Already processed: {session_id}:{file_size}, skipping")
        return False
    
    # Extract annotations
    decisions = extract_decisions(content)
    errors = extract_errors(content)
    summary = extract_session_summary(content)
    
    total_found = len(decisions) + len(errors) + (1 if summary else 0)
    if total_found == 0:
        print(f"[harvester] No [DECISION]/[ERROR]/[SESSION_SUMMARY] found in session {session_id}")
        return False
    
    print(f"[harvester] Found: {len(decisions)} decisions, {len(errors)} errors, "
          f"{"1 summary" if summary else "no summary"} → {vault_label}")
    
    # Write to target vault
    written = write_session_to_vault(target_vault, session_id, date_str, meta,
                                     decisions, errors, summary, original_cwd)
    
    # Mark as processed (composite key)
    mark_processed(heartbeat_path, session_id, file_size)
    
    return True


# ── Transcript Finding (Codex path) ──────────────────────────

def find_latest_transcript():
    """Find the most recent Codex session JSONL file."""
    glob_pattern = os.path.join(SESSIONS_PATH, "**/*.jsonl")
    files = sorted(glob_mod.glob(glob_pattern, recursive=True), key=os.path.getmtime, reverse=True)
    
    for f in files[:10]:  # Check top 10 most recent
        if os.path.getsize(f) > 100:  # Skip empty files
            return f
    
    # Fallback: check session_index.jsonl
    index_path = os.path.join(CODEX_HOME, "session_index.jsonl")
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    sid = rec.get("id", "")
                    if sid:
                        # Search sessions/ for this id
                        for root, dirs, files in os.walk(SESSIONS_PATH):
                            for fn in files:
                                if fn.endswith(".jsonl") and sid in fn:
                                    return os.path.join(root, fn)
        except Exception:
            pass
    
    return None


def find_recent_transcripts(processed, hours=48):
    """Find transcripts modified in the last N hours that haven't been processed."""
    cutoff = datetime.now().timestamp() - (hours * 3600)
    candidates = []
    
    for root, dirs, files in os.walk(SESSIONS_PATH):
        for f in files:
            if not f.endswith(".jsonl"):
                continue
            fp = os.path.join(root, f)
            try:
                mtime = os.path.getmtime(fp)
                if mtime < cutoff:
                    continue
                # Extract session_id from filename
                session_id = extract_id_from_filename(f)
                if not session_id:
                    continue
                file_size = os.path.getsize(fp)
                if not is_already_processed_path(processed, session_id, file_size):
                    candidates.append(fp)
            except OSError:
                continue
    
    return candidates


def extract_id_from_filename(filename):
    """Extract UUID from rollout-{timestamp}-{uuid}.jsonl filename."""
    m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", filename)
    return m.group(1) if m else None


# ── Transcript Reading (Codex JSONL format) ──────────────────

def read_transcript(transcript_path):
    """Read JSONL transcript, return full content as string."""
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        print(f"[harvester] ERROR reading {transcript_path}: {e}")
        return ""


def extract_session_meta(content):
    """Extract session_meta from the first line of JSONL.
    
    Returns dict with keys: id, cwd, originator, cli_version, timestamp.
    Used to resolve the original cwd for vault routing (not runtime cwd).
    """
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if rec.get("type") == "session_meta":
                payload = rec.get("payload", {})
                return {
                    "id": payload.get("id", ""),
                    "cwd": payload.get("cwd", ""),
                    "originator": payload.get("originator", ""),
                    "cli_version": payload.get("cli_version", ""),
                    "timestamp": rec.get("timestamp", ""),
                }
        except (json.JSONDecodeError, KeyError):
            continue
    return {}


def extract_decisions(content):
    """Extract [DECISION:] annotations from assistant messages.
    
    Searches all response_item lines with role=assistant for [DECISION: ... | context: ...]
    """
    decisions = []
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if rec.get("type") != "response_item":
                continue
            payload = rec.get("payload", {})
            if payload.get("role") not in ("assistant",):
                continue
            msg_text = payload.get("content", "")
            if isinstance(msg_text, list):
                msg_text = " ".join(str(b.get("text", "")) for b in msg_text if isinstance(b, dict))
            elif not isinstance(msg_text, str):
                msg_text = str(msg_text)
            
            # Strip backtick-quoted code to eliminate format-explanation false positives
            msg_text = re.sub(r"`[^`]*?\[(?:DECISION|ERROR|SESSION_SUMMARY)[^`]*?`", "", msg_text)
            
            # Pattern: [DECISION: <text> | context: <context>]
            for m in re.finditer(r"\[DECISION:\s*(.+?)\s*\|\s*context:\s*(.+?)\]", msg_text):
                decisions.append({
                    "text": m.group(1).strip(),
                    "context": m.group(2).strip(),
                })
        except (json.JSONDecodeError, KeyError):
            continue
    
    return decisions


def extract_errors(content):
    """Extract [ERROR:] annotations from assistant messages.
    
    Pattern: [ERROR: type=<from-taxonomy> | resolution=<how fixed>]
    """
    errors = []
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if rec.get("type") != "response_item":
                continue
            payload = rec.get("payload", {})
            if payload.get("role") not in ("assistant",):
                continue
            msg_text = payload.get("content", "")
            if isinstance(msg_text, list):
                msg_text = " ".join(str(b.get("text", "")) for b in msg_text if isinstance(b, dict))
            elif not isinstance(msg_text, str):
                msg_text = str(msg_text)
            
            # Strip backtick-quoted code to eliminate format-explanation false positives
            msg_text = re.sub(r"\x60[^\x60]*?\[(?:DECISION|ERROR|SESSION_SUMMARY)[^\x60]*?\x60", "", msg_text)
            
            # Pattern: [ERROR: type=<type> | resolution=<resolution>]
            for m in re.finditer(r"\[ERROR:\s*type=(.+?)\s*\|\s*resolution=(.+?)\]", msg_text):
                errors.append({
                    "type": m.group(1).strip(),
                    "resolution": m.group(2).strip(),
                })
        except (json.JSONDecodeError, KeyError):
            continue
    
    return errors


def extract_session_summary(content):
    """Extract [SESSION_SUMMARY] block from the transcript."""
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if rec.get("type") != "response_item":
                continue
            payload = rec.get("payload", {})
            if payload.get("role") not in ("assistant",):
                continue
            msg_text = payload.get("content", "")
            if isinstance(msg_text, list):
                msg_text = " ".join(str(b.get("text", "")) for b in msg_text if isinstance(b, dict))
            elif not isinstance(msg_text, str):
                msg_text = str(msg_text)
            
            if "[SESSION_SUMMARY]" in msg_text and "[/SESSION_SUMMARY]" in msg_text:
                return msg_text
        except (json.JSONDecodeError, KeyError):
            continue
    
    return None


# ── Idempotency (Composite Key: session_id:file_size) ──────

def load_processed_sessions(cfg):
    """Load processed sessions from heartbeat or config."""
    heartbeat_path = os.path.join(cfg["vault_path"], "heartbeat.md")
    return _load_heartbeat(heartbeat_path)


def _load_heartbeat(heartbeat_path):
    """Extract processed_sessions from heartbeat frontmatter."""
    if not os.path.exists(heartbeat_path):
        return {}
    try:
        with open(heartbeat_path, "r", encoding="utf-8") as f:
            content = f.read()
        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}
        fm = yaml.safe_load(parts[1])
        return fm.get("processed_sessions", {}) if isinstance(fm, dict) else {}
    except Exception:
        return {}


def is_already_processed(heartbeat_path, session_id, file_size):
    """Check if a session has been processed using composite key.
    
    Composite key = session_id:file_size.
    This prevents duplicates even if the file is at a different path.
    """
    processed = _load_heartbeat(heartbeat_path)
    key = f"{session_id}:{file_size}"
    return key in processed


def is_already_processed_path(processed, session_id, file_size):
    """Check if a session_id:file_size combo is in a processed dict."""
    key = f"{session_id}:{file_size}"
    return key in processed


def mark_processed(heartbeat_path, session_id, file_size):
    """Mark a session as processed using composite key."""
    processed = _load_heartbeat(heartbeat_path)
    key = f"{session_id}:{file_size}"
    processed[key] = datetime.now(CST).isoformat()
    _write_heartbeat(heartbeat_path, processed)


def _write_heartbeat(heartbeat_path, processed):
    """Write processed_sessions back to heartbeat.md atomically."""
    os.makedirs(os.path.dirname(heartbeat_path), exist_ok=True)
    
    existing = {}
    if os.path.exists(heartbeat_path):
        try:
            with open(heartbeat_path, "r", encoding="utf-8") as f:
                content = f.read()
            parts = content.split("---", 2)
            if len(parts) >= 3:
                existing = yaml.safe_load(parts[1]) or {}
            existing_body = parts[2] if len(parts) > 2 else ""
        except Exception:
            existing_body = "\n\n"
    else:
        existing_body = "\n\n"
    
    existing["processed_sessions"] = processed
    existing["last_updated"] = datetime.now(CST).isoformat()
    
    fm_yaml = yaml.dump(existing, allow_unicode=True, default_flow_style=False, sort_keys=False)
    content = f"---\n{fm_yaml}---\n{existing_body}"
    
    tmp = heartbeat_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, heartbeat_path)


# ── Vault Writing ──────────────────────────────────────────────

def write_session_to_vault(vault_path, session_id, date_str, meta,
                           decisions, errors, summary, original_cwd):
    """Write harvested session knowledge to the target vault.
    
    Creates:
    - vault/journal/YYYY-MM-DD.md (harvest log)
    - vault/knowledge/zk-codex-*-*-*.md if decisions or errors found
    """
    # 1. Journal entry
    journal_dir = os.path.join(vault_path, "journal")
    os.makedirs(journal_dir, exist_ok=True)
    journal_path = os.path.join(journal_dir, f"{date_str}.md")
    
    journal_entry = (
        f"- [{datetime.now(CST).strftime('%H:%M:%S')}] "
        f"收割会话 {session_id[:12]}...\n"
        f"  - 决策: {len(decisions)}, 错误: {len(errors)}, 摘要: {'是' if summary else '否'}\n"
        f"  - 原始 cwd: {original_cwd}\n"
    )
    
    _append_atomic(journal_path, journal_entry)
    
    # 2. Knowledge node (if decisions or errors found)
    if decisions or errors:
        _write_knowledge_node(vault_path, session_id, date_str, decisions, errors, original_cwd)
    
    return True


def _write_knowledge_node(vault_path, session_id, date_str, decisions, errors, original_cwd):
    """Write a Zettelkasten knowledge node for this session.
    
    Naming: zk-codex-{catseq}-{docseq}-{slug}.md
    - catseq: aa0 (通用决策) or bb0 (通用错误/方案)
    - docseq: auto-incremented from existing knowledge/ files
    """
    knowledge_dir = os.path.join(vault_path, "knowledge")
    os.makedirs(knowledge_dir, exist_ok=True)
    
    # Determine category
    if errors:
        catseq = "bb0"  # Solutions/patterns
    else:
        catseq = "aa0"  # Decisions/knowledge
    
    # Auto-increment docseq
    existing = [f for f in os.listdir(knowledge_dir) 
                if f.startswith(f"zk-{ZK_DOMAIN}-{catseq}-")]
    docseq = len(existing) if existing else 0
    
    # Generate slug from first decision/error
    slug = "session-knowledge"
    if decisions:
        slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff-]", "-", decisions[0]["text"][:40])
    elif errors:
        slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff-]", "-", errors[0]["type"][:40])
    slug = slug.strip("-").lower()[:50] or "session-knowledge"
    
    filename = f"zk-{ZK_DOMAIN}-{catseq}-{docseq}-{slug}.md"
    filepath = os.path.join(knowledge_dir, filename)
    
    # Build content
    lines = []
    lines.append("---")
    lines.append(f"title: \"会话知识收割: {slug}\"")
    lines.append(f"date: {date_str}")
    lines.append(f"source: harvested")
    lines.append(f"source_session: {session_id}")
    lines.append(f"source_cwd: \"{original_cwd}\"")
    lines.append(f"domain: {ZK_DOMAIN}")
    lines.append(f"tags: [{ZK_DOMAIN}, harvested, session]")
    lines.append(f"status: distilled")
    lines.append("---")
    lines.append("")
    lines.append(f"# Session Knowledge: {date_str}")
    lines.append("")
    lines.append(f"Source session: `{session_id}`")
    lines.append(f"Working directory: `{original_cwd}`")
    lines.append("")
    
    if decisions:
        lines.append("## Decisions")
        lines.append("")
        for d in decisions:
            lines.append(f"- **{d['text']}**")
            if d.get("context"):
                lines.append(f"  - Context: {d['context']}")
    
    if errors:
        lines.append("")
        lines.append("## Errors & Resolutions")
        lines.append("")
        for e in errors:
            lines.append(f"- **{e['type']}** → {e['resolution']}")
    
    lines.append("")
    
    content = "\n".join(lines)
    
    # Atomic write
    tmp = filepath + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, filepath)
        print(f"[harvester] Wrote: {filepath}")
    except Exception as e:
        print(f"[harvester] WARNING: Could not write knowledge node: {e}")


def _append_atomic(filepath, text):
    """Atomically append text to a file (journal entry)."""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        # Read existing, append, write atomically
        existing = ""
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                existing = f.read()
        
        new_content = existing + text
        
        tmp = filepath + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(new_content)
        os.replace(tmp, filepath)
    except Exception as e:
        print(f"[harvester] WARNING: Could not append to {filepath}: {e}")


def generate_session_id(transcript_path):
    """Extract a session ID from the file path."""
    basename = os.path.basename(transcript_path)
    # Try UUID pattern
    m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", basename)
    if m:
        return m.group(1)
    # Fallback: hash the full path
    return hashlib.md5(transcript_path.encode()).hexdigest()[:16]


# ── Scanner Trigger ────────────────────────────────────────────

def run_scanner_incremental(cfg):
    """Run incremental scanner (analyze + maintain + compile)."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    runner = os.path.join(script_dir, "runner.py")
    
    if not os.path.exists(runner):
        print("[harvester] WARNING: runner.py not found, skipping incremental scan")
        return
    
    cmd = [sys.executable, runner, "--step", "analyze", "--step", "compile"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                                cwd=script_dir, env=os.environ.copy())
        if result.returncode != 0:
            print(f"[harvester] Scanner warnings:\n{result.stderr[:300]}")
        else:
            print(f"[harvester] Incremental scan completed")
    except subprocess.TimeoutExpired:
        print("[harvester] WARNING: Scanner timed out after 120s")
    except Exception as e:
        print(f"[harvester] WARNING: Scanner failed: {e}")


# ── Entry Point ────────────────────────────────────────────────
if __name__ == "__main__":
    import subprocess  # needed for run_scanner_incremental
    sys.exit(main())
