# Task
请分析以下日志是否满足故障手册中的定义。

## Input Data
【参考手册】:
{manual_content}

【系统日志】:
{log_content}

## Output Format (JSON Only)
{
    "is_fault": true,
    "confidence": 95,
    "title": "故障名称 (From Manual)",
    "reason": "简要证据链...",
    "fix": "修复建议..."
}