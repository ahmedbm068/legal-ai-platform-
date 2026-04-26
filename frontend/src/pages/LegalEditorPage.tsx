import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";
import { loadEditorDraftSeed, type EditorDraftSeed } from "../editorDraftSeed";
import type { CitationItem, SourceItem } from "../types";

type EditorDocumentType = "client_update" | "legal_memo" | "demand_letter" | "strategy_note";
type SectionTrust = "grounded" | "review" | "missing";
type ReviewDecision = "pending" | "approved" | "needs_revision";
type ShareMode = "private" | "internal_review" | "client_review";

type EditorSection = {
    id: string;
    title: string;
    body: string;
    trust: SectionTrust;
    sources: string[];
    citations?: SectionCitation[];
    trustReason?: string;
};

type SectionCitation = {
    label: string;
    snippet?: string | null;
    kind: "case" | "document" | "assistant" | "timeline" | "intake" | "jurisdiction";
};

type EditorTextSelection = {
    sectionId: string;
    start: number;
    end: number;
    text: string;
};

type EditorComment = {
    id: string;
    sectionId: string;
    author: string;
    body: string;
    createdAt: string;
    resolved: boolean;
};

type EditorCollaborationState = {
    shareMode: ShareMode;
    shareNote: string;
    comments: EditorComment[];
};

type EditorVersion = {
    id: string;
    label: string;
    createdAt: string;
    documentType: EditorDocumentType;
    sections: EditorSection[];
    stats: {
        sections: number;
        words: number;
        citations: number;
        grounded: number;
        review: number;
        missing: number;
    };
};

const DOCUMENT_TYPES: Array<{ id: EditorDocumentType; label: string; description: string }> = [
    {
        id: "client_update",
        label: "Client update letter",
        description: "Plain-language status, risks, next steps, and missing items.",
    },
    {
        id: "legal_memo",
        label: "Legal analysis memo",
        description: "Issue, facts, rule, application, risks, and recommendations.",
    },
    {
        id: "demand_letter",
        label: "Demand letter",
        description: "Formal position, breach basis, requested remedy, and deadline.",
    },
    {
        id: "strategy_note",
        label: "Internal strategy note",
        description: "Position strength, proof gaps, negotiation line, and action plan.",
    },
];

function parseCaseId(value?: string) {
    const parsed = Number(value);
    if (!value || Number.isNaN(parsed) || parsed <= 0) {
        return null;
    }
    return parsed;
}

function formatDate(value: string | null | undefined, locale: string, fallback: string) {
    if (!value) return fallback;
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return fallback;
    return new Intl.DateTimeFormat(locale, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    }).format(parsed);
}

function trustLabel(value: SectionTrust) {
    if (value === "grounded") return "Grounded";
    if (value === "review") return "Needs review";
    return "Missing evidence";
}

function makeId(prefix: string) {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
        return `${prefix}-${crypto.randomUUID()}`;
    }
    return `${prefix}-${Date.now()}-${Math.round(Math.random() * 1_000_000)}`;
}

function joinLines(lines: Array<string | null | undefined>) {
    return lines.map((line) => String(line || "").trim()).filter(Boolean).join("\n");
}

function sourceLabelFromSeed(source: SourceItem) {
    return [
        source.filename,
        source.chunk_index !== null && source.chunk_index !== undefined ? `chunk ${source.chunk_index}` : null,
    ].filter(Boolean).join(" | ");
}

function uniqueLabels(labels: string[]) {
    return Array.from(new Set(labels.map((label) => label.trim()).filter(Boolean)));
}

function citationKindFromLabel(label: string): SectionCitation["kind"] {
    const normalized = label.toLowerCase();
    if (normalized.includes("document")) return "document";
    if (normalized.includes("intake")) return "intake";
    if (normalized.includes("appointment") || normalized.includes("voice")) return "timeline";
    if (normalized.includes("jurisdiction")) return "jurisdiction";
    if (normalized.includes("assistant")) return "assistant";
    return "case";
}

function citationsFromSources(sources: string[], snippet?: string | null): SectionCitation[] {
    return uniqueLabels(sources).map((label) => ({
        label,
        snippet,
        kind: citationKindFromLabel(label),
    }));
}

function citationsFromAssistant(citations: CitationItem[] | undefined, fallbackSources: string[]): SectionCitation[] {
    if (citations?.length) {
        return citations.slice(0, 8).map((citation) => ({
            label: citation.label,
            snippet: citation.snippet,
            kind: "assistant",
        }));
    }
    return citationsFromSources(fallbackSources, "Assistant answer did not include a direct citation snippet.");
}

function versionStorageKey(caseId: number) {
    return `legal-ai-editor-version-history:${caseId}`;
}

function collaborationStorageKey(caseId: number) {
    return `legal-ai-editor-collaboration:${caseId}`;
}

function wordCountFromSections(sections: EditorSection[]) {
    return sections.reduce((total, section) => {
        const words = section.body.trim().split(/\s+/).filter(Boolean).length;
        return total + words;
    }, 0);
}

function cloneSections(sections: EditorSection[]) {
    return sections.map((section) => ({
        ...section,
        sources: [...section.sources],
        citations: section.citations?.map((citation) => ({ ...citation })),
    }));
}

