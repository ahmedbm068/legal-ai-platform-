from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JurisdictionProfile:
    country_code: str
    display_name: str
    constitutional_references: list[str]
    legal_guardrails: list[str]
    risk_focus_areas: list[str]


class JurisdictionContextService:
    _profiles: dict[str, JurisdictionProfile] = {
        "tunisia": JurisdictionProfile(
            country_code="tunisia",
            display_name="Tunisia",
            constitutional_references=[
                "https://www.wipo.int/wipolex/en/legislation/details/21853",
                "https://www.kas.de/documents/265308/265357/English%2BTranslation%2Bof%2Bthe%2B2022%2BConstitution%2Bof%2BTunisia.pdf/b5a12daa-b05f-9d94-062e-9e6b228cc746?version=1.0",
            ],
            legal_guardrails=[
                "Apply Tunisian constitutional principles and national legislation before external/common-law assumptions.",
                "Do not treat foreign enforcement practice as directly applicable without Tunisian procedural validation.",
                "Flag whenever contractual clauses appear to conflict with local public-order or mandatory-law constraints.",
            ],
            risk_focus_areas=[
                "Due process and procedural fairness in dispute handling",
                "Contract enforceability under mandatory local provisions",
                "Data/privacy and evidence handling standards under local law",
            ],
        ),
        "germany": JurisdictionProfile(
            country_code="germany",
            display_name="Germany",
            constitutional_references=[
                "https://www.gesetze-im-internet.de/englisch_gg/",
                "https://www.bundestag.de/en/parliament/function/legal/legal-197642",
            ],
            legal_guardrails=[
                "Apply German constitutional principles and mandatory statutory framework before generic legal assumptions.",
                "Treat rights-impacting decisions with proportionality and due-process checks.",
                "Validate contractual terms against mandatory consumer, labor, competition, and data-protection constraints.",
            ],
            risk_focus_areas=[
                "Proportionality and rights-impact review",
                "Consumer/procurement clause enforceability controls",
                "Privacy and data processing compliance alignment",
            ],
        ),
    }

    @staticmethod
    def normalize_country(raw_value: str | None) -> str:
        value = (raw_value or "").strip().lower()
        if value in {"de", "deu", "germany", "german"}:
            return "germany"
        if value in {"tn", "tun", "tunisia", "tunisian"}:
            return "tunisia"
        return "tunisia"

    def get_profile(self, raw_country: str | None) -> JurisdictionProfile:
        normalized = self.normalize_country(raw_country)
        return self._profiles.get(normalized, self._profiles["tunisia"])

    def get_prompt_block(self, raw_country: str | None) -> str:
        profile = self.get_profile(raw_country)
        lines = [
            f"Jurisdiction Country: {profile.display_name}",
            "Jurisdiction guardrails:",
            *[f"- {item}" for item in profile.legal_guardrails],
            "Risk focus areas:",
            *[f"- {item}" for item in profile.risk_focus_areas],
            "Constitution references:",
            *[f"- {item}" for item in profile.constitutional_references],
        ]
        return "\n".join(lines).strip()

    def get_response_context(self, raw_country: str | None) -> dict[str, Any]:
        profile = self.get_profile(raw_country)
        return {
            "country_code": profile.country_code,
            "country_display_name": profile.display_name,
            "constitutional_references": profile.constitutional_references,
            "legal_guardrails": profile.legal_guardrails,
            "risk_focus_areas": profile.risk_focus_areas,
        }


jurisdiction_context_service = JurisdictionContextService()
