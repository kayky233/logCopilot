import json

import code_utils
import utils


class BaseAgent:
    def __init__(self, client, model_name):
        self.client = client
        self.model_name = model_name

    def call_llm(self, system_prompt, user_content, max_tokens=2000):
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
                max_tokens=max_tokens,
            )
            return {"ok": True, "content": response.choices[0].message.content}
        except Exception as e:
            return {"ok": False, "error": str(e), "content": None}


class ManualAgent(BaseAgent):
    """
    📚 手册顾问：在分析日志前，先通读手册，制定“结构化维测指南”。
    """

    def extract_criteria(self, manual_content, focus_keywords=None):
        """
        Phase 1: 阅读手册，输出给 Log Agent 的结构化搜查令。
        """
        short_manual = manual_content[:15000]
        kw_hint = ""
        if focus_keywords and len(focus_keywords) > 0:
            kw_str = ", ".join(focus_keywords)
            kw_hint = f"🔍 **重点线索提示**：用户怀疑故障与以下关键词有关，请优先关注相关章节：[{kw_str}]"

        sys_p = """你是基站故障排查专家（Tier-3 Technical Support）。

你要把手册内容转换为“可机读的诊断规则集”，供 Log Agent 精确匹配。

硬性要求：

1) 只输出一个 JSON（不得包含 Markdown、解释文字、代码块标记）。
2) 必须给每条规则一个唯一的 rule_id（例如 "R001"）。
3) 不要编造手册中没有的错误码/字符串/阈值；不确定就不要写入 rules。
4) 规则要包含“故障判据”和“恢复/自愈判据”（如果手册提到）。

输出 JSON schema：

{

  "product": "string or null",

  "version": "string or null",

  "rules": [

    {

      "rule_id": "R001",

      "title": "string",

      "severity": "FATAL|ERROR|WARN|INFO|UNKNOWN",

      "signatures": [

        {"type":"literal|regex|code", "value":"string", "must": true|false}

      ],

      "conditions": ["IF ... THEN ...", "..."],

      "recovery_signatures": [{"type":"literal|regex|code", "value":"string"}],

      "ignore_signatures": [{"type":"literal|regex|code", "value":"string"}],

      "thresholds": [{"name":"string","op":"<|<=|>|>=|==","value":"number|string","unit":"string or null"}],

      "notes": "string"

    }

  ]

}
"""

        user_p = f"""

【手册内容片段】

{short_manual}

{kw_hint}

请生成结构化维测指南：

"""
        resp = self.call_llm(sys_p, user_p, max_tokens=1500)
        if resp.get("ok"):
            return resp.get("content", "")
        return f"Agent Error: {resp.get('error', 'Unknown')}"


class LogAgent(BaseAgent):
    """
    🕵️‍♂️ 日志侦探：持有 Manual Agent 提供的指南，在日志中搜证。
    """

    def summarize(self, raw_log_content, manual_guide):
        snippet = utils.get_smart_snippet(raw_log_content, head=3000, tail=5000)

        sys_p = """你是嵌入式日志取证专家。

你将收到：

- Manual rules（严格 JSON）

- 日志片段

任务：从日志中提取“最关键的一起事件”，并判断它是否命中某条规则。

硬性要求：

1) 只输出一个 JSON（不得包含 Markdown、解释文字）。
2) 不得编造错误码/规则/路径/行号。没有就填 null。
3) 如果命中规则，必须填写 matched_rule_id，并在 match_reason 中引用该 rule_id。
4) 必须输出 evidence_lines：直接复制日志原文中最关键的 3~8 行（包含时间戳也可以），用于人工复核。
5) 如果日志存在异常但没有任何规则命中，matched_rule_id 填 null，match_reason 固定写：

   "日志存在异常，但未在指南中找到对应描述"

"""

        required_schema = {
            "error_time": "String (yyyy-mm-dd hh:mm:ss) or null",
            "module_id": "String (模块ID) or null",
            "log_level": "String (如 FATAL, ERROR) or null",
            "dotlog_content": "String ...",
            "file_path": "String ... or null",
            "line_number": "Integer or null",
            "match_reason": "String ...",
        }

        user_p = (
            "【📚 Manual Agent 提供的维测指南】\n"
            + str(manual_guide)
            + "\n\n"
            + "【📄 日志片段】\n"
            + str(snippet)
            + "\n\n"
            + "Required JSON Structure:\n"
            + json.dumps(required_schema, ensure_ascii=False, indent=2)
        )

        resp = self.call_llm(sys_p, user_p, max_tokens=1500)
        if resp.get("ok"):
            return resp.get("content", "")
        return f"Agent Error: {resp.get('error', 'Unknown')}"


