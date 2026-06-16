#!/usr/bin/env python3
"""deploy.py — Environment verification (12 checks) for codex-vault-migrator v2.0.
Replaces deploy-checklist.ps1 with cross-platform Python implementation.
"""
import os
import sys
import platform
import subprocess
import shutil
import json
from pathlib import Path

CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
VAULT_PATH = Path.home() / "OneDrive" / "Codex-Brain"
VAULT_SKILLS = VAULT_PATH / "02-技能-vaults"
SKILLS_DIR = CODEX_HOME / "skills"
ONEDRIVE = Path.home() / "OneDrive"

PASS = 0
FAIL = 0
WARN = 0
RESULTS = []

def check(name, status, detail=""):
    global PASS, FAIL, WARN
    icon = {"pass": "✅", "fail": "❌", "warn": "⚠️"}.get(status, "❓")
    if status == "pass": PASS += 1
    elif status == "fail": FAIL += 1
    else: WARN += 1
    RESULTS.append(f"  {icon} {name}: {detail}")
    print(f"  {icon} {name}: {detail}")

def main():
    global PASS, FAIL, WARN
    
    print("=" * 50)
    print("  codex-vault-migrator v2.0 — 环境验收")
    print(f"  设备: {platform.node()}")
    print(f"  用户: {os.environ.get("USERNAME", os.environ.get("USER", "unknown"))}")
    print(f"  时间: {__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")}")
    print("=" * 50)
    
    # [1/12] OS
    os_name = platform.system()
    os_ver = platform.version()
    if os_name == "Windows":
        check("pass", "操作系统", f"{os_name} {os_ver}")
    elif os_name in ("Darwin", "Linux"):
        check("warn", "操作系统", f"{os_name} {os_ver} (部分功能需管理员权限)")
    else:
        check("fail", "操作系统", f"不支持: {os_name}")
    
    # [2/12] OneDrive
    if os_name == "Windows":
        result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq OneDrive.exe"],
                               capture_output=True, text=True)
        if "OneDrive.exe" in result.stdout:
            check("pass", "OneDrive", "运行中")
        else:
            check("fail", "OneDrive", "未运行 (请启动 OneDrive)")
    else:
        check("warn", "OneDrive", "非 Windows 系统，跳过 OneDrive 检查")
    
    # [3/12] Vault sync
    if VAULT_SKILLS.exists():
        skill_count = len(list(VAULT_SKILLS.iterdir()))
        check("pass", "Vault 同步", f"已同步 ({skill_count} 个 skill)")
    else:
        check("fail", "Vault 同步", f"未同步: {VAULT_SKILLS} 不存在")
    
    # [4/12] Node.js
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10)
        ver = result.stdout.strip()
        ver_num = int(ver.lstrip("v").split(".")[0])
        if ver_num >= 18:
            check("pass", "Node.js", ver)
        else:
            check("warn", "Node.js", f"{ver} (需 ≥ v18)")
    except FileNotFoundError:
        check("fail", "Node.js", "未安装")
    
    # [5/12] Python
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    if sys.version_info >= (3, 10):
        check("pass", "Python", py_ver)
    else:
        check("fail", "Python", f"{py_ver} (需 ≥ 3.10)")
    
    # [6/12] txtai
    try:
        import importlib
        spec = importlib.util.find_spec("txtai")
        if spec:
            check("pass", "txtai", "已安装")
        else:
            check("fail", "txtai", "未安装 (运行: pip install txtai)")
    except ImportError:
        check("fail", "txtai", "未安装")
    
    # [7/12] Junction integrity
    expected_junctions = [
        "equity-incentive", "tax-compliance-expert", "hk-ipo", "financial-analysis",
        "trading-agents-007", "serenity-a-share-investor", "ima-knowledge", "weekly-report",
        "proactive-agent", "wechat-article-downloader", "llm-wiki", "quant-factor-skill",
        "trading-analysis", "serenity-skill", "ontology", "pdf", "playwright",
        "markdown-converter", "obsidian", "agent-browser", "humanizer", "imap-smtp-email",
        "cloakbrowser", "a-share-research", "engineering-practices",
    ]
    ok_count = 0
    missing = []
    for s in expected_junctions:
        p = SKILLS_DIR / s
        if p.is_symlink() or p.exists():
            ok_count += 1
        else:
            missing.append(s)
    
    if ok_count == len(expected_junctions):
        check("pass", "Junction 完整性", f"{ok_count}/{len(expected_junctions)} 全部存在")
    elif ok_count >= 10:
        check("warn", "Junction 完整性", f"{ok_count}/{len(expected_junctions)} 存在, 缺少: {", ".join(missing[:5])}...")
    else:
        check("fail", "Junction 完整性", f"{ok_count}/{len(expected_junctions)} 存在, 缺少过多")
    
    # [8/12] API proxy (DeepSeek / CCX)
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:3000/health")
        resp = urllib.request.urlopen(req, timeout=3)
        data = json.loads(resp.read())
        if data.get("status") == "healthy":
            check("pass", "API 代理", f"运行中 (v{data.get("version", {}).get("version", "?")})")
        else:
            check("warn", "API 代理", "响应但非健康状态")
    except Exception:
        check("fail", "API 代理", "未运行 (localhost:3000 无响应)")
    
    # [9/12] config.toml proxy
    config_toml = CODEX_HOME / "config.toml"
    if config_toml.exists():
        content = config_toml.read_text(encoding="utf-8")
        if "localhost:3000" in content:
            check("pass", "config.toml", "代理已配置")
        else:
            check("warn", "config.toml", "存在但未配置代理")
    else:
        check("fail", "config.toml", "不存在")
    
    # [10/12] npm dependencies (imap-smtp-email)
    imap_dir = SKILLS_DIR / "imap-smtp-email"
    node_modules = imap_dir / "node_modules"
    if node_modules.exists():
        pkg_count = len(list(node_modules.iterdir()))
        check("pass", "npm 依赖", f"已安装 ({pkg_count} 个包)")
    else:
        check("fail", "npm 依赖", f"未安装 (运行: cd {imap_dir} && npm install)")
    
    # [11/12] Obsidian vault
    if os_name == "Windows":
        appdata = Path(os.environ.get("APPDATA", ""))
        obs_config = appdata / "Obsidian" / "obsidian.json"
        if obs_config.exists():
            content = obs_config.read_text(encoding="utf-8")
            if str(VAULT_PATH) in content:
                check("pass", "Obsidian vault", "已注册 Codex-Brain vault")
            else:
                check("warn", "Obsidian vault", "未注册 Codex-Brain vault")
        else:
            check("warn", "Obsidian vault", "配置未找到")
    else:
        check("warn", "Obsidian vault", "非 Windows 系统，跳过")
    
    # [12/12] mcp.json
    mcp_files = [VAULT_PATH / "mcp.json", CODEX_HOME / "mcp.json"]
    mcp_found = False
    for m in mcp_files:
        if m.exists():
            check("pass", "mcp.json", f"存在 ({m})")
            mcp_found = True
            break
    if not mcp_found:
        check("fail", "mcp.json", "未找到")
    
    # Summary
    print()
    print("=" * 50)
    print(f"  验收汇总")
    print("=" * 50)
    print(f"  通过: {PASS}/12")
    print(f"  警告: {WARN}")
    print(f"  失败: {FAIL}")
    if FAIL == 0 and PASS >= 10:
        print("  结论: ✅ 全部就绪")
    elif FAIL <= 2:
        print("  结论: ⚠️ 尚有 {FAIL} 项需要修复")
    else:
        print("  结论: ❌ 尚有 {FAIL} 项需要修复")

if __name__ == "__main__":
    main()
