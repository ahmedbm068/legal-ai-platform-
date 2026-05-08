import { memo, useState } from "react";
import type { ChatMessage } from "../types";

type UiLanguage = "en" | "fr" | "de" | "ar";

interface ExecutionTracePanelProps {
  message: ChatMessage | null;
  language: UiLanguage;
  onClose: () => void;
}

interface StageRecord {
  name?: string;
  status?: "success" | "failed" | "skipped" | string;
  detail?: string | null;
  metadata?: Record<string, unknown>;
}

const COPY: Record<UiLanguage, Record<string, string>> = {
  en: {
    title: "Show your work",
    subtitle: "Pipeline trace for this answer",
    sectionStages: "Pipeline stages",
    sectionRetrieval: "Retrieval audit",
    sectionSources: "Sources & reranker scores",
    sectionIrac: "IRAC structure",
    sectionVerifier: "Verifier",
    sectionJudge: "Deep-reasoning judge",
    close: "Close",
    empty: "This message has no trace data yet — run a query first.",
    statusSuccess: "success",
    statusFailed: "failed",
    statusSkipped: "skipped",
    fusionMethod: "Fusion method",
    queries: "Queries",
    pool: "Candidate pool",
    final: "Final results",
    hyde: "HyDE",
    multiQuery: "Multi-query",
    on: "on",
    off: "off",
    score: "score",
    grounded: "Grounded",
    partial: "Partial",
    refused: "Refused",
    issue: "Issue / case risks",
    rule: "Applicable law",
    application: "Legal assessment",
    missing: "Missing facts",
    counsel: "Counsel note",
    chosen: "Chosen",
    primary: "primary",
    steelman: "steelman",
    reasoningEmpty: "(no reasoning provided)",
    metadata: "Metadata",
  },
  fr: {
    title: "Afficher le travail",
    subtitle: "Trace du pipeline pour cette réponse",
    sectionStages: "Étapes du pipeline",
    sectionRetrieval: "Audit de récupération",
    sectionSources: "Sources et scores du reranker",
    sectionIrac: "Structure IRAC",
    sectionVerifier: "Vérificateur",
    sectionJudge: "Juge de raisonnement profond",
    close: "Fermer",
    empty: "Ce message n'a pas encore de trace — lancez d'abord une requête.",
    statusSuccess: "succès",
    statusFailed: "échec",
    statusSkipped: "ignoré",
    fusionMethod: "Méthode de fusion",
    queries: "Requêtes",
    pool: "Vivier de candidats",
    final: "Résultats finaux",
    hyde: "HyDE",
    multiQuery: "Multi-requête",
    on: "actif",
    off: "inactif",
    score: "score",
    grounded: "Fondé",
    partial: "Partiel",
    refused: "Refusé",
    issue: "Risques / question",
    rule: "Droit applicable",
    application: "Analyse juridique",
    missing: "Faits manquants",
    counsel: "Note du conseil",
    chosen: "Choisi",
    primary: "principal",
    steelman: "contre-position",
    reasoningEmpty: "(aucun raisonnement fourni)",
    metadata: "Métadonnées",
  },
  de: {
    title: "Arbeit anzeigen",
    subtitle: "Pipeline-Trace dieser Antwort",
    sectionStages: "Pipeline-Schritte",
    sectionRetrieval: "Retrieval-Audit",
    sectionSources: "Quellen & Reranker-Scores",
    sectionIrac: "IRAC-Struktur",
    sectionVerifier: "Prüfer",
    sectionJudge: "Deep-Reasoning-Richter",
    close: "Schließen",
    empty: "Diese Nachricht hat noch keine Trace-Daten.",
    statusSuccess: "Erfolg",
    statusFailed: "Fehlgeschlagen",
    statusSkipped: "Übersprungen",
    fusionMethod: "Fusionsmethode",
    queries: "Anfragen",
    pool: "Kandidatenpool",
    final: "Endergebnisse",
    hyde: "HyDE",
    multiQuery: "Multi-Query",
    on: "an",
    off: "aus",
    score: "Score",
    grounded: "Belegt",
    partial: "Teilweise",
    refused: "Abgelehnt",
    issue: "Fallrisiken",
    rule: "Anwendbares Recht",
    application: "Rechtliche Bewertung",
    missing: "Fehlende Fakten",
    counsel: "Anwaltshinweis",
    chosen: "Gewählt",
    primary: "primär",
    steelman: "Steelman",
    reasoningEmpty: "(keine Begründung)",
    metadata: "Metadaten",
  },
  ar: {
    title: "أظهر عملك",
    subtitle: "أثر خط المعالجة لهذه الإجابة",
    sectionStages: "مراحل خط المعالجة",
    sectionRetrieval: "مراجعة الاسترجاع",
    sectionSources: "المصادر ودرجات إعادة الترتيب",
    sectionIrac: "بنية IRAC",
    sectionVerifier: "المحقق",
    sectionJudge: "حكم الاستدلال العميق",
    close: "إغلاق",
    empty: "لا توجد بيانات أثر لهذه الرسالة بعد.",
    statusSuccess: "نجاح",
    statusFailed: "فشل",
    statusSkipped: "تم التخطي",
    fusionMethod: "طريقة الدمج",
    queries: "الاستفسارات",
    pool: "بركة المرشحين",
    final: "النتائج النهائية",
    hyde: "HyDE",
    multiQuery: "تعدد الاستفسارات",
    on: "مفعّل",
    off: "معطّل",
    score: "درجة",
    grounded: "مدعّم",
    partial: "جزئي",
    refused: "مرفوض",
    issue: "مخاطر القضية",
    rule: "القانون المطبَّق",
    application: "التقييم القانوني",
    missing: "الوقائع الناقصة",
    counsel: "ملاحظة المستشار",
    chosen: "المختار",
    primary: "أساسي",
    steelman: "موقف مضاد",
    reasoningEmpty: "(لا يوجد استدلال)",
    metadata: "البيانات الوصفية",
  },
};

