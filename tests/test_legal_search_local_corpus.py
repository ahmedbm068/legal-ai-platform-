import unittest
from unittest.mock import patch

from backend.services.ai.legal_search_mode_service import LegalSearchModeService


class LegalSearchLocalCorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = LegalSearchModeService()

    def test_local_legal_corpus_contains_supported_countries(self) -> None:
        corpus = self.service._load_local_legal_codes_corpus()
        self.assertIn("tunisia", corpus)
        self.assertGreater(len(corpus["tunisia"]), 0)

    def test_local_code_retrieval_matches_article_query(self) -> None:
        results = self.service._retrieve_local_legal_code_sources(
            country="tunisia",
            query="Check article inheritance succession testament",
            case_focus_terms=[],
            top_k=5,
            preferred_code_families=["code_succession"],
        )
        self.assertGreater(len(results), 0)
        references = [str(item.get("reference") or "") for item in results]
        self.assertTrue(any(reference.strip() for reference in references))
        self.assertTrue(all(item.get("code_family") == "code_succession" for item in results))
        self.assertTrue(all(item.get("source_origin") == "local_code" for item in results))

    def test_jurisdiction_retrieval_prefers_local_sources_before_web_calls(self) -> None:
        local_results = [
            {
                "title": "Article 1 GG",
                "url": "https://example.org/gg-1",
                "domain": "example.org",
                "snippet": "Human dignity is inviolable.",
                "rank": 1,
                "source_type": "official",
                "source_origin": "local_code",
                "priority": 4,
                "reference": "Article 1 GG",
                "score": 50.0,
            },
            {
                "title": "Article 2 GG",
                "url": "https://example.org/gg-2",
                "domain": "example.org",
                "snippet": "General freedom of action.",
                "rank": 2,
                "source_type": "official",
                "source_origin": "local_code",
                "priority": 4,
                "reference": "Article 2 GG",
                "score": 48.0,
            },
            {
                "title": "Article 3 GG",
                "url": "https://example.org/gg-3",
                "domain": "example.org",
                "snippet": "Equality before the law.",
                "rank": 3,
                "source_type": "official",
                "source_origin": "local_code",
                "priority": 4,
                "reference": "Article 3 GG",
                "score": 47.0,
            },
        ]

        with patch.object(self.service, "_retrieve_local_legal_code_sources", return_value=local_results):
            with patch("backend.services.ai.legal_search_mode_service.external_research_service.search") as web_search:
                with patch(
                    "backend.services.ai.legal_search_mode_service.reranker_service.rerank",
                    side_effect=lambda query, results, top_k: (results[:top_k], ["mock"]),
                ):
                    results = self.service._retrieve_jurisdiction_sources(
                        country="germany",
                        query="Constitutional equality and dignity",
                        case_focus_terms=["equality", "dignity"],
                        top_k=5,
                        case_topic={"code_families": ["code_civil"]},
                    )

        web_search.assert_not_called()
        self.assertGreaterEqual(len(results), 3)
        self.assertTrue(all(item.get("source_origin") == "local_code" for item in results[:3]))

    def test_infer_case_topic_prefers_succession_family(self) -> None:
        topic = self.service._infer_case_topic(
            country="tunisia",
            query="Client asks about succession rights of heirs and testament sharing",
            case_focus_terms=["succession", "heirs", "testament"],
            internal_results=[],
            code_scope=["code_civil", "code_succession", "code_international_prive"],
        )
        self.assertIn("code_succession", topic.get("code_families") or [])

    def test_legal_analysis_framework_includes_rule_application_and_next_steps(self) -> None:
        framework = self.service._build_legal_analysis_framework(
            country="tunisia",
            case_topic={"topic": "Code de Succession", "code_families": ["code_succession"]},
            has_internal_context=True,
        )
        lowered = framework.lower()
        self.assertIn("identify the legal issue", lowered)
        self.assertIn("governing legal basis", lowered)
        self.assertIn("apply the rule", lowered)
        self.assertIn("counter-analysis", lowered)
        self.assertIn("practical next steps", lowered)
        self.assertIn("case applicability check", lowered)

    def test_default_structure_enforcement_appends_required_sections(self) -> None:
        response = self.service._ensure_default_legal_response_structure(
            answer_body="Preliminary legal analysis based on current snippets.",
            query="Is succession share affected by testament wording?",
            legal_sources=[{"reference": "Article 12", "title": "Article 12"}],
            confidence="medium",
            verification_status="source_grounded_article_references_present",
            user_language="en",
        )
        self.assertIn("1. Matter Understood", response)
        self.assertIn("2. Confirmed Facts", response)
        self.assertIn("10. Lawyer Review Note", response)

    def test_default_structure_enforcement_localizes_french_sections(self) -> None:
        response = self.service._ensure_default_legal_response_structure(
            answer_body="Analyse preliminaire fondee sur les extraits actuellement disponibles.",
            query="Le testament modifie-t-il la part successorale ?",
            legal_sources=[{"reference": "Article 12", "title": "Article 12"}],
            confidence="medium",
            verification_status="source_grounded_article_references_present",
            user_language="fr",
        )
        self.assertIn("1. Question Comprise", response)
        self.assertIn("2. Faits Confirmes", response)
        self.assertIn("10. Note de Revue par l'Avocat", response)
        self.assertIn("Niveau de confiance", response)
        self.assertNotIn("1. Matter Understood", response)

    def test_format_output_includes_trust_status_block(self) -> None:
        output = self.service._format_legal_search_output(
            country="Tunisia",
            source_lines=["Article 12 - Code de Succession"],
            answer_body="1. Matter Understood\nPreliminary analysis.",
            fallback_notice=None,
            confidence="high",
            verification_status="source_grounded_article_references_present",
            lawyer_review_note=self.service.LAWYER_REVIEW_NOTE,
        )
        self.assertIn("[Trust Status]", output)
        self.assertIn("Confidence: high", output)
        self.assertIn("Verification status: source_grounded_article_references_present", output)


if __name__ == "__main__":
    unittest.main()
