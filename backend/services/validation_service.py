"""低成本验证服务：使用模拟日志验证架构闭环。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.services.diagnosis_core import build_default_core


@dataclass
class ValidationCase:
    name: str
    logs: list[str]
    expected_root_keywords: list[str]


def default_validation_cases() -> list[ValidationCase]:
    return [
        ValidationCase(
            name="clock_holdover_single_component",
            logs=[
                "[CLK][WARN] reference lost",
                "[CLK][ERROR] unlock timeout",
                "[CLK][INFO] enter holdover",
            ],
            expected_root_keywords=["参考源", "holdover"],
        ),
        ValidationCase(
            name="switch_clock_fusion",
            logs=[
                "[SW][WARN] port flap detected on ge0/0/1",
                "[CLK][INFO] enter holdover",
            ],
            expected_root_keywords=["Switch", "Holdover"],
        ),
    ]


def run_validation() -> dict[str, Any]:
    core = build_default_core()
    cases = default_validation_cases()

    results = []
    passed = 0
    for case in cases:
        report = core.diagnose(case.logs)
        root = report["root_cause"]
        ok = all(k.lower() in root.lower() for k in case.expected_root_keywords)
        if ok:
            passed += 1
        results.append({
            "name": case.name,
            "passed": ok,
            "root_cause": root,
            "causal_chain": report.get("causal_chain", []),
        })

    return {
        "total": len(cases),
        "passed": passed,
        "details": results,
    }
