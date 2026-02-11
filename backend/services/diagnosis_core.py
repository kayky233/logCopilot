"""多组件诊断内核：Core + SkillPack + 渐进式检索 + 融合推理。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
import re

# ---------------------------------------------------------------------------
# 公共工具：日志行解析（兼容 DOTLOG / BBU / 简写标签 三种格式）
# ---------------------------------------------------------------------------

# ===== 格式 1: DOTLOG（主格式，类似 Linux 内核 pr_err 宏输出）=====
# 字段: tick, pid, timestamp, code, level(TIPS/ERROR), path, line, dotlog(函数名+内容), p1,p2,p3,p4
# 示例: [360015][42] 2026/02/01 10:00:15.550901234 0x30A00201 ERROR src/driver/clk/clk_core.c:405 Clk_CheckPllStatus: PLL lost lock (0x00000003, 0x00000000, 0x00000050, 0x00000000)
_RE_DOTLOG_HEADER = re.compile(
    r"^\[(\d+)\]\[(\d+)\]\s+"                                 # [tick][pid]
    r"(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+"       # timestamp
    r"(0x[0-9A-Fa-f]+)\s+"                                    # code
    r"(\w+)\s+"                                                # level (TIPS/ERROR)
    r"(\S+?):(\d+)\s+"                                        # path:line
)
_RE_DOTLOG_PARAMS = re.compile(r"\(([^)]+)\)\s*$")             # 尾部 (p1, p2, p3, p4)

# ===== 格式 2: BBU 板级格式 =====
# 示例: c[2026/02/01 10:00:15.550901234] sev:ERR error:0x30A002 src:PLL_CTRL:: [clk.c/func/405]: msg
_RE_BBU_TIMESTAMP = re.compile(r"c\[(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]")
_RE_BBU_LEVEL = re.compile(r"\bsev:(INFO|WARN|ERR|FATAL|DEBUG)\b", re.IGNORECASE)
_RE_BBU_MODULE = re.compile(r"\bsrc:(\S+?)(?:::|[\s])", re.IGNORECASE)

# ===== 格式 3: 简写标签格式 =====
# 示例: [CLK][WARN] reference lost
_RE_TAG_LEVEL = re.compile(r"\[(INFO|WARN|ERROR|FATAL|DEBUG)\]", re.IGNORECASE)

# 级别归一化
_LEVEL_NORM: dict[str, str] = {
    "INFO": "INFO", "TIPS": "INFO", "WARN": "WARN", "WARNING": "WARN",
    "ERR": "ERROR", "ERROR": "ERROR",
    "FATAL": "FATAL", "DEBUG": "DEBUG",
}

# 根据 dotlog 内容推断严重级别（DOTLOG 格式没有显式 sev 字段）
_SEVERITY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("FATAL", ["fatal error", "panic", "crash", "system halt", "dead", "watchdog reset"]),
    ("ERROR", ["error", "failed", "fault", "lost", "unavailable", "unreachable",
               "timeout", "exceed", "abnormal", "violation", "unlock"]),
    ("WARN",  ["warn", "degraded", "insufficient", "weak", "oscillation",
               "suppress", "flap", "holdover", "switchover", "accumulating"]),
]


@dataclass
class ParsedLine:
    """一行日志的结构化解析结果。"""
    format: str                     # "dotlog" | "bbu" | "tag" | "unknown"
    timestamp: str | None = None
    tick: int | None = None
    pid: int | None = None
    code: str | None = None         # DOTLOG code, e.g. "0x30A00201"
    path: str | None = None         # 源文件路径
    line_no: int | None = None      # 源文件行号
    func: str | None = None         # 函数名
    message: str = ""               # 日志正文
    level: str = "INFO"             # 推断的级别
    module: str | None = None       # 模块名 (从 path 或 src: 提取)
    params: list[str] = field(default_factory=list)  # p1~p4
    raw: str = ""


def _infer_level_from_content(text: str) -> str:
    """根据日志正文关键词推断严重级别。"""
    low = text.lower()
    for level, keywords in _SEVERITY_KEYWORDS:
        if any(kw in low for kw in keywords):
            return level
    return "INFO"


def _module_from_path(path: str) -> str | None:
    """从源文件路径提取模块名，如 src/driver/clk/clk_core.c → clk。"""
    parts = path.replace("\\", "/").split("/")
    # 尝试找有意义的目录名
    for p in reversed(parts[:-1]):  # 跳过文件名
        if p and p not in ("src", "driver", "module", "lib", "platform"):
            return p
    return None


def parse_line(raw: str) -> ParsedLine:
    """解析一行日志，自动识别格式。"""
    stripped = raw.strip()
    if not stripped:
        return ParsedLine(format="unknown", raw=raw)

    # ---- 尝试 DOTLOG 格式 ----
    m = _RE_DOTLOG_HEADER.match(stripped)
    if m:
        tick = int(m.group(1))
        pid = int(m.group(2))
        timestamp = m.group(3)
        code = m.group(4)
        raw_level = m.group(5).upper()           # TIPS / ERROR
        path = m.group(6)
        line_no = int(m.group(7))
        rest = stripped[m.end():]

        # 提取尾部参数 (p1, p2, p3, p4)
        params: list[str] = []
        pm = _RE_DOTLOG_PARAMS.search(rest)
        if pm:
            params = [p.strip() for p in pm.group(1).split(",")]
            rest = rest[:pm.start()].strip()

        # 提取函数名和消息
        func = None
        message = rest
        colon_idx = rest.find(":")
        if colon_idx > 0 and colon_idx < 60:  # 合理的函数名长度
            func = rest[:colon_idx].strip()
            message = rest[colon_idx + 1:].strip()

        module = _module_from_path(path)
        # DOTLOG 有显式 level 字段：ERROR 直接采用，TIPS 进一步用内容推断细化
        if raw_level == "ERROR":
            inferred = _infer_level_from_content(message)
            # "fatal error" 等关键词 → FATAL，否则保持 ERROR
            level = inferred if inferred == "FATAL" else "ERROR"
        else:
            # TIPS → 默认 INFO，但内容中有 warn 级关键词可升级
            level = _LEVEL_NORM.get(raw_level, "INFO")

        return ParsedLine(
            format="dotlog", timestamp=timestamp, tick=tick, pid=pid,
            code=code, path=path, line_no=line_no, func=func,
            message=message, level=level, module=module, params=params, raw=raw,
        )

    # ---- 尝试 BBU 格式 ----
    bbu_ts = _RE_BBU_TIMESTAMP.search(stripped)
    if bbu_ts:
        timestamp = bbu_ts.group(1)
        lm = _RE_BBU_LEVEL.search(stripped)
        level = _LEVEL_NORM.get(lm.group(1).upper(), "INFO") if lm else _infer_level_from_content(stripped)
        mm = _RE_BBU_MODULE.search(stripped)
        module = mm.group(1) if mm else None
        return ParsedLine(
            format="bbu", timestamp=timestamp, level=level,
            module=module, message=stripped, raw=raw,
        )

    # ---- 尝试简写标签格式 ----
    tm = _RE_TAG_LEVEL.search(stripped)
    if tm:
        level = _LEVEL_NORM.get(tm.group(1).upper(), "INFO")
        return ParsedLine(
            format="tag", level=level, message=stripped, raw=raw,
        )

    # ---- 未知格式 ----
    return ParsedLine(
        format="unknown", level=_infer_level_from_content(stripped),
        message=stripped, raw=raw,
    )


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数。中文 ≈ 1.5 token/字，英文 ≈ 1 token/4字符（近似值）。"""
    cn_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    en_chars = len(text) - cn_chars
    return max(1, int(cn_chars * 1.5 + en_chars / 4))


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# SkillPack Protocol
# ---------------------------------------------------------------------------

