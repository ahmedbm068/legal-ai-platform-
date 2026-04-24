import unittest

from scripts.import_legal_codes_corpus import _select_chunks_for_document


class ImportLegalCodesCorpusTests(unittest.TestCase):
    def test_select_chunks_prefers_structural_when_articles_are_sparse(self) -> None:
        long_body = "This section explains succession rules and inheritance distribution in detail. " * 4
        text = "\n\n".join(
            [
                "Article 1\nShort rule.",
                "Article 2\nAnother short rule.",
                f"Titre I Dispositions generales\n{long_body}",
                f"Chapitre 1 Heirs\n{long_body}",
                f"Section 1 Order of succession\n{long_body}",
            ]
        )

        chunks = _select_chunks_for_document(text)
        self.assertGreaterEqual(len(chunks), 3)
        self.assertTrue(chunks[0][0].lower().startswith("titre"))

    def test_select_chunks_keeps_articles_when_article_density_is_high(self) -> None:
        article_blocks = [
            f"Article {index}\nThis article body is sufficiently long to be useful for retrieval."
            for index in range(1, 22)
        ]
        text = "\n\n".join(article_blocks)

        chunks = _select_chunks_for_document(text)
        self.assertEqual(len(chunks), 21)
        self.assertTrue(chunks[0][0].lower().startswith("article"))

    def test_select_chunks_uses_structural_when_no_articles_exist(self) -> None:
        long_body = "Rules on private international law and conflict of laws apply here. " * 4
        text = "\n\n".join(
            [
                f"Titre II International jurisdiction\n{long_body}",
                f"Section 1 Competence\n{long_body}",
            ]
        )

        chunks = _select_chunks_for_document(text)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(not heading.lower().startswith("article") for heading, _ in chunks))


if __name__ == "__main__":
    unittest.main()
