import { Fragment, memo, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { ChatMessage, FeedbackRootCause } from "../types";

type FeedbackValue = "up" | "down";
type FeedbackStatus = "idle" | "saving" | "submitted" | "error";
type UiLanguage = "en" | "fr" | "de" | "ar";

export interface MessageFeedbackState {
  value: FeedbackValue | null;
  status: FeedbackStatus;
  rootCause?: FeedbackRootCause | null;
}

interface ChatMessageBubbleProps {
  language: UiLanguage;
  message: ChatMessage;
  feedback: MessageFeedbackState | undefined;
  onCopy: (message: ChatMessage) => void;
  onRegenerate: (message: ChatMessage) => void;
  onFeedback: (message: ChatMessage, value: FeedbackValue, rootCause?: FeedbackRootCause | null) => void;
  onAskMissingInfo?: (message: ChatMessage, missingInfo: string) => void;
  onTrustReview?: (message: ChatMessage, decision: "approved" | "needs_revision") => void;
}

interface MessageSection {
  title: string;
  paragraphs: string[];
  bullets: string[];
}

type TagKey = "highRisk" | "mediumRisk" | "deadline" | "contradiction" | "missingInfo" | "legalSource";

type GenericRecord = Record<string, unknown>;

interface PositionStrengthView {
  score: number;
  label: "weak" | "arguable" | "strong";
  reason: string;
}

interface RecommendedStrategyView {
  type: "negotiate" | "litigate" | "gather_evidence" | "wait" | "escalate";
  reason: string;
  risk_level: "low" | "medium" | "high";
}

interface EvidenceStrengthView {
  strong: string[];
  medium: string[];
  weak: string[];
}

interface ContradictionView {
  description: string;
  impact: "low" | "medium" | "high";
  sources: string[];
  type?: string;
  severityScore?: number;
}

interface ClaimEvidenceView {
  claim: string;
  sourceLabel: string;
  evidenceStrength: string;
  quote: string;
  exactQuoteSpan: string;
  note: string;
}

interface TimelineImpactView {
  event: string;
  legal_effect: string;
  risk: "low" | "medium" | "high";
}

interface ClientRiskSummaryView {
  financial_risk: string;
  legal_risk: string;
  urgency: "low" | "medium" | "high";
  summary: string;
}

interface LegalTrustPanelData {
  confidence: string;
  confidenceScore: number;
  verificationStatus: string;
  positionStrength: PositionStrengthView;
  recommendedStrategy: RecommendedStrategyView;
  evidenceStrength: EvidenceStrengthView;
  contradictions: ContradictionView[];
  timelineLegalImpact: TimelineImpactView[];
  clientRiskSummary: ClientRiskSummaryView;
  missingInformation: string[];
  unsupportedClaims: ClaimEvidenceView[];
  sentenceMappings: ClaimEvidenceView[];
  lawyerReviewNote: string;
  citationCoverage: number;
  hallucinationRate: number;
}

const BUBBLE_TEXT: Record<UiLanguage, Record<string, string>> = {
  en: {
    sectionResponse: "Response",
    aiInsight: "AI Insight",
    confidence: "Confidence",
    basedOnSources: "Based on {count} sources",
    copy: "Copy",
    regenerate: "Regenerate",
    saving: "Saving...",
    saved: "Saved",
    failed: "Failed",
    you: "You",
    highRisk: "High Risk",
    mediumRisk: "Medium Risk",
    deadline: "Deadline",
    contradiction: "Contradiction",
    missingInfo: "Missing Info",
    legalSource: "Legal Source",
    downvoteReasonPrompt: "Why was this answer not helpful?",
    downvoteReasonUnclearPrompt: "Prompt interpretation issue",
    downvoteReasonWrongJurisdiction: "Wrong jurisdiction",
    downvoteReasonMissingEvidence: "Missing evidence",
    downvoteReasonGenericAnswer: "Too generic",
    downvoteReasonWrongLegalArea: "Wrong legal area",
    downvoteReasonUngrounded: "Not grounded in sources",
    downvoteReasonOther: "Other",
    downvoteReasonSelected: "Selected reason: {reason}",
    cancel: "Cancel",
    trustPanelTitle: "Trust and Risk Panel",
    trustPanelSubtitle: "Preliminary decision-support view for lawyer review.",
    verificationStatusLabel: "Verification",
    positionStrengthLabel: "Position Strength",
    strategyLabel: "Recommended Strategy",
    strategyRiskLabel: "Strategy Risk",
    evidenceStrengthLabel: "Evidence Strength",
    contradictionsLabel: "Contradictions",
    clientRiskSummaryLabel: "Client Risk Summary",
    financialRiskLabel: "Financial Risk",
    legalRiskLabel: "Legal Risk",
    urgencyLabel: "Urgency",
    confidenceLabel: "Confidence",
    strongLabel: "Strong",
    mediumLabel: "Medium",
    weakLabel: "Weak",
    timelineImpactLabel: "Timeline Legal Impact",
    eventLabel: "Event",
    legalEffectLabel: "Legal Effect",
    riskLabel: "Risk",
    sourcesLabel: "Sources",
    noneDetected: "None detected",
    missingInformationLabel: "Missing Information",
    unsupportedClaimsLabel: "Unsupported Claims",
    evidenceMappingLabel: "Sentence-to-Source Evidence",
    quoteLabel: "Quote",
    spanLabel: "Span",
    askForInfo: "Ask follow-up",
    lawyerReviewNoteLabel: "Lawyer Review Note",
    markReviewed: "Mark reviewed",
    needsCorrection: "Needs correction",
    citationCoverageLabel: "Citation Coverage",
    hallucinationRateLabel: "Unsupported Rate",
  },
  fr: {
    sectionResponse: "Reponse",
    aiInsight: "Insight IA",
    confidence: "Confiance",
    basedOnSources: "Base sur {count} sources",
    copy: "Copier",
    regenerate: "Regenerer",
    saving: "Enregistrement...",
    saved: "Enregistre",
    failed: "Echec",
    you: "Vous",
    highRisk: "Risque eleve",
    mediumRisk: "Risque moyen",
    deadline: "Echeance",
    contradiction: "Contradiction",
    missingInfo: "Info manquante",
    legalSource: "Source juridique",
    downvoteReasonPrompt: "Why was this answer not helpful?",
    downvoteReasonUnclearPrompt: "Prompt interpretation issue",
    downvoteReasonWrongJurisdiction: "Wrong jurisdiction",
    downvoteReasonMissingEvidence: "Missing evidence",
    downvoteReasonGenericAnswer: "Too generic",
    downvoteReasonWrongLegalArea: "Wrong legal area",
    downvoteReasonUngrounded: "Not grounded in sources",
    downvoteReasonOther: "Other",
    downvoteReasonSelected: "Selected reason: {reason}",
    cancel: "Cancel",
    trustPanelTitle: "Tableau confiance et risque",
    trustPanelSubtitle: "Vue preliminaire d'aide a la decision pour revue avocat.",
    verificationStatusLabel: "Verification",
    positionStrengthLabel: "Force de position",
    strategyLabel: "Strategie recommandee",
    strategyRiskLabel: "Risque de strategie",
    evidenceStrengthLabel: "Force de preuve",
    contradictionsLabel: "Contradictions",
    clientRiskSummaryLabel: "Resume du risque client",
    financialRiskLabel: "Risque financier",
    legalRiskLabel: "Risque juridique",
    urgencyLabel: "Urgence",
    confidenceLabel: "Confiance",
    noneDetected: "Aucune",
    missingInformationLabel: "Informations manquantes",
    unsupportedClaimsLabel: "Affirmations non supportees",
    evidenceMappingLabel: "Preuves phrase-source",
    quoteLabel: "Citation",
    spanLabel: "Position",
    askForInfo: "Demander precision",
    lawyerReviewNoteLabel: "Note de revue avocat",
    markReviewed: "Marquer revu",
    needsCorrection: "A corriger",
    citationCoverageLabel: "Couverture citations",
    hallucinationRateLabel: "Taux non supporte",
  },
  de: {
    sectionResponse: "Antwort",
    aiInsight: "AI-Einblick",
    confidence: "Vertrauen",
    basedOnSources: "Basiert auf {count} Quellen",
    copy: "Kopieren",
    regenerate: "Neu erzeugen",
    saving: "Speichern...",
    saved: "Gespeichert",
    failed: "Fehlgeschlagen",
    you: "Du",
    highRisk: "Hohes Risiko",
    mediumRisk: "Mittleres Risiko",
    deadline: "Frist",
    contradiction: "Widerspruch",
    missingInfo: "Fehlende Infos",
    legalSource: "Rechtsquelle",
    downvoteReasonPrompt: "Why was this answer not helpful?",
    downvoteReasonUnclearPrompt: "Prompt interpretation issue",
    downvoteReasonWrongJurisdiction: "Wrong jurisdiction",
    downvoteReasonMissingEvidence: "Missing evidence",
    downvoteReasonGenericAnswer: "Too generic",
    downvoteReasonWrongLegalArea: "Wrong legal area",
    downvoteReasonUngrounded: "Not grounded in sources",
    downvoteReasonOther: "Other",
    downvoteReasonSelected: "Selected reason: {reason}",
    cancel: "Cancel",
    trustPanelTitle: "Vertrauens- und Risikopanel",
    trustPanelSubtitle: "Vorlaeufige Entscheidungsunterstuetzung fuer Anwaltspruefung.",
    verificationStatusLabel: "Verifizierung",
    positionStrengthLabel: "Positionsstaerke",
    strategyLabel: "Empfohlene Strategie",
    strategyRiskLabel: "Strategierisiko",
    evidenceStrengthLabel: "Evidenzstaerke",
    contradictionsLabel: "Widersprueche",
    clientRiskSummaryLabel: "Mandantenrisiko",
    financialRiskLabel: "Finanzielles Risiko",
    legalRiskLabel: "Rechtliches Risiko",
    urgencyLabel: "Dringlichkeit",
    confidenceLabel: "Vertrauen",
    noneDetected: "Keine",
    missingInformationLabel: "Fehlende Informationen",
    unsupportedClaimsLabel: "Nicht belegte Aussagen",
    evidenceMappingLabel: "Satz-zu-Quelle-Evidenz",
    quoteLabel: "Zitat",
    spanLabel: "Spanne",
    askForInfo: "Nachfrage stellen",
    lawyerReviewNoteLabel: "Anwaltspruefnotiz",
    markReviewed: "Geprueft markieren",
    needsCorrection: "Korrektur noetig",
    citationCoverageLabel: "Zitationsabdeckung",
    hallucinationRateLabel: "Nicht belegt",
  },
  ar: {
    sectionResponse: "الرد",
    aiInsight: "رؤية الذكاء",
    confidence: "الثقة",
    basedOnSources: "استناداً إلى {count} مصدر",
    copy: "نسخ",
    regenerate: "إعادة التوليد",
    saving: "جارٍ الحفظ...",
    saved: "تم الحفظ",
    failed: "فشل",
    you: "أنت",
    highRisk: "مخاطر عالية",
    mediumRisk: "مخاطر متوسطة",
    deadline: "موعد نهائي",
    contradiction: "تناقض",
    missingInfo: "معلومات ناقصة",
    legalSource: "مصدر قانوني",
    downvoteReasonPrompt: "Why was this answer not helpful?",
    downvoteReasonUnclearPrompt: "Prompt interpretation issue",
    downvoteReasonWrongJurisdiction: "Wrong jurisdiction",
    downvoteReasonMissingEvidence: "Missing evidence",
    downvoteReasonGenericAnswer: "Too generic",
    downvoteReasonWrongLegalArea: "Wrong legal area",
    downvoteReasonUngrounded: "Not grounded in sources",
    downvoteReasonOther: "Other",
    downvoteReasonSelected: "Selected reason: {reason}",
    cancel: "Cancel",
    trustPanelTitle: "لوحة الثقة والمخاطر",
    trustPanelSubtitle: "عرض أولي لدعم القرار لمراجعة المحامي.",
    verificationStatusLabel: "التحقق",
    positionStrengthLabel: "قوة الموقف",
    strategyLabel: "الاستراتيجية الموصى بها",
    strategyRiskLabel: "مخاطر الاستراتيجية",
    evidenceStrengthLabel: "قوة الأدلة",
    contradictionsLabel: "التناقضات",
    clientRiskSummaryLabel: "ملخص مخاطر العميل",
    financialRiskLabel: "المخاطر المالية",
    legalRiskLabel: "المخاطر القانونية",
    urgencyLabel: "الاستعجال",
    confidenceLabel: "الثقة",
    noneDetected: "لا يوجد",
    missingInformationLabel: "Missing Information",
    unsupportedClaimsLabel: "Unsupported Claims",
    evidenceMappingLabel: "Sentence-to-Source Evidence",
    quoteLabel: "Quote",
    spanLabel: "Span",
    askForInfo: "Ask follow-up",
    lawyerReviewNoteLabel: "Lawyer Review Note",
    markReviewed: "Mark reviewed",
    needsCorrection: "Needs correction",
    citationCoverageLabel: "Citation Coverage",
    hallucinationRateLabel: "Unsupported Rate",
  },
};

const DOWNVOTE_REASON_OPTIONS: Array<{ value: FeedbackRootCause; labelKey: string; fallback: string }> = [
  { value: "unclear_prompt", labelKey: "downvoteReasonUnclearPrompt", fallback: "Prompt interpretation issue" },
  { value: "wrong_jurisdiction", labelKey: "downvoteReasonWrongJurisdiction", fallback: "Wrong jurisdiction" },
  { value: "missing_evidence", labelKey: "downvoteReasonMissingEvidence", fallback: "Missing evidence" },
  { value: "generic_answer", labelKey: "downvoteReasonGenericAnswer", fallback: "Too generic" },
  { value: "wrong_legal_area", labelKey: "downvoteReasonWrongLegalArea", fallback: "Wrong legal area" },
  { value: "ungrounded", labelKey: "downvoteReasonUngrounded", fallback: "Not grounded in sources" },
  { value: "other", labelKey: "downvoteReasonOther", fallback: "Other" },
];

const KEYWORD_PATTERN = /\b(risk|deadline|urgent|liability|evidence|article|section|compliance|penalty)\b/gi;
const KNOWN_BARE_SECTION_TITLES = new Set([
  "summary",
  "document inventory",
  "claim trace",
  "contradictions",
  "contradictions to resolve",
  "live deadlines and date signals",
  "live deadlines",
  "open proof gaps",
  "recommended next steps",
  "evidence reviewed",
  "issue identification",
  "applicable rule / law",
  "application to facts",
  "evidence mapping",
  "uncertainty / missing information",
  "counter-arguments / alternative interpretations",
  "risk assessment (per party)",
]);

function formatMessageTime(value: string, language: UiLanguage): string {
  const locale = language === "de" ? "de-DE" : language === "ar" ? "ar-TN" : language === "fr" ? "fr-FR" : "en-US";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function parseSections(content: string, defaultTitle: string): MessageSection[] {
  const lines = content.split(/\r?\n/);
  const sections: MessageSection[] = [];
  let current: MessageSection = { title: defaultTitle, paragraphs: [], bullets: [] };

  const isBareSectionTitle = (line: string): boolean => {
    const normalized = line.trim().toLowerCase();
    if (!normalized || normalized.length > 48) return false;
    return KNOWN_BARE_SECTION_TITLES.has(normalized);
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) continue;

    const bracketHeader = line.match(/^\[(.+?)\]$/);
    const colonHeader = line.match(/^([A-Za-z][A-Za-z ]{2,32}):$/);
    const inlineHeader = line.match(/^([A-Za-z][A-Za-z ]{2,32}):\s+(.+)$/);
    const numberedKnownHeader = line.match(/^\d+[\).]\s+(.+)$/);
    if (numberedKnownHeader && isBareSectionTitle(numberedKnownHeader[1])) {
      if (current.paragraphs.length || current.bullets.length) {
        sections.push(current);
      }
      current = {
        title: numberedKnownHeader[1].trim(),
        paragraphs: [],
        bullets: [],
      };
      continue;
    }
    if (bracketHeader || colonHeader) {
      if (current.paragraphs.length || current.bullets.length) {
        sections.push(current);
      }
      current = {
        title: (bracketHeader?.[1] || colonHeader?.[1] || "Section").trim(),
        paragraphs: [],
        bullets: [],
      };
      continue;
    }

    if (inlineHeader) {
      if (current.paragraphs.length || current.bullets.length) {
        sections.push(current);
      }
      current = {
        title: inlineHeader[1].trim(),
        paragraphs: [inlineHeader[2].trim()],
        bullets: [],
      };
      continue;
    }

    if (isBareSectionTitle(line)) {
      if (current.paragraphs.length || current.bullets.length) {
        sections.push(current);
      }
      current = {
        title: line,
        paragraphs: [],
        bullets: [],
      };
      continue;
    }

    if (line.startsWith("- ") || line.startsWith("* ")) {
      current.bullets.push(line.slice(2).trim());
      continue;
    }

    const numberedBullet = line.match(/^\d+[\).]\s+(.+)/);
    if (numberedBullet) {
      current.bullets.push(numberedBullet[1].trim());
      continue;
    }

    current.paragraphs.push(line);
  }

  if (current.paragraphs.length || current.bullets.length) {
    sections.push(current);
  }

  return sections.length ? sections : [{ title: defaultTitle, paragraphs: [content.trim()], bullets: [] }];
}

