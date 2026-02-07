"""多组件诊断内核：Core + SkillPack + 渐进式检索 + 融合推理。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
import re


@dataclass
class UnifiedEvent:
    timestamp: str | None
    component: str
    module: str | None
    level: str | None
    event_type: str
    keywords: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    raw: str = ""


@dataclass
class KnowledgeSnippet:
    level: int
    text: str
    source: str


class SkillPack(Protocol):
    name: str

    def detect(self, line: str) -> bool: ...

    def normalize(self, line: str) -> UnifiedEvent | None: ...

    def retrieve(self, query: str, level: int, budget_tokens: int) -> list[KnowledgeSnippet]: ...


class ClockSkillPack:
    """示例组件包：Clock。"""

    name = "clock"

    _knowledge: dict[int, list[KnowledgeSnippet]] = {
        0: [KnowledgeSnippet(0, "Clock 组件负责同步锁定与保持。", "clock:L0:summary")],
        1: [
            KnowledgeSnippet(1, "1588/PTP 锁定失败时可能进入 holdover。", "clock:L1:principle"),
            KnowledgeSnippet(1, "参考源丢失会触发时钟稳定性下降。", "clock:L1:principle"),
        ],
        2: [
            KnowledgeSnippet(2, "连续 unlock timeout + reference lost 通常指向参考源异常。", "clock:L2:rule"),
            KnowledgeSnippet(2, "进入 holdover 是同步链路异常的关键状态信号。", "clock:L2:rule"),
        ],
        3: [KnowledgeSnippet(3, "建议动作：检查上游同步源链路、PTP 会话与参考源输入。", "clock:L3:ops")],
    }

    def detect(self, line: str) -> bool:
        l = line.lower()
        return "[clk]" in l or "holdover" in l or "unlock" in l or "reference" in l

    def normalize(self, line: str) -> UnifiedEvent | None:
        if not self.detect(line):
            return None
        l = line.lower()
        level = "INFO"
        m = re.search(r"\[(info|warn|error|debug)\]", l)
        if m:
            level = m.group(1).upper()

        if "holdover" in l:
            event_type = "state_change"
            keywords = ["holdover"]
        elif "reference lost" in l:
            event_type = "reference_lost"
            keywords = ["reference", "lost"]
        elif "unlock" in l:
            event_type = "unlock_timeout"
            keywords = ["unlock", "timeout"]
        elif "1588" in l or "ptp" in l:
            event_type = "sync_quality_drop"
            keywords = ["ptp", "1588"]
        else:
            event_type = "clock_unknown"
            keywords = ["clock"]

        return UnifiedEvent(
            timestamp=None,
            component="clock",
            module="sync",
            level=level,
            event_type=event_type,
            keywords=keywords,
            raw=line,
        )

    def retrieve(self, query: str, level: int, budget_tokens: int) -> list[KnowledgeSnippet]:
        snippets = list(self._knowledge.get(level, []))
        out: list[KnowledgeSnippet] = []
        used = 0
        for s in snippets:
            cost = max(1, len(s.text) // 2)
            if used + cost > budget_tokens:
                break
            out.append(s)
            used += cost
        return out


class SwitchSkillPack:
    name = "switch"

    _knowledge: dict[int, list[KnowledgeSnippet]] = {
        0: [KnowledgeSnippet(0, "Switch 组件负责链路稳定与转发。", "switch:L0:summary")],
        2: [KnowledgeSnippet(2, "port flap 会导致上游同步抖动与短时中断。", "switch:L2:rule")],
    }

    def detect(self, line: str) -> bool:
        l = line.lower()
        return "[sw]" in l or "port flap" in l

    def normalize(self, line: str) -> UnifiedEvent | None:
        if not self.detect(line):
            return None
        l = line.lower()
        event_type = "port_flap" if "port flap" in l else "switch_unknown"
        return UnifiedEvent(
            timestamp=None,
            component="switch",
            module="port",
            level="WARN" if "warn" in l else "INFO",
            event_type=event_type,
            keywords=["port", "flap"] if event_type == "port_flap" else ["switch"],
            raw=line,
        )

    def retrieve(self, query: str, level: int, budget_tokens: int) -> list[KnowledgeSnippet]:
        snippets = list(self._knowledge.get(level, []))
        out: list[KnowledgeSnippet] = []
        used = 0
        for s in snippets:
            cost = max(1, len(s.text) // 2)
            if used + cost > budget_tokens:
                break
            out.append(s)
            used += cost
        return out


class DiagnosisCore:
    """组件无关内核：统一事件 + 渐进检索 + 融合输出。"""

    def __init__(self):
        self.skillpacks: dict[str, SkillPack] = {}

    def register(self, skillpack: SkillPack) -> None:
        self.skillpacks[skillpack.name] = skillpack

    def route_components(self, log_lines: list[str]) -> list[str]:
        hits: dict[str, int] = {k: 0 for k in self.skillpacks}
        for line in log_lines:
            for name, sp in self.skillpacks.items():
                if sp.detect(line):
                    hits[name] += 1
        return [name for name, cnt in sorted(hits.items(), key=lambda x: x[1], reverse=True) if cnt > 0]

    def normalize_events(self, log_lines: list[str]) -> list[UnifiedEvent]:
        events: list[UnifiedEvent] = []
        for line in log_lines:
            for sp in self.skillpacks.values():
                evt = sp.normalize(line)
                if evt:
                    events.append(evt)
                    break
        return events

    def progressive_retrieve(self, component: str, query: str, max_level: int = 3, budget_per_level: int = 120) -> list[KnowledgeSnippet]:
        sp = self.skillpacks[component]
        selected: list[KnowledgeSnippet] = []
        for level in range(max_level + 1):
            selected.extend(sp.retrieve(query=query, level=level, budget_tokens=budget_per_level))
            # 足够证据则停止扩检
            if level >= 2 and len(selected) >= 3:
                break
        return selected

    def diagnose(self, log_lines: list[str]) -> dict[str, Any]:
        routed = self.route_components(log_lines)
        events = self.normalize_events(log_lines)

        evidence: list[str] = []
        retrieval_trace: dict[str, list[str]] = {}
        for comp in routed:
            snippets = self.progressive_retrieve(comp, query="\n".join(log_lines))
            retrieval_trace[comp] = [s.source for s in snippets]
            evidence.extend([s.text for s in snippets])

        etypes = {e.event_type for e in events}
        root_cause = "未识别"
        actions = ["补充上下文日志并复核告警时间窗"]
        impact = "待确认"
        chain: list[str] = []

        if "port_flap" in etypes and "state_change" in etypes:
            root_cause = "Switch 端口抖动导致同步抖动，Clock 进入 Holdover"
            impact = "同步质量下降，可能引发业务去激活"
            actions = ["修复/更换异常端口链路", "检查 PTP 会话稳定性", "确认 Clock 退出 holdover"]
            chain = ["Switch port flap", "PTP jitter", "Clock holdover"]
        elif {"reference_lost", "state_change"}.issubset(etypes) or {"unlock_timeout", "state_change"}.issubset(etypes):
            root_cause = "参考源异常触发 Clock holdover"
            impact = "时钟精度下降，业务存在质量风险"
            actions = ["检查同步源链路与输入质量", "核查上游参考源状态"]
            chain = ["reference anomaly", "clock unlock/holdover"]

        return {
            "phenomenon_summary": f"检测到 {len(events)} 条关键事件，涉及组件: {', '.join(routed) if routed else 'none'}",
            "root_cause": root_cause,
            "impact": impact,
            "recommended_actions": actions,
            "causal_chain": chain,
            "evidence": evidence[:8],
            "retrieval_trace": retrieval_trace,
            "events": [e.__dict__ for e in events],
        }


def build_default_core() -> DiagnosisCore:
    core = DiagnosisCore()
    core.register(ClockSkillPack())
    core.register(SwitchSkillPack())
    return core
