import ast
import json
import re
from typing import Any, Dict, List, Tuple

import httpx
from openai import OpenAI

from agents import BossAgent, CodeAgent, LogAgent, ManualAgent


class FaultDetectorClient:
    def __init__(self, api_key: str, base_url: str, model_name: str):
        self.smart_model = model_name
        self.fast_model = model_name
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            http_client=httpx.Client(trust_env=False, timeout=300.0),
        )

        self.log_agent = LogAgent(self.client, self.fast_model)
        self.manual_agent = ManualAgent(self.client, self.fast_model)
        self.code_agent = CodeAgent(self.client, self.smart_model)
        self.boss_agent = BossAgent(self.client, self.smart_model)

        self.model_name = self.smart_model

    def _safe_parse_json(self, text: str) -> Dict[str, Any]:
        """[增强版] 鲁棒的 JSON 解析器"""
        if not text:
            return {}
        if "Agent Error" in text:
            print(f"❌ LLM 调用失败，原始错误: {text}")
            return {}

        clean_text = text.strip()
        if "```" in clean_text:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_text, re.IGNORECASE)
            if match:
                clean_text = match.group(1)

        try:
            parsed = json.loads(clean_text)
            if isinstance(parsed, list):
                return parsed[0] if len(parsed) > 0 else {}
            return parsed
        except Exception:
            pass

        match = re.search(r"\{[\s\S]*\}", clean_text)
        if match:
            candidate = match.group(0)
            try:
                return json.loads(candidate)
            except Exception:
                try:
                    return json.loads(candidate + "}")
                except Exception:
                    pass

        print(f"⚠️ JSON Parse Failed. Raw preview: {text[:100]}...")
        return {}

    def _normalize_result(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "is_fault": bool(data.get("is_fault", False)),
            "confidence": int(data.get("confidence", 0)),
            "title": str(data.get("title", "未命名故障")),
            "reason": str(data.get("reason", "无详细证据")),
            "fix": str(data.get("fix", "无建议")),
        }

    def analyze(
        self,
        manual_content: str,
        log_content: str,
        sys_prompt: str,
        user_tpl: str,
        codebase_root: str = "",
        server_path_prefix: str = "",
        enable_code_agent: bool = True,
        focus_keywords: list = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        v3.0 核心业务方法：Manual -> Log -> Boss 串行流水线
        """
        trace_data = {
            "steps": [],
            "manual_guide": "",
            "log_summary": "",
            "code_insight": "",
            "final_input": "",
            "raw_response": "",
        }

        try:
            # =========================================================
            # Phase 1: 📚 Manual Agent (先读手册，制定标准)
            # =========================================================
            trace_data["steps"].append(f"📚 Manual Agent ({self.fast_model}): 正在研读手册，制定维测指南...")
            manual_guide = self.manual_agent.extract_criteria(manual_content, focus_keywords)
            # 🟢 确保 manual_guide 是字符串
            manual_guide = str(manual_guide) if manual_guide else "(Manual Agent 返回为空)"
            trace_data["manual_guide"] = manual_guide

            print("\n" + "=" * 50)
            print("🐛 [DEBUG] Manual Agent 原始返回内容 (前200字):")
            print(manual_guide[:200])
            print("=" * 50 + "\n")

            # =========================================================
            # Phase 2: 🕵️‍♂️ Log Agent (带着指南查日志)
            # =========================================================
            trace_data["steps"].append(f"🕵️‍♂️ Log Agent ({self.fast_model}): 正在根据指南分析日志...")
            log_summary_json_str = ""
            log_info = {}

            try:
                log_summary_json_str = self.log_agent.summarize(log_content, manual_guide)
                # 🟢 确保是字符串
                log_summary_json_str = str(log_summary_json_str) if log_summary_json_str else ""

                print("\n" + "=" * 50)
                print("🐛 [DEBUG] Log Agent 原始返回内容:")
                print(log_summary_json_str)
                print("=" * 50 + "\n")

                log_info = self._safe_parse_json(log_summary_json_str)
                if isinstance(log_info, list):
                    log_info = log_info[0] if log_info else {}
                if not log_info:
                    raise ValueError("Empty JSON")
            except Exception as e:
                print(f"❌ Log Agent 异常: {e} -> 触发自动降级")
                fallback_summary = {
                    "dotlog_content": f"Log Analysis Failed ({str(e)})",
                    "module_id": "UNKNOWN",
                    "file_path": None,
                    "line_number": None,
                }
                log_info = fallback_summary
                log_summary_json_str = json.dumps(fallback_summary, ensure_ascii=False)
                trace_data["steps"].append(f"⚠️ Log Agent 降级: {str(e)}")

            trace_data["log_summary"] = log_summary_json_str

            # 🟢 提前记录 final_input，即使后续 Phase 3/4 异常也能保留上下文
            trace_data["final_input"] = (
                f"Manual Guide:\n{manual_guide}\n\n"
                f"Log Summary:\n{log_summary_json_str}"
            )

            # =========================================================
            # Phase 3: 💻 Code Agent (按需)
            # =========================================================
            code_insight = "未启用代码审计。"
            if enable_code_agent:
                if codebase_root and log_info.get("file_path") and log_info.get("line_number"):
                    trace_data["steps"].append(
                        f"💻 Code Agent ({self.smart_model}): 正在审计 {log_info['file_path']}..."
                    )
                    code_insight = self.code_agent.investigate(
                        codebase_root,
                        server_path_prefix,
                        str(log_info["file_path"]),
                        log_info["line_number"],
                    )
                elif not codebase_root:
                    code_insight = "本地代码库未配置，跳过代码审计。"
            else:
                trace_data["steps"].append("💻 Code Agent: 已禁用 (跳过)")

            # 🟢 确保 code_insight 是字符串
            code_insight = str(code_insight) if code_insight else "(Code Agent 返回为空)"
            trace_data["code_insight"] = code_insight

            # =========================================================
            # Phase 4: 🧠 Boss Agent (最终判决)
            # =========================================================
            trace_data["steps"].append(f"🧠 Boss Agent ({self.smart_model}): 正在生成最终报告...")
            raw_res = self.boss_agent.conclude(
                manual_guide=manual_guide,
                log_summary=log_summary_json_str,
                code_insight=code_insight,
            )
            # 🟢 确保是字符串
            raw_res = str(raw_res) if raw_res else ""

            trace_data["raw_response"] = raw_res
            # 追加 Code Insight 到 final_input
            trace_data["final_input"] += f"\n\nCode Insight:\n{code_insight}"

            print("\n" + "=" * 50)
            print(f"🐛 [DEBUG] final_input 字符数: {len(trace_data['final_input'])}")
            print("=" * 50 + "\n")

            parsed_data = self._safe_parse_json(raw_res)
            if isinstance(parsed_data, list):
                parsed_data = parsed_data[0] if parsed_data else {}
            return self._normalize_result(parsed_data), trace_data

        except Exception as e:
            import traceback
            print(f"❌ Pipeline 外层异常: {e}")
            traceback.print_exc()
            # 🟢 防御: 即使异常也尝试填充 final_input
            if not trace_data.get("final_input"):
                trace_data["final_input"] = f"(Pipeline异常，部分数据丢失)\nError: {str(e)}"
            error_res = {
                "is_fault": False,
                "title": "Pipeline Error",
                "reason": f"System Error: {str(e)}",
                "confidence": 0,
                "fix": "Check System Logs",
            }
            return error_res, trace_data

    def get_search_keywords(self, manual_content: str) -> List[str]:
        """
        [修复版] 关键词提取：增加 ast 解析以支持单引号列表
        """
        short_manual = manual_content[:10000]
        prompt = f"""

请阅读手册，提取 5-10 个用于定位此故障的关键特征字符串（如错误码、Hex值、特定的报错英文）。

要求：

输出格式必须是标准的 Python List。
只要特征词，不要解释。

Manual Snippet:

{short_manual}

Output Example:

["26263", "Ref_Lost", "0x8000"]

"""

        try:
            response = self.client.chat.completions.create(
                model=self.fast_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            content = response.choices[0].message.content
            match = re.search(r"\[.*\]", content, re.DOTALL)
            if match:
                list_str = match.group(0)
                try:
                    return json.loads(list_str)
                except Exception:
                    try:
                        return ast.literal_eval(list_str)
                    except Exception:
                        pass
            return []
        except Exception as e:
            print(f"关键词提取失败: {e}")
            return []