function extractTags(content: string): TagKey[] {
  const tags = new Set<TagKey>();
  const lower = content.toLowerCase();
  if (lower.includes("high risk")) tags.add("highRisk");
  if (lower.includes("medium risk")) tags.add("mediumRisk");
  if (lower.includes("deadline")) tags.add("deadline");
  if (lower.includes("contradiction")) tags.add("contradiction");
  if (lower.includes("missing")) tags.add("missingInfo");
  if (lower.includes("article") || lower.includes("section")) tags.add("legalSource");
  return Array.from(tags);
}

function highlightKeywords(value: string): Array<string | { keyword: string }> {
  const result: Array<string | { keyword: string }> = [];
  let cursor = 0;
  let match = KEYWORD_PATTERN.exec(value);
  while (match) {
    if (match.index > cursor) {
      result.push(value.slice(cursor, match.index));
    }
    result.push({ keyword: match[0] });
    cursor = match.index + match[0].length;
    match = KEYWORD_PATTERN.exec(value);
  }
  if (cursor < value.length) {
    result.push(value.slice(cursor));
  }
  KEYWORD_PATTERN.lastIndex = 0;
  return result;
}

function normalizeUrlToken(rawUrl: string): { href: string; trailing: string } {
  let href = String(rawUrl || "");
  let trailing = "";
  while (href.length > 0) {
    const lastChar = href[href.length - 1];
    if (![".", ",", ";", ":", "!", "?", ")"].includes(lastChar)) {
      break;
    }
    if (lastChar === ")") {
      const openCount = (href.match(/\(/g) || []).length;
      const closeCount = (href.match(/\)/g) || []).length;
      if (closeCount <= openCount) {
        break;
      }
    }
    trailing = `${lastChar}${trailing}`;
    href = href.slice(0, -1);
  }
  return { href, trailing };
}

