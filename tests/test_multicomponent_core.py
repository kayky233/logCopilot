import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.diagnosis_core import (
    build_default_core,
    parse_line,
)
from backend.services.validation_service import run_validation


# ---------------------------------------------------------------------------
# DOTLOG 格式解析测试
# ---------------------------------------------------------------------------

class TestDotlogParsing:
    """测试 DOTLOG 格式解析：tick, pid, timestamp, code, path, line, func, message, p1~p4。"""

    SAMPLE = (
        "[360155][42] 2026/02/01 10:00:15.550901234 0x30A00002 "
        "ERROR src/driver/clk/clk_core.c:405 Clk_CheckPllStatus: "
        "PLL status changed LOCK->UNLOCK state_reg=0x3 "
        "(0x00000003, 0x00000000, 0x00000044, 0x00000000)"
    )

    def test_format_detected(self):
        p = parse_line(self.SAMPLE)
        assert p.format == "dotlog"

    def test_tick_and_pid(self):
        p = parse_line(self.SAMPLE)
        assert p.tick == 360155
        assert p.pid == 42

    def test_timestamp(self):
        p = parse_line(self.SAMPLE)
        assert p.timestamp == "2026/02/01 10:00:15.550901234"

    def test_code(self):
        p = parse_line(self.SAMPLE)
        assert p.code == "0x30A00002"

    def test_path_and_line(self):
        p = parse_line(self.SAMPLE)
        assert p.path == "src/driver/clk/clk_core.c"
        assert p.line_no == 405

    def test_func(self):
        p = parse_line(self.SAMPLE)
        assert p.func == "Clk_CheckPllStatus"

    def test_message_contains_content(self):
        p = parse_line(self.SAMPLE)
        assert "PLL status changed" in p.message

    def test_params(self):
        p = parse_line(self.SAMPLE)
        assert len(p.params) == 4
        assert p.params[0] == "0x00000003"

    def test_level_inferred_from_content(self):
        p = parse_line(self.SAMPLE)
        # "UNLOCK" 关键词 → ERROR
        assert p.level == "ERROR"

    def test_module_from_path(self):
        p = parse_line(self.SAMPLE)
        assert p.module == "clk"


class TestBbuParsing:
    """测试 BBU 格式向后兼容。"""

    SAMPLE = "c[2026/02/01 10:00:15.550901234] sev:FATAL src:CLK_CORE:: Fatal Error"

    def test_format_detected(self):
        p = parse_line(self.SAMPLE)
        assert p.format == "bbu"

    def test_level(self):
        p = parse_line(self.SAMPLE)
        assert p.level == "FATAL"


class TestTagParsing:
    """测试简写标签格式向后兼容。"""

    def test_format_and_level(self):
        p = parse_line("[CLK][ERROR] PLL unlock")
        assert p.format == "tag"
        assert p.level == "ERROR"

    def test_fatal_level(self):
        p = parse_line("[CLK][FATAL] critical failure")
        assert p.level == "FATAL"


# ---------------------------------------------------------------------------
# 渐进式检索测试
# ---------------------------------------------------------------------------

def test_progressive_retrieval_includes_all_levels():
    """验证渐进检索在 L2 证据不足时能检索到 L3 运维建议。"""
    core = build_default_core()
    snippets = core.progressive_retrieve("clock", query="what causes holdover", max_level=3, budget_per_level=200)
    levels_retrieved = {s.level for s in snippets}
    assert levels_retrieved == {0, 1, 2, 3}, f"期望覆盖全部四层, 实际: {levels_retrieved}"


def test_progressive_retrieval_budget_control():
    """验证低预算下检索数量受控。"""
    core = build_default_core()
    snippets = core.progressive_retrieve("clock", query="holdover", max_level=3, budget_per_level=40)
    assert 1 <= len(snippets) <= 6


def test_progressive_retrieve_invalid_component():
    """验证未注册组件名抛出 ValueError。"""
    core = build_default_core()
    try:
        core.progressive_retrieve("nonexistent", query="test")
        assert False, "应该抛出 ValueError"
    except ValueError as e:
        assert "未注册" in str(e)


# ---------------------------------------------------------------------------
# 事件规范化 —— DOTLOG 格式
# ---------------------------------------------------------------------------

def test_normalization_dotlog_pll_unlock():
    core = build_default_core()
    logs = [
        "[360155][42] 2026/02/01 10:00:15.550901234 0x30A00002 ERROR src/driver/clk/clk_core.c:405 Clk_CheckPllStatus: PLL status changed LOCK->UNLOCK state_reg=0x3 (0x00000003, 0x00000000, 0x00000044, 0x00000000)",
        "[360170][42] 2026/02/01 10:00:10.700234567 0x30100020 TIPS src/driver/clk/holdover.c:88 Holdover_Activate: Holdover mode activated oscillator=OCXO (0x00000001, 0x0000000F, 0x00015180, 0x00000000)",
    ]
    events = core.normalize_events(logs)
    assert len(events) == 2
    assert events[0].component == "clock"
    assert events[0].event_type == "pll_unlock"
    assert events[0].timestamp == "2026/02/01 10:00:15.550901234"
    assert events[0].attributes.get("code") == "0x30A00002"
    assert events[0].attributes.get("p1") == "0x00000003"
    assert events[1].event_type == "state_change"


