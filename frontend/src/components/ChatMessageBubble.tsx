import { memo, useMemo } from "react";
import type { ChatMessage } from "../types";

type FeedbackValue = "up" | "down";
type FeedbackStatus = "idle" | "saving" | "submitted" | "error";
type UiLanguage = "en" | "de" | "ar";

export interface MessageFeedbackState {
  value: FeedbackValue | null;
  status: FeedbackStatus;
}

interface ChatMessageBubbleProps {
  language: UiLanguage;
  message: ChatMessage;
  feedback: MessageFeedbackState | undefined;
  onCopy: (message: ChatMessage) => void;
  onRegenerate: (message: ChatMessage) => void;
  onFeedback: (message: ChatMessage, value: FeedbackValue) => void;
}

interface MessageSection {
  title: string;
  paragraphs: string[];
  bullets: string[];
}

type TagKey = "highRisk" | "mediumRisk" | "deadline" | "contradiction" | "missingInfo" | "legalSource";

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
  },
};

const KEYWORD_PATTERN = /\b(risk|deadline|urgent|liability|evidence|article|section|compliance|penalty)\b/gi;

function formatMessageTime(value: string, language: UiLanguage): string {
  const locale = language === "de" ? "de-DE" : language === "ar" ? "ar-TN" : "en-US";
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

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) continue;

    const bracketHeader = line.match(/^\[(.+?)\]$/);
    const colonHeader = line.match(/^([A-Za-z][A-Za-z ]{2,32}):$/);
    const inlineHeader = line.match(/^([A-Za-z][A-Za-z ]{2,32}):\s+(.+)$/);
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

    if (line.startsWith("- ") || line.startsWith("* ")) {
      current.bullets.push(line.slice(2).trim());
      continue;
    }

    const numberedBullet = line.match(/^\d+\.\s+(.+)/);
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

function ChatMessageBubbleComponent(props: ChatMessageBubbleProps) {
  const { language, message, feedback, onCopy, onRegenerate, onFeedback } = props;
  const copy = BUBBLE_TEXT[language] || BUBBLE_TEXT.en;
  const tb = (key: string, fallback: string) => copy[key] || BUBBLE_TEXT.en[key] || fallback;
  const sections = useMemo(() => parseSections(message.content, tb("sectionResponse", "Response")), [message.content, language]);
  const tags = useMemo(() => extractTags(message.content), [message.content]);
  const sourceCount = message.meta?.sources?.length ?? 0;
  const citationCount = message.meta?.citations?.length ?? 0;
  const confidence = message.meta?.confidence;
  const cache = message.meta?.cache;
  const isStreaming =
    message.role === "assistant" &&
    typeof message.meta?.rawAnswer === "string" &&
    message.meta.rawAnswer.length > 0 &&
    message.content !== message.meta.rawAnswer;
  const canShowActions = message.role === "assistant" && !isStreaming;

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
                  {highlightKeywords(paragraph).map((token, tokenIndex) =>
                    typeof token === "string" ? (
                      <span key={`${paragraphIndex}-txt-${tokenIndex}`}>{token}</span>
                    ) : (
                      <mark key={`${paragraphIndex}-key-${tokenIndex}`}>{token.keyword}</mark>
                    )
                  )}
                </p>
              ))}

              {section.bullets.length ? (
                <ul>
                  {section.bullets.map((bullet, bulletIndex) => (
                    <li key={`${section.title}-b-${bulletIndex}`}>
                      {highlightKeywords(bullet).map((token, tokenIndex) =>
                        typeof token === "string" ? (
                          <span key={`${bulletIndex}-txt-${tokenIndex}`}>{token}</span>
                        ) : (
                          <mark key={`${bulletIndex}-key-${tokenIndex}`}>{token.keyword}</mark>
                        )
                      )}
                    </li>
                  ))}
                </ul>
              ) : null}
            </section>
          ))}
        </div>

        {canShowActions && message.meta?.citations?.length ? (
          <div className="assistant-sections">
            <section className="assistant-section">
              <h4>Citations</h4>
              <ul className="citation-list">
                {message.meta.citations.slice(0, 5).map((citation) => (
                  <li key={`${citation.label}-${citation.snippet}`} className="citation-item">
                    <strong>{citation.label}</strong>
                    <span> {citation.snippet}</span>
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
                onClick={() => onFeedback(message, "up")}
              >
                👍
              </button>
              <button
                className={feedback?.value === "down" ? "active" : ""}
                disabled={feedback?.status === "saving"}
                type="button"
                onClick={() => onFeedback(message, "down")}
              >
                👎
              </button>
            </div>
            <div className="assistant-actions-state" aria-live="polite">
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