function renderLinkifiedText(value: string, keyPrefix: string): ReactNode[] {
  if (!value) {
    return [];
  }

  const nodes: ReactNode[] = [];
  let cursor = 0;
  const matches = value.matchAll(/https?:\/\/[^\s]+/gi);

  for (const match of matches) {
    const matchText = match[0] || "";
    const matchIndex = match.index ?? -1;
    if (!matchText || matchIndex < 0) {
      continue;
    }

    if (matchIndex > cursor) {
      nodes.push(
        <span key={`${keyPrefix}-plain-${cursor}`}>
          {value.slice(cursor, matchIndex)}
        </span>
      );
    }

    const { href, trailing } = normalizeUrlToken(matchText);
    if (href) {
      nodes.push(
        <a
          key={`${keyPrefix}-url-${matchIndex}`}
          href={href}
          target="_blank"
          rel="noreferrer noopener"
        >
          {href}
        </a>
      );
    }
    if (trailing) {
      nodes.push(<span key={`${keyPrefix}-trail-${matchIndex}`}>{trailing}</span>);
    }
    cursor = matchIndex + matchText.length;
  }

  if (cursor < value.length) {
    nodes.push(<span key={`${keyPrefix}-end`}>{value.slice(cursor)}</span>);
  }

  if (!nodes.length) {
    nodes.push(<span key={`${keyPrefix}-all`}>{value}</span>);
  }
  return nodes;
}

