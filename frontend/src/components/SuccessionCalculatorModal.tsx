import { useMemo, useState } from "react";
import { workspaceApi } from "../workspaceApi";
import type { SuccessionCalculateRequest, SuccessionCalculateResponse } from "../types";

type UiLanguage = "en" | "fr" | "de" | "ar";

interface SuccessionCalculatorModalProps {
  token: string;
  language: UiLanguage;
  onClose: () => void;
}

interface SuccessionCopy {
  kicker: string;
  title: string;
  spouseKind: string;
  husband: string;
  wife: string;
  none: string;
  sons: string;
  daughters: string;
  fatherAlive: string;
  motherAlive: string;
  showSiblings: string;
  fullBrothers: string;
  fullSisters: string;
  paternalBrothers: string;
  paternalSisters: string;
  maternalSiblings: string;
  estate: string;
  estatePlaceholder: string;
  submit: string;
  cancel: string;
  resultsTitle: string;
  heir: string;
  share: string;
  percent: string;
  amount: string;
  articles: string;
  awlNotice: string;
  raddNotice: string;
  citationsTitle: string;
  submitting: string;
  error: string;
  notesTitle: string;
  disclaimer: string;
  heirNames: Record<string, string>;
}

const COPY: Record<UiLanguage, SuccessionCopy> = {
  en: {
    kicker: "Tunisia · Code de Statut Personnel",
    title: "Succession entitlement calculator",
    spouseKind: "Spouse",
    husband: "Surviving husband",
    wife: "Surviving wife",
    none: "None",
    sons: "Sons",
    daughters: "Daughters",
    fatherAlive: "Father alive",
    motherAlive: "Mother alive",
    showSiblings: "Show siblings",
    fullBrothers: "Full brothers",
    fullSisters: "Full sisters",
    paternalBrothers: "Paternal half-brothers",
    paternalSisters: "Paternal half-sisters",
    maternalSiblings: "Uterine siblings",
    estate: "Estate value (TND, optional)",
    estatePlaceholder: "e.g. 120000",
    submit: "Compute shares",
    cancel: "Close",
    resultsTitle: "Heir entitlements",
    heir: "Heir",
    share: "Share",
    percent: "%",
    amount: "Amount (TND)",
    articles: "Articles",
    awlNotice: "ʿAwl applied — fardh sum exceeded 1, all shares scaled proportionally.",
    raddNotice: "Radd applied — residue returned to fardh heirs (spouse excluded).",
    citationsTitle: "Citations (CSP arts 85–152)",
    submitting: "Computing…",
    error: "The calculation failed. Please verify the inputs and try again.",
    notesTitle: "Notes",
    disclaimer: "Counsel must verify the official article wording before relying on this output. The calculator covers the standard Sunni / Maliki rules codified in the CSP.",
    heirNames: {
      husband: "Husband",
      wife: "Wife",
      father: "Father",
      mother: "Mother",
      son: "Son",
      daughter: "Daughter",
      full_brother: "Full brother",
      full_sister: "Full sister",
      paternal_brother: "Paternal half-brother",
      paternal_sister: "Paternal half-sister",
      maternal_sibling: "Uterine sibling",
    },
  },
  fr: {
    kicker: "Tunisie · Code de Statut Personnel",
    title: "Calculateur d'entitlement successoral",
    spouseKind: "Conjoint",
    husband: "Mari survivant",
    wife: "Épouse survivante",
    none: "Aucun",
    sons: "Fils",
    daughters: "Filles",
    fatherAlive: "Père vivant",
    motherAlive: "Mère vivante",
    showSiblings: "Afficher les frères et sœurs",
    fullBrothers: "Frères germains",
    fullSisters: "Sœurs germaines",
    paternalBrothers: "Demi-frères consanguins",
    paternalSisters: "Demi-sœurs consanguines",
    maternalSiblings: "Frères/sœurs utérins",
    estate: "Valeur de la succession (TND, facultatif)",
    estatePlaceholder: "ex. 120000",
    submit: "Calculer les parts",
    cancel: "Fermer",
    resultsTitle: "Parts des héritiers",
    heir: "Héritier",
    share: "Part",
    percent: "%",
    amount: "Montant (TND)",
    articles: "Articles",
    awlNotice: "ʿAwl appliqué — la somme des fardh dépassait 1, parts réduites proportionnellement.",
    raddNotice: "Radd appliqué — résidu restitué aux héritiers réservataires (conjoint exclu).",
    citationsTitle: "Citations (arts 85–152 du CSP)",
    submitting: "Calcul…",
    error: "Le calcul a échoué. Vérifiez les données et réessayez.",
    notesTitle: "Notes",
    disclaimer: "Le conseil doit vérifier le libellé officiel des articles avant de se fier à ce résultat. Le calculateur couvre les règles sunnites / malékites codifiées dans le CSP.",
    heirNames: {
      husband: "Mari",
      wife: "Épouse",
      father: "Père",
      mother: "Mère",
      son: "Fils",
      daughter: "Fille",
      full_brother: "Frère germain",
      full_sister: "Sœur germaine",
      paternal_brother: "Demi-frère consanguin",
      paternal_sister: "Demi-sœur consanguine",
      maternal_sibling: "Frère/sœur utérin",
    },
  },
  de: {
    kicker: "Tunesien · Code de Statut Personnel",
    title: "Erbteilungsrechner",
    spouseKind: "Ehegatte",
    husband: "Ehemann",
    wife: "Ehefrau",
    none: "Keiner",
    sons: "Söhne",
    daughters: "Töchter",
    fatherAlive: "Vater lebt",
    motherAlive: "Mutter lebt",
    showSiblings: "Geschwister anzeigen",
    fullBrothers: "Vollbrüder",
    fullSisters: "Vollschwestern",
    paternalBrothers: "Halbbrüder väterlicherseits",
    paternalSisters: "Halbschwestern väterlicherseits",
    maternalSiblings: "Halbgeschwister mütterlicherseits",
    estate: "Nachlasswert (TND, optional)",
    estatePlaceholder: "z. B. 120000",
    submit: "Anteile berechnen",
    cancel: "Schließen",
    resultsTitle: "Erbteile",
    heir: "Erbe",
    share: "Anteil",
    percent: "%",
    amount: "Betrag (TND)",
    articles: "Artikel",
    awlNotice: "ʿAwl angewandt — Fardh-Summe > 1, Anteile proportional reduziert.",
    raddNotice: "Radd angewandt — Rest an Fardh-Erben zurückgegeben (ohne Ehegatten).",
    citationsTitle: "Zitate (CSP-Artikel 85–152)",
    submitting: "Berechne…",
    error: "Berechnung fehlgeschlagen. Eingaben prüfen und erneut versuchen.",
    notesTitle: "Hinweise",
    disclaimer: "Der Anwalt muss den offiziellen Artikelwortlaut prüfen, bevor er sich auf dieses Ergebnis verlässt.",
    heirNames: {
      husband: "Ehemann",
      wife: "Ehefrau",
      father: "Vater",
      mother: "Mutter",
      son: "Sohn",
      daughter: "Tochter",
      full_brother: "Vollbruder",
      full_sister: "Vollschwester",
      paternal_brother: "Halbbruder",
      paternal_sister: "Halbschwester",
      maternal_sibling: "Halbgeschwister",
    },
  },
  ar: {
    kicker: "تونس · مجلة الأحوال الشخصية",
    title: "حاسبة الأنصبة الإرثية",
    spouseKind: "الزوج/الزوجة",
    husband: "الزوج",
    wife: "الزوجة",
    none: "لا أحد",
    sons: "الأبناء",
    daughters: "البنات",
    fatherAlive: "الأب على قيد الحياة",
    motherAlive: "الأم على قيد الحياة",
    showSiblings: "إظهار الإخوة والأخوات",
    fullBrothers: "إخوة أشقاء",
    fullSisters: "أخوات شقيقات",
    paternalBrothers: "إخوة لأب",
    paternalSisters: "أخوات لأب",
    maternalSiblings: "إخوة لأم",
    estate: "قيمة التركة (د.ت، اختياري)",
    estatePlaceholder: "مثال: 120000",
    submit: "احسب الأنصبة",
    cancel: "إغلاق",
    resultsTitle: "أنصبة الورثة",
    heir: "الوارث",
    share: "النصيب",
    percent: "%",
    amount: "المبلغ (د.ت)",
    articles: "المواد",
    awlNotice: "تطبيق العول — مجموع الفروض تجاوز الواحد، تم تخفيض الأنصبة بالتناسب.",
    raddNotice: "تطبيق الردّ — الباقي يردّ إلى أصحاب الفروض (ما عدا الزوج/الزوجة).",
    citationsTitle: "المواد المرجعية (مجلة الأحوال الشخصية 85–152)",
    submitting: "جاري الحساب…",
    error: "فشل الحساب. تحقق من المدخلات وحاول مرة أخرى.",
    notesTitle: "ملاحظات",
    disclaimer: "يجب على المحامي التحقق من النص الرسمي للمواد قبل الاعتماد على هذه النتيجة.",
    heirNames: {
      husband: "الزوج",
      wife: "الزوجة",
      father: "الأب",
      mother: "الأم",
      son: "ابن",
      daughter: "بنت",
      full_brother: "أخ شقيق",
      full_sister: "أخت شقيقة",
      paternal_brother: "أخ لأب",
      paternal_sister: "أخت لأب",
      maternal_sibling: "أخ/أخت لأم",
    },
  },
};

