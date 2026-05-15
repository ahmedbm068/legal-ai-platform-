import { memo, useState } from "react";
import type { ChatMessage } from "../types";

type UiLanguage = "en" | "fr" | "de" | "ar";

interface TrustDrawerProps {
  message: ChatMessage;
  language: UiLanguage;
}

const COPY: Record<UiLanguage, Record<string, string>> = {
  en: {
    title: "Trust details",
    verifier: "Verifier verdict",
    judge: "Deep-reasoning judge",
    faithfulness: "Per-claim faithfulness",
    missingFacts: "Missing facts to verify",
    citationChecklist: "Before you rely on this",
    retrieval: "Retrieval audit",
    open: "Show trust details",
    close: "Hide trust details",
    grounded: "Grounded",
    partial: "Partial",
    refused: "Refused",
    chosen: "Chosen",
    candidate: "Candidate",
    primary: "primary",
    steelman: "steelman counter-position",
    none: "None flagged",
    faithfulnessSkipped: "Faithfulness scoring skipped — no grounded claims to score.",
    verifyArticle: "Verify the article number against the official text",
    verifyQuotation: "Verify the quoted rule wording matches the source",
    verifyDate: "Verify the statute is current at the relevant date",
    verifyJurisdiction: "Verify the jurisdiction matches your matter",
  },
  fr: {
    title: "Détails de confiance",
    verifier: "Verdict du vérificateur",
    judge: "Juge de raisonnement profond",
    faithfulness: "Fidélité par revendication",
    missingFacts: "Faits manquants à vérifier",
    citationChecklist: "Avant de vous y fier",
    retrieval: "Audit de récupération",
    open: "Afficher les détails de confiance",
    close: "Masquer les détails de confiance",
    grounded: "Fondé",
    partial: "Partiel",
    refused: "Refusé",
    chosen: "Choisi",
    candidate: "Candidat",
    primary: "principal",
    steelman: "contre-position renforcée",
    none: "Aucun signalé",
    faithfulnessSkipped: "Notation de fidélité ignorée — aucune revendication fondée à évaluer.",
    verifyArticle: "Vérifier le numéro d’article dans le texte officiel",
    verifyQuotation: "Vérifier que la formulation citée correspond à la source",
    verifyDate: "Vérifier que le texte est en vigueur à la date concernée",
    verifyJurisdiction: "Vérifier que la juridiction correspond à votre dossier",
  },
  de: {
    title: "Vertrauensdetails",
    verifier: "Prüfer-Urteil",
    judge: "Deep-Reasoning-Richter",
    faithfulness: "Treue je Aussage",
    missingFacts: "Fehlende Fakten zur Prüfung",
    citationChecklist: "Bevor Sie sich darauf verlassen",
    retrieval: "Retrieval-Audit",
    open: "Vertrauensdetails anzeigen",
    close: "Vertrauensdetails ausblenden",
    grounded: "Belegt",
    partial: "Teilweise",
    refused: "Abgelehnt",
    chosen: "Gewählt",
    candidate: "Kandidat",
    primary: "primär",
    steelman: "Steelman-Gegenposition",
    none: "Keine markiert",
    faithfulnessSkipped: "Treue-Bewertung übersprungen — keine fundierten Aussagen.",
    verifyArticle: "Artikelnummer mit dem amtlichen Text abgleichen",
    verifyQuotation: "Wortlaut der zitierten Regel mit der Quelle abgleichen",
    verifyDate: "Geltungsdatum des Gesetzestextes prüfen",
    verifyJurisdiction: "Gerichtsbarkeit prüfen",
  },
  ar: {
    title: "تفاصيل الثقة",
    verifier: "حكم المحقق",
    judge: "حكم الاستدلال العميق",
    faithfulness: "الأمانة لكل ادعاء",
    missingFacts: "وقائع ناقصة يجب التحقق منها",
    citationChecklist: "قبل الاعتماد على هذا",
    retrieval: "مراجعة الاسترجاع",
    open: "عرض تفاصيل الثقة",
    close: "إخفاء تفاصيل الثقة",
    grounded: "مدعّم",
    partial: "جزئي",
    refused: "مرفوض",
    chosen: "مختار",
    candidate: "مرشح",
    primary: "أساسي",
    steelman: "موقف مضاد مدعّم",
    none: "لا شيء",
    faithfulnessSkipped: "تم تخطّي تقييم الأمانة — لا توجد ادعاءات مدعّمة لتقييمها.",
    verifyArticle: "تحقق من رقم المادة في النص الرسمي",
    verifyQuotation: "تحقق من تطابق الاقتباس مع المصدر",
    verifyDate: "تحقق من سريان النص في التاريخ المعني",
    verifyJurisdiction: "تحقق من مطابقة الاختصاص القضائي",
  },
};