class SkillPack(Protocol):
    name: str

    def detect(self, line: str) -> bool: ...

    def normalize(self, line: str) -> UnifiedEvent | None: ...

    def retrieve(self, query: str, level: int, budget_tokens: int) -> list[KnowledgeSnippet]: ...


# ---------------------------------------------------------------------------
# ClockSkillPack
# ---------------------------------------------------------------------------

class ClockSkillPack:
    """组件包：Clock（时钟与同步子系统）。"""

    name = "clock"

    def __init__(self) -> None:
        self._knowledge: dict[int, list[KnowledgeSnippet]] = {
            0: [KnowledgeSnippet(0, "Clock 组件负责同步锁定与保持，核心是 DPLL 锁定外部参考源。", "clock:L0:summary")],
            1: [
                KnowledgeSnippet(1, "1588/PTP 锁定失败时可能进入 holdover，需检查上游 T-BC 和 Master 状态。", "clock:L1:principle"),
                KnowledgeSnippet(1, "参考源丢失会触发时钟稳定性下降，系统按 GNSS→1588→SyncE→本地晶振 优先级回退。", "clock:L1:principle"),
            ],
            2: [
                KnowledgeSnippet(2, "PLL 失锁 (LOCK->UNLOCK) + reference lost 通常指向参考源异常。", "clock:L2:rule"),
                KnowledgeSnippet(2, "进入 holdover 是同步链路异常的关键状态信号，OCXO 漂移约 1μs/h。", "clock:L2:rule"),
                KnowledgeSnippet(2, "TDD 帧偏移超过 ±1.5μs 会导致站间干扰和业务中断。", "clock:L2:rule"),
            ],
            3: [
                KnowledgeSnippet(3, "建议动作：检查上游同步源链路、PTP 会话与参考源输入。", "clock:L3:ops"),
                KnowledgeSnippet(3, "建议动作：检查 GPS 天线电压(4.6~5.4V)、馈线连接、避雷器状态。", "clock:L3:ops"),
            ],
        }

    # 路径前缀 → 属于时钟组件
    _CLK_PATH_DIRS = ("clk", "pll", "gnss", "holdover", "ptp", "sync", "dpll", "clock")
    # BBU src: 前缀
    _CLK_MODULE_PREFIXES = ("clk_", "pll_", "gnss_", "holdover_", "ptp_")
    # 关键词兜底
    _CLK_KEYWORDS = ("holdover", "unlock", "reference", "pll", "1588", "ptp",
                     "gnss", "synce", "dpll", "free_run", "free-run", "clock",
                     "satellite", "antenna")

    def detect(self, line: str) -> bool:
        parsed = parse_line(line)
        # DOTLOG: 根据源文件路径中的目录名判定
        if parsed.format == "dotlog" and parsed.module:
            if parsed.module.lower() in self._CLK_PATH_DIRS:
                return True
        # BBU: 根据 src: 模块名前缀
        if parsed.format == "bbu" and parsed.module:
            if parsed.module.lower().startswith(self._CLK_MODULE_PREFIXES):
                return True
        # 简写标签
        low = line.lower()
        if "[clk]" in low or "[gnss]" in low or "[ptp]" in low:
            return True
        # 关键词兜底
        return any(kw in low for kw in self._CLK_KEYWORDS)

    def normalize(self, line: str) -> UnifiedEvent | None:
        if not self.detect(line):
            return None
        parsed = parse_line(line)
        low = parsed.message.lower() if parsed.message else line.lower()

        # 事件类型映射 —— 按特异性从高到低
        if "holdover" in low:
            event_type = "state_change"
            keywords = ["holdover"]
        elif "free_run" in low or "free-run" in low or "free running" in low:
            event_type = "state_change"
            keywords = ["free_run"]
        elif "reference" in low and ("lost" in low or "unavailable" in low):
            event_type = "reference_lost"
            keywords = ["reference", "lost"]
        elif "lock -> unlock" in low or "lock->unlock" in low or ("lock" in low and "unlock" in low):
            event_type = "pll_unlock"
            keywords = ["pll", "unlock"]
        elif "unlock" in low:
            event_type = "pll_unlock"
            keywords = ["pll", "unlock"]
        elif "jitter" in low or "exceed" in low:
            event_type = "jitter_exceed"
            keywords = ["jitter", "exceed"]
        elif ("1588" in low or "ptp" in low) and ("timeout" in low or "lost" in low or "fail" in low):
            event_type = "sync_quality_drop"
            keywords = ["ptp", "1588"]
        elif "antenna" in low and ("fault" in low or "abnormal" in low or "short" in low or "open" in low):
            event_type = "antenna_fault"
            keywords = ["antenna"]
        elif "satellite" in low or ("gnss" in low and ("insufficient" in low or "search" in low)):
            event_type = "gnss_signal_issue"
            keywords = ["gnss", "satellite"]
        elif "switchover" in low:
            event_type = "source_switchover"
            keywords = ["switchover"]
        elif "oscillation" in low:
            event_type = "source_oscillation"
            keywords = ["oscillation"]
        else:
            event_type = "clock_unknown"
            keywords = ["clock"]

        attrs: dict[str, Any] = {}
        if parsed.code:
            attrs["code"] = parsed.code
        if parsed.params:
            for i, p in enumerate(parsed.params, 1):
                attrs[f"p{i}"] = p
        if parsed.tick is not None:
            attrs["tick"] = parsed.tick
        if parsed.path:
            attrs["path"] = parsed.path
            attrs["line_no"] = parsed.line_no
        if parsed.func:
            attrs["func"] = parsed.func

        return UnifiedEvent(
            timestamp=parsed.timestamp,
            component="clock",
            module=parsed.module or "sync",
            level=parsed.level,
            event_type=event_type,
            keywords=keywords,
            attributes=attrs,
            raw=line,
        )

    def retrieve(self, query: str, level: int, budget_tokens: int) -> list[KnowledgeSnippet]:
        snippets = list(self._knowledge.get(level, []))
        out: list[KnowledgeSnippet] = []
        used = 0
        for s in snippets:
            cost = _estimate_tokens(s.text)
            if used + cost > budget_tokens:
                break
            out.append(s)
            used += cost
        return out


