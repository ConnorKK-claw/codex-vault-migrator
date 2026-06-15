<#
.SYNOPSIS
  codex-vault-migrator 环境验收脚本
.DESCRIPTION
  逐一检查跨设备部署的 12 项前置条件和最终状态。
  输出格式: ✅ / ❌ / ⚠️
#>

$VAULT_PATH = "$env:USERPROFILE\OneDrive\Codex-Brain"
$CODEX_HOME = "$env:USERPROFILE\.codex"
$SKILLS_DIR = "$CODEX_HOME\skills"
$CCX_ENV = "D:\CCX\ccx-windows\.env"
$VAULT_SKILLS = "$VAULT_PATH\02-技能-vaults"
$WORKSPACE_DIR = "$env:USERPROFILE\OneDrive\文档"

$passed = 0
$failed = 0
$warnings = 0

Write-Output "============================================"
Write-Output "  codex-vault-migrator 环境验收"
Write-Output "  设备: $env:COMPUTERNAME"
Write-Output "  用户: $env:USERNAME"
Write-Output "  时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Output "============================================"

# === 1. 操作系统 ===
Write-Output "`n[1/12] 操作系统"
$os = Get-CimInstance Win32_OperatingSystem
if ($os.Caption -match "Windows (11|10)") {
    Write-Output "  ✅ $($os.Caption) (Build $($os.BuildNumber))"
    $passed++
} else {
    Write-Output "  ❌ 不支持的 OS: $($os.Caption)"
    $failed++
}

# === 2. OneDrive 运行状态 ===
Write-Output "`n[2/12] OneDrive 运行状态"
$od = Get-Process OneDrive -ErrorAction SilentlyContinue
if ($od) {
    Write-Output "  ✅ OneDrive 运行中 (PID $($od.Id))"
    $passed++
} else {
    Write-Output "  ❌ OneDrive 未运行"
    $failed++
}

# === 3. Vault 同步状态 ===
Write-Output "`n[3/12] Vault 同步状态"
if (Test-Path $VAULT_SKILLS) {
    Write-Output "  ✅ vault 已同步: $VAULT_SKILLS"
    $passed++
} else {
    Write-Output "  ❌ vault 未同步：$VAULT_SKILLS 不存在"
    $failed++
}

# === 4. Node.js ===
Write-Output "`n[4/12] Node.js"
$nodeVer = cmd /c "node --version" 2>&1
if ($nodeVer -match "v(\d+)") {
    $verNum = [int]$Matches[1]
    if ($verNum -ge 18) {
        Write-Output "  ✅ Node.js $nodeVer"
        $passed++
    } else {
        Write-Output "  ⚠️ Node.js $nodeVer (需 ≥ v18)"
        $warnings++
    }
} else {
    Write-Output "  ❌ Node.js 未安装"
    $failed++
}

# === 5. Python ===
Write-Output "`n[5/12] Python"
$pyVer = cmd /c "python --version" 2>&1
if ($pyVer -match "Python (\d+)\.(\d+)") {
    $major = [int]$Matches[1]; $minor = [int]$Matches[2]
    if ($major -ge 3 -and $minor -ge 10) {
        Write-Output "  ✅ $pyVer"
        $passed++
    } else {
        Write-Output "  ⚠️ $pyVer (需 ≥ 3.10)"
        $warnings++
    }
} else {
    Write-Output "  ❌ Python 未安装"
    $failed++
}

# === 6. txtai ===
Write-Output "`n[6/12] txtai"
$txtai = cmd /c "pip show txtai 2>&1" | Select-String "Version"
if ($txtai) {
    Write-Output "  ✅ txtai $($txtai.ToString().Trim())"
    $passed++
} else {
    Write-Output "  ❌ txtai 未安装 (运行: pip install txtai)"
    $failed++
}

