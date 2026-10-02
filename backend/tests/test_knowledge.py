from app.services.knowledge import search_chunks, split_markdown_chunks


def test_split_markdown_chunks_by_headings():
    text = "# 投资知识库\n\n## 黄金\n\n实际利率影响黄金。\n\n## AI 产业链\n\n算力芯片是核心。"

    chunks = split_markdown_chunks(text)

    assert len(chunks) == 2
    assert chunks[0].title == "黄金"
    assert "实际利率" in chunks[0].content


def test_search_chunks_scores_keyword_matches():
    chunks = split_markdown_chunks("# K\n\n## 黄金\n\n美元和实际利率。\n\n## 债券\n\n利率影响债券。")

    results = search_chunks(chunks, "黄金 实际利率", limit=1)

    assert results[0].title == "黄金"
