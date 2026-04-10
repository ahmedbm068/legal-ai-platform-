import { memo, useMemo, useState } from "react";
import type {
  CaseItem,
  ChatMessage,
  Client,
  ConsultationRequest,
  DocumentItem,
  FullDocumentAnalysis,
  VoiceRecording,
} from "../types";

type CardTone = "risk" | "warning" | "stable" | "neutral";
type CardKey = "summary" | "risks" | "missing" | "evidence" | "timeline" | "contradictions";

interface IntelligencePanelProps {
  language: "en" | "de" | "ar";
  caseItem: CaseItem | null;
  client: Client | null;
  documents: DocumentItem[];
  consultations: ConsultationRequest[];
  recordings: VoiceRecording[];
  analysis: FullDocumentAnalysis | null;
  latestAssistantMessage: ChatMessage | null;
  onLaunchAction?: (prompt: string) => void;
}

interface TimelineRow {
  title: string;
  date: string;
  detail: string;
}

const PANEL_TEXT: Record<"en" | "de" | "ar", Record<string, string>> = {
  en: {
    unknownDate: "Unknown date",
    caseIntelligence: "Case Intelligence",
    noCaseSelected: "No Case Selected",
    basedOnDocs: "Based on {count} document(s)",
    confidence: "Confidence",
    high: "High",
    medium: "Medium",
    summary: "Summary",
    risks: "Risks",
    missingInfo: "Missing Info",
    evidence: "Evidence",
    timeline: "Timeline",
    contradictions: "Contradictions",
    noSummary: "No summary available yet. Ask copilot to generate a case summary from your evidence.",
    noRisk: "No explicit high-risk signal detected yet. Continue monitoring new evidence and deadlines.",
    missingCaseNarrative: "Case narrative is missing a complete factual statement.",
    missingClientEmail: "Client email is missing.",
    missingClientPhone: "Client phone is missing.",
    missingDocs: "No supporting documents uploaded to the case.",
    missingConsult: "No consultation request linked to this matter.",
    missingDeadlines: "No extracted legal deadlines detected yet.",
    noEvidenceFiles: "No evidence files yet",
    uploadEvidenceHint: "Upload PDF contracts, notices, or reports to ground AI answers.",
    consultationPrefix: "Consultation",
    consultationCreated: "Consultation created.",
    voiceNotePrefix: "Voice Note",
    transcriptionStatus: "Transcription status",
    keyDate: "Key date",
    extractedFromDocs: "Extracted from uploaded documents.",
    closedPendingEvidence: "Case marked closed while evidence processing is still pending.",
    closedConsultationReview: "Case is closed but there are consultations still under review.",
    noContradiction: "No structural contradiction detected across current case records.",
    noTimeline: "No case events detected yet.",
  },
  de: {
    unknownDate: "Unbekanntes Datum",
    caseIntelligence: "Fall-Intelligence",
    noCaseSelected: "Kein Fall ausgewaehlt",
    basedOnDocs: "Basiert auf {count} Dokument(en)",
    confidence: "Vertrauen",
    high: "Hoch",
    medium: "Mittel",
    summary: "Zusammenfassung",
    risks: "Risiken",
    missingInfo: "Fehlende Infos",
    evidence: "Evidenz",
    timeline: "Zeitleiste",
    contradictions: "Widersprueche",
    noSummary: "Noch keine Zusammenfassung verfuegbar. Bitte Copilot um eine fallbezogene Zusammenfassung.",
    noRisk: "Noch kein explizites Hochrisiko-Signal erkannt. Neue Evidenz und Fristen weiter beobachten.",
    missingCaseNarrative: "Die Falldarstellung ist unvollstaendig.",
    missingClientEmail: "Client-E-Mail fehlt.",
    missingClientPhone: "Client-Telefon fehlt.",
    missingDocs: "Keine unterstuetzenden Dokumente im Fall.",
    missingConsult: "Keine Beratung mit diesem Fall verknuepft.",
    missingDeadlines: "Noch keine extrahierten Rechtsfristen erkannt.",
    noEvidenceFiles: "Noch keine Evidenzdateien",
    uploadEvidenceHint: "Lade PDF-Vertraege, Hinweise oder Berichte hoch, um AI-Antworten zu untermauern.",
    consultationPrefix: "Beratung",
    consultationCreated: "Beratung erstellt.",
    voiceNotePrefix: "Sprachnotiz",
    transcriptionStatus: "Transkriptionsstatus",
    keyDate: "Wichtiges Datum",
    extractedFromDocs: "Aus hochgeladenen Dokumenten extrahiert.",
    closedPendingEvidence: "Fall ist als geschlossen markiert, waehrend Evidenz noch verarbeitet wird.",
    closedConsultationReview: "Fall ist geschlossen, aber Beratungen sind noch in Pruefung.",
    noContradiction: "Keine strukturellen Widersprueche in den aktuellen Falldaten erkannt.",
    noTimeline: "Noch keine Fallereignisse erkannt.",
  },
  ar: {
    unknownDate: "تاريخ غير معروف",
    caseIntelligence: "ذكاء القضية",
    noCaseSelected: "لا توجد قضية محددة",
    basedOnDocs: "استناداً إلى {count} مستند",
    confidence: "الثقة",
    high: "عالية",
    medium: "متوسطة",
    summary: "الملخص",
    risks: "المخاطر",
    missingInfo: "معلومات ناقصة",
    evidence: "الأدلة",
    timeline: "الجدول الزمني",
    contradictions: "التناقضات",
    noSummary: "لا يوجد ملخص بعد. اطلب من المساعد إنشاء ملخص للقضية من الأدلة.",
    noRisk: "لم يتم رصد إشارة مخاطر عالية صريحة بعد. استمر في متابعة الأدلة والمواعيد.",
    missingCaseNarrative: "وصف القضية ينقصه عرض واقعي كامل.",
    missingClientEmail: "بريد العميل الإلكتروني مفقود.",
    missingClientPhone: "رقم هاتف العميل مفقود.",
    missingDocs: "لا توجد مستندات داعمة مرفوعة لهذه القضية.",
    missingConsult: "لا يوجد طلب استشارة مرتبط بهذه القضية.",
    missingDeadlines: "لم يتم استخراج مواعيد قانونية بعد.",
    noEvidenceFiles: "لا توجد ملفات أدلة بعد",
    uploadEvidenceHint: "ارفع عقود PDF أو إشعارات أو تقارير لتدعيم إجابات الذكاء الاصطناعي.",
    consultationPrefix: "استشارة",
    consultationCreated: "تم إنشاء الاستشارة.",
    voiceNotePrefix: "ملاحظة صوتية",
    transcriptionStatus: "حالة التفريغ",
    keyDate: "تاريخ مهم",
    extractedFromDocs: "تم استخراجه من المستندات المرفوعة.",
    closedPendingEvidence: "تم إغلاق القضية بينما لا تزال معالجة الأدلة قيد التنفيذ.",
    closedConsultationReview: "القضية مغلقة لكن توجد استشارات ما زالت قيد المراجعة.",
    noContradiction: "لا يوجد تناقض بنيوي عبر سجلات القضية الحالية.",
    noTimeline: "لم يتم رصد أحداث للقضية بعد.",
  },
};

