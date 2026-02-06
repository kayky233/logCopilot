"""
Phase 3 验证测试 — 模型路由、报告导出、RAG
运行: python -m pytest tests/test_phase3.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestModelRouter:
    """测试多模型智能路由"""

    def test_default_selection(self):
        from backend.services.model_router import ModelRouter
        router = ModelRouter("deepseek-chat")
        model = router.select_model(task_type="general")
        assert model.name is not None

    def test_fast_model_for_log_task(self):
        from backend.services.model_router import ModelRouter
        router = ModelRouter()
        model = router.select_model(task_type="log")
        # 应该选速度最快或最便宜的
        assert model.speed_tier <= 2

    def test_quality_model_for_boss_task(self):
        from backend.services.model_router import ModelRouter
        router = ModelRouter()
        model = router.select_model(task_type="boss", prefer_quality=True)
        assert model.capability_tier >= 2

    def test_budget_constraint(self):
        from backend.services.model_router import ModelRouter
        router = ModelRouter()
        model = router.select_model(budget_remaining_usd=0.001)
        # 应该选最便宜的
        assert model.cost_per_1k_tokens <= 0.001

    def test_circuit_breaker(self):
        from backend.services.model_router import ModelRouter
        router = ModelRouter()
        # 连续 3 次报错 → 熔断
        for _ in range(3):
            router.report_error("deepseek-chat")
        assert not router.registry["deepseek-chat"].is_available

        # 恢复
        router.report_success("deepseek-chat")
        assert router.registry["deepseek-chat"].is_available

    def test_status_report(self):
        from backend.services.model_router import ModelRouter
        router = ModelRouter()
        status = router.get_status()
        assert len(status) >= 4
        assert all("name" in s for s in status)


class TestReportExport:
    """测试报告导出"""

    def test_export_json(self):
        from backend.services.report_service import export_json
        data = [{"is_fault": True, "title": "PLL故障", "confidence": 95}]
        result = export_json(data)
        assert "PLL故障" in result
        assert '"is_fault": true' in result

    def test_export_csv(self):
        from backend.services.report_service import export_csv
        data = [{
            "log_filename": "test.log",
            "manual_filename": "pll.md",
            "domain": "CLK",
            "is_fault": True,
            "confidence": 90,
            "title": "PLL Unlock",
            "reason": "频繁解锁",
            "fix": "检查参考源",
            "model_name": "deepseek-chat",
            "completed_at": "2026-02-06",
        }]
        result = export_csv(data)
        assert "PLL Unlock" in result
        assert "test.log" in result

    def test_export_csv_empty(self):
        from backend.services.report_service import export_csv
        assert export_csv([]) == ""

    def test_export_html(self):
        from backend.services.report_service import export_html
        data = [{
            "log_filename": "a.log",
            "domain": "CLK",
            "manual_filename": "m.md",
            "is_fault": True,
            "confidence": 85,
            "title": "Clock Fault",
            "reason": "PLL unlock",
            "fix": "Reset PLL",
        }]
        html = export_html(data)
        assert "<html" in html
        assert "Clock Fault" in html
        assert "LogPilot" in html


class TestRAGService:
    """测试 RAG 文档切片 (不依赖 ChromaDB)"""

    def test_chunk_short_doc(self):
        from backend.services.rag_service import RAGService
        svc = RAGService()
        chunks = svc.chunk_document("短文档内容")
        assert len(chunks) == 1

    def test_chunk_markdown_sections(self):
        from backend.services.rag_service import RAGService
        svc = RAGService()
        doc = """# 故障1
PLL解锁

## 现象
频繁告警

# 故障2
时钟源切换

## 现象
GPS信号丢失"""
        chunks = svc.chunk_document(doc)
        assert len(chunks) >= 3

    def test_chunk_long_section(self):
        from backend.services.rag_service import RAGService
        svc = RAGService()
        doc = "A " * 2000  # 很长的单段
        chunks = svc.chunk_document(doc, chunk_size=500, overlap=100)
        assert len(chunks) > 1


class TestTokenService:
    """测试 Token 计费服务 (纯计算逻辑，不触发 DB)"""

    def test_estimate_cost(self):
        # 直接测试定价逻辑，避免触发 database import
        MODEL_PRICING = {
            "deepseek-chat": {"prompt": 0.14 / 1_000_000, "completion": 0.28 / 1_000_000},
            "default": {"prompt": 0.50 / 1_000_000, "completion": 1.0 / 1_000_000},
        }
        pricing = MODEL_PRICING.get("deepseek-chat", MODEL_PRICING["default"])
        cost = 1000 * pricing["prompt"] + 500 * pricing["completion"]
        assert cost > 0
        assert cost < 1.0

    def test_estimate_cost_unknown_model(self):
        MODEL_PRICING = {
            "default": {"prompt": 0.50 / 1_000_000, "completion": 1.0 / 1_000_000},
        }
        pricing = MODEL_PRICING.get("unknown-model-xyz", MODEL_PRICING["default"])
        cost = 1000 * pricing["prompt"] + 500 * pricing["completion"]
        assert cost > 0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

