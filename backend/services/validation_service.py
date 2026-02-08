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
        # ---- 简写标签格式（向后兼容）----
        ValidationCase(
            name="clock_holdover_tag_format",
            logs=[
                "[CLK][WARN] reference lost",
                "[CLK][ERROR] PLL status changed: LOCK -> UNLOCK",
                "[CLK][INFO] enter holdover",
            ],
            expected_root_keywords=["参考源", "holdover"],
        ),
        ValidationCase(
            name="switch_clock_fusion_tag_format",
            logs=[
                "[SW][WARN] port flap detected on ge0/0/1",
                "[CLK][INFO] enter holdover",
            ],
            expected_root_keywords=["Switch", "Holdover"],
        ),
        # ---- DOTLOG 格式（主格式）----
        ValidationCase(
            name="clock_holdover_dotlog_format",
            logs=[
                "[360150][42] 2026/02/01 10:00:10.500890123 0x30B00010 ERROR src/driver/clk/clk_ref_sel.c:200 ClkRefSel_QualityMonitor: GNSS reference source unavailable (0x00000001, 0x00000000, 0x00000000, 0x00000000)",
                "[360155][42] 2026/02/01 10:00:15.550901234 0x30A00002 ERROR src/driver/clk/clk_core.c:405 Clk_CheckPllStatus: PLL status changed LOCK->UNLOCK state_reg=0x3 (0x00000003, 0x00000000, 0x00000044, 0x00000000)",
                "[360170][42] 2026/02/01 10:00:10.700234567 0x30100020 TIPS src/driver/clk/holdover.c:88 Holdover_Activate: Holdover mode activated oscillator=OCXO (0x00000001, 0x0000000F, 0x00015180, 0x00000000)",
            ],
            expected_root_keywords=["参考源", "holdover"],
        ),
        ValidationCase(
            name="switch_clock_fusion_dotlog_format",
            logs=[
                "[360050][80] 2026/02/01 10:00:05.000567890 0x80A00001 ERROR src/driver/switch/port_mgr.c:88 PortMgr_LinkFlapDetect: port flap detected on ge0/0/1 flap_count=5 (0x00000005, 0x00000001, 0x00000000, 0x00000000)",
                "[360170][42] 2026/02/01 10:00:10.700234567 0x30100020 TIPS src/driver/clk/holdover.c:88 Holdover_Activate: Holdover mode activated oscillator=OCXO (0x00000001, 0x0000000F, 0x00015180, 0x00000000)",
            ],
            expected_root_keywords=["Switch", "Holdover"],
        ),
        # ---- BBU 格式（向后兼容）----
        ValidationCase(
            name="clock_holdover_bbu_format",
            logs=[
                "c[2026/02/01 10:00:10.500890123] sev:WARN src:CLK_REF_SEL RefQualityMonitor(): GNSS reference source unavailable.",
                "c[2026/02/01 10:00:15.550901234] sev:ERR error:0x30A002 src:PLL_CTRL:: [ clk_core.c / Clk_CheckPllStatus / 405 ]: PLL status changed: LOCK -> UNLOCK.",
                "c[2026/02/01 10:00:10.700234567] sev:INFO src:HOLDOVER_CTRL HoldoverActivate(): Holdover mode activated.",
            ],
            expected_root_keywords=["参考源", "holdover"],
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
