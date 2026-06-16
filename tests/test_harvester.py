"""Tests for session_harvester.py v2.0 (Codex-adapted)."""
import os
import sys
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from session_harvester import (
    extract_session_meta,
    extract_decisions,
    extract_errors,
    extract_session_summary,
    is_already_processed,
    mark_processed,
    resolve_target_vault,
)


def _build_jsonl(lines):
    """Build a JSONL string from dicts (handles encoding properly)."""
    return "\n".join(json.dumps(line, ensure_ascii=False) for line in lines)


class TestHarvesterAdapter(unittest.TestCase):
    """Test the Codex-adapted harvester functions."""
    
    def setUp(self):
        # Build fixtures with proper JSON encoding
        self.sample_records = [
            {"timestamp": "2026-06-01T01:35:44.595Z", "type": "session_meta",
             "payload": {"id": "019e80d2-8847-72e2-88fb-c727bcf8ed70",
                         "cwd": "C:\\Users\\hexk\\OneDrive\\文档\\New project 6",
                         "originator": "Codex Desktop", "cli_version": "0.133.0"}},
            {"timestamp": "2026-06-01T08:16:56.124Z", "type": "response_item",
             "payload": {"type": "message", "role": "user", "content": "帮我写一个Python脚本"}},
            {"timestamp": "2026-06-01T08:17:00.124Z", "type": "response_item",
             "payload": {"type": "message", "role": "assistant",
                         "content": (
                             "好的，我来帮你写。\n\n"
                             "[DECISION: 使用requests库处理HTTP请求 | context: 标准库无需额外安装]\n\n"
                             "[DECISION: 使用pathlib处理文件路径 | context: 跨平台兼容性好]\n\n"
                             "[ERROR: type=ssl_error | resolution=添加verify=False参数绕过SSL验证]\n\n"
                             "[SESSION_SUMMARY]\nprojects: [test]\nprimary: test\ndecisions:\n"
                             "  - id: TEST-D01\n    text: \"use requests for HTTP\"\n[/SESSION_SUMMARY]"
                         )}},
            {"timestamp": "2026-06-01T08:17:05.124Z", "type": "turn_context",
             "payload": {"type": "tool_use", "name": "bash", "input": "python script.py"}},
        ]
        self.sample_jsonl = _build_jsonl(self.sample_records)
        
        # Empty session
        self.empty_records = [
            {"timestamp": "2026-06-01T01:35:44.595Z", "type": "session_meta",
             "payload": {"id": "019e9999-0000-0000-0000-000000000000",
                         "cwd": "C:\\Users\\test", "originator": "Codex Desktop"}},
            {"timestamp": "2026-06-01T08:16:56.124Z", "type": "response_item",
             "payload": {"type": "message", "role": "user", "content": "hello"}},
            {"timestamp": "2026-06-01T08:17:00.124Z", "type": "response_item",
             "payload": {"type": "message", "role": "assistant", "content": "Hi there!"}},
        ]
        self.empty_jsonl = _build_jsonl(self.empty_records)
        
        # Skill-nesting session (cwd stays at New project 6 but mentions skill path)
        self.nested_records = [
            {"timestamp": "2026-06-01T01:35:44.595Z", "type": "session_meta",
             "payload": {"id": "019e8888-1111-2222-3333-444444444444",
                         "cwd": "C:\\Users\\hexk\\OneDrive\\文档\\New project 6",
                         "originator": "Codex Desktop", "cli_version": "0.133.0"}},
            {"timestamp": "2026-06-01T08:17:00.124Z", "type": "response_item",
             "payload": {"type": "message", "role": "assistant",
                         "content": (
                             "[DECISION: 使用Junction而非硬链接 | context: NTFS跨卷支持]\n"
                             "[ERROR: type=path_separator_mix | resolution=统一使用正斜杠]\n"
                             "现在我在C:\\Users\\hexk\\.codex\\skills\\equity-incentive\\vault下工作"
                         )}},
        ]
        self.nested_jsonl = _build_jsonl(self.nested_records)
    
    def test_extract_session_meta(self):
        meta = extract_session_meta(self.sample_jsonl)
        self.assertEqual(meta.get("id"), "019e80d2-8847-72e2-88fb-c727bcf8ed70")
        self.assertIn("New project 6", meta.get("cwd", ""))
        self.assertEqual(meta.get("originator"), "Codex Desktop")
    
    def test_extract_session_meta_empty(self):
        self.assertEqual(extract_session_meta(""), {})
    
    def test_extract_session_meta_no_meta(self):
        self.assertEqual(extract_session_meta('{"type":"response_item","payload":{}}'), {})
    
    def test_extract_decisions(self):
        decisions = extract_decisions(self.sample_jsonl)
        self.assertEqual(len(decisions), 2)
        self.assertEqual(decisions[0]["text"], "使用requests库处理HTTP请求")
        self.assertEqual(decisions[0]["context"], "标准库无需额外安装")
        self.assertEqual(decisions[1]["text"], "使用pathlib处理文件路径")
    
    def test_extract_decisions_empty(self):
        self.assertEqual(len(extract_decisions(self.empty_jsonl)), 0)
    
    def test_extract_decisions_nested(self):
        decisions = extract_decisions(self.nested_jsonl)
        self.assertEqual(len(decisions), 1)
        self.assertIn("Junction", decisions[0]["text"])
    
    def test_extract_errors(self):
        errors = extract_errors(self.sample_jsonl)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["type"], "ssl_error")
    
    def test_extract_errors_nested(self):
        errors = extract_errors(self.nested_jsonl)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["type"], "path_separator_mix")
    
    def test_extract_session_summary(self):
        summary = extract_session_summary(self.sample_jsonl)
        self.assertIsNotNone(summary)
        self.assertIn("[SESSION_SUMMARY]", summary)
        self.assertIn("[/SESSION_SUMMARY]", summary)
    
    def test_extract_session_summary_empty(self):
        self.assertIsNone(extract_session_summary(self.empty_jsonl))
    
    def test_idempotency_composite_key(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("---\nprocessed_sessions: {}\n---\n")
            hb_path = f.name
        
        try:
            self.assertFalse(is_already_processed(hb_path, "s1", 1000))
            mark_processed(hb_path, "s1", 1000)
            self.assertTrue(is_already_processed(hb_path, "s1", 1000))
            self.assertFalse(is_already_processed(hb_path, "s1", 2000))  # diff size
        finally:
            os.unlink(hb_path)
    
    def test_resolve_target_vault_kknexus(self):
        cfg = {
            "vault_path": "C:/KKNexus",
            "vault_routing_rules": [
                {"pattern": "New project [0-9]+", "vault": "C:/KKNexus", "label": "KKNexus"},
                {"pattern": ".*", "vault": "_unrouted", "label": "UNROUTED"},
            ]
        }
        vault, label = resolve_target_vault(cfg, "C:\\Users\\hexk\\OneDrive\\文档\\New project 6")
        self.assertEqual(vault, "C:/KKNexus")
        self.assertEqual(label, "KKNexus")
    
    def test_resolve_target_vault_skill(self):
        cfg = {
            "vault_path": "C:/KKNexus",
            "codex_home": os.path.expanduser("~/.codex"),
            "vault_routing_rules": [
                {"pattern": "equity[-_]?incentive", "vault": "%CODEX_HOME%/skills/equity-incentive/vault", "label": "ei"},
                {"pattern": ".*", "vault": "_unrouted", "label": "UNROUTED"},
            ]
        }
        vault, label = resolve_target_vault(cfg, "/home/user/.codex/skills/equity-incentive/vault")
        self.assertIn("equity-incentive", vault)
        self.assertEqual(label, "ei")
    
    def test_resolve_target_vault_unrouted(self):
        cfg = {
            "vault_path": "C:/KKNexus",
            "vault_routing_rules": [
                {"pattern": "New project [0-9]+", "vault": "C:/KKNexus", "label": "KKNexus"},
                {"pattern": ".*", "vault": "_unrouted", "label": "UNROUTED"},
            ]
        }
        vault, label = resolve_target_vault(cfg, "/tmp/test")
        self.assertEqual(vault, "C:/KKNexus")
        self.assertEqual(label, "UNROUTED")


class TestDeploy(unittest.TestCase):
    def test_discover_skill_vaults(self):
        from config import discover_skill_vaults
        codex_home = os.environ.get("CODEX_HOME", os.path.expanduser("~/.codex"))
        vaults = discover_skill_vaults(codex_home)
        self.assertIn("equity-incentive", vaults)
        self.assertIn("ima-knowledge", vaults)
        self.assertGreaterEqual(len(vaults), 3)
    
    def test_generate_routing_rules(self):
        from config import generate_routing_rules
        mock = {"equity-incentive": "/skills/equity-incentive/vault",
                "tax-compliance-expert": "/skills/tax-compliance-expert/vault"}
        rules = generate_routing_rules(mock)
        self.assertEqual(len(rules), 2)


if __name__ == "__main__":
    unittest.main()