# === 7. Junction 完整性 ===
Write-Output "`n[7/12] Directory Junctions (23 个)"
$junctions = @(
    "equity-incentive","tax-compliance-expert","hk-ipo","financial-analysis",
    "trading-agents-007","serenity-a-share-investor","ima-knowledge","weekly-report",
    "proactive-agent","wechat-article-downloader","llm-wiki","quant-factor-skill",
    "trading-analysis","serenity-skill","ontology","pdf","playwright",
    "markdown-converter","obsidian","agent-browser","humanizer","imap-smtp-email",
    "cloakbrowser"
)
$ok = 0; $missing = @()
foreach ($s in $junctions) {
    $p = "$SKILLS_DIR\$s"
    $item = Get-Item $p -Force -ErrorAction SilentlyContinue
    if ($item -and $item.LinkType -eq 'Junction') { $ok++ }
    else { $missing += $s }
}
$status = if ($ok -eq 23) { "✅" } elseif ($ok -ge 10) { "⚠️" } else { "❌" }
Write-Output "  $status $ok/23 Junction 存在"
if ($missing.Count -gt 0) { Write-Output "  缺少: $($missing -join ', ')" }
if ($ok -eq 23) { $passed++ } else { $failed++ }

# === 8. DeepSeek 代理 ===
Write-Output "`n[8/12] DeepSeek 代理 (localhost:3000)"
try {
    $resp = Invoke-WebRequest "http://localhost:3000/health" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
    $data = $resp.Content | ConvertFrom-Json
    if ($data.status -eq "healthy") {
        Write-Output "  ✅ CCX 代理运行中 (v$($data.version.version), 启动 $([math]::Round($data.uptime/3600,1))h 前)"
        $passed++
    } else { throw "非健康状态" }
} catch {
    Write-Output "  ❌ 代理未运行: $_"
    $failed++
}

# === 9. config.toml 代理配置 ===
Write-Output "`n[9/12] config.toml 代理配置"
$cfg = "$CODEX_HOME\config.toml"
if (Test-Path $cfg) {
    $hasProxy = Select-String -Path $cfg -Pattern "localhost:3000" -SimpleMatch
    if ($hasProxy) {
        Write-Output "  ✅ base_url 已指向 localhost:3000"
        $passed++
    } else {
        Write-Output "  ⚠️ config.toml 存在但未配置代理地址"
        $warnings++
    }
} else {
    Write-Output "  ❌ config.toml 不存在"
    $failed++
}

# === 10. imap-smtp-email npm 依赖 ===
Write-Output "`n[10/12] imap-smtp-email npm 依赖"
$imapDir = "$SKILLS_DIR\imap-smtp-email"
if (Test-Path "$imapDir\node_modules") {
    $pkgCount = (Get-ChildItem "$imapDir\node_modules" -Directory).Count
    Write-Output "  ✅ node_modules 已安装 ($pkgCount 个包)"
    $passed++
} else {
    Write-Output "  ❌ node_modules 未安装 (运行: cd $imapDir && npm install)"
    $failed++
}

# === 11. Obsidian vault ===
Write-Output "`n[11/12] Obsidian vault 注册状态"
$obsConfig = "$env:APPDATA\Obsidian\obsidian.json"
if (Test-Path $obsConfig) {
    $hasVault = (Get-Content $obsConfig -Raw) -match [regex]::Escape($VAULT_PATH)
    if ($hasVault) {
        Write-Output "  ✅ Obsidian 中已注册 Codex-Brain vault"
        $passed++
    } else {
        Write-Output "  ⚠️ Obsidian 配置存在但未注册 Codex-Brain vault"
        $warnings++
    }
} else {
    Write-Output "  ⚠️ Obsidian 配置未找到 (需至少打开过一次)"
    $warnings++
}

# === 12. mcp.json ===
Write-Output "`n[12/12] mcp.json"
$mcpFiles = @("$VAULT_PATH\mcp.json", "$CODEX_HOME\mcp.json")
$mcpFound = $false
foreach ($m in $mcpFiles) {
    if (Test-Path $m) {
        $userReplaced = (Get-Content $m -Raw) -match "62307"
        Write-Output "  ✅ $m $(if($userReplaced){'(用户名已替换)'})"
        $mcpFound = $true
        $passed++
        break
    }
}
if (-not $mcpFound) {
    Write-Output "  ❌ mcp.json 未找到"
    $failed++
}

# === 汇总 ===
Write-Output "`n============================================"
Write-Output "  验收汇总"
Write-Output "============================================"
Write-Output "  通过: $passed/12"
Write-Output "  警告: $warnings"
Write-Output "  失败: $failed"
if ($failed -eq 0) {
    Write-Output "  结论: ✅ 全部就绪"
} else {
    Write-Output "  结论: ❌ 尚有 $failed 项需要修复"
}
