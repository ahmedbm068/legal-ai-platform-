# Local Legal Corpus

This folder contains local jurisdiction-first legal snippets used by Legal Search mode.

## File

- `constitution_corpus.json`: country-indexed legal entries used before web fallback.
- `legal_codes_corpus.json`: code-family indexed legal entries used for case-topic-first legal search.

## Build From PDFs

Run the importer after placing official code PDFs in a local folder:

`c:/Users/ahmed/Desktop/pfe.2/legal-ai-platform/.venv/Scripts/python.exe scripts/import_legal_codes_corpus.py --input-dir C:/Users/ahmed/Downloads/code --output backend/services/ai/data/legal_codes_corpus.json --country tunisia`

## Entry format

```json
{
  "article": "Article 55 (Constitution 2022)",
  "title": "Limits on rights and freedoms",
  "summary": "Short legal summary used for retrieval and answer grounding.",
  "keywords": ["rights", "proportionality", "restriction"],
  "tags": ["constitution", "fundamental-rights"],
  "url": "https://official-source.example"
}
```

Preferred legal-code entry fields:

```json
{
  "country": "tunisia",
  "code_family": "code_civil",
  "code_name": "Code Civil",
  "article": "Article 123",
  "title": "Contractual liability",
  "summary": "Short legal summary used for retrieval and answer grounding.",
  "keywords": ["contract", "liability", "damages"],
  "tags": ["code_civil", "local-legal-code"],
  "url": "https://official-source.example",
  "source_filename": "code de procedure civile et commerciale.pdf"
}
```

## Notes

- Keep summaries concise and legally neutral.
- Prefer official/public legal sources for `url`.
- Add new countries at the top-level key (`"country_name": [...]`).
- Country keys are normalized in code; supported values are currently Tunisia and Germany.
- For Tunisia legal search mode, supported code families are `code_civil`, `code_succession`, and `code_international_prive`.
