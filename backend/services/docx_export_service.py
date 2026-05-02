from __future__ import annotations

import html
import re
import zipfile
from io import BytesIO

from backend.services.draft_document_service import html_to_text


def _xml_escape(value: str) -> str:
    return html.escape(value or "", quote=True)


class DocxExportService:
    def build_docx(self, *, title: str, content_html: str, citations: list[dict]) -> bytes:
        text = html_to_text(content_html)
        paragraphs = [title, "", *[line.strip() for line in re.split(r"\n{1,}", text) if line.strip()]]
        if citations:
            paragraphs.extend(["", "Citations"])
            paragraphs.extend(
                f"{index + 1}. {item.get('label') or item.get('filename') or 'Source'}: {item.get('snippet') or ''}"
                for index, item in enumerate(citations[:40])
            )

        document_body = "".join(
            f"<w:p><w:r><w:t xml:space=\"preserve\">{_xml_escape(paragraph)}</w:t></w:r></w:p>"
            for paragraph in paragraphs
        )
        document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{document_body}<w:sectPr/></w:body>
</w:document>"""
        content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
        rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("_rels/.rels", rels)
            archive.writestr("word/document.xml", document_xml)
        return buffer.getvalue()


docx_export_service = DocxExportService()