function TrustDrawerImpl({ message, language }: TrustDrawerProps) {
  const t = COPY[language] ?? COPY.en;
  const meta = message.meta;
  const [open, setOpen] = useState(false);

  if (!meta) return null;

  const verificationState = meta.verificationState ?? null;
  const verificationReason = meta.verificationReason ?? null;
  const judge = meta.judge ?? null;
  const candidates = meta.candidates ?? null;
  const faithfulness = meta.faithfulness ?? null;
  const missingFacts = meta.irac?.missing_facts ?? [];
  const sources = meta.sources ?? [];
  const retrievalAudit = meta.retrievalAudit ?? null;

  const hasVerifier = Boolean(verificationState || verificationReason);
  const hasJudge = Boolean(judge && (judge.chosen || judge.reasoning || judge.scores));
  // Faithfulness is only meaningful when the answer was actually grounded — on
  // verifier refusal or when scoring was skipped, the only "claim" is the
  // refusal disclaimer itself, which scores ~0 and misleads the reader.
  const faithfulnessSkippedReason = faithfulness?.skipped_reason ?? null;
  const isRefusalOrSkipped =
    verificationState === "refused" || Boolean(faithfulnessSkippedReason);
  const hasFaithfulness =
    Boolean(faithfulness && Array.isArray(faithfulness.claims) && faithfulness.claims.length > 0)
    && !isRefusalOrSkipped;
  const showFaithfulnessSkipped = Boolean(faithfulness) && isRefusalOrSkipped;
  const hasMissing = missingFacts.length > 0;
  const hasSources = sources.length > 0;
  const hasRetrieval = Boolean(retrievalAudit);

  if (!hasVerifier && !hasJudge && !hasFaithfulness && !showFaithfulnessSkipped && !hasMissing && !hasSources && !hasRetrieval) {
    return null;
  }

  const stateLabel = (state: string | null | undefined) =>
    state === "grounded" ? t.grounded : state === "partial" ? t.partial : state === "refused" ? t.refused : "";

  return (
    <section className={`trust-drawer trust-drawer-${verificationState ?? "unknown"}`} aria-label={t.title}>
      <button
        type="button"
        className="trust-drawer-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="trust-drawer-toggle-label">{open ? t.close : t.open}</span>
        {verificationState ? (
          <span className={`trust-drawer-state-pill state-${verificationState}`}>
            {stateLabel(verificationState)}
          </span>
        ) : null}
        {hasJudge && judge?.chosen ? (
          <span className="trust-drawer-judge-pill">
            {t.chosen}: {String(judge.chosen).toUpperCase()}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="trust-drawer-body">
          {hasVerifier ? (
            <div className="trust-section trust-section-verifier">
              <h4>{t.verifier}</h4>
              <p>
                <strong>{stateLabel(verificationState)}</strong>
                {verificationReason ? ` — ${verificationReason}` : ""}
              </p>
            </div>
          ) : null}

          {hasJudge ? (
            <div className="trust-section trust-section-judge">
              <h4>{t.judge}</h4>
              {judge?.reasoning ? <p className="trust-judge-reasoning">{judge.reasoning}</p> : null}
              {judge?.scores ? (
                <div className="trust-judge-scores">
                  {Object.entries(judge.scores).map(([k, v]) =>
                    typeof v === "number" ? (
                      <span key={k} className="trust-score-chip">
                        <strong>{k}</strong>: {Math.round((v || 0) * 100)}%
                      </span>
                    ) : null
                  )}
                </div>
              ) : null}
              {Array.isArray(candidates) && candidates.length > 0 ? (
                <div className="trust-candidates-grid">
                  {candidates.map((candidate) => (
                    <article key={candidate.id} className={`trust-candidate-card candidate-${candidate.id}`}>
                      <header>
                        <strong>{t.candidate} {candidate.id}</strong>
                        <em>{candidate.persona === "steelman" ? t.steelman : t.primary}</em>
                      </header>
                      <pre>{candidate.text}</pre>
                    </article>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {hasFaithfulness && faithfulness ? (
            <div className="trust-section trust-section-faithfulness">
              <h4>
                {t.faithfulness}
                <span className="trust-section-headline">
                  {Math.round((faithfulness.score || 0) * 100)}%
                </span>
              </h4>
              <ul className="trust-faithfulness-claims">
                {(faithfulness.claims || []).map((claim, ci) => (
                  <li key={ci} className={`trust-faithfulness-claim ${claim.label}`}>
                    <span className="claim-text">{claim.text}</span>
                    <span className="claim-meta">
                      {claim.label} · {Math.round((claim.best_score || 0) * 100)}%
                      {typeof claim.best_source_index === "number" ? ` · doc:${claim.best_source_index}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : showFaithfulnessSkipped ? (
            <div className="trust-section trust-section-faithfulness trust-section-faithfulness-skipped">
              <h4>{t.faithfulness}</h4>
              <p className="trust-faithfulness-skipped">{t.faithfulnessSkipped}</p>
            </div>
          ) : null}

          {hasMissing ? (
            <div className="trust-section trust-section-missing">
              <h4>{t.missingFacts}</h4>
              <ul className="trust-missing-list">
                {missingFacts.map((fact, fi) => (
                  <li key={fi}>{fact}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {hasSources ? (
            <div className="trust-section trust-section-citations">
              <h4>{t.citationChecklist}</h4>
              <ul className="trust-citation-checklist">
                {sources.slice(0, 6).map((src, si) => {
                  const label = src.filename || `Source ${si + 1}`;
                  return (
                    <li key={si} className="trust-citation-item">
                      <span className="citation-label">{label}</span>
                      <ul>
                        <li>{t.verifyArticle}</li>
                        <li>{t.verifyQuotation}</li>
                        <li>{t.verifyDate}</li>
                        <li>{t.verifyJurisdiction}</li>
                      </ul>
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}

          {hasRetrieval && retrievalAudit ? (
            <div className="trust-section trust-section-retrieval">
              <h4>{t.retrieval}</h4>
              <ul className="trust-retrieval-list">
                <li>fusion: <strong>{retrievalAudit.fusion_method ?? "—"}</strong></li>
                <li>queries: {(retrievalAudit.queries ?? []).length}</li>
                <li>
                  pool: {retrievalAudit.candidate_pool_size ?? 0} · final: {retrievalAudit.final_count ?? 0}
                </li>
                <li>HyDE: {retrievalAudit.used_hyde ? "on" : "off"} · MQ: {retrievalAudit.used_multi_query ? "on" : "off"}</li>
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export const TrustDrawer = memo(TrustDrawerImpl);
export default TrustDrawer;
