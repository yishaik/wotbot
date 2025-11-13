from typing import List


def split_for_whatsapp(text: str, chunk_size: int = 1200) -> List[str]:
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= chunk_size:
            chunks.append(remaining)
            break
        # try break at last newline within chunk
        idx = remaining.rfind("\n", 0, chunk_size)
        if idx == -1:
            idx = chunk_size
        chunks.append(remaining[:idx])
        remaining = remaining[idx:].lstrip("\n")
    return chunks

