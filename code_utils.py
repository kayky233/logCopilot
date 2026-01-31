import os


def validate_path(base_dir: str, relative_path: str) -> str:
    """
    安全检查：确保请求的文件路径在允许的代码库根目录内。
    防止目录遍历攻击 (Directory Traversal Attack)。
    """
    real_base = os.path.abspath(base_dir)
    candidate_path = os.path.abspath(os.path.join(real_base, relative_path))

    if os.path.commonpath([real_base, candidate_path]) != real_base:
        raise PermissionError(f"Security Alert: Access denied to path outside codebase: {relative_path}")

    if not os.path.exists(candidate_path):
        raise FileNotFoundError(f"File not found: {relative_path}")

    if not os.path.isfile(candidate_path):
        raise IsADirectoryError(f"Path is a directory, not a file: {relative_path}")

    return candidate_path


def read_file_snippet(
    base_dir: str,
    relative_path: str,
    start_line: int,
    context_lines: int = 10,
    strip_prefix: str = "",
) -> str:
    """
    读取文件指定行附近的片段 (增强版：支持跨平台路径映射 + 安全检查)
    """
    if strip_prefix and relative_path.startswith(strip_prefix):
        relative_path = relative_path.replace(strip_prefix, "", 1)

    relative_path = relative_path.replace("/", os.sep).replace("\\", os.sep)
    relative_path = relative_path.lstrip(os.sep)

    try:
        full_path = validate_path(base_dir, relative_path)
    except Exception as e:
        return f"[Security Error] {str(e)}\n(Check: 'Local Code Root' setting or file existence)"

    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)
        target_line_idx = start_line - 1
        start_idx = max(0, target_line_idx - context_lines)
        end_idx = min(total_lines, target_line_idx + context_lines + 1)

        snippet = []
        for i in range(start_idx, end_idx):
            prefix = ">> " if (i == target_line_idx) else "   "
            snippet.append(f"{prefix}{i + 1}: {lines[i].rstrip()}")

        return "\n".join(snippet)
    except Exception as e:
        return f"[Error] Read file failed: {str(e)}"


CODE_RETRIEVAL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_code_file",
            "description": (
                "Strictly call this tool when the log contains a file path and line "
                "number to read the actual source code. Do not guess paths."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "The relative file path extracted exactly from the log "
                            "(e.g., 'src/backend/server.go')."
                        ),
                    },
                    "line_number": {
                        "type": "integer",
                        "description": "The specific line number implicated in the log.",
                    },
                },
                "required": ["file_path", "line_number"],
            },
        },
    }
]

