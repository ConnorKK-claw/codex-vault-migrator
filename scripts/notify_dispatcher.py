"""notify_dispatcher.py — Codex Desktop notify event dispatcher.
Fallback when hooks.json is not available or PostToolUse is too frequent.
Usage in config.toml:
  notify = [ "python scripts/notify_dispatcher.py", "turn-ended" ]
"""
import sys
import subprocess
import os

def main():
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    
    dispatchers = {
        "turn-ended": [
            [sys.executable, os.path.join(script_dir(), "session_harvester.py"), "--mode", "stop"],
        ],
        "turn-started": [
            [sys.executable, os.path.join(script_dir(), "session_harvester.py"), "--mode", "start"],
        ],
    }
    
    for cmd in dispatchers.get(event, []):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                print(f"[dispatcher] WARNING: {" ".join(cmd[:3])} failed: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            print(f"[dispatcher] WARNING: {" ".join(cmd[:3])} timed out")
        except Exception as e:
            print(f"[dispatcher] ERROR: {e}")

def script_dir():
    return os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    main()
