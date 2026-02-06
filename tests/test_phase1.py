"""
Phase 1 验证测试 — 用户隔离、缓存、文件限制
运行: python -m pytest tests/test_phase1.py -v
"""
import os
import sys
import json

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import utils


class TestUserWorkspace:
    """测试用户工作空间隔离"""

    def test_sanitize_user_id(self):
        assert utils._sanitize_user_id("alice") == "alice"
        assert utils._sanitize_user_id("../../../etc") == "etc"
        assert utils._sanitize_user_id("user@domain.com") == "userdomaincom"
        assert utils._sanitize_user_id("") == "default"
        assert len(utils._sanitize_user_id("a" * 100)) <= 64

    def test_workspace_paths_isolated(self):
        ws_a = utils.get_user_workspace("alice")
        ws_b = utils.get_user_workspace("bob")
        assert ws_a["root"] != ws_b["root"]
        assert "alice" in ws_a["root"]
        assert "bob" in ws_b["root"]

    def test_init_creates_directories(self):
        utils.init_environment("test_user_123")
        ws = utils.get_user_workspace("test_user_123")
        assert os.path.exists(ws["logs"])
        manual_root = utils.get_user_manual_root("test_user_123")
        for domain in utils.DOMAINS:
            assert os.path.exists(os.path.join(manual_root, domain))

    def test_storage_usage_empty(self):
        utils.init_environment("test_empty_user")
        usage = utils.get_user_storage_usage("test_empty_user")
        assert usage["total_mb"] >= 0
        assert usage["file_count"] >= 0
        assert usage["limit_mb"] == utils.MAX_TOTAL_STORAGE_MB


class TestFileUploadSecurity:
    """测试文件上传安全限制"""

    def test_upload_allowed_normal(self):
        allowed, reason = utils.check_upload_allowed("test_user", 1024 * 1024)  # 1MB
        assert allowed is True

    def test_upload_rejected_too_large(self):
        allowed, reason = utils.check_upload_allowed("test_user", 60 * 1024 * 1024)  # 60MB
        assert allowed is False
        assert "限制" in reason


class TestCache:
    """测试 LLM 缓存层"""

    def test_cache_miss_and_hit(self):
        utils.cache_clear("test_ns")
        assert utils.cache_get("test_ns", "key1") is None

        utils.cache_set("test_ns", "hello world", "key1")
        assert utils.cache_get("test_ns", "key1") == "hello world"

    def test_cache_clear(self):
        utils.cache_set("test_clear", "data", "k")
        utils.cache_clear("test_clear")
        assert utils.cache_get("test_clear", "k") is None


class TestLogProcessing:
    """测试日志处理工具"""

    def test_smart_snippet_short(self):
        content = "short log"
        assert utils.get_smart_snippet(content) == content

    def test_smart_snippet_long(self):
        content = "A" * 50000
        result = utils.get_smart_snippet(content, head=100, tail=100)
        assert len(result) < 50000
        assert "省略" in result

    def test_filter_log_content(self):
        log = "line1 OK\nline2 ERROR something\nline3 OK\nline4 FATAL crash\nline5 OK"
        result = utils.filter_log_content(log, ["ERROR", "FATAL"], context_lines=0)
        assert "ERROR" in result
        assert "FATAL" in result

    def test_filter_empty_keywords(self):
        log = "some log content"
        result = utils.filter_log_content(log, [], context_lines=0)
        assert result == log

    def test_filter_no_match(self):
        log = "everything is fine\nall good\nno issues"
        result = utils.filter_log_content(log, ["CRITICAL_BUG"], context_lines=0)
        assert "System Filter" in result


class TestFileLoading:
    """测试文件加载"""

    def test_load_text_file(self):
        test_file = os.path.join(os.path.dirname(__file__), "..", "test_cases", "log_pll_unlock.txt")
        if os.path.exists(test_file):
            content = utils.load_file_content(test_file)
            assert len(content) > 0
            assert "❌" not in content

    def test_load_nonexistent_file(self):
        content = utils.load_file_content("/nonexistent/file.txt")
        assert "❌" in content or "失败" in content or content == ""


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