function heirDisplayName(heirCode: string, t: SuccessionCopy): string {
  // Strip trailing _<digit> suffix the calculator adds for multiple
  // children: "son_1" → "son" (ordinal), "father" → "father".
  const match = /^([a-z_]+?)(?:_(\d+))?$/.exec(heirCode);
  const base = match?.[1] ?? heirCode;
  const ordinal = match?.[2];
  const label = t.heirNames[base] ?? heirCode;
  return ordinal ? `${label} ${ordinal}` : label;
}

export default function SuccessionCalculatorModal({
  token, language, onClose,
}: SuccessionCalculatorModalProps) {
  const t = COPY[language] ?? COPY.en;
  const [request, setRequest] = useState<SuccessionCalculateRequest>({
    spouse_kind: "wife",
    sons: 0,
    daughters: 0,
    father_alive: false,
    mother_alive: false,
    full_brothers: 0,
    full_sisters: 0,
    paternal_brothers: 0,
    paternal_sisters: 0,
    maternal_siblings: 0,
    estate_value_tnd: null,
  });
  const [showSiblings, setShowSiblings] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SuccessionCalculateResponse | null>(null);

  const update = <K extends keyof SuccessionCalculateRequest>(key: K, value: SuccessionCalculateRequest[K]) =>
    setRequest((prev) => ({ ...prev, [key]: value }));

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await workspaceApi.calculateSuccession(token, request);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.error);
    } finally {
      setSubmitting(false);
    }
  };

  const totalAmount = useMemo(() => {
    if (!result || request.estate_value_tnd == null) return null;
    return result.heirs.reduce((acc, h) => acc + (h.share_amount_tnd ?? 0), 0);
  }, [result, request.estate_value_tnd]);

  return (
    <div className="calendar-modal-backdrop" role="presentation" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="calendar-event-modal succession-modal" role="dialog" aria-modal="true" aria-label={t.title}>
        <div className="calendar-modal-head">
          <div>
            <p className="shell-page-kicker">{t.kicker}</p>
            <h3>{t.title}</h3>
          </div>
          <button onClick={onClose} type="button" aria-label={t.cancel}>×</button>
        </div>

        <div className="succession-grid">
          <label className="editor-field">
            <span>{t.spouseKind}</span>
            <select
              value={request.spouse_kind}
              onChange={(e) => update("spouse_kind", e.target.value as "husband" | "wife" | "none")}
            >
              <option value="none">{t.none}</option>
              <option value="husband">{t.husband}</option>
              <option value="wife">{t.wife}</option>
            </select>
          </label>

          <label className="editor-field">
            <span>{t.sons}</span>
            <input
              type="number" min={0} max={20}
              value={request.sons}
              onChange={(e) => update("sons", Math.max(0, Math.min(20, Number(e.target.value) || 0)))}
            />
          </label>

          <label className="editor-field">
            <span>{t.daughters}</span>
            <input
              type="number" min={0} max={20}
              value={request.daughters}
              onChange={(e) => update("daughters", Math.max(0, Math.min(20, Number(e.target.value) || 0)))}
            />
          </label>

          <label className="editor-field editor-field-checkbox">
            <input
              type="checkbox"
              checked={request.father_alive}
              onChange={(e) => update("father_alive", e.target.checked)}
            />
            <span>{t.fatherAlive}</span>
          </label>

          <label className="editor-field editor-field-checkbox">
            <input
              type="checkbox"
              checked={request.mother_alive}
              onChange={(e) => update("mother_alive", e.target.checked)}
            />
            <span>{t.motherAlive}</span>
          </label>

          <label className="editor-field succession-estate">
            <span>{t.estate}</span>
            <input
              type="number" min={0} step={0.01}
              placeholder={t.estatePlaceholder}
              value={request.estate_value_tnd ?? ""}
              onChange={(e) => {
                const raw = e.target.value;
                update("estate_value_tnd", raw === "" ? null : Math.max(0, Number(raw)));
              }}
            />
          </label>
        </div>

        <button
          type="button"
          className="succession-toggle-siblings"
          onClick={() => setShowSiblings((v) => !v)}
        >
          {t.showSiblings} {showSiblings ? "▴" : "▾"}
        </button>

        {showSiblings ? (
          <div className="succession-grid succession-siblings-grid">
            {([
              ["full_brothers", t.fullBrothers],
              ["full_sisters", t.fullSisters],
              ["paternal_brothers", t.paternalBrothers],
              ["paternal_sisters", t.paternalSisters],
              ["maternal_siblings", t.maternalSiblings],
            ] as const).map(([key, label]) => (
              <label key={key} className="editor-field">
                <span>{label}</span>
                <input
                  type="number" min={0} max={20}
                  value={request[key] as number}
                  onChange={(e) =>
                    update(key as keyof SuccessionCalculateRequest, Math.max(0, Math.min(20, Number(e.target.value) || 0)) as SuccessionCalculateRequest[typeof key])
                  }
                />
              </label>
            ))}
          </div>
        ) : null}

        <div className="succession-modal-actions">
          <button type="button" className="primary" onClick={submit} disabled={submitting}>
            {submitting ? t.submitting : t.submit}
          </button>
          <button type="button" onClick={onClose}>{t.cancel}</button>
        </div>

        {error ? <p className="succession-error">{error}</p> : null}

        {result ? (
          <section className="succession-results">
            <h4>{t.resultsTitle}</h4>
            {result.awl_applied ? <p className="succession-notice succession-notice-awl">{t.awlNotice}</p> : null}
            {result.radd_applied ? <p className="succession-notice succession-notice-radd">{t.raddNotice}</p> : null}

            <table className="succession-table">
              <thead>
                <tr>
                  <th>{t.heir}</th>
                  <th>{t.share}</th>
                  <th>{t.percent}</th>
                  {request.estate_value_tnd != null ? <th>{t.amount}</th> : null}
                  <th>{t.articles}</th>
                </tr>
              </thead>
              <tbody>
                {result.heirs.map((h) => (
                  <tr key={h.heir}>
                    <td>{heirDisplayName(h.heir, t)}</td>
                    <td><code>{h.share_fraction}</code></td>
                    <td>{h.share_percent.toFixed(2)}%</td>
                    {request.estate_value_tnd != null ? (
                      <td>{(h.share_amount_tnd ?? 0).toLocaleString()}</td>
                    ) : null}
                    <td>{h.article_refs.join(", ")}</td>
                  </tr>
                ))}
                {totalAmount != null ? (
                  <tr className="succession-total">
                    <td>—</td>
                    <td><code>{result.total_distributed}</code></td>
                    <td>{result.total_percent.toFixed(2)}%</td>
                    <td>{totalAmount.toLocaleString()}</td>
                    <td>—</td>
                  </tr>
                ) : null}
              </tbody>
            </table>

            {result.notes.length > 0 ? (
              <div className="succession-notes">
                <h5>{t.notesTitle}</h5>
                <ul>
                  {result.notes.map((note, ni) => (<li key={ni}>{note}</li>))}
                </ul>
              </div>
            ) : null}

            {result.citations.length > 0 ? (
              <div className="succession-citations">
                <h5>{t.citationsTitle}</h5>
                <ul>
                  {result.citations.map((c) => (
                    <li key={c.article}>
                      <strong>{c.article}</strong> — {c.summary}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <p className="succession-disclaimer">{t.disclaimer}</p>
          </section>
        ) : null}
      </div>
    </div>
  );
}