function renderHighlightedWithLinks(value: string, keyPrefix: string): ReactNode[] {
  return highlightKeywords(value).map((token, tokenIndex) => {
    if (typeof token === "string") {
      return (
        <Fragment key={`${keyPrefix}-txt-${tokenIndex}`}>
          {renderLinkifiedText(token, `${keyPrefix}-txt-${tokenIndex}`)}
        </Fragment>
      );
    }
    return <mark key={`${keyPrefix}-key-${tokenIndex}`}>{token.keyword}</mark>;
  });
}

function extractFirstUrl(value: string): string | null {
  const match = String(value || "").match(/https?:\/\/[^\s]+/i);
  if (!match || !match.length) {
    return null;
  }
  const normalized = normalizeUrlToken(match[0]);
  return normalized.href || null;
}

function asRecord(value: unknown): GenericRecord | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as GenericRecord;
  }
  return null;
}

function asStringList(value: unknown, limit = 12): string[] {
  if (!Array.isArray(value)) return [];
  const rows: string[] = [];
  for (const item of value) {
    const text = String(item || "").trim();
    if (!text || rows.includes(text)) continue;
    rows.push(text);
    if (rows.length >= limit) break;
  }
  return rows;
}

function normalizeRiskLevel(value: unknown): "low" | "medium" | "high" {
  const token = String(value || "").trim().toLowerCase();
  if (token === "low" || token === "medium" || token === "high") return token;
  return "medium";
}

function normalizeRiskFromSeverity(value: unknown): "low" | "medium" | "high" {
  const score = Number(value);
  if (!Number.isFinite(score)) return "medium";
  if (score >= 0.7) return "high";
  if (score >= 0.35) return "medium";
  return "low";
}

function normalizeStrengthLabel(value: unknown): "weak" | "arguable" | "strong" {
  const token = String(value || "").trim().toLowerCase();
  if (token === "weak" || token === "arguable" || token === "strong") return token;
  return "weak";
}

function normalizeStrategyType(value: unknown): "negotiate" | "litigate" | "gather_evidence" | "wait" | "escalate" {
  const token = String(value || "").trim().toLowerCase().replace(/\s+/g, "_");
  if (token === "negotiate" || token === "litigate" || token === "gather_evidence" || token === "wait" || token === "escalate") {
    return token;
  }
  return "gather_evidence";
}

function normalizeContradictions(value: unknown): ContradictionView[] {
  if (!Array.isArray(value)) return [];
  const rows: ContradictionView[] = [];
  for (const item of value) {
    const entry = asRecord(item);
    if (!entry) continue;
    const description = String(entry.description || entry.contradiction_type || "").trim();
    if (!description) continue;
    const conflictingSources = Array.isArray(entry.conflicting_sources)
      ? entry.conflicting_sources
        .map((source) => {
          const sourceRecord = asRecord(source);
          if (!sourceRecord) return String(source || "").trim();
          const label = String(sourceRecord.source_label || "").trim();
          const snippet = String(sourceRecord.snippet || "").trim();
          return [label, snippet].filter(Boolean).join(": ");
        })
        .filter(Boolean)
      : [];
    const severityScore = Number(entry.severity_score);
    rows.push({
      description,
      impact: entry.severity_score !== undefined ? normalizeRiskFromSeverity(entry.severity_score) : normalizeRiskLevel(entry.impact),
      sources: asStringList(entry.sources, 5).concat(conflictingSources).slice(0, 5),
      type: String(entry.contradiction_type || "").trim() || undefined,
      severityScore: Number.isFinite(severityScore) ? severityScore : undefined,
    });
    if (rows.length >= 8) break;
  }
  return rows;
}

function normalizeClaimEvidence(value: unknown, limit = 8): ClaimEvidenceView[] {
  if (!Array.isArray(value)) return [];
  const rows: ClaimEvidenceView[] = [];
  for (const item of value) {
    const entry = asRecord(item);
    if (!entry) continue;
    const mapping = Array.isArray(entry.mappings) ? asRecord(entry.mappings[0]) : null;
    const source = mapping || entry;
    const claim = String(entry.claim || entry.sentence || source?.sentence || "").trim();
    if (!claim) continue;
    rows.push({
      claim,
      sourceLabel: String(source?.source_label || "No matching source").trim(),
      evidenceStrength: String(entry.evidence_strength || source?.evidence_strength || "NONE").trim(),
      quote: String(source?.quote || "").trim(),
      exactQuoteSpan: String(source?.exact_quote_span || "").trim(),
      note: String(entry.note || "").trim(),
    });
    if (rows.length >= limit) break;
  }
  return rows;
}

