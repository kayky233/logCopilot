"""
报告导出服务 — Phase 3

支持将分析结果导出为:
  - JSON (原始数据)
  - CSV (批量分析汇总)
  - HTML (可视化报告)
"""
import csv
import io
import json
from datetime import datetime
from typing import Optional


def export_json(results: list[dict]) -> str:
    """导出为 JSON 格式"""
    return json.dumps(results, ensure_ascii=False, indent=2)


def export_csv(results: list[dict]) -> str:
    """导出为 CSV 格式 (适合 Excel 打开)"""
    if not results:
        return ""

    output = io.StringIO()
    # BOM 头 (确保 Excel 正确识别 UTF-8)
    output.write('\ufeff')

    fields = [
        "序号", "日志文件", "手册文件", "领域", "是否故障",
        "置信度", "故障标题", "根因分析", "修复建议",
        "模型", "分析时间",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()

    for i, r in enumerate(results, 1):
        writer.writerow({
            "序号": i,
            "日志文件": r.get("log_filename", ""),
            "手册文件": r.get("manual_filename", ""),
            "领域": r.get("domain", ""),
            "是否故障": "✅ 是" if r.get("is_fault") else "❌ 否",
            "置信度": f"{r.get('confidence', 0)}%",
            "故障标题": r.get("title", ""),
            "根因分析": r.get("reason", ""),
            "修复建议": r.get("fix", ""),
            "模型": r.get("model_name", ""),
            "分析时间": r.get("completed_at", ""),
        })

    return output.getvalue()


def export_html(results: list[dict], title: str = "LogPilot 分析报告") -> str:
    """导出为 HTML 可视化报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(results)
    faults = sum(1 for r in results if r.get("is_fault"))
    avg_conf = sum(r.get("confidence", 0) for r in results) / total if total > 0 else 0

    # 生成结果行
    rows_html = ""
    for i, r in enumerate(results, 1):
        is_fault = r.get("is_fault", False)
        badge = '<span class="badge fault">🔴 故障</span>' if is_fault else '<span class="badge ok">🟢 正常</span>'
        conf = r.get("confidence", 0)
        conf_class = "high" if conf >= 80 else "mid" if conf >= 50 else "low"

        rows_html += f"""
        <tr class="{'fault-row' if is_fault else ''}">
            <td>{i}</td>
            <td>{r.get('log_filename', '-')}</td>
            <td><span class="domain">{r.get('domain', '-')}</span> {r.get('manual_filename', '-')}</td>
            <td>{badge}</td>
            <td><span class="conf {conf_class}">{conf}%</span></td>
            <td><strong>{r.get('title', '-')}</strong></td>
            <td class="reason">{r.get('reason', '-')[:200]}</td>
            <td class="fix">{r.get('fix', '-')[:200]}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; background: #f5f6fa; padding: 2rem; color: #333; }}
    .header {{ text-align: center; margin-bottom: 2rem; }}
    .header h1 {{ font-size: 1.8rem; color: #2c3e50; }}
    .header .meta {{ color: #7f8c8d; margin-top: 0.5rem; }}
    .stats {{ display: flex; gap: 1rem; justify-content: center; margin-bottom: 2rem; flex-wrap: wrap; }}
    .stat-card {{ background: white; border-radius: 12px; padding: 1.2rem 2rem; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.08); min-width: 150px; }}
    .stat-card .value {{ font-size: 2rem; font-weight: bold; color: #2c3e50; }}
    .stat-card .label {{ font-size: 0.85rem; color: #7f8c8d; }}
    .stat-card.fault .value {{ color: #e74c3c; }}
    .stat-card.ok .value {{ color: #27ae60; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    th {{ background: #2c3e50; color: white; padding: 0.8rem; text-align: left; font-size: 0.85rem; }}
    td {{ padding: 0.7rem 0.8rem; border-bottom: 1px solid #ecf0f1; font-size: 0.83rem; vertical-align: top; }}
    tr:hover {{ background: #f8f9fa; }}
    .fault-row {{ background: #fff5f5; }}
    .badge {{ padding: 3px 8px; border-radius: 4px; font-size: 0.78rem; }}
    .badge.fault {{ background: #fde8e8; color: #e74c3c; }}
    .badge.ok {{ background: #e8fde8; color: #27ae60; }}
    .conf {{ font-weight: bold; }}
    .conf.high {{ color: #e74c3c; }}
    .conf.mid {{ color: #f39c12; }}
    .conf.low {{ color: #95a5a6; }}
    .domain {{ background: #ebf5fb; color: #2980b9; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; }}
    .reason, .fix {{ max-width: 250px; overflow: hidden; text-overflow: ellipsis; }}
    .footer {{ text-align: center; margin-top: 2rem; color: #bdc3c7; font-size: 0.8rem; }}
</style>
</head>
<body>
<div class="header">
    <h1>📡 {title}</h1>
    <div class="meta">生成时间: {now} | LogPilot v3.2</div>
</div>

<div class="stats">
    <div class="stat-card">
        <div class="value">{total}</div>
        <div class="label">总分析数</div>
    </div>
    <div class="stat-card fault">
        <div class="value">{faults}</div>
        <div class="label">发现故障</div>
    </div>
    <div class="stat-card ok">
        <div class="value">{total - faults}</div>
        <div class="label">正常</div>
    </div>
    <div class="stat-card">
        <div class="value">{avg_conf:.0f}%</div>
        <div class="label">平均置信度</div>
    </div>
</div>

<table>
<thead>
    <tr>
        <th>#</th><th>日志文件</th><th>手册场景</th><th>判定</th>
        <th>置信度</th><th>故障标题</th><th>根因分析</th><th>修复建议</th>
    </tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>

<div class="footer">
    <p>📡 LogPilot — 基站故障深度判决系统 | Powered by Multi-Agent AI</p>
</div>
</body>
</html>"""

    return html