function ExecutionTracePanelImpl({ message, language, onClose }: ExecutionTracePanelProps) {
  const t = COPY[language] ?? COPY.en;
  const [expandedStage, setExpandedStage] = useState<number | null>(null);

  if (!message) return null;
  const meta = message.meta ?? {};
  const stages = (Array.isArray(meta.executionTrace) ? meta.executionTrace : []) as StageRecord[];
  const retrieval = meta.retrievalAudit ?? null;
  const sources = Array.isArray(meta.sources) ? meta.sources : [];
  const irac = meta.irac ?? null;
  const verificationState = meta.verificationState ?? null;
  const verificationReason = meta.verificationReason ?? null;
  const judge = meta.judge ?? null;
  const candidates = meta.candidates ?? null;

  const hasAny =
    stages.length > 0 || retrieval || sources.length > 0 || irac ||
    verificationState || judge;

  const stateLabel = (s: string | null | undefined) =>
    s === "grounded" ? t.grounded : s === "partial" ? t.partial : s === "refused" ? t.refused : "";

  const statusLabel = (s: string | undefined) =>
    s === "success" ? t.statusSuccess : s === "failed" ? t.statusFailed : s === "skipped" ? t.statusSkipped : (s ?? "");

  return (
    <aside className="trace-panel" role="complementary" aria-label={t.title}>
      <header className="trace-panel-header">
        <div>
          <h3>{t.title}</h3>
          <p className="trace-panel-subtitle">{t.subtitle}</p>
        </div>
        <button type="button" className="trace-panel-close" onClick={onClose} aria-label={t.close}>
          ×
        </button>
      </header>

      <div className="trace-panel-body">
        {!hasAny ? <p className="trace-panel-empty">{t.empty}</p> : null}

        {stages.length > 0 ? (
          <section className="trace-panel-section">
            <h4>{t.sectionStages}</h4>
            <ol className="trace-panel-timeline">
              {stages.map((stage, idx) => {
                const isOpen = expandedStage === idx;
                const status = String(stage.status ?? "");
                return (
                  <li key={idx} className={`trace-panel-stage status-${status || "unknown"}`}>
                    <button
                      type="button"
                      className="trace-panel-stage-toggle"
                      onClick={() => setExpandedStage(isOpen ? null : idx)}
                    >
                      <span className="trace-panel-stage-name">{stage.name ?? `stage-${idx}`}</span>
                      <span className={`trace-panel-stage-status status-${status || "unknown"}`}>
                        {statusLabel(status)}
                      </span>
                    </button>
                    {stage.detail ? (
                      <p className="trace-panel-stage-detail">{stage.detail}</p>
                    ) : null}
                    {isOpen && stage.metadata && Object.keys(stage.metadata).length > 0 ? (
                      <pre className="trace-panel-metadata" aria-label={t.metadata}>
                        {JSON.stringify(stage.metadata, null, 2)}
                      </pre>
                    ) : null}
                  </li>
                );
              })}
            </ol>
          </section>
        ) : null}

        {retrieval ? (
          <section className="trace-panel-section">
            <h4>{t.sectionRetrieval}</h4>
            <ul className="trace-panel-kv">
              <li>
                <strong>{t.fusionMethod}:</strong> {retrieval.fusion_method ?? "—"}
              </li>
              <li>
                <strong>{t.queries}:</strong> {(retrieval.queries ?? []).length}
              </li>
              <li>
                <strong>{t.pool}:</strong> {retrieval.candidate_pool_size ?? 0}
                {" · "}
                <strong>{t.final}:</strong> {retrieval.final_count ?? 0}
              </li>
              <li>
                <strong>{t.hyde}:</strong> {retrieval.used_hyde ? t.on : t.off}
                {" · "}
                <strong>{t.multiQuery}:</strong> {retrieval.used_multi_query ? t.on : t.off}
              </li>
            </ul>
            {Array.isArray(retrieval.queries) && retrieval.queries.length > 0 ? (
              <ol className="trace-panel-queries">
                {retrieval.queries.map((q, qi) => (
                  <li key={qi}>{q}</li>
                ))}
              </ol>
            ) : null}
          </section>
        ) : null}

        {sources.length > 0 ? (
          <section className="trace-panel-section">
            <h4>{t.sectionSources}</h4>
            <ul className="trace-panel-sources">
              {sources.slice(0, 8).map((src, si) => (
                <li key={si}>
                  <span className="trace-source-name">{src.filename || `Source ${si + 1}`}</span>
                  <span className="trace-source-score">
                    {t.score}: {Number(src.score ?? 0).toFixed(3)}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {irac ? (
          <section className="trace-panel-section">
            <h4>{t.sectionIrac}</h4>
            <div className="trace-panel-irac">
              {irac.case_risks ? (
                <details>
                  <summary>{t.issue}</summary>
                  <p>{irac.case_risks}</p>
                </details>
              ) : null}
              {Array.isArray(irac.applicable_law) && irac.applicable_law.length > 0 ? (
                <details>
                  <summary>{t.rule}</summary>
                  <ul>
                    {irac.applicable_law.map((law, li) => (
                      <li key={li}>
                        <strong>{law.reference}</strong>
                        {law.code_family ? ` (${law.code_family})` : ""}
                        {" — "}
                        {law.summary}
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
              {irac.legal_assessment ? (
                <details>
                  <summary>{t.application}</summary>
                  <p>{irac.legal_assessment}</p>
                </details>
              ) : null}
              {Array.isArray(irac.missing_facts) && irac.missing_facts.length > 0 ? (
                <details>
                  <summary>{t.missing}</summary>
                  <ul>
                    {irac.missing_facts.map((fact, fi) => (
                      <li key={fi}>{fact}</li>
                    ))}
                  </ul>
                </details>
              ) : null}
              {irac.counsel_note ? (
                <details>
                  <summary>{t.counsel}</summary>
                  <p>{irac.counsel_note}</p>
                </details>
              ) : null}
            </div>
          </section>
        ) : null}

        {verificationState ? (
          <section className="trace-panel-section">
            <h4>{t.sectionVerifier}</h4>
            <p>
              <span className={`trace-state-pill state-${verificationState}`}>
                {stateLabel(verificationState)}
              </span>
              {verificationReason ? <span className="trace-state-reason">{verificationReason}</span> : null}
            </p>
          </section>
        ) : null}

        {judge ? (
          <section className="trace-panel-section">
            <h4>{t.sectionJudge}</h4>
            {judge.chosen ? (
              <p>
                <strong>{t.chosen}:</strong>{" "}
                <span className="trace-judge-pill">{String(judge.chosen).toUpperCase()}</span>
              </p>
            ) : null}
            <p className="trace-judge-reasoning">{judge.reasoning || t.reasoningEmpty}</p>
            {judge.scores ? (
              <div className="trace-judge-scores">
                {Object.entries(judge.scores).map(([k, v]) =>
                  typeof v === "number" ? (
                    <span key={k} className="trace-score-chip">
                      <strong>{k}</strong>: {Math.round(v * 100)}%
                    </span>
                  ) : null
                )}
              </div>
            ) : null}
            {Array.isArray(candidates) && candidates.length > 0 ? (
              <div className="trace-candidates">
                {candidates.map((c) => (
                  <article key={c.id} className={`trace-candidate candidate-${c.id}`}>
                    <header>
                      <strong>{c.id}</strong>
                      <em>{c.persona === "steelman" ? t.steelman : t.primary}</em>
                    </header>
                    <pre>{c.text}</pre>
                  </article>
                ))}
              </div>
            ) : null}
          </section>
        ) : null}
      </div>
    </aside>
  );
}

export const ExecutionTracePanel = memo(ExecutionTracePanelImpl);
export default ExecutionTracePanel;
