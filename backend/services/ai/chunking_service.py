from typing import List


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
    if not text or not text.strip():
        return []

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: List[str] = []
    current_chunk: List[str] = []

    for paragraph in paragraphs:
        current_text = "\n".join(current_chunk)

        if not current_chunk:
            current_chunk.append(paragraph)
            continue

        if len(current_text) + len(paragraph) + 1 <= chunk_size:
            current_chunk.append(paragraph)
        else:
            chunks.append("\n".join(current_chunk))
            current_chunk = [paragraph]

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    if overlap <= 0 or len(chunks) <= 1:
        return chunks

    overlapped_chunks: List[str] = []
    for i, chunk in enumerate(chunks):
        if i == 0:
            overlapped_chunks.append(chunk)
            continue

        prev_tail = chunks[i - 1][-overlap:]
        overlapped_chunks.append(prev_tail + "\n" + chunk)

    return overlapped_chunks