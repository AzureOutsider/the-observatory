from dataclasses import dataclass
import re


@dataclass(frozen=True)
class MarkdownChunk:
    title: str
    content: str
    source_path: str = ""


@dataclass(frozen=True)
class SearchResult:
    title: str
    content: str
    source_path: str
    score: int


def split_markdown_chunks(text: str, source_path: str = "") -> list[MarkdownChunk]:
    chunks: list[MarkdownChunk] = []
    current_title: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        match = re.match(r"^##\s+(.+)$", line)
        if match:
            if current_title and "".join(current_lines).strip():
                chunks.append(
                    MarkdownChunk(
                        title=current_title,
                        content="\n".join(current_lines).strip(),
                        source_path=source_path,
                    )
                )
            current_title = match.group(1).strip()
            current_lines = []
        elif current_title:
            current_lines.append(line)

    if current_title and "".join(current_lines).strip():
        chunks.append(
            MarkdownChunk(
                title=current_title,
                content="\n".join(current_lines).strip(),
                source_path=source_path,
            )
        )

    return chunks


def search_chunks(chunks: list[MarkdownChunk], query: str, limit: int = 5) -> list[SearchResult]:
    terms = [term.lower() for term in re.split(r"\s+", query.strip()) if term.strip()]
    scored: list[SearchResult] = []
    for chunk in chunks:
        title = chunk.title.lower()
        content = chunk.content.lower()
        score = 0
        for term in terms:
            if term in title:
                score += 5
            if term in content:
                score += 1
        if score:
            scored.append(
                SearchResult(
                    title=chunk.title,
                    content=chunk.content,
                    source_path=chunk.source_path,
                    score=score,
                )
            )
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:limit]
