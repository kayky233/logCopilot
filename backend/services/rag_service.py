"""
RAG 向量检索服务 — Phase 3

将故障手册切片并向量化，实现语义级的手册检索。
当手册库较大时，Manual Agent 不再需要全量阅读手册，
而是基于日志关键信息精准召回最相关的手册片段。

依赖: pip install chromadb sentence-transformers
"""
import hashlib
import os
import re
from typing import Optional

from backend.config import get_settings

settings = get_settings()


class RAGService:
    """手册知识库 RAG 服务"""

    def __init__(self, persist_dir: str = ""):
        self.persist_dir = persist_dir or settings.VECTOR_DB_PATH
        self._collection = None
        self._client = None

    def _ensure_client(self):
        """懒加载 ChromaDB 客户端"""
        if self._client is not None:
            return

        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            self._client = chromadb.Client(ChromaSettings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=self.persist_dir,
                anonymized_telemetry=False,
            ))
            self._collection = self._client.get_or_create_collection(
                name="fault_manuals",
                metadata={"hnsw:space": "cosine"},
            )
            print(f"✅ RAG: ChromaDB 已初始化 ({self.persist_dir})")
        except ImportError:
            print("⚠️ RAG: chromadb 未安装，向量检索不可用。pip install chromadb")
            self._client = None
            self._collection = None

    def chunk_document(self, content: str, chunk_size: int = 800, overlap: int = 200) -> list[dict]:
        """
        文档切片算法 — 语义感知切片

        策略:
        1. 先按标题 (# / ## / ###) 分段
        2. 短段直接保留，长段按 chunk_size 滑窗切片
        3. 保留 overlap 字符的前文上下文
        """
        if not content:
            return []

        # 按 Markdown 标题分段
        sections = re.split(r'\n(?=#{1,3}\s)', content)
        chunks = []

        for section in sections:
            section = section.strip()
            if not section:
                continue

            if len(section) <= chunk_size:
                chunks.append({"text": section, "type": "section"})
            else:
                # 滑窗切片
                start = 0
                while start < len(section):
                    end = start + chunk_size
                    chunk_text = section[start:end]

                    # 尝试在句号/换行处断开
                    if end < len(section):
                        last_break = max(
                            chunk_text.rfind('\n'),
                            chunk_text.rfind('。'),
                            chunk_text.rfind('.'),
                        )
                        if last_break > chunk_size * 0.5:
                            chunk_text = chunk_text[:last_break + 1]
                            end = start + last_break + 1

                    chunks.append({"text": chunk_text, "type": "sliding"})
                    start = end - overlap

        return chunks

    def index_document(self, doc_id: str, content: str, metadata: dict = None):
        """索引一个文档到向量库"""
        self._ensure_client()
        if self._collection is None:
            return {"error": "RAG 服务不可用"}

        chunks = self.chunk_document(content)
        if not chunks:
            return {"error": "文档为空"}

        ids = []
        documents = []
        metadatas = []

        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk_{i}"
            ids.append(chunk_id)
            documents.append(chunk["text"])
            meta = {
                "doc_id": doc_id,
                "chunk_index": i,
                "chunk_type": chunk["type"],
            }
            if metadata:
                meta.update(metadata)
            metadatas.append(meta)

        # 先删除旧版本
        try:
            existing = self._collection.get(where={"doc_id": doc_id})
            if existing and existing["ids"]:
                self._collection.delete(ids=existing["ids"])
        except Exception:
            pass

        # 插入新切片
        self._collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        return {"indexed_chunks": len(chunks), "doc_id": doc_id}

    def search(self, query: str, n_results: int = 5, domain: str = None) -> list[dict]:
        """语义搜索手册"""
        self._ensure_client()
        if self._collection is None:
            return []

        where_filter = None
        if domain:
            where_filter = {"domain": domain}

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filter,
            )
        except Exception as e:
            print(f"⚠️ RAG 搜索异常: {e}")
            return []

        hits = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                dist = results["distances"][0][i] if results["distances"] else 0
                hits.append({
                    "text": doc,
                    "score": round(1 - dist, 4),  # 转换为相似度
                    "metadata": meta,
                })

        return hits

    def get_relevant_context(self, log_snippet: str, domain: str = None, max_chars: int = 5000) -> str:
        """
        从向量库检索与日志最相关的手册内容，返回拼接后的上下文文本。
        供 Manual Agent 使用，替代全量手册阅读。
        """
        hits = self.search(log_snippet[:2000], n_results=8, domain=domain)
        if not hits:
            return ""

        context_parts = []
        total_chars = 0
        for hit in hits:
            if total_chars + len(hit["text"]) > max_chars:
                break
            context_parts.append(
                f"[相关度: {hit['score']:.2f}] {hit['text']}"
            )
            total_chars += len(hit["text"])

        return "\n---\n".join(context_parts)

    def get_stats(self) -> dict:
        """获取知识库统计"""
        self._ensure_client()
        if self._collection is None:
            return {"status": "unavailable"}

        count = self._collection.count()
        return {
            "status": "ready",
            "total_chunks": count,
            "persist_dir": self.persist_dir,
        }

    def clear(self):
        """清空知识库"""
        self._ensure_client()
        if self._client:
            try:
                self._client.delete_collection("fault_manuals")
                self._collection = self._client.get_or_create_collection(
                    name="fault_manuals",
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception:
                pass