class CodeAgent(BaseAgent):
    """
    代码专家：审计代码逻辑 (逻辑保持不变)。
    """

    def investigate(self, codebase_root, server_prefix, file_path, line_number):
        if not file_path or not line_number:
            return "无具体代码位置信息，跳过代码分析。"

        raw_code = ""
        try:
            line_num = int(str(line_number).replace(",", ""))
            raw_code = code_utils.read_file_snippet(
                base_dir=codebase_root,
                relative_path=file_path,
                start_line=line_num,
                context_lines=15,
                strip_prefix=server_prefix,
            )
        except ValueError:
            return f"行号格式错误: {line_number}"
        except Exception as e:
            return f"代码读取过程异常: {str(e)}"

        if "[Error]" in raw_code or "[Security Error]" in raw_code:
            return f"代码文件读取失败: {raw_code}"

        sys_p = "你是一个资深 C/C++ 开发专家。"
        user_p = f"""

请阅读以下代码片段，该片段在 Line {line_number} 处报错。

请解释该处的代码逻辑，特别是：

1. 触发报错/断言的条件是什么？
2. 变量可能的取值是什么？

Code Snippet:

{raw_code}

"""

        resp = self.call_llm(sys_p, user_p)
        if resp.get("ok"):
            return resp.get("content", "")
        return f"Agent Error: {resp.get('error', 'Unknown')}"


class BossAgent(BaseAgent):
    """
    首席大法官：汇总判决。
    """

    def conclude(self, manual_guide, log_summary, code_insight):
        sys_p = """你是故障诊断判决器（Boss Agent）。你必须严格基于输入字段做结论。

硬性规则：

1) 如果 manual_ok=false 或 log_ok=false，则 is_fault 必须为 false，confidence 必须 <= 50。
2) 当上游失败时，title 只能是 "PipelineFailure" 或 "Unknown"。
3) reason 必须解释是哪一步失败，失败原因是什么；不得把 HTTP 504、timeout 等当成设备故障。
4) fix 必须给出可执行的“恢复 pipeline/重试/采集更多日志”的建议，而不是设备侧修复。
5) 只输出一个 JSON，不得输出 Markdown 或额外文字。

"""

        user_p = f"""

请基于以下三位专家的报告，生成最终的故障分析报告。

【1. 📚 判据来源 (Manual Guide)】

{manual_guide}

【2. 🕵️‍♂️ 现场证据 (Log Analysis)】

{log_summary}

【3. 💻 代码逻辑 (Code Insight)】

{code_insight}

# 判决任务

1. **Is Fault**: 判断是否为真正的故障。
2. **Confidence**: 给出置信度 (0-100)。如果日志完美匹配了手册指南中的特征，置信度应 > 90。
3. **Reason**: 结合代码逻辑和手册判据，解释为什么发生该故障。
4. **Fix**: 给出具体的排查或恢复建议。

# Output Format (JSON Only)

{

    "is_fault": boolean,

    "confidence": integer,

    "title": "String (故障标题)",

    "reason": "String (详细的根因分析)",

    "fix": "String (建议列表)"

}

"""

        resp = self.call_llm(sys_p, user_p, max_tokens=2000)
        if resp.get("ok"):
            return resp.get("content", "")
        return f"Agent Error: {resp.get('error', 'Unknown')}"