function compactDate(value: string | null | undefined, locale: string, unknownLabel: string): string {
  if (!value) return unknownLabel;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return unknownLabel;
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(parsed);
}

function iconFor(key: CardKey): string {
  switch (key) {
    case "summary":
      return "AI";
    case "risks":
      return "!";
    case "missing":
      return "?";
    case "evidence":
      return "E";
    case "timeline":
      return "T";
    case "contradictions":
      return "C";
    default:
      return ".";
  }
}

function extractRiskLines(text: string): string[] {
  if (!text.trim()) return [];
  const rows = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => /risk|deadline|exposure|penalty|breach|liability/i.test(line))
    .slice(0, 6);
  return rows;
}

function extractMissingLines(text: string): string[] {
  if (!text.trim()) return [];
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => /missing|unknown|not provided|insufficient|unclear/i.test(line))
    .slice(0, 6);
}

function IntelligencePanelComponent(props: IntelligencePanelProps) {
  const { language, caseItem, client, documents, consultations, recordings, analysis, latestAssistantMessage, onLaunchAction } = props;
  const copy = PANEL_TEXT[language] || PANEL_TEXT.en;
  const tp = (key: string, fallback: string) => copy[key] || PANEL_TEXT.en[key] || fallback;
  const locale = language === "de" ? "de-DE" : language === "ar" ? "ar-TN" : "en-US";

  const [expanded, setExpanded] = useState<Record<CardKey, boolean>>({
    summary: true,
    risks: true,
    missing: true,
    evidence: true,
    timeline: true,
    contradictions: true,
  });

  // Optimization: memoized data slices prevent heavy recomputation while typing in chat.
  const summary = useMemo(() => {
    return (
      analysis?.summary_short ||
      analysis?.summary ||
      caseItem?.description ||
      latestAssistantMessage?.content ||
      tp("noSummary", "No summary available yet. Ask copilot to generate a case summary from your evidence.")
    );
  }, [analysis?.summary, analysis?.summary_short, caseItem?.description, latestAssistantMessage?.content, language]);

  const risks = useMemo(() => {
    const fromAnalysis = analysis?.insights?.legal_risks?.filter(Boolean) || [];
    const fromAssistant = latestAssistantMessage ? extractRiskLines(latestAssistantMessage.content) : [];
    const merged = [...fromAnalysis, ...fromAssistant];
    if (!merged.length) {
      return [tp("noRisk", "No explicit high-risk signal detected yet. Continue monitoring new evidence and deadlines.")];
    }
    return Array.from(new Set(merged)).slice(0, 8);
  }, [analysis?.insights?.legal_risks, latestAssistantMessage, language]);

  const missingInfo = useMemo(() => {
    const rows: string[] = [];
    if (!caseItem?.description?.trim()) rows.push(tp("missingCaseNarrative", "Case narrative is missing a complete factual statement."));
    if (!client?.email) rows.push(tp("missingClientEmail", "Client email is missing."));
    if (!client?.phone) rows.push(tp("missingClientPhone", "Client phone is missing."));
    if (!documents.length) rows.push(tp("missingDocs", "No supporting documents uploaded to the case."));
    if (!consultations.length) rows.push(tp("missingConsult", "No consultation request linked to this matter."));
    if (!analysis?.insights?.important_dates?.length) rows.push(tp("missingDeadlines", "No extracted legal deadlines detected yet."));
    const assistantHints = latestAssistantMessage ? extractMissingLines(latestAssistantMessage.content) : [];
    return Array.from(new Set([...rows, ...assistantHints])).slice(0, 8);
  }, [analysis?.insights?.important_dates, caseItem?.description, client?.email, client?.phone, consultations.length, documents.length, latestAssistantMessage, language]);

  const evidenceRows = useMemo(() => {
    if (!documents.length) {
      return [
        {
          title: tp("noEvidenceFiles", "No evidence files yet"),
          detail: tp("uploadEvidenceHint", "Upload PDF contracts, notices, or reports to ground AI answers."),
        },
      ];
    }
    return documents.slice(0, 8).map((document) => ({
      title: `${document.filename} (Doc #${document.id})`,
      detail: `${document.processing_status} | ${Math.max(1, Math.round(document.file_size / 1024))} KB`,
    }));
  }, [documents, language]);

  const timelineRows = useMemo<TimelineRow[]>(() => {
    const rows: TimelineRow[] = [];

    analysis?.insights?.important_dates?.forEach((item) => {
      rows.push({
        title: item.label || tp("keyDate", "Key date"),
        date: item.value,
        detail: tp("extractedFromDocs", "Extracted from uploaded documents."),
      });
    });

    consultations.forEach((consultation) => {
      rows.push({
        title: `${tp("consultationPrefix", "Consultation")} #${consultation.id}`,
        date: consultation.created_at,
        detail: consultation.issue_summary || tp("consultationCreated", "Consultation created."),
      });
    });

    recordings.forEach((recording) => {
      rows.push({
        title: `${tp("voiceNotePrefix", "Voice Note")} ${recording.filename}`,
        date: recording.created_at,
        detail: `${tp("transcriptionStatus", "Transcription status")}: ${recording.transcription_status}`,
      });
    });

    rows.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
    return rows.slice(0, 8);
  }, [analysis?.insights?.important_dates, consultations, recordings, language]);

  const contradictions = useMemo(() => {
    const rows: string[] = [];
    if (caseItem?.status === "closed" && documents.some((document) => document.processing_status !== "completed")) {
      rows.push(tp("closedPendingEvidence", "Case marked closed while evidence processing is still pending."));
    }
    if (consultations.some((consultation) => consultation.status === "ready_for_review") && caseItem?.status === "closed") {
      rows.push(tp("closedConsultationReview", "Case is closed but there are consultations still under review."));
    }
    if (!rows.length) {
      rows.push(tp("noContradiction", "No structural contradiction detected across current case records."));
    }
    return rows;
  }, [caseItem?.status, consultations, documents, language]);

  const specialistLaunchers = useMemo(
    () => [
      {
        title: "Case memory",
        detail: caseItem
          ? `Snapshot case #${caseItem.id} with claims, gaps, and deadlines`
          : "Snapshot the current matter with claims, gaps, and deadlines",
        prompt: caseItem
          ? `Generate a case memory snapshot for case #${caseItem.id} (${caseItem.title}). Include document inventory, claim trace, contradictions, open proof gaps, and deadline signals.`
          : "Generate a case memory snapshot for the active matter. Include document inventory, claim trace, contradictions, open proof gaps, and deadline signals.",
      },
      {
        title: "Trace evidence",
        detail: caseItem
          ? `Map claims to evidence for case #${caseItem.id}`
          : "Map claims to evidence for the active matter",
        prompt: caseItem
          ? `Trace claims to evidence for case #${caseItem.id} (${caseItem.title}). Show supporting documents, unsupported claims, and recommended follow-up.`
          : "Trace claims to evidence for the active matter. Show supporting documents, unsupported claims, and recommended follow-up.",
      },
      {
        title: "Deadline monitor",
        detail: caseItem
          ? `Track deadlines and obligations in case #${caseItem.id}`
          : "Track deadlines and obligations in the current matter",
        prompt: caseItem
          ? `Monitor deadlines and obligations for case #${caseItem.id} (${caseItem.title}). Identify notice windows, cure periods, renewal dates, and recommended next steps.`
          : "Monitor deadlines and obligations for the active matter. Identify notice windows, cure periods, renewal dates, and recommended next steps.",
      },
      {
        title: "Contract redline",
        detail: documents.length
          ? `Draft clause-level edits for the current contract pack`
          : "Draft clause-level edits for the current matter",
        prompt: caseItem
          ? `Draft a contract redline for case #${caseItem.id} (${caseItem.title}). Include clause-level edits, fallback positions, risk notes, and source documents.`
          : "Draft a contract redline for the active matter. Include clause-level edits, fallback positions, risk notes, and source documents.",
      },
    ],
    [caseItem, documents.length]
  );

  function toggleCard(key: CardKey) {
    setExpanded((current) => ({ ...current, [key]: !current[key] }));
  }

  const cards: Array<{
    key: CardKey;
    title: string;
    tone: CardTone;
    aiEnhanced?: boolean;
    body: JSX.Element;
  }> = [
      {
        key: "summary",
        title: tp("summary", "Summary"),
        tone: "stable",
        aiEnhanced: true,
        body: <p>{summary}</p>,
      },
      {
        key: "risks",
        title: tp("risks", "Risks"),
        tone: "risk",
        aiEnhanced: true,
        body: (
          <ul>
            {risks.map((risk) => (
              <li key={risk}>{risk}</li>
            ))}
          </ul>
        ),
      },
      {
        key: "missing",
        title: tp("missingInfo", "Missing Info"),
        tone: "warning",
        body: (
          <ul>
            {missingInfo.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ),
      },
      {
        key: "evidence",
        title: tp("evidence", "Evidence"),
        tone: "stable",
        body: (
          <div className="intel-row-list">
            {evidenceRows.map((row) => (
              <article key={row.title}>
                <strong>{row.title}</strong>
                <small>{row.detail}</small>
              </article>
            ))}
          </div>
        ),
      },
      {
        key: "timeline",
        title: tp("timeline", "Timeline"),
        tone: "neutral",
        body: timelineRows.length ? (
          <div className="intel-row-list">
            {timelineRows.map((row) => (
              <article key={`${row.title}-${row.date}`}>
                <strong>{row.title}</strong>
                <small>{compactDate(row.date, locale, tp("unknownDate", "Unknown date"))}</small>
                <p>{row.detail}</p>
              </article>
            ))}
          </div>
        ) : (
          <p>{tp("noTimeline", "No case events detected yet.")}</p>
        ),
      },
      {
        key: "contradictions",
        title: tp("contradictions", "Contradictions"),
        tone: "warning",
        body: (
          <ul>
            {contradictions.map((row) => (
              <li key={row}>{row}</li>
            ))}
          </ul>
        ),
      },
    ];

  return (
    <aside className="intel-panel-shell">
      <header className="intel-panel-head">
        <div>
          <p>{tp("caseIntelligence", "Case Intelligence")}</p>
          <h2>{caseItem ? `${caseItem.title} | ${tp("caseIntelligence", "Case Intelligence")} #${caseItem.id}` : tp("noCaseSelected", "No Case Selected")}</h2>
        </div>
        <div className="intel-head-badges">
          <span className="intel-badge ai">AI</span>
          <span className="intel-badge">{tp("basedOnDocs", "Based on {count} document(s)").replace("{count}", String(documents.length))}</span>
          <span className="intel-badge">{tp("confidence", "Confidence")}: {analysis?.summary_status === "ready" ? tp("high", "High") : tp("medium", "Medium")}</span>
        </div>
      </header>

      <div className="workflow-grid">
        {specialistLaunchers.map((launcher) => (
          <button
            key={launcher.title}
            className="workflow-card"
            disabled={!caseItem || !onLaunchAction}
            onClick={() => onLaunchAction?.(launcher.prompt)}
            type="button"
          >
            <strong>{launcher.title}</strong>
            <small>{launcher.detail}</small>
          </button>
        ))}
      </div>

      <div className="intel-cards">
        {cards.map((card) => (
          <section key={card.key} className={`intel-card ${card.tone} ${card.aiEnhanced ? "ai-generated" : ""}`}>
            <button className="intel-card-head" onClick={() => toggleCard(card.key)} type="button">
              <span className="intel-card-icon">{iconFor(card.key)}</span>
              <strong>{card.title}</strong>
              <span className="intel-card-toggle">{expanded[card.key] ? "-" : "+"}</span>
            </button>
            {expanded[card.key] ? <div className="intel-card-body">{card.body}</div> : null}
          </section>
        ))}
      </div>
    </aside>
  );
}

// Optimization: memoized panel avoids unnecessary re-renders when unrelated UI state updates.
export default memo(IntelligencePanelComponent);
