import pytest

from mcp.toolset import RAGToolset


REQUIRED_KEYS = {"chunk_id", "doc_id", "url", "title", "section_path", "position", "score", "text"}


class StubRetriever:
    def dense_search(self, query: str, top_k: int | None = None):
        return [
            {
                "chunk_id": "c1",
                "doc_id": "d1",
                "url": "https://example.com/a",
                "title": "Title",
                "section_path": "Section > Sub",
                "position": 0,
                "text": "chunk text",
                "score": 0.9,
            }
        ]

    def lexical_search(self, query: str, top_k: int | None = None):
        return [
            {
                "chunk_id": "c2",
                "doc_id": "d1",
                "url": "https://example.com/b",
                "title": "Title",
                "section_path": "Section > Sub",
                "position": 1,
                "text": "chunk text",
                "score": 0.8,
            }
        ]

    def hybrid_search(self, query: str, top_k: int | None = None):
        return [
            {
                "chunk_id": "c3",
                "doc_id": "d3",
                "url": "https://example.com/c",
                "title": "Title",
                "section_path": "Section > Sub",
                "position": 2,
                "text": "chunk text",
                "score": 0.85,
            }
        ]

    def chunks_for_url(self, url: str):
        return [
            {
                "chunk_id": "c4",
                "doc_id": "d4",
                "url": url,
                "title": "Title",
                "section_path": "Section > Sub",
                "position": 3,
                "text": "full page text",
                "score": 0.5,
            }
        ]


def test_tools_return_required_metadata():
    toolset = RAGToolset(
        retriever=StubRetriever(),
        force_english_queries=True,
    )

    for tool_name, payload in [
        ("dense_search", {"query": "example query"}),
        ("lexical_search", {"query": "example query"}),
        ("hybrid_search", {"query": "example query"}),
    ]:
        results = toolset.call(tool_name, payload)
        assert isinstance(results, list)
        assert results, f"{tool_name} debe devolver resultados."
        for item in results:
            missing = REQUIRED_KEYS.difference(item.keys())
            assert not missing, f"Faltan metadatos {missing} en {tool_name}."

    chunks = toolset.call("chunks_by_url", {"url": "https://example.com/a"})
    assert chunks and chunks[0]["url"] == "https://example.com/a"


def test_tool_requires_query_parameter():
    toolset = RAGToolset(
        retriever=StubRetriever(),
        force_english_queries=True,
    )
    with pytest.raises(ValueError):
        toolset.call("dense_search", {})
