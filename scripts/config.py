"""Load configuration from config.yaml — v2.0 Codex-adapted."""
import os
import sys
import yaml
import re

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

def load_config():
    """Load and validate configuration, with auto-derived defaults."""
    cfg_path = os.environ.get("CODEX_MIGRATOR_CONFIG", CONFIG_PATH)
    if not os.path.exists(cfg_path):
        # Try project root
        cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml")
    if not os.path.exists(cfg_path):
        raise FileNotFoundError(
            f"config.yaml not found. Copy config.example.yaml to config.yaml and fill in your paths.\n"
            f"  Searched: {CONFIG_PATH}\n"
            f"  Searched: {cfg_path}"
        )
    
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    
    # Auto-derive codex_home
    if not cfg.get("codex_home"):
        cfg["codex_home"] = os.environ.get("CODEX_HOME", os.path.expanduser("~/.codex"))
    
    # Auto-derive sessions_path
    if not cfg.get("sessions_path"):
        cfg["sessions_path"] = os.path.join(cfg["codex_home"], "sessions")
    
    # Validate required keys
    required = ["vault_path"]
    for key in required:
        if key not in cfg:
            raise KeyError(f"config.yaml missing required key: {key}")
    
    # Ensure vault_path exists (create if not)
    if not os.path.exists(cfg["vault_path"]):
        os.makedirs(cfg["vault_path"], exist_ok=True)
    
    return cfg


def resolve_target_vault(cfg, cwd):
    """Route a session to its target vault based on configurable regex rules.
    
    Args:
        cfg: Config dict (from load_config)
        cwd: Original session cwd from session_meta
    
    Returns:
        Tuple of (vault_path: str, label: str)
    """
    rules = cfg.get("vault_routing_rules", [])
    cwd_lower = cwd.lower() if cwd else ""
    
    for rule in rules:
        try:
            if re.search(rule["pattern"], cwd_lower, re.IGNORECASE):
                vault_path = rule["vault"]
                label = rule.get("label", "UNKNOWN")
                if vault_path == "_unrouted":
                    return (cfg["vault_path"], "UNROUTED")
                # Expand environment variables
                vault_path = os.path.expandvars(vault_path)
                vault_path = vault_path.replace("%CODEX_HOME%", cfg.get("codex_home", ""))
                vault_path = vault_path.replace("%USERPROFILE%", os.path.expanduser("~"))
                return (vault_path, label)
        except re.error as e:
            print(f"  WARNING: Invalid routing regex '{rule['pattern']}': {e}")
            continue
    
    return (cfg["vault_path"], "FALLBACK")


def get_api_config(cfg):
    """Read API configuration from config.yaml + settings.json."""
    api_cfg = cfg.get("api", {})
    settings_path = api_cfg.get("settings_json", "")
    settings = {}
    if settings_path and os.path.exists(settings_path):
        import json
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    
    env = settings.get("env", {})
    api_key = (api_cfg.get("key") or
               env.get("ANTHROPIC_AUTH_TOKEN") or
               settings.get("ANTHROPIC_AUTH_TOKEN") or
               "")
    
    return {
        "key": api_key,
        "base_url": (api_cfg.get("base_url") or
                     env.get("ANTHROPIC_BASE_URL") or
                     settings.get("ANTHROPIC_BASE_URL") or
                     "https://api.anthropic.com/v1"),
        "model": (api_cfg.get("model") or
                  env.get("ANTHROPIC_MODEL") or
                  settings.get("ANTHROPIC_MODEL") or
                  "claude-sonnet-4-20250514"),
        "temperature": api_cfg.get("temperature", 0.3),
        "max_tokens": api_cfg.get("max_tokens", 4000),
        "max_retries": api_cfg.get("max_retries", 3),
        "retry_backoff_sec": api_cfg.get("retry_backoff_sec", [2, 4, 8]),
    }


def discover_skill_vaults(codex_home):
    """Auto-discover all skill vaults under ~/.codex/skills/.
    
    Returns:
        {name: vault_path} mapping for all skills that have a vault/ subdirectory.
    """
    skills_dir = os.path.join(codex_home, "skills")
    result = {}
    if not os.path.exists(skills_dir):
        return result
    for entry in sorted(os.listdir(skills_dir)):
        vault_path = os.path.join(skills_dir, entry, "vault")
        if os.path.isdir(vault_path) and not entry.endswith(".bak"):
            result[entry] = vault_path
    return result


def generate_routing_rules(skill_vaults):
    """Auto-generate vault_routing_rules from discovered skill vaults.
    
    Args:
        skill_vaults: {name: path} mapping from discover_skill_vaults()
    
    Returns:
        List of rule dicts suitable for vault_routing_rules.
    """
    rules = []
    for name, path in skill_vaults.items():
        # Convert skill name to a regex that handles -/_ variations
        pattern = re.sub(r"[-_]+", "[-_]?", re.escape(name.lower()))
        rules.append({
            "pattern": pattern,
            "vault": path,
            "label": name,
        })
    return rules