function normalizeEvidenceStrengthFromPanel(value: unknown, mappings: ClaimEvidenceView[]): EvidenceStrengthView {
  const record = asRecord(value);
  if (record) {
    if (Array.isArray(record.strong) || Array.isArray(record.medium) || Array.isArray(record.weak)) {
      return {
        strong: asStringList(record.strong, 10),
        medium: asStringList(record.medium, 10),
        weak: asStringList(record.weak, 10),
      };
    }
  }

  const buckets: EvidenceStrengthView = { strong: [], medium: [], weak: [] };
  for (const row of mappings) {
    const label = row.sourceLabel || row.claim;
    const strength = row.evidenceStrength.toUpperCase();
    if (strength === "STRONG" && !buckets.strong.includes(label)) buckets.strong.push(label);
    else if (strength === "MEDIUM" && !buckets.medium.includes(label)) buckets.medium.push(label);
    else if (strength === "WEAK" && !buckets.weak.includes(label)) buckets.weak.push(label);
  }
  return {
    strong: buckets.strong.slice(0, 10),
    medium: buckets.medium.slice(0, 10),
    weak: buckets.weak.slice(0, 10),
  };
}

function normalizeTimelineLegalImpact(value: unknown): TimelineImpactView[] {
  if (!Array.isArray(value)) return [];
  const rows: TimelineImpactView[] = [];
  for (const item of value) {
    const entry = asRecord(item);
    if (!entry) continue;
    const event = String(entry.event || entry.date || "").trim();
    const legalEffect = String(entry.legal_effect || entry.legalEffect || "").trim();
    if (!event && !legalEffect) continue;
    rows.push({
      event: event || "timeline event",
      legal_effect: legalEffect || "legal impact requires lawyer review",
      risk: normalizeRiskLevel(entry.risk),
    });
    if (rows.length >= 8) break;
  }
  return rows;
}

function extractLegalTrustPanelData(message: ChatMessage): LegalTrustPanelData | null {
  const structuredRoot = asRecord(message.meta?.structuredResult);
  const directTrustPanel = asRecord(message.meta?.trustPanel) || asRecord(structuredRoot?.trust_panel);
  const globalContract = asRecord(structuredRoot?.global_output_contract);
  const legalWorkflow = asRecord(structuredRoot?.legal_workflow_agents);
  if (!structuredRoot && !directTrustPanel) return null;

  const verificationStatusRaw =
    (asRecord(legalWorkflow?.verification)?.verification_status as unknown)
    ?? globalContract?.verification_status
    ?? (directTrustPanel?.unsupported_claims ? "claim_validated" : undefined);
  const verificationStatus = String(verificationStatusRaw || "").trim().toLowerCase();
  const strategyRaw =
    (legalWorkflow?.recommended_strategy as unknown)
    ?? (legalWorkflow?.strategy as unknown)
    ?? globalContract?.recommended_strategy;
  const positionRaw =
    (legalWorkflow?.position_strength as unknown)
    ?? globalContract?.position_strength;
  const evidenceRaw =
    (legalWorkflow?.evidence_strength as unknown)
    ?? globalContract?.evidence_strength;
  const contradictionRaw =
    (legalWorkflow?.contradictions as unknown)
    ?? (legalWorkflow?.contradiction_analysis as unknown)
    ?? globalContract?.contradictions;
  const timelineImpactRaw =
    (legalWorkflow?.timeline_legal_impact as unknown)
    ?? globalContract?.timeline_legal_impact;
  const clientRiskRaw =
    (legalWorkflow?.client_risk_summary as unknown)
    ?? globalContract?.client_risk_summary
    ?? directTrustPanel?.risk_summary;
  const directMappings = normalizeClaimEvidence(directTrustPanel?.sentence_to_source_mapping, 10);
  const unsupportedClaims = normalizeClaimEvidence(directTrustPanel?.unsupported_claims, 8);
  const directMetrics = asRecord(directTrustPanel?.metrics);
  const directRisk = asRecord(directTrustPanel?.risk_summary);

  const positionRecord = asRecord(positionRaw);
  const strategyRecord = asRecord(strategyRaw);
  const evidenceRecord = asRecord(evidenceRaw);
  const clientRiskRecord = asRecord(clientRiskRaw);
  const contradictions = normalizeContradictions(directTrustPanel?.contradictions ?? contradictionRaw);
  const timelineLegalImpact = normalizeTimelineLegalImpact(timelineImpactRaw);

  const isSerious = Boolean(
    directTrustPanel || (globalContract && (
      globalContract.legal_issue
      || globalContract.matter_type
      || globalContract.position_strength
      || globalContract.recommended_strategy
      || globalContract.timeline_legal_impact
    ))
  );
  if (!isSerious) return null;

  const parsedScore = Number(positionRecord?.score || 0);
  const positionScore = Number.isFinite(parsedScore) ? Math.max(0, Math.min(100, Math.round(parsedScore))) : 0;
  const positionStrength: PositionStrengthView = {
    score: positionScore,
    label: normalizeStrengthLabel(positionRecord?.label),
    reason: String(positionRecord?.reason || "").trim(),
  };
  const recommendedStrategy: RecommendedStrategyView = {
    type: normalizeStrategyType(strategyRecord?.type),
    reason: String(strategyRecord?.reason || "").trim(),
    risk_level: normalizeRiskLevel(strategyRecord?.risk_level),
  };
  const evidenceStrength = normalizeEvidenceStrengthFromPanel(evidenceRecord ?? directTrustPanel?.evidence_strength, directMappings);
  const clientRiskSummary: ClientRiskSummaryView = {
    financial_risk: String(clientRiskRecord?.financial_risk || directRisk?.client || "").trim(),
    legal_risk: String(clientRiskRecord?.legal_risk || directRisk?.opposing_party || "").trim(),
    urgency: normalizeRiskLevel(clientRiskRecord?.urgency),
    summary: String(clientRiskRecord?.summary || "").trim(),
  };
  const confidenceScore = Number(directTrustPanel?.confidence_score);
  const citationCoverage = Number(directMetrics?.citation_coverage);
  const hallucinationRate = Number(directMetrics?.hallucination_rate);

  return {
    confidence: String(globalContract?.confidence || message.meta?.confidence || "").trim().toLowerCase(),
    confidenceScore: Number.isFinite(confidenceScore) ? confidenceScore : 0,
    verificationStatus: verificationStatus || "unverified",
    positionStrength,
    recommendedStrategy,
    evidenceStrength,
    contradictions,
    timelineLegalImpact,
    clientRiskSummary,
    missingInformation: asStringList(directTrustPanel?.missing_information ?? globalContract?.missing_facts, 10),
    unsupportedClaims,
    sentenceMappings: directMappings,
    lawyerReviewNote: String(globalContract?.lawyer_review_note || directTrustPanel?.lawyer_review_note || "").trim(),
    citationCoverage: Number.isFinite(citationCoverage) ? citationCoverage : 0,
    hallucinationRate: Number.isFinite(hallucinationRate) ? hallucinationRate : 0,
  };
}