function safeFileName(value: string) {
    const normalized = value.trim().replace(/[\\/:*?"<>|]+/g, "-").replace(/\s+/g, "-");
    return normalized || "legal-document";
}

function reviewDecisionLabel(value: ReviewDecision) {
    if (value === "approved") return "Approved";
    if (value === "needs_revision") return "Needs revision";
    return "Pending";
}

function shareModeLabel(value: ShareMode) {
    if (value === "client_review") return "Client review";
    if (value === "internal_review") return "Internal review";
    return "Private draft";
}

export default function LegalEditorPage() {
    const params = useParams();
    const routeCaseId = useMemo(() => parseCaseId(params.caseId), [params.caseId]);
    const {
        selectedCaseId,
        setSelectedCaseId,
        selectedCase,
        cases,
        documents,
        recordings,
        consultations,
        calendarAppointments,
        caseContextLoading,
        caseContextError,
        user,
        locale,
        t,
    } = useRoutedWorkspace();

    const activeCaseId = routeCaseId ?? selectedCaseId;
    const activeCase = selectedCase || (activeCaseId ? cases.find((item) => item.id === activeCaseId) || null : null);
    const [documentType, setDocumentType] = useState<EditorDocumentType>("legal_memo");
    const [sections, setSections] = useState<EditorSection[]>([]);
    const [selectedSectionId, setSelectedSectionId] = useState<string | null>(null);
    const [refineInstruction, setRefineInstruction] = useState("Strengthen this section with clearer legal reasoning.");
    const [suggestion, setSuggestion] = useState<string | null>(null);
    const [suggestionTarget, setSuggestionTarget] = useState<EditorTextSelection | null>(null);
    const [textSelection, setTextSelection] = useState<EditorTextSelection | null>(null);
    const [versions, setVersions] = useState<EditorVersion[]>([]);
    const [activeVersionId, setActiveVersionId] = useState<string | null>(null);
    const [versionLabel, setVersionLabel] = useState("");
    const [versionHistoryCaseId, setVersionHistoryCaseId] = useState<number | null>(null);
    const [reviewDecisions, setReviewDecisions] = useState<Record<string, ReviewDecision>>({});
    const [collaborationCaseId, setCollaborationCaseId] = useState<number | null>(null);
    const [shareMode, setShareMode] = useState<ShareMode>("private");
    const [shareNote, setShareNote] = useState("");
    const [commentDraft, setCommentDraft] = useState("");
    const [comments, setComments] = useState<EditorComment[]>([]);
    const [notice, setNotice] = useState<string | null>(null);

    useEffect(() => {
        if (routeCaseId && routeCaseId !== selectedCaseId) {
            setSelectedCaseId(routeCaseId);
        }
    }, [routeCaseId, selectedCaseId, setSelectedCaseId]);

    useEffect(() => {
        if (!activeCaseId) {
            setVersions([]);
            setActiveVersionId(null);
            setVersionHistoryCaseId(null);
            return;
        }

        try {
            const raw = window.localStorage.getItem(versionStorageKey(activeCaseId));
            const parsed = raw ? JSON.parse(raw) as EditorVersion[] : [];
            setVersions(Array.isArray(parsed) ? parsed.slice(0, 12) : []);
        } catch {
            setVersions([]);
        }
        setActiveVersionId(null);
        setVersionHistoryCaseId(activeCaseId);
    }, [activeCaseId]);

    useEffect(() => {
        if (!activeCaseId || versionHistoryCaseId !== activeCaseId) return;
        window.localStorage.setItem(versionStorageKey(activeCaseId), JSON.stringify(versions.slice(0, 12)));
    }, [activeCaseId, versionHistoryCaseId, versions]);

    useEffect(() => {
        if (!activeCaseId) {
            setCollaborationCaseId(null);
            setShareMode("private");
            setShareNote("");
            setComments([]);
            setCommentDraft("");
            return;
        }

        try {
            const raw = window.localStorage.getItem(collaborationStorageKey(activeCaseId));
            const parsed = raw ? JSON.parse(raw) as Partial<EditorCollaborationState> : null;
            setShareMode(parsed?.shareMode || "private");
            setShareNote(parsed?.shareNote || "");
            setComments(Array.isArray(parsed?.comments) ? parsed.comments : []);
        } catch {
            setShareMode("private");
            setShareNote("");
            setComments([]);
        }
        setCommentDraft("");
        setCollaborationCaseId(activeCaseId);
    }, [activeCaseId]);

    useEffect(() => {
        if (!activeCaseId || collaborationCaseId !== activeCaseId) return;
        const payload: EditorCollaborationState = {
            shareMode,
            shareNote,
            comments,
        };
        window.localStorage.setItem(collaborationStorageKey(activeCaseId), JSON.stringify(payload));
    }, [activeCaseId, collaborationCaseId, comments, shareMode, shareNote]);

    const evidenceSources = useMemo(() => {
        const docSources = documents.slice(0, 6).map((item) => `Document: ${item.filename}`);
        const voiceSources = recordings.slice(0, 3).map((item) => `Voice: ${item.filename}`);
        const intakeSources = consultations.slice(0, 3).map((item) => `Intake: ${formatDate(item.created_at, locale, "No date")}`);
        return [...docSources, ...voiceSources, ...intakeSources];
    }, [consultations, documents, locale, recordings]);

    const editorStats = useMemo(() => ({
        groundedSections: sections.filter((section) => section.trust === "grounded").length,
        reviewSections: sections.filter((section) => section.trust === "review").length,
        missingSections: sections.filter((section) => section.trust === "missing").length,
        sourceCount: new Set(sections.flatMap((section) => section.sources)).size,
        citationCount: sections.reduce((total, section) => total + getSectionCitations(section).length, 0),
    }), [sections]);

    const currentVersionStats = useMemo(() => ({
        sections: sections.length,
        words: wordCountFromSections(sections),
        citations: editorStats.citationCount,
        grounded: editorStats.groundedSections,
        review: editorStats.reviewSections,
        missing: editorStats.missingSections,
    }), [editorStats, sections]);

    const reviewMatrixRows = useMemo(() => sections.map((section, index) => {
        const citations = getSectionCitations(section);
        const decision = reviewDecisions[section.id] || "pending";
        const blockers = [
            section.trust === "missing" ? "Missing evidence" : null,
            citations.length === 0 ? "No citations" : null,
            section.sources.length === 0 ? "No sources" : null,
            section.trust === "review" ? "Lawyer validation" : null,
        ].filter(Boolean) as string[];

        return {
            section,
            index,
            decision,
            citations,
            blockers,
            trustScore: trustScore(section),
        };
    }), [reviewDecisions, sections]);

    const reviewStats = useMemo(() => ({
        approved: reviewMatrixRows.filter((row) => row.decision === "approved").length,
        pending: reviewMatrixRows.filter((row) => row.decision === "pending").length,
        needsRevision: reviewMatrixRows.filter((row) => row.decision === "needs_revision").length,
        blocked: reviewMatrixRows.filter((row) => row.blockers.length > 0).length,
    }), [reviewMatrixRows]);

    const selectedSectionComments = useMemo(
        () => comments
            .filter((comment) => comment.sectionId === selectedSectionId)
            .sort((left, right) => right.createdAt.localeCompare(left.createdAt)),
        [comments, selectedSectionId]
    );

    const collaborationStats = useMemo(() => ({
        open: comments.filter((comment) => !comment.resolved).length,
        resolved: comments.filter((comment) => comment.resolved).length,
        sectionsWithComments: new Set(comments.map((comment) => comment.sectionId)).size,
    }), [comments]);

    const activeSavedVersion = useMemo(
        () => versions.find((version) => version.id === activeVersionId) || null,
        [activeVersionId, versions]
    );

    const hasUnsavedVersionChanges = useMemo(() => {
        if (!sections.length) return false;
        if (!activeSavedVersion) return true;
        return JSON.stringify(activeSavedVersion.sections) !== JSON.stringify(sections)
            || activeSavedVersion.documentType !== documentType;
    }, [activeSavedVersion, documentType, sections]);

    const selectedSection = useMemo(
        () => sections.find((section) => section.id === selectedSectionId) || sections[0] || null,
        [sections, selectedSectionId]
    );

    const activeTextSelection = useMemo(() => {
        if (!selectedSection || !textSelection || textSelection.sectionId !== selectedSection.id) return null;
        return textSelection.text.trim() ? textSelection : null;
    }, [selectedSection, textSelection]);

    function getSectionCommentCount(sectionId: string) {
        return comments.filter((comment) => comment.sectionId === sectionId && !comment.resolved).length;
    }

    function getSectionCitations(section: EditorSection) {
        return section.citations?.length ? section.citations : citationsFromSources(section.sources);
    }

    function trustScore(section: EditorSection) {
        const citationCount = getSectionCitations(section).length;
        if (section.trust === "grounded") return Math.min(96, 82 + citationCount * 4);
        if (section.trust === "review") return Math.min(74, 48 + citationCount * 6);
        return Math.min(35, citationCount * 8);
    }

    function trustReason(section: EditorSection) {
        if (section.trustReason) return section.trustReason;
        if (section.trust === "grounded") return "Section has linked citations and can be reviewed against the evidence binder.";
        if (section.trust === "review") return "Section is useful drafting material but still needs lawyer validation.";
        return "Section needs evidence before it should be shared or exported.";
    }

    function buildSuggestedRewrite(text: string, citations: SectionCitation[]) {
        const cleanText = text.trim().replace(/\s+/g, " ");
        const citationLine = citations.length
            ? `Ground this wording in ${citations.slice(0, 2).map((citation) => citation.label).join(" and ")}.`
            : "Add an evidence anchor before final use.";
        return joinLines([
            cleanText,
            `Refinement: ${refineInstruction}`,
            citationLine,
            "Lawyer review remains required before sharing or export.",
        ]);
    }

    function captureTextSelection(section: EditorSection, element: HTMLTextAreaElement) {
        const start = element.selectionStart;
        const end = element.selectionEnd;
        const text = element.value.slice(start, end);
        setSelectedSectionId(section.id);
        if (end > start && text.trim()) {
            setTextSelection({ sectionId: section.id, start, end, text });
            return;
        }
        setTextSelection((current) => current?.sectionId === section.id ? null : current);
    }

    function getVersionStats(version: EditorVersion) {
        if (version.stats) return version.stats;
        return {
            sections: version.sections.length,
            words: wordCountFromSections(version.sections),
            citations: version.sections.reduce((total, section) => total + getSectionCitations(section).length, 0),
            grounded: version.sections.filter((section) => section.trust === "grounded").length,
            review: version.sections.filter((section) => section.trust === "review").length,
            missing: version.sections.filter((section) => section.trust === "missing").length,
        };
    }

    function changedSectionCount(version: EditorVersion) {
        const length = Math.max(version.sections.length, sections.length);
        let changed = 0;
        for (let index = 0; index < length; index += 1) {
            const left = version.sections[index];
            const right = sections[index];
            if (!left || !right || left.title !== right.title || left.body !== right.body || left.trust !== right.trust) {
                changed += 1;
            }
        }
        return changed;
    }

    function buildDraftSections(type: EditorDocumentType): EditorSection[] {
        const caseTitle = activeCase?.title || "Selected matter";
        const jurisdiction = activeCase?.jurisdiction_country || "tunisia";
        const caseStatus = activeCase?.status || "open";
        const firstDocument = documents[0]?.filename;
        const nextAppointment = calendarAppointments[0];
        const latestConsultation = consultations[0];
        const sourceFallback = evidenceSources.length ? evidenceSources : ["Case record"];

        if (type === "client_update") {
            return [
                {
                    id: makeId("section"),
                    title: "Opening summary",
                    body: joinLines([
                        `We are writing with an update on ${caseTitle}.`,
                        `The matter is currently marked as ${caseStatus} in the workspace.`,
                        latestConsultation ? "The latest client intake has been reviewed and should be validated against the uploaded evidence." : "No recent client intake is attached yet.",
                    ]),
                    trust: latestConsultation ? "grounded" : "review",
                    sources: latestConsultation ? [`Intake: ${formatDate(latestConsultation.created_at, locale, "No date")}`] : ["Case record"],
                },
                {
                    id: makeId("section"),
                    title: "Evidence reviewed",
                    body: firstDocument
                        ? `The current review relies first on ${firstDocument}. Additional uploaded materials should be checked before final advice is sent.`
                        : "No processed document is available yet. The legal position should remain provisional until the evidence file is complete.",
                    trust: firstDocument ? "grounded" : "missing",
                    sources: firstDocument ? [`Document: ${firstDocument}`] : [],
                },
                {
                    id: makeId("section"),
                    title: "Next steps",
                    body: nextAppointment
                        ? `The next scheduled item is ${nextAppointment.title} on ${formatDate(nextAppointment.scheduled_at, locale, "No date")}. Prepare questions, missing proof, and client instructions before that date.`
                        : "Recommended next steps: complete evidence collection, confirm the timeline, identify deadlines, and prepare a lawyer-reviewed action plan.",
                    trust: nextAppointment ? "grounded" : "review",
                    sources: nextAppointment ? [`Appointment: ${nextAppointment.title}`] : sourceFallback.slice(0, 2),
                },
            ];
        }

        if (type === "demand_letter") {
            return [
                {
                    id: makeId("section"),
                    title: "Position and demand",
                    body: `Our client reserves all rights in relation to ${caseTitle}. Based on the current record, the opposing party should be requested to cure the disputed conduct and respond within a lawyer-approved deadline.`,
                    trust: "review",
                    sources: sourceFallback.slice(0, 2),
                },
                {
                    id: makeId("section"),
                    title: "Factual basis",
                    body: firstDocument
                        ? `The factual basis should cite the uploaded evidence, beginning with ${firstDocument}, and any correspondence or payment records relevant to the dispute.`
                        : "The factual basis is incomplete because no document is available for citation.",
                    trust: firstDocument ? "grounded" : "missing",
                    sources: firstDocument ? [`Document: ${firstDocument}`] : [],
                },
                {
                    id: makeId("section"),
                    title: "Reservation of rights",
                    body: `Nothing in this letter should be treated as a waiver of claims, remedies, procedural rights, or rights available under the applicable ${jurisdiction} legal framework.`,
                    trust: "review",
                    sources: ["Jurisdiction context"],
                },
            ];
        }

        if (type === "strategy_note") {
            return [
                {
                    id: makeId("section"),
                    title: "Strategic posture",
                    body: `${caseTitle} should be treated as a ${caseStatus} matter. The immediate strategy is to separate confirmed evidence from assumptions before making any external commitment.`,
                    trust: "review",
                    sources: ["Case record"],
                },
                {
                    id: makeId("section"),
                    title: "Proof strengths",
                    body: evidenceSources.length
                        ? `Current source base: ${evidenceSources.slice(0, 4).join("; ")}. These should be mapped to each legal claim before drafting a final position.`
                        : "The proof base is not ready. Upload core documents and intake materials before finalizing strategy.",
                    trust: evidenceSources.length ? "grounded" : "missing",
                    sources: evidenceSources.slice(0, 4),
                },
                {
                    id: makeId("section"),
                    title: "Negotiation line",
                    body: "Recommended negotiation line: maintain a firm evidence-led position, avoid unsupported concessions, and keep fallback options tied to documented risk.",
                    trust: "review",
                    sources: sourceFallback.slice(0, 2),
                },
            ];
        }

        return [
            {
                id: makeId("section"),
                title: "Issue",
                body: `The issue is to assess the legal position in ${caseTitle}, including the factual record, applicable ${jurisdiction} context, risks, and recommended next steps.`,
                trust: "review",
                sources: ["Case record", "Jurisdiction context"],
            },
            {
                id: makeId("section"),
                title: "Relevant facts",
                body: evidenceSources.length
                    ? `The current fact base is drawn from ${evidenceSources.slice(0, 4).join("; ")}. Each fact should remain tied to its source before final use.`
                    : "The fact base is incomplete because no evidence source is available yet.",
                trust: evidenceSources.length ? "grounded" : "missing",
                sources: evidenceSources.slice(0, 4),
            },
            {
                id: makeId("section"),
                title: "Preliminary analysis",
                body: "The legal position should be framed cautiously until the lawyer confirms the rule, supporting evidence, counterarguments, and any procedural deadlines.",
                trust: "review",
                sources: sourceFallback.slice(0, 2),
            },
            {
                id: makeId("section"),
                title: "Recommended next steps",
                body: "Complete evidence mapping, validate dates, identify missing proof, prepare client questions, and generate a final lawyer-reviewed version before export.",
                trust: "review",
                sources: sourceFallback.slice(0, 3),
            },
        ];
    }

    function buildSeededSections(seed: EditorDraftSeed): EditorSection[] {
        const answer = String(seed.answer || "").trim();
        const prompt = String(seed.prompt || "").trim();
        const citationSources = uniqueLabels((seed.citations || []).map((citation) => citation.label));
        const retrievalSources = uniqueLabels((seed.sources || []).map(sourceLabelFromSeed));
        const seedSources = uniqueLabels([...citationSources, ...retrievalSources]).slice(0, 8);
        const sourceFallback = seedSources.length ? seedSources : evidenceSources.slice(0, 4);
        const hasGrounding = seedSources.length > 0 || Boolean(answer);
        const assistantCitations = citationsFromAssistant(seed.citations, sourceFallback);

        return [
            {
                id: makeId("section"),
                title: "Draft basis",
                body: joinLines([
                    `This document was generated from the matter workspace for ${seed.caseTitle || activeCase?.title || "the selected case"}.`,
                    prompt ? `Assistant prompt: ${prompt}` : "Starting point: selected case context.",
                    "The text below should be reviewed, refined, and cited before external use.",
                ]),
                trust: prompt ? "grounded" : "review",
                sources: sourceFallback.length ? sourceFallback.slice(0, 3) : ["Case record"],
                citations: citationsFromSources(sourceFallback.length ? sourceFallback.slice(0, 3) : ["Case record"], prompt || "Generated from the active case and assistant prompt."),
                trustReason: prompt ? "Prompt, matter, and attached answer are preserved for reviewer traceability." : "Generated from case context and requires lawyer confirmation.",
            },
            {
                id: makeId("section"),
                title: "Assistant-generated analysis",
                body: answer || "No assistant answer was attached. Generate a case draft, then revise this section with the case assistant.",
                trust: hasGrounding ? "grounded" : "missing",
                sources: sourceFallback,
                citations: assistantCitations,
                trustReason: hasGrounding ? "Assistant answer is tied to the response citations or retrieval sources." : "No answer or citation basis was available.",
            },
            {
                id: makeId("section"),
                title: "Citation and evidence map",
                body: seed.citations?.length
                    ? seed.citations.slice(0, 5).map((citation, index) => `${index + 1}. ${citation.label}: ${citation.snippet}`).join("\n")
                    : "No citation list was attached to the assistant response. Add evidence anchors before finalizing.",
                trust: seed.citations?.length ? "grounded" : "missing",
                sources: seedSources,
                citations: assistantCitations,
                trustReason: seed.citations?.length ? "Citation snippets were carried from the assistant response into this section." : "The assistant response did not return direct citations.",
            },
            {
                id: makeId("section"),
                title: "Lawyer review checklist",
                body: joinLines([
                    "Confirm the legal issue, jurisdiction, deadlines, procedural posture, and client instructions.",
                    "Check every factual statement against the source binder.",
                    "Revise tone and remedy language for the chosen document type before export.",
                ]),
                trust: "review",
                sources: sourceFallback.length ? sourceFallback.slice(0, 3) : ["Case record"],
                citations: citationsFromSources(sourceFallback.length ? sourceFallback.slice(0, 3) : ["Case record"]),
                trustReason: "Checklist is procedural guidance and should be signed off by the responsible lawyer.",
            },
        ];
    }

    function applyDraft(nextSections: EditorSection[], nextNotice: string) {
        setSections(nextSections);
        setSelectedSectionId(nextSections[0]?.id || null);
        setActiveVersionId(null);
        setReviewDecisions({});
        setTextSelection(null);
        setSuggestionTarget(null);
        setSuggestion(null);
        setNotice(nextNotice);
    }

    function generateDraft(type = documentType) {
        applyDraft(buildDraftSections(type), t("draftGenerated", "Draft generated from current case context."));
    }

    function updateSection(sectionId: string, body: string) {
        setSections((current) => current.map((section) => section.id === sectionId ? { ...section, body } : section));
        setActiveVersionId(null);
    }

    function saveVersion(label = versionLabel.trim() || "Lawyer snapshot") {
        if (!sections.length) return;
        const version: EditorVersion = {
            id: makeId("version"),
            label,
            createdAt: new Date().toISOString(),
            documentType,
            sections: cloneSections(sections),
            stats: currentVersionStats,
        };
        setVersions((current) => [version, ...current].slice(0, 8));
        setActiveVersionId(version.id);
        setVersionLabel("");
        setNotice(t("versionSaved", "Version saved."));
    }

    function restoreVersion(version: EditorVersion) {
        setDocumentType(version.documentType || documentType);
        setSections(cloneSections(version.sections));
        setSelectedSectionId(version.sections[0]?.id || null);
        setActiveVersionId(version.id);
        setReviewDecisions({});
        setTextSelection(null);
        setSuggestionTarget(null);
        setSuggestion(null);
        setNotice(t("versionRestored", "Version restored."));
    }

    function deleteVersion(versionId: string) {
        setVersions((current) => current.filter((version) => version.id !== versionId));
        if (activeVersionId === versionId) {
            setActiveVersionId(null);
        }
        setNotice(t("versionDeleted", "Version deleted."));
    }

    function updateReviewDecision(sectionId: string, decision: ReviewDecision) {
        setReviewDecisions((current) => ({
            ...current,
            [sectionId]: decision,
        }));
    }

    function buildShareLink() {
        const caseId = activeCase?.id || activeCaseId || "draft";
        return `${window.location.origin}/editor/${caseId}?share=${shareMode}`;
    }

    async function copyShareLink() {
        await navigator.clipboard.writeText(buildShareLink());
        setNotice(t("shareLinkCopied", "Share link copied."));
    }

    function addComment() {
        if (!selectedSection || !commentDraft.trim()) return;
        const comment: EditorComment = {
            id: makeId("comment"),
            sectionId: selectedSection.id,
            author: user?.name || "Lawyer reviewer",
            body: commentDraft.trim(),
            createdAt: new Date().toISOString(),
            resolved: false,
        };
        setComments((current) => [comment, ...current]);
        setCommentDraft("");
        setNotice(t("commentAdded", "Comment added."));
    }

    function toggleCommentResolved(commentId: string) {
        setComments((current) => current.map((comment) => (
            comment.id === commentId ? { ...comment, resolved: !comment.resolved } : comment
        )));
    }

    function deleteComment(commentId: string) {
        setComments((current) => current.filter((comment) => comment.id !== commentId));
    }

    function suggestEdit() {
        if (!selectedSection) return;
        const selectedCitations = getSectionCitations(selectedSection);
        const target = activeTextSelection;
        setSuggestionTarget(target);
        setSuggestion(buildSuggestedRewrite(target?.text || selectedSection.body, selectedCitations));
    }

    function acceptSuggestion() {
        if (!selectedSection || !suggestion) return;
        if (suggestionTarget && suggestionTarget.sectionId === selectedSection.id) {
            const currentBody = selectedSection.body;
            const exactRangeStillMatches = currentBody.slice(suggestionTarget.start, suggestionTarget.end) === suggestionTarget.text;
            if (exactRangeStillMatches) {
                updateSection(
                    selectedSection.id,
                    `${currentBody.slice(0, suggestionTarget.start)}${suggestion}${currentBody.slice(suggestionTarget.end)}`
                );
            } else {
                updateSection(selectedSection.id, currentBody.replace(suggestionTarget.text, suggestion));
            }
            setTextSelection(null);
            setSuggestionTarget(null);
            setSuggestion(null);
            setNotice(t("suggestionAccepted", "Suggested edit accepted."));
            return;
        }
        updateSection(selectedSection.id, suggestion);
        setSuggestionTarget(null);
        setSuggestion(null);
        setNotice(t("suggestionAccepted", "Suggested edit accepted."));
    }

    async function copyDocument() {
        const text = renderPlainDocument();
        await navigator.clipboard.writeText(text);
        setNotice(t("documentCopied", "Document copied to clipboard."));
    }

    function renderPlainDocument() {
        const docTypeLabel = DOCUMENT_TYPES.find((item) => item.id === documentType)?.label || "Legal document";
        return [
            docTypeLabel,
            activeCase ? `Matter: ${activeCase.title}` : "Matter: Unselected",
            `Generated: ${new Date().toLocaleString(locale)}`,
            "",
            ...sections.flatMap((section, index) => [
                `${index + 1}. ${section.title}`,
                section.body,
                getSectionCitations(section).length
                    ? `Citations: ${getSectionCitations(section).map((citation, citationIndex) => `[${citationIndex + 1}] ${citation.label}`).join("; ")}`
                    : "Citations: Missing evidence",
                section.sources.length ? `Sources: ${section.sources.join("; ")}` : "Sources: Missing evidence",
                `Trust: ${trustLabel(section.trust)} (${trustScore(section)}%) - ${trustReason(section)}`,
                `Review: ${reviewDecisionLabel(reviewDecisions[section.id] || "pending")}`,
                `Open comments: ${getSectionCommentCount(section.id)}`,
                "",
            ]),
        ].join("\n");
    }

    async function exportDocx() {
        const { AlignmentType, Document: DocxDocument, HeadingLevel, Packer, Paragraph, TextRun } = await import("docx");
        const docTypeLabel = DOCUMENT_TYPES.find((item) => item.id === documentType)?.label || "Legal document";
        const children = [
            new Paragraph({
                alignment: AlignmentType.CENTER,
                heading: HeadingLevel.TITLE,
                text: docTypeLabel,
            }),
            new Paragraph({
                alignment: AlignmentType.CENTER,
                children: [
                    new TextRun({ text: activeCase ? `Matter: ${activeCase.title}` : "Matter: Unselected", bold: true }),
                ],
            }),
            new Paragraph({
                alignment: AlignmentType.CENTER,
                children: [
                    new TextRun(`Generated: ${new Date().toLocaleString(locale)}`),
                ],
                spacing: { after: 360 },
            }),
        ];

        sections.forEach((section, sectionIndex) => {
            const citations = getSectionCitations(section);
            const reviewDecision = reviewDecisions[section.id] || "pending";
            const openCommentCount = getSectionCommentCount(section.id);
            children.push(
                new Paragraph({
                    heading: HeadingLevel.HEADING_2,
                    text: `${sectionIndex + 1}. ${section.title}`,
                    spacing: { before: 260, after: 120 },
                }),
                new Paragraph({
                    children: [
                        new TextRun({
                            text: `Trust: ${trustLabel(section.trust)} (${trustScore(section)}%) - ${trustReason(section)}`,
                            bold: true,
                        }),
                    ],
                    spacing: { after: 160 },
                }),
                new Paragraph({
                    children: [
                        new TextRun({ text: `Review: ${reviewDecisionLabel(reviewDecision)}`, bold: true }),
                    ],
                    spacing: { after: 160 },
                }),
                new Paragraph({
                    children: [
                        new TextRun({ text: `Open comments: ${openCommentCount}`, bold: true }),
                    ],
                    spacing: { after: 160 },
                })
            );

            section.body.split(/\n+/).map((line) => line.trim()).filter(Boolean).forEach((line) => {
                children.push(new Paragraph({
                    children: [new TextRun(line)],
                    spacing: { after: 120 },
                }));
            });

            children.push(new Paragraph({
                children: [new TextRun({ text: "Citations", bold: true })],
                spacing: { before: 160, after: 80 },
            }));

            if (citations.length) {
                citations.slice(0, 8).forEach((citation, citationIndex) => {
                    children.push(new Paragraph({
                        children: [
                            new TextRun({ text: `[${citationIndex + 1}] ${citation.label}`, bold: true }),
                            new TextRun(citation.snippet ? `: ${citation.snippet}` : ""),
                        ],
                        spacing: { after: 80 },
                    }));
                });
            } else {
                children.push(new Paragraph("Missing evidence"));
            }

            children.push(new Paragraph({
                children: [
                    new TextRun({ text: "Sources: ", bold: true }),
                    new TextRun(section.sources.length ? section.sources.join("; ") : "Missing evidence"),
                ],
                spacing: { after: 180 },
            }));
        });
        const doc = new DocxDocument({
            sections: [{
                properties: {},
                children,
            }],
        });
        const blob = await Packer.toBlob(doc);
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `${safeFileName(activeCase?.title || "legal-document")}.docx`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        setNotice(t("documentExported", "DOCX document exported."));
    }

    useEffect(() => {
        if (activeCase) {
            const seed = loadEditorDraftSeed(activeCase.id);
            if (seed?.source === "assistant") {
                applyDraft(buildSeededSections(seed), t("draftGeneratedFromAssistant", "Draft generated from assistant answer and case context."));
                return;
            }
            generateDraft(documentType);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeCase?.id]);

    return (
        <section className="shell-page legal-editor-page">
            <header className="shell-page-header legal-editor-header">
                <div>
                    <p className="shell-page-kicker">{t("legalEditorKicker", "Legal Editor")}</p>
                    <h2>{t("legalEditorTitle", "Case-to-document drafting workspace")}</h2>
                    <p>{t("legalEditorSubtitle", "Generate, edit, verify, version, and export legal documents without leaving the case workspace.")}</p>
                </div>
                <div className="editor-header-actions">
                    <button onClick={() => generateDraft()} type="button">{t("generateDraft", "Generate draft")}</button>
                    <button disabled={!sections.length} onClick={() => saveVersion()} type="button">{t("saveVersion", "Save version")}</button>
                    <button disabled={!sections.length} onClick={copyDocument} type="button">{t("copyDocument", "Copy")}</button>
                    <button disabled={!sections.length} onClick={() => { void exportDocx(); }} type="button">{t("exportDocx", "Export DOCX")}</button>
                </div>
            </header>

            {!activeCaseId ? (
                <article className="shell-card editor-empty-state">
                    <h3>{t("selectCaseForEditor", "Select a case to start drafting")}</h3>
                    <p>{t("selectCaseForEditorHint", "The editor needs a case context so every section can cite evidence and carry trust metadata.")}</p>
                    <Link className="shell-inline-link" to="/cases">{t("openCases", "Open Cases")}</Link>
                </article>
            ) : (
                <div className="legal-editor-grid">
                    <aside className="editor-sidebar">
                        <article className="shell-card">
                            <h3>{t("draftSetup", "Draft setup")}</h3>
                            <label className="editor-field">
                                <span>{t("documentType", "Document type")}</span>
                                <select
                                    value={documentType}
                                    onChange={(event) => {
                                        const nextType = event.target.value as EditorDocumentType;
                                        setDocumentType(nextType);
                                        generateDraft(nextType);
                                    }}
                                >
                                    {DOCUMENT_TYPES.map((item) => (
                                        <option key={item.id} value={item.id}>{item.label}</option>
                                    ))}
                                </select>
                            </label>
                            <p className="editor-muted">{DOCUMENT_TYPES.find((item) => item.id === documentType)?.description}</p>
                            <div className="editor-case-card">
                                <span>{t("currentMatter", "Current matter")}</span>
                                <strong>{activeCase?.title || `Case #${activeCaseId}`}</strong>
                                <p>{activeCase?.jurisdiction_country || "Tunisia"} | {activeCase?.status || "open"}</p>
                            </div>
                        </article>

                        <article className="shell-card">
                            <h3>{t("trustCoverage", "Trust coverage")}</h3>
                            <div className="editor-trust-grid">
                                <span><strong>{editorStats.groundedSections}</strong>{t("grounded", "grounded")}</span>
                                <span><strong>{editorStats.reviewSections}</strong>{t("needsReview", "review")}</span>
                                <span><strong>{editorStats.missingSections}</strong>{t("missingEvidence", "missing")}</span>
                                <span><strong>{editorStats.sourceCount}</strong>{t("sources", "sources")}</span>
                                <span><strong>{editorStats.citationCount}</strong>{t("citations", "citations")}</span>
                                <span><strong>{reviewStats.approved}</strong>{t("approved", "approved")}</span>
                            </div>
                        </article>

                        <article className="shell-card">
                            <h3>{t("sourceBinder", "Source binder")}</h3>
                            <ul className="editor-source-list">
                                {evidenceSources.length ? evidenceSources.map((source) => (
                                    <li key={source}>{source}</li>
                                )) : (
                                    <li>{t("noSourcesYet", "No sources yet. Upload documents or intake notes to strengthen drafts.")}</li>
                                )}
                            </ul>
                        </article>
                    </aside>

                    <main className="editor-document-shell">
                        {caseContextError ? <p className="shell-error-text">{caseContextError}</p> : null}
                        {caseContextLoading ? <p>{t("loadingCaseContext", "Loading selected case context...")}</p> : null}
                        {notice ? <p className="shell-success-text">{notice}</p> : null}

                        <article className="review-matrix-card" aria-label={t("reviewMatrix", "Review matrix")}>
                            <div className="review-matrix-head">
                                <div>
                                    <p className="shell-page-kicker">{t("reviewMatrix", "Review Matrix")}</p>
                                    <h3>{t("preExportQualityGate", "Pre-export quality gate")}</h3>
                                </div>
                                <div className="review-matrix-stats">
                                    <span><strong>{reviewStats.approved}</strong>{t("approved", "approved")}</span>
                                    <span><strong>{reviewStats.pending}</strong>{t("pending", "pending")}</span>
                                    <span><strong>{reviewStats.needsRevision}</strong>{t("needsRevision", "needs revision")}</span>
                                    <span><strong>{reviewStats.blocked}</strong>{t("blocked", "blocked")}</span>
                                </div>
                            </div>

                            <div className="review-matrix-table-wrap">
                                <table className="review-matrix-table">
                                    <thead>
                                        <tr>
                                            <th>{t("section", "Section")}</th>
                                            <th>{t("trust", "Trust")}</th>
                                            <th>{t("evidence", "Evidence")}</th>
                                            <th>{t("blockers", "Blockers")}</th>
                                            <th>{t("review", "Review")}</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {reviewMatrixRows.map((row) => (
                                            <tr
                                                className={selectedSectionId === row.section.id ? "active" : ""}
                                                key={row.section.id}
                                                onClick={() => setSelectedSectionId(row.section.id)}
                                            >
                                                <td>
                                                    <strong>{row.index + 1}. {row.section.title}</strong>
                                                    <small>{wordCountFromSections([row.section])} {t("words", "words")}</small>
                                                </td>
                                                <td>
                                                    <em className={`trust-badge ${row.section.trust}`}>
                                                        {trustLabel(row.section.trust)} | {row.trustScore}%
                                                    </em>
                                                </td>
                                                <td>
                                                    <span>{row.citations.length} {t("citations", "citations")}</span>
                                                    <small>{row.section.sources.length} {t("sources", "sources")}</small>
                                                </td>
                                                <td>
                                                    {row.blockers.length ? row.blockers.map((blocker) => (
                                                        <span className="review-blocker-chip" key={blocker}>{blocker}</span>
                                                    )) : (
                                                        <span className="review-clear-chip">{t("clear", "Clear")}</span>
                                                    )}
                                                </td>
                                                <td>
                                                    <div className="review-decision-control" onClick={(event) => event.stopPropagation()}>
                                                        {(["pending", "approved", "needs_revision"] as ReviewDecision[]).map((decision) => (
                                                            <button
                                                                className={row.decision === decision ? "active" : ""}
                                                                key={decision}
                                                                onClick={() => updateReviewDecision(row.section.id, decision)}
                                                                type="button"
                                                            >
                                                                {reviewDecisionLabel(decision)}
                                                            </button>
                                                        ))}
                                                    </div>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </article>

                        <article className="editor-paper" aria-label={t("draftDocument", "Draft document")}>
                            <header className="editor-paper-title">
                                <p>{DOCUMENT_TYPES.find((item) => item.id === documentType)?.label}</p>
                                <h3>{activeCase?.title || t("untitledMatter", "Untitled matter")}</h3>
                            </header>

                            {sections.map((section, index) => {
                                const sectionCitations = getSectionCitations(section);
                                const openCommentCount = getSectionCommentCount(section.id);
                                return (
                                    <section
                                        key={section.id}
                                        className={`editor-section ${selectedSection?.id === section.id ? "active" : ""}`}
                                        onClick={() => setSelectedSectionId(section.id)}
                                    >
                                        <div className="editor-section-head">
                                            <div>
                                                <span>{index + 1}</span>
                                                <h4>{section.title}</h4>
                                            </div>
                                            <div className="section-trust-stack">
                                                <em className={`trust-badge ${section.trust}`}>
                                                    {trustLabel(section.trust)} | {trustScore(section)}%
                                                </em>
                                                <small>
                                                    {sectionCitations.length} {t("sectionCitations", "citation(s)")}
                                                    {" | "}
                                                    {openCommentCount} {t("comments", "comment(s)")}
                                                </small>
                                            </div>
                                        </div>
                                        <p className="section-trust-reason">{trustReason(section)}</p>
                                        <textarea
                                            value={section.body}
                                            onChange={(event) => updateSection(section.id, event.target.value)}
                                            onKeyUp={(event) => captureTextSelection(section, event.currentTarget)}
                                            onMouseUp={(event) => captureTextSelection(section, event.currentTarget)}
                                            onSelect={(event) => captureTextSelection(section, event.currentTarget)}
                                        />
                                        <div className="section-citation-panel" aria-label={t("sectionCitations", "Section citations")}>
                                            {sectionCitations.length ? sectionCitations.slice(0, 5).map((citation, citationIndex) => (
                                                <span className={`section-citation-chip ${citation.kind}`} key={`${citation.label}-${citationIndex}`}>
                                                    <strong>[{citationIndex + 1}] {citation.label}</strong>
                                                    {citation.snippet ? <small>{citation.snippet}</small> : null}
                                                </span>
                                            )) : (
                                                <span className="section-citation-chip missing">
                                                    <strong>{t("missingSource", "Missing source")}</strong>
                                                    <small>{t("missingSourceHint", "Attach evidence before final use.")}</small>
                                                </span>
                                            )}
                                        </div>
                                        <div className="section-source-row">
                                            {section.sources.length ? section.sources.map((source) => (
                                                <span key={source}>{source}</span>
                                            )) : (
                                                <span>{t("missingSource", "Missing source")}</span>
                                            )}
                                        </div>
                                    </section>
                                );
                            })}
                        </article>
                    </main>

                    <aside className="editor-ai-panel">
                        <article className="shell-card">
                            <h3>{t("aiRevisionPanel", "AI revision panel")}</h3>
                            <p className="editor-muted">
                                {selectedSection
                                    ? `${t("selectedSection", "Selected")}: ${selectedSection.title}`
                                    : t("selectSectionToRevise", "Select a section to revise.")}
                            </p>
                            {activeTextSelection ? (
                                <div className="selected-text-preview">
                                    <span>{t("highlightedText", "Highlighted text")}</span>
                                    <p>{activeTextSelection.text}</p>
                                </div>
                            ) : (
                                <p className="editor-muted">{t("highlightTextHint", "Highlight text inside the document to suggest a focused edit.")}</p>
                            )}
                            <label className="editor-field">
                                <span>{t("revisionInstruction", "Revision instruction")}</span>
                                <textarea
                                    value={refineInstruction}
                                    onChange={(event) => setRefineInstruction(event.target.value)}
                                />
                            </label>
                            <button disabled={!selectedSection} onClick={suggestEdit} type="button">
                                {activeTextSelection ? t("suggestHighlightedEdit", "Suggest edit for highlight") : t("suggestEdits", "Suggest edits")}
                            </button>
                            {suggestion ? (
                                <div className="suggestion-box">
                                    <strong>
                                        {suggestionTarget
                                            ? t("suggestedHighlightedRevision", "Suggested replacement")
                                            : t("suggestedRevision", "Suggested revision")}
                                    </strong>
                                    <pre>{suggestion}</pre>
                                    <div className="editor-button-row">
                                        <button onClick={acceptSuggestion} type="button">{t("accept", "Accept")}</button>
                                        <button onClick={() => setSuggestion(null)} type="button">{t("reject", "Reject")}</button>
                                    </div>
                                </div>
                            ) : null}
                        </article>

                        <article className="shell-card collaboration-card">
                            <h3>{t("shareCommentWorkflow", "Share / comment workflow")}</h3>
                            <div className="share-status-card">
                                <div>
                                    <span>{t("shareStatus", "Share status")}</span>
                                    <strong>{shareModeLabel(shareMode)}</strong>
                                </div>
                                <em>
                                    {collaborationStats.open} {t("openComments", "open")}
                                    {" | "}
                                    {collaborationStats.resolved} {t("resolved", "resolved")}
                                </em>
                            </div>
                            <label className="editor-field">
                                <span>{t("accessMode", "Access mode")}</span>
                                <select value={shareMode} onChange={(event) => setShareMode(event.target.value as ShareMode)}>
                                    <option value="private">{t("privateDraft", "Private draft")}</option>
                                    <option value="internal_review">{t("internalReview", "Internal review")}</option>
                                    <option value="client_review">{t("clientReview", "Client review")}</option>
                                </select>
                            </label>
                            <label className="editor-field">
                                <span>{t("shareNote", "Share note")}</span>
                                <textarea
                                    value={shareNote}
                                    onChange={(event) => setShareNote(event.target.value)}
                                    placeholder={t("shareNotePlaceholder", "Ask for review on evidence, remedy language, or client-facing tone.")}
                                />
                            </label>
                            <button disabled={!activeCaseId || shareMode === "private"} onClick={() => { void copyShareLink(); }} type="button">
                                {t("copyShareLink", "Copy share link")}
                            </button>

                            <div className="comment-composer">
                                <strong>{selectedSection ? selectedSection.title : t("selectSection", "Select a section")}</strong>
                                <textarea
                                    disabled={!selectedSection}
                                    value={commentDraft}
                                    onChange={(event) => setCommentDraft(event.target.value)}
                                    placeholder={t("commentPlaceholder", "Leave a section-level comment for review.")}
                                />
                                <button disabled={!selectedSection || !commentDraft.trim()} onClick={addComment} type="button">
                                    {t("addComment", "Add comment")}
                                </button>
                            </div>

                            <ul className="editor-comment-list">
                                {selectedSectionComments.length ? selectedSectionComments.map((comment) => (
                                    <li className={comment.resolved ? "resolved" : ""} key={comment.id}>
                                        <div>
                                            <strong>{comment.author}</strong>
                                            <span>{formatDate(comment.createdAt, locale, "No date")}</span>
                                        </div>
                                        <p>{comment.body}</p>
                                        <div className="comment-actions">
                                            <button onClick={() => toggleCommentResolved(comment.id)} type="button">
                                                {comment.resolved ? t("reopen", "Reopen") : t("resolve", "Resolve")}
                                            </button>
                                            <button onClick={() => deleteComment(comment.id)} type="button">{t("delete", "Delete")}</button>
                                        </div>
                                    </li>
                                )) : (
                                    <li>{t("noSectionComments", "No comments on the selected section.")}</li>
                                )}
                            </ul>
                        </article>

                        <article className="shell-card">
                            <h3>{t("versionHistory", "Version history")}</h3>
                            <div className="version-current-card">
                                <div>
                                    <strong>{hasUnsavedVersionChanges ? t("unsavedDraft", "Unsaved draft") : t("savedDraft", "Saved draft")}</strong>
                                    <span>
                                        {currentVersionStats.words} {t("words", "words")}
                                        {" | "}
                                        {currentVersionStats.citations} {t("citations", "citations")}
                                    </span>
                                </div>
                                <em>{versions.length} {t("savedVersions", "saved")}</em>
                            </div>
                            <label className="editor-field version-name-field">
                                <span>{t("versionName", "Version name")}</span>
                                <input
                                    value={versionLabel}
                                    onChange={(event) => setVersionLabel(event.target.value)}
                                    placeholder={t("versionNamePlaceholder", "Client letter after evidence review")}
                                />
                            </label>
                            <button
                                className="version-save-button"
                                disabled={!sections.length}
                                onClick={() => saveVersion()}
                                type="button"
                            >
                                {hasUnsavedVersionChanges ? t("saveCurrentVersion", "Save current version") : t("saveAnotherVersion", "Save another version")}
                            </button>
                            <ul className="editor-version-list">
                                {versions.length ? versions.map((version) => {
                                    const stats = getVersionStats(version);
                                    const changedSections = changedSectionCount(version);
                                    return (
                                        <li className={activeVersionId === version.id ? "active" : ""} key={version.id}>
                                            <div className="version-row-main">
                                                <strong>{version.label}</strong>
                                                <span>{formatDate(version.createdAt, locale, "No date")}</span>
                                                <small>
                                                    {stats.sections} {t("sections", "sections")}
                                                    {" | "}
                                                    {stats.words} {t("words", "words")}
                                                    {" | "}
                                                    {stats.citations} {t("citations", "citations")}
                                                </small>
                                                <small>
                                                    {stats.grounded} {t("grounded", "grounded")}
                                                    {" | "}
                                                    {stats.review} {t("needsReview", "review")}
                                                    {" | "}
                                                    {stats.missing} {t("missingEvidence", "missing")}
                                                </small>
                                                <em>
                                                    {activeVersionId === version.id && !hasUnsavedVersionChanges
                                                        ? t("currentVersion", "Current version")
                                                        : `${changedSections} ${t("sectionChanges", "section change(s)")}`}
                                                </em>
                                            </div>
                                            <div className="version-row-actions">
                                                <button onClick={() => restoreVersion(version)} type="button">{t("restore", "Restore")}</button>
                                                <button onClick={() => deleteVersion(version.id)} type="button">{t("delete", "Delete")}</button>
                                            </div>
                                        </li>
                                    );
                                }) : (
                                    <li>{t("noVersionsYet", "No versions saved yet.")}</li>
                                )}
                            </ul>
                        </article>
                    </aside>
                </div>
            )}
        </section>
    );
}
