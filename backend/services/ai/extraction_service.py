from pypdf import PdfReader


def extract_text_from_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    pages_text = []

    for page in reader.pages:
        text = page.extract_text() or ""
        cleaned = text.strip()
        if cleaned:
            pages_text.append(cleaned)

    return "\n\n".join(pages_text).strip()