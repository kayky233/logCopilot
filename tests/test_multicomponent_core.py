import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from backend.services.diagnosis_core import build_default_core
from backend.services.validation_service import run_validation


def test_stage1_progressive_retrieval_without_full_text():
    core = build_default_core()
    snippets = core.progressive_retrieve("clock", query="what causes holdover", max_level=3, budget_per_level=40)
    # 在预算限制下仍可获取分层知识，且数量受控
    assert 1 <= len(snippets) <= 6
    assert all(s.source.startswith("clock:") for s in snippets)


def test_stage2_event_normalization():
    core = build_default_core()
    logs = ["[CLK][WARN] reference lost", "[CLK][INFO] enter holdover"]
    events = core.normalize_events(logs)
    assert len(events) == 2
    assert events[0].component == "clock"
    assert events[1].event_type == "state_change"


def test_stage3_single_component_reasoning_closure():
    core = build_default_core()
    report = core.diagnose([
        "[CLK][ERROR] unlock timeout",
        "[CLK][INFO] enter holdover",
    ])
    assert "参考源" in report["root_cause"]
    assert report["recommended_actions"]
    assert report["evidence"]


def test_stage5_multi_component_fusion_chain():
    core = build_default_core()
    report = core.diagnose([
        "[SW][WARN] port flap detected",
        "[CLK][INFO] enter holdover",
    ])
    assert "Switch" in report["root_cause"]
    assert report["causal_chain"] == ["Switch port flap", "PTP jitter", "Clock holdover"]


def test_validation_service_mvp_package():
    result = run_validation()
    assert result["total"] == 2
    assert result["passed"] >= 2