# ---------------------------------------------------------------------------
# SwitchSkillPack
# ---------------------------------------------------------------------------

class SwitchSkillPack:
    """组件包：Switch（交换与链路管理）。"""

    name = "switch"

    def __init__(self) -> None:
        self._knowledge: dict[int, list[KnowledgeSnippet]] = {
            0: [KnowledgeSnippet(0, "Switch 组件负责链路稳定与转发，含端口管理、ESMC 透传。", "switch:L0:summary")],
            1: [
                KnowledgeSnippet(1, "端口 flap 可能由光模块故障、光纤弯曲、对端设备重启引起。", "switch:L1:principle"),
                KnowledgeSnippet(1, "ESMC (以太网同步消息通道) 丢失会导致 SyncE 参考源不可用。", "switch:L1:principle"),
            ],
            2: [KnowledgeSnippet(2, "port flap 会导致上游 PTP 同步抖动与短时中断，进而影响 Clock 子系统。", "switch:L2:rule")],
            3: [
                KnowledgeSnippet(3, "建议动作：检查光模块收发功率、光纤连接、对端端口状态。", "switch:L3:ops"),
                KnowledgeSnippet(3, "建议动作：检查是否存在 STP 拓扑变更或环路。", "switch:L3:ops"),
            ],
        }

    _SW_PATH_DIRS = ("switch", "sw", "port", "esmc", "eth")
    _SW_MODULE_PREFIXES = ("switch_", "sw_", "port_", "esmc_")
    _SW_KEYWORDS = ("port flap", "port down", "port up", "link flap",
                    "esmc", "[sw]", "switch")

    def detect(self, line: str) -> bool:
        parsed = parse_line(line)
        if parsed.format == "dotlog" and parsed.module:
            if parsed.module.lower() in self._SW_PATH_DIRS:
                return True
        if parsed.format == "bbu" and parsed.module:
            if parsed.module.lower().startswith(self._SW_MODULE_PREFIXES):
                return True
        low = line.lower()
        if "[sw]" in low:
            return True
        return any(kw in low for kw in self._SW_KEYWORDS)

    def normalize(self, line: str) -> UnifiedEvent | None:
        if not self.detect(line):
            return None
        parsed = parse_line(line)
        low = parsed.message.lower() if parsed.message else line.lower()

        if "port flap" in low or "link flap" in low:
            event_type = "port_flap"
            keywords = ["port", "flap"]
        elif "port down" in low:
            event_type = "port_down"
            keywords = ["port", "down"]
        elif "esmc" in low:
            event_type = "esmc_event"
            keywords = ["esmc"]
        else:
            event_type = "switch_unknown"
            keywords = ["switch"]

        attrs: dict[str, Any] = {}
        if parsed.code:
            attrs["code"] = parsed.code
        if parsed.params:
            for i, p in enumerate(parsed.params, 1):
                attrs[f"p{i}"] = p

        return UnifiedEvent(
            timestamp=parsed.timestamp,
            component="switch",
            module=parsed.module or "port",
            level=parsed.level,
            event_type=event_type,
            keywords=keywords,
            attributes=attrs,
            raw=line,
        )

    def retrieve(self, query: str, level: int, budget_tokens: int) -> list[KnowledgeSnippet]:
        snippets = list(self._knowledge.get(level, []))
        out: list[KnowledgeSnippet] = []
        used = 0
        for s in snippets:
            cost = _estimate_tokens(s.text)
            if used + cost > budget_tokens:
                break
            out.append(s)
            used += cost
        return out


