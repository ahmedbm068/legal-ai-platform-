from __future__ import annotations

import textwrap
from io import BytesIO

from backend.services.draft_document_service import html_to_text


def _pdf_escape(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class PdfExportService:
    def build_pdf(self, *, title: str, content_html: str, citations: list[dict]) -> bytes:
        text = html_to_text(content_html)
        lines = [title, "", *textwrap.wrap(text, width=92)]
        if citations:
            lines.extend(["", "Citations"])
            for index, item in enumerate(citations[:25]):
                label = item.get("label") or item.get("filename") or "Source"
                snippet = item.get("snippet") or ""
                lines.extend(textwrap.wrap(f"{index + 1}. {label}: {snippet}", width=92))

        stream_lines = ["BT", "/F1 10 Tf", "50 790 Td", "14 TL"]
        for line in lines[:52]:
            stream_lines.append(f"({_pdf_escape(line)}) Tj")
            stream_lines.append("T*")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", errors="replace")

        objects = [
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj",
            b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >> endobj",
            b"5 0 obj << /Length " + str(len(stream)).encode() + b" >> stream\n" + stream + b"\nendstream endobj",
        ]
        buffer = BytesIO()
        buffer.write(b"%PDF-1.4\n")
        offsets = [0]
        for obj in objects:
            offsets.append(buffer.tell())
            buffer.write(obj + b"\n")
        xref = buffer.tell()
        buffer.write(f"xref\n0 {len(objects) + 1}\n".encode())
        buffer.write(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            buffer.write(f"{offset:010d} 00000 n \n".encode())
        buffer.write(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
        return buffer.getvalue()


pdf_export_service = PdfExportService()