function toTitleCase(value: string): string {
  const clean = String(value || "").replace(/_/g, " ").trim();
  if (!clean) return "";
  return clean.charAt(0).toUpperCase() + clean.slice(1);
}

function verificationSeverity(value: string): "low" | "medium" | "high" {
  const token = String(value || "").trim().toLowerCase();
  if (token === "verified") return "low";
  if (token === "partial") return "medium";
  return "high";
}

function ChatMessageBubbleComponent(props: ChatMessageBubbleProps) {
  const { language, message, feedback, onCopy, onRegenerate, onFeedback, onAskMissingInfo, onTrustReview } = props;
  const [showDownvoteReasonSelector, setShowDownvoteReasonSelector] = useState(false);
  const copy = BUBBLE_TEXT[language] || BUBBLE_TEXT.en;
  const tb = (key: string, fallback: string) => copy[key] || BUBBLE_TEXT.en[key] || fallback;
  const sections = useMemo(() => parseSections(message.content, tb("sectionResponse", "Response")), [message.content, language]);
  const tags = useMemo(() => extractTags(message.content), [message.content]);
  const sourceCount = message.meta?.sources?.length ?? 0;
  const citationCount = message.meta?.citations?.length ?? 0;
  const confidence = message.meta?.confidence;
  const trustPanel = useMemo(() => extractLegalTrustPanelData(message), [message]);
  const reasoningResult = message.meta?.reasoningResult;
  const rankedCandidates = reasoningResult?.candidates ?? [];
  const secondBestCandidate = rankedCandidates.find((candidate) => candidate.rank === 2) || null;
  const cache = message.meta?.cache;
  const isStreaming =
    message.role === "assistant" &&
    typeof message.meta?.rawAnswer === "string" &&
    message.meta.rawAnswer.length > 0 &&
    message.content !== message.meta.rawAnswer;
  const canShowActions = message.role === "assistant" && !isStreaming;
  const selectedDownvoteReasonLabel = useMemo(() => {
    if (!feedback?.rootCause) {
      return null;
    }
    const option = DOWNVOTE_REASON_OPTIONS.find((item) => item.value === feedback.rootCause);
    return option ? tb(option.labelKey, option.fallback) : feedback.rootCause;
  }, [feedback?.rootCause, language]);

  const handleUpvote = () => {
    setShowDownvoteReasonSelector(false);
    onFeedback(message, "up", null);
  };

  const handleDownvoteSelection = (rootCause: FeedbackRootCause) => {
    setShowDownvoteReasonSelector(false);
    onFeedback(message, "down", rootCause);
  };

  return (
    <article className={`copilot-message ${message.role}${isStreaming ? " streaming" : ""}`}>
      <div className="copilot-avatar">{message.role === "assistant" ? "AI" : tb("you", "You")}</div>
      <div className="copilot-bubble">
        <div className="message-head">
          <strong>{message.role === "assistant" ? tb("aiInsight", "AI Insight") : tb("you", "You")}</strong>
          <small>{formatMessageTime(message.timestamp, language)}</small>
        </div>
        {message.role === "assistant" ? (
          <header className="assistant-meta">
            <span className="assistant-meta-badge ai">{tb("aiInsight", "AI Insight")}</span>
            {confidence ? <span className="assistant-meta-badge">{tb("confidence", "Confidence")}: {confidence}</span> : null}
            {sourceCount > 0 ? <span className="assistant-meta-badge">{tb("basedOnSources", "Based on {count} sources").replace("{count}", String(sourceCount))}</span> : null}
            {citationCount > 0 ? <span className="assistant-meta-badge">Citations: {citationCount}</span> : null}
            {cache ? <span className="assistant-meta-badge">Cache: {cache.hit ? "hit" : "miss"}</span> : null}
            {tags.map((tag) => (
              <span key={tag} className="assistant-meta-badge tag">
                {tb(tag, tag)}
              </span>
            ))}
          </header>
        ) : null}

        <div className="assistant-sections">
          {sections.map((section, index) => (
            <section key={`${section.title}-${index}`} className="assistant-section">
              {sections.length > 1 ? <h4>{section.title}</h4> : null}

              {section.paragraphs.map((paragraph, paragraphIndex) => (
                <p key={`${section.title}-p-${paragraphIndex}`}>
                  {renderHighlightedWithLinks(paragraph, `${section.title}-p-${paragraphIndex}`)}
                </p>
              ))}

              {section.bullets.length ? (
                <ul>
                  {section.bullets.map((bullet, bulletIndex) => (
                    <li key={`${section.title}-b-${bulletIndex}`}>
                      {renderHighlightedWithLinks(bullet, `${section.title}-b-${bulletIndex}`)}
                    </li>
                  ))}
                </ul>
              ) : null}
            </section>
          ))}
        </div>

        {canShowActions
          && reasoningResult?.reasoning_level === "high"
          && reasoningResult.activated
          && secondBestCandidate ? (
          <div className="assistant-sections">
            <section className="assistant-section">
              <details className="reasoning-alt-detail">
                <summary>
                  Alternative high-reasoning answer (rank #2)
                </summary>
                <div className="reasoning-alt-card">
                  <div className="reasoning-alt-meta">
                    <span className="assistant-meta-badge">Style: {secondBestCandidate.style}</span>
                    <span className="assistant-meta-badge">Overall: {secondBestCandidate.score.overall_score.toFixed(2)}</span>
                    <span className="assistant-meta-badge">Grounding: {secondBestCandidate.score.grounding_score.toFixed(2)}</span>
                    <span className="assistant-meta-badge">Citations: {secondBestCandidate.score.citation_score.toFixed(2)}</span>
                    <span className="assistant-meta-badge">Factual: {secondBestCandidate.score.factual_consistency_score.toFixed(2)}</span>
                  </div>
                  {reasoningResult.winner_reason ? <p>Judge reason: {reasoningResult.winner_reason}</p> : null}
                  {secondBestCandidate.answer.split("\n\n").map((paragraph, paragraphIndex) => (
                    <p key={`reasoning-alt-${paragraphIndex}`}>
                      {renderHighlightedWithLinks(paragraph, `reasoning-alt-${paragraphIndex}`)}
                    </p>
                  ))}
                </div>
              </details>
            </section>
          </div>
        ) : null}

        {message.role === "assistant" && trustPanel ? (
          <div className="assistant-sections">
            <section className="assistant-section trust-risk-panel">
              <div className="trust-risk-head">
                <h4>{tb("trustPanelTitle", "Trust and Risk Panel")}</h4>
                <p>{tb("trustPanelSubtitle", "Preliminary decision-support view for lawyer review.")}</p>
              </div>

              <div className="trust-risk-grid">
                <article className="trust-card">
                  <h5>{tb("verificationStatusLabel", "Verification")}</h5>
                  <p className={`trust-status ${verificationSeverity(trustPanel.verificationStatus)}`}>
                    {toTitleCase(trustPanel.verificationStatus)}
                  </p>
                  <small>{tb("confidenceLabel", "Confidence")}: {toTitleCase(trustPanel.confidence || "low")}</small>
                  {trustPanel.confidenceScore > 0 ? (
                    <div className="trust-meter" aria-label={`${tb("confidenceLabel", "Confidence")}: ${Math.round(trustPanel.confidenceScore * 100)}%`}>
                      <span style={{ width: `${Math.round(trustPanel.confidenceScore * 100)}%` }} />
                    </div>
                  ) : null}
                </article>

                <article className="trust-card">
                  <h5>{tb("positionStrengthLabel", "Position Strength")}</h5>
                  <p className={`trust-status ${trustPanel.positionStrength.label === "strong" ? "low" : trustPanel.positionStrength.label === "arguable" ? "medium" : "high"}`}>
                    {toTitleCase(trustPanel.positionStrength.label)} ({trustPanel.positionStrength.score})
                  </p>
                  <small>{trustPanel.positionStrength.reason || tb("noneDetected", "None detected")}</small>
                </article>

                <article className="trust-card">
                  <h5>{tb("strategyLabel", "Recommended Strategy")}</h5>
                  <p>{toTitleCase(trustPanel.recommendedStrategy.type)}</p>
                  <small>{tb("strategyRiskLabel", "Strategy Risk")}: {toTitleCase(trustPanel.recommendedStrategy.risk_level)}</small>
                  {trustPanel.recommendedStrategy.reason ? <small>{trustPanel.recommendedStrategy.reason}</small> : null}
                </article>
              </div>

              <div className="trust-metrics-row">
                <span>{tb("citationCoverageLabel", "Citation Coverage")}: {Math.round(trustPanel.citationCoverage * 100)}%</span>
                <span>{tb("hallucinationRateLabel", "Unsupported Rate")}: {Math.round(trustPanel.hallucinationRate * 100)}%</span>
              </div>

              <div className="trust-subsection">
                <h5>{tb("evidenceStrengthLabel", "Evidence Strength")}</h5>
                <div className="trust-evidence-grid">
                  <div className="trust-evidence-col">
                    <strong>{tb("strongLabel", "Strong")}</strong>
                    {trustPanel.evidenceStrength.strong.length ? (
                      <ul>
                        {trustPanel.evidenceStrength.strong.slice(0, 4).map((row) => <li key={`strong-${row}`}>{row}</li>)}
                      </ul>
                    ) : <small>{tb("noneDetected", "None detected")}</small>}
                  </div>
                  <div className="trust-evidence-col">
                    <strong>{tb("mediumLabel", "Medium")}</strong>
                    {trustPanel.evidenceStrength.medium.length ? (
                      <ul>
                        {trustPanel.evidenceStrength.medium.slice(0, 4).map((row) => <li key={`medium-${row}`}>{row}</li>)}
                      </ul>
                    ) : <small>{tb("noneDetected", "None detected")}</small>}
                  </div>
                  <div className="trust-evidence-col">
                    <strong>{tb("weakLabel", "Weak")}</strong>
                    {trustPanel.evidenceStrength.weak.length ? (
                      <ul>
                        {trustPanel.evidenceStrength.weak.slice(0, 4).map((row) => <li key={`weak-${row}`}>{row}</li>)}
                      </ul>
                    ) : <small>{tb("noneDetected", "None detected")}</small>}
                  </div>
                </div>
              </div>

              <div className="trust-subsection">
                <h5>{tb("missingInformationLabel", "Missing Information")}</h5>
                {trustPanel.missingInformation.length ? (
                  <ul className="trust-action-list">
                    {trustPanel.missingInformation.slice(0, 6).map((row) => (
                      <li key={`missing-${row}`}>
                        <span>{row}</span>
                        {onAskMissingInfo ? (
                          <button type="button" onClick={() => onAskMissingInfo(message, row)}>
                            {tb("askForInfo", "Ask follow-up")}
                          </button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>{tb("noneDetected", "None detected")}</p>
                )}
              </div>

              <div className="trust-subsection">
                <h5>{tb("unsupportedClaimsLabel", "Unsupported Claims")}</h5>
                {trustPanel.unsupportedClaims.length ? (
                  <ul className="trust-claim-list">
                    {trustPanel.unsupportedClaims.slice(0, 5).map((row, index) => (
                      <li key={`unsupported-${index}`}>
                        <strong>{row.claim}</strong>
                        {row.note ? <small>{row.note}</small> : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>{tb("noneDetected", "None detected")}</p>
                )}
              </div>

              <div className="trust-subsection">
                <h5>{tb("evidenceMappingLabel", "Sentence-to-Source Evidence")}</h5>
                {trustPanel.sentenceMappings.length ? (
                  <ul className="trust-evidence-map">
                    {trustPanel.sentenceMappings.slice(0, 6).map((row, index) => (
                      <li key={`mapping-${index}`}>
                        <strong>{row.claim}</strong>
                        <span>{row.sourceLabel} · {row.evidenceStrength}</span>
                        {row.quote ? <small>{tb("quoteLabel", "Quote")}: "{row.quote}"</small> : null}
                        {row.exactQuoteSpan ? <small>{tb("spanLabel", "Span")}: {row.exactQuoteSpan}</small> : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>{tb("noneDetected", "None detected")}</p>
                )}
              </div>

              <div className="trust-subsection">
                <h5>{tb("contradictionsLabel", "Contradictions")}</h5>
                {trustPanel.contradictions.length ? (
                  <ul>
                    {trustPanel.contradictions.slice(0, 5).map((row, index) => (
                      <li key={`contradiction-${index}`}>
                        <strong>{toTitleCase(row.type || row.impact)}:</strong> {row.description}
                        {row.severityScore !== undefined ? <small> Severity: {Math.round(row.severityScore * 100)}%</small> : null}
                        {row.sources.length ? <small> {tb("sourcesLabel", "Sources")}: {row.sources.join(", ")}</small> : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>{tb("noneDetected", "None detected")}</p>
                )}
              </div>

              <div className="trust-subsection">
                <h5>{tb("timelineImpactLabel", "Timeline Legal Impact")}</h5>
                {trustPanel.timelineLegalImpact.length ? (
                  <ul className="timeline-impact-list">
                    {trustPanel.timelineLegalImpact.slice(0, 6).map((row, index) => (
                      <li key={`timeline-impact-${index}`} className="timeline-impact-item">
                        <strong>{tb("eventLabel", "Event")}:</strong> {row.event}
                        <span><strong>{tb("legalEffectLabel", "Legal Effect")}:</strong> {row.legal_effect}</span>
                        <small>{tb("riskLabel", "Risk")}: {toTitleCase(row.risk)}</small>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>{tb("noneDetected", "None detected")}</p>
                )}
              </div>

              <div className="trust-subsection">
                <h5>{tb("clientRiskSummaryLabel", "Client Risk Summary")}</h5>
                <ul>
                  <li><strong>{tb("financialRiskLabel", "Financial Risk")}:</strong> {trustPanel.clientRiskSummary.financial_risk || tb("noneDetected", "None detected")}</li>
                  <li><strong>{tb("legalRiskLabel", "Legal Risk")}:</strong> {trustPanel.clientRiskSummary.legal_risk || tb("noneDetected", "None detected")}</li>
                  <li><strong>{tb("urgencyLabel", "Urgency")}:</strong> {toTitleCase(trustPanel.clientRiskSummary.urgency)}</li>
                </ul>
                {trustPanel.clientRiskSummary.summary ? <p>{trustPanel.clientRiskSummary.summary}</p> : null}
              </div>

              {trustPanel.lawyerReviewNote ? (
                <div className="trust-subsection lawyer-review-note">
                  <h5>{tb("lawyerReviewNoteLabel", "Lawyer Review Note")}</h5>
                  <p>{trustPanel.lawyerReviewNote}</p>
                </div>
              ) : null}

              {onTrustReview ? (
                <div className="trust-review-actions">
                  <button type="button" onClick={() => onTrustReview(message, "approved")}>
                    {tb("markReviewed", "Mark reviewed")}
                  </button>
                  <button type="button" onClick={() => onTrustReview(message, "needs_revision")}>
                    {tb("needsCorrection", "Needs correction")}
                  </button>
                </div>
              ) : null}
            </section>
          </div>
        ) : null}

        {canShowActions && message.meta?.citations?.length ? (
          <div className="assistant-sections">
            <section className="assistant-section">
              <h4>Citations</h4>
              <ul className="citation-list">
                {message.meta.citations.slice(0, 5).map((citation) => (
                  <li key={`${citation.label}-${citation.snippet}`} className="citation-item">
                    <strong>{citation.label}</strong>
                    <span>{renderLinkifiedText(` ${citation.snippet}`, `${citation.label}-snippet`)}</span>
                    {(citation.url || extractFirstUrl(citation.snippet)) ? (
                      <a
                        className="citation-source-link"
                        href={(citation.url || extractFirstUrl(citation.snippet)) || ""}
                        target="_blank"
                        rel="noreferrer noopener"
                      >
                        Open source
                      </a>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
          </div>
        ) : null}

        {canShowActions ? (
          <div className="assistant-actions">
            <div className="assistant-actions-main">
              <button type="button" onClick={() => onCopy(message)}>
                {tb("copy", "Copy")}
              </button>
              <button type="button" onClick={() => onRegenerate(message)}>
                {tb("regenerate", "Regenerate")}
              </button>
              <button
                className={feedback?.value === "up" ? "active" : ""}
                disabled={feedback?.status === "saving"}
                type="button"
                onClick={handleUpvote}
              >
                👍
              </button>
              <button
                className={feedback?.value === "down" ? "active" : ""}
                disabled={feedback?.status === "saving"}
                type="button"
                onClick={() => setShowDownvoteReasonSelector((current) => !current)}
              >
                👎
              </button>
            </div>
            {showDownvoteReasonSelector ? (
              <div className="downvote-reason-panel">
                <small>{tb("downvoteReasonPrompt", "Why was this answer not helpful?")}</small>
                <div className="downvote-reason-grid">
                  {DOWNVOTE_REASON_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={feedback?.rootCause === option.value ? "active" : ""}
                      onClick={() => handleDownvoteSelection(option.value)}
                      disabled={feedback?.status === "saving"}
                    >
                      {tb(option.labelKey, option.fallback)}
                    </button>
                  ))}
                  <button
                    type="button"
                    className="downvote-reason-cancel"
                    onClick={() => setShowDownvoteReasonSelector(false)}
                    disabled={feedback?.status === "saving"}
                  >
                    {tb("cancel", "Cancel")}
                  </button>
                </div>
              </div>
            ) : null}
            <div className="assistant-actions-state" aria-live="polite">
              {feedback?.status === "submitted" && feedback?.value === "down" && selectedDownvoteReasonLabel ? (
                <small>
                  {tb("downvoteReasonSelected", "Selected reason: {reason}").replace("{reason}", selectedDownvoteReasonLabel)}
                </small>
              ) : null}
              {feedback?.status === "saving" ? <small>{tb("saving", "Saving...")}</small> : null}
              {feedback?.status === "submitted" ? <small>{tb("saved", "Saved")}</small> : null}
              {feedback?.status === "error" ? <small>{tb("failed", "Failed")}</small> : null}
            </div>
          </div>
        ) : null}
      </div>
    </article>
  );
}

export default memo(ChatMessageBubbleComponent);