# ---------------------------------------------------------------------------
# DiagnosisCore
# ---------------------------------------------------------------------------

class DiagnosisCore:
    """组件无关内核：统一事件 + 渐进检索 + 融合输出。"""

    def __init__(self) -> None:
        self.skillpacks: dict[str, SkillPack] = {}

    def register(self, skillpack: SkillPack) -> None:
        self.skillpacks[skillpack.name] = skillpack

    def _route_and_normalize(self, log_lines: list[str]) -> tuple[list[str], list[UnifiedEvent]]:
        """单次遍历：组件命中统计 + 事件规范化。"""
        hits: dict[str, int] = {k: 0 for k in self.skillpacks}
        events: list[UnifiedEvent] = []
        for line in log_lines:
            for name, sp in self.skillpacks.items():
                evt = sp.normalize(line)
                if evt:
                    hits[name] += 1
                    events.append(evt)
                    break
        routed = [name for name, cnt in sorted(hits.items(), key=lambda x: x[1], reverse=True) if cnt > 0]
        return routed, events

    def route_components(self, log_lines: list[str]) -> list[str]:
        routed, _ = self._route_and_normalize(log_lines)
        return routed

    def normalize_events(self, log_lines: list[str]) -> list[UnifiedEvent]:
        _, events = self._route_and_normalize(log_lines)
        return events

    def progressive_retrieve(
        self,
        component: str,
        query: str,
        max_level: int = 3,
        budget_per_level: int = 120,
    ) -> list[KnowledgeSnippet]:
        sp = self.skillpacks.get(component)
        if sp is None:
            raise ValueError(f"未注册的组件: {component!r}，已注册: {list(self.skillpacks.keys())}")

        selected: list[KnowledgeSnippet] = []
        for level in range(max_level + 1):
            selected.extend(sp.retrieve(query=query, level=level, budget_tokens=budget_per_level))
            # 仅在 L0/L1（背景/原理）充足时可跳过，L2（规则）和 L3（运维）总是尝试
            if level <= 1 and len(selected) >= 6:
                break
        return selected

    def diagnose(self, log_lines: list[str]) -> dict[str, Any]:
        routed, events = self._route_and_normalize(log_lines)

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

        # ---- 多组件因果链 ----
        if "port_flap" in etypes and ("state_change" in etypes or "pll_unlock" in etypes):
            root_cause = "Switch 端口抖动导致同步抖动，Clock 进入 Holdover"
            impact = "同步质量下降，可能引发业务去激活"
            actions = ["修复/更换异常端口链路", "检查 PTP 会话稳定性", "确认 Clock 退出 holdover"]
            chain = ["Switch port flap", "PTP jitter", "Clock holdover"]

        # ---- 单组件：参考源异常 → Clock 故障 ----
        elif {"reference_lost", "state_change"}.issubset(etypes) or {"pll_unlock", "state_change"}.issubset(etypes):
            root_cause = "参考源异常触发 Clock holdover"
            impact = "时钟精度下降，业务存在质量风险"
            actions = ["检查同步源链路与输入质量", "核查上游参考源状态"]
            chain = ["reference anomaly", "clock unlock/holdover"]

        elif "pll_unlock" in etypes:
            root_cause = "PLL 失锁，参考源可能异常"
            impact = "时钟精度下降，业务存在中断风险"
            actions = ["检查参考源输入", "检查 PLL 硬件状态寄存器"]
            chain = ["pll unlock"]

        elif "antenna_fault" in etypes:
            root_cause = "GPS 天线故障（开路/短路）"
            impact = "GNSS 参考源不可用，影响时钟同步"
            actions = ["检查天线馈线连接", "检查避雷器状态", "测量天线电压"]
            chain = ["antenna fault", "GNSS unavailable"]

        elif "source_oscillation" in etypes:
            root_cause = "时钟源切换振荡，参考源信号不稳定"
            impact = "PLL 频繁重锁，同步质量不稳定"
            actions = ["增大 WTR 回切迟滞时间", "排查 GNSS 干扰源", "考虑手动锁定备用源"]
            chain = ["reference instability", "source oscillation"]

        elif "port_flap" in etypes or "port_down" in etypes:
            root_cause = "Switch 端口异常"
            impact = "链路中断，可能影响传输和同步"
            actions = ["检查光模块和光纤", "检查对端端口状态"]
            chain = ["port fault"]

        return {
            "phenomenon_summary": f"检测到 {len(events)} 条关键事件，涉及组件: {', '.join(routed) if routed else 'none'}",
            "root_cause": root_cause,
            "impact": impact,
            "recommended_actions": actions,
            "causal_chain": chain,
            "evidence": evidence[:10],
            "retrieval_trace": retrieval_trace,
            "events": [e.__dict__ for e in events],
        }


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------

def build_default_core() -> DiagnosisCore:
    core = DiagnosisCore()
    core.register(ClockSkillPack())
    core.register(SwitchSkillPack())
    return core