def test_normalization_dotlog_switch_port_flap():
    core = build_default_core()
    logs = [
        "[360050][80] 2026/02/01 10:00:05.000567890 0x80A00001 ERROR src/driver/switch/port_mgr.c:88 PortMgr_LinkFlapDetect: port flap detected on ge0/0/1 (0x00000005, 0x00000001, 0x00000000, 0x00000000)",
    ]
    events = core.normalize_events(logs)
    assert len(events) == 1
    assert events[0].component == "switch"
    assert events[0].event_type == "port_flap"
    assert events[0].module == "switch"


def test_normalization_dotlog_gnss_antenna_fault():
    core = build_default_core()
    logs = [
        "[720105][55] 2026/02/01 10:00:10.050678901 0x40A00011 ERROR src/driver/gnss/gnss_hw.c:135 Gnss_AntennaFaultDetect: GPS antenna connection fault detected SHORT_CIRCUIT (0x00000001, 0x000000C8, 0x00000000, 0x00000000)",
    ]
    events = core.normalize_events(logs)
    assert len(events) == 1
    assert events[0].event_type == "antenna_fault"
    assert events[0].module == "gnss"


# ---------------------------------------------------------------------------
# 事件规范化 —— 简写标签格式（向后兼容）
# ---------------------------------------------------------------------------

def test_normalization_tag_format():
    core = build_default_core()
    logs = ["[CLK][WARN] reference lost", "[CLK][INFO] enter holdover"]
    events = core.normalize_events(logs)
    assert len(events) == 2
    assert events[0].event_type == "reference_lost"
    assert events[0].level == "WARN"
    assert events[1].event_type == "state_change"


# ---------------------------------------------------------------------------
# 单组件推理 —— DOTLOG 格式
# ---------------------------------------------------------------------------

def test_single_component_reasoning_dotlog():
    core = build_default_core()
    report = core.diagnose([
        "[360155][42] 2026/02/01 10:00:15.550901234 0x30A00002 ERROR src/driver/clk/clk_core.c:405 Clk_CheckPllStatus: PLL status changed LOCK->UNLOCK (0x00000003, 0x00000000, 0x00000000, 0x00000000)",
        "[360170][42] 2026/02/01 10:00:10.700234567 0x30100020 TIPS src/driver/clk/holdover.c:88 Holdover_Activate: Holdover mode activated (0x00000001, 0x00000000, 0x00000000, 0x00000000)",
    ])
    assert "参考源" in report["root_cause"]
    assert report["causal_chain"]
    assert report["evidence"]


def test_single_component_reasoning_tag():
    core = build_default_core()
    report = core.diagnose([
        "[CLK][ERROR] PLL status changed: LOCK -> UNLOCK",
        "[CLK][INFO] enter holdover",
    ])
    assert "参考源" in report["root_cause"]


# ---------------------------------------------------------------------------
# 多组件融合 —— DOTLOG 格式
# ---------------------------------------------------------------------------

def test_multi_component_fusion_dotlog():
    core = build_default_core()
    report = core.diagnose([
        "[360050][80] 2026/02/01 10:00:05.000567890 0x80A00001 ERROR src/driver/switch/port_mgr.c:88 PortMgr_LinkFlapDetect: port flap detected on ge0/0/1 (0x00000005, 0x00000001, 0x00000000, 0x00000000)",
        "[360170][42] 2026/02/01 10:00:10.700234567 0x30100020 TIPS src/driver/clk/holdover.c:88 Holdover_Activate: Holdover mode activated (0x00000001, 0x00000000, 0x00000000, 0x00000000)",
    ])
    assert "Switch" in report["root_cause"]
    assert "Holdover" in report["root_cause"]
    assert report["causal_chain"] == ["Switch port flap", "PTP jitter", "Clock holdover"]


def test_multi_component_fusion_tag():
    core = build_default_core()
    report = core.diagnose([
        "[SW][WARN] port flap detected",
        "[CLK][INFO] enter holdover",
    ])
    assert "Switch" in report["root_cause"]
    assert report["causal_chain"] == ["Switch port flap", "PTP jitter", "Clock holdover"]


# ---------------------------------------------------------------------------
# MVP 验证包
# ---------------------------------------------------------------------------

def test_validation_service_mvp():
    result = run_validation()
    assert result["total"] == 5  # 2 tag + 2 dotlog + 1 bbu
    assert result["passed"] == result["total"], (
        f"验证未全部通过: {result['passed']}/{result['total']}, "
        f"详情: {[d for d in result['details'] if not d['passed']]}"
    )
