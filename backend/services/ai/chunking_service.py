from typing import List


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if not paragraphs:
        return []

    chunks = []
    current_chunk = []

    for paragraph in paragraphs:
        current_text = "\n".join(current_chunk)

        if len(current_text) + len(paragraph) + 1 <= chunk_size:
            current_chunk.append(paragraph)
        else:
            if current_chunk:
                chunks.append("\n".join(current_chunk))
            current_chunk = [paragraph]

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    if overlap <= 0 or len(chunks) <= 1:
        return chunks

    overlapped_chunks = []
    for i, chunk in enumerate(chunks):
        if i == 0:
            overlapped_chunks.append(chunk)
            continue

        prev_tail = chunks[i - 1][-overlap:]
        overlapped_chunks.append(prev_tail + "\n" + chunk)

    return overlapped_chunks