# Legal Practice and Harvey Gap Analysis

Date: 2026-04-23

## 1. Why this document exists

This document compares three things:

- how real legal analysis is taught in the legal-practice material from `C:\Users\ahmed\Downloads\legal practice (1).pdf`
- how Harvey describes its product and operating model in the transcript shared on 2026-04-23
- how the current Legal AI Platform actually works today

The goal is simple: turn the project from a broad legal AI demo into a more lawyer-realistic product that earns trust.

## 2. What the legal-practice material says lawyers actually do

The legal-practice material is not mainly about firm management. It is about how legal reasoning works.

Core takeaways:

- A lawyer starts by identifying the exact issue, not by producing an answer immediately.
- Facts matter twice:
  first to understand what happened, then to isolate the operative facts that change the result.
- Legal analysis is structured:
  conclusion, rule, explanation, application, counter-analysis.
- Case reading requires:
  court, procedural posture, parties, facts, legal issue, holding, reasoning, dicta, and outcome.
- Good legal work compares the client fact pattern against authority, instead of only summarizing authority.
- Legal conclusions should be framed with the correct level of confidence and with awareness of missing facts.

What this means for your product:

- Your AI should act more like a junior associate preparing a grounded internal note.
- The system should separate:
  facts we know, rules we found, application, uncertainties, and next steps.
- "Answer quality" in law is not just fluency. It is issue spotting, rule accuracy, fact matching, and cautious reasoning.

## 3. What Harvey gets right from the transcript

The Harvey transcript points to five strong product principles.

### A. Trust is the product

- Prestige matters because trust matters.
- Citations were a core investment from day one.
- Lawyers trust systems that show their work.

### B. Intent -> context -> validation

Harvey describes legal AI as three linked problems:

1. What does the user want?
2. What context do we need?
3. Is this right?

That maps directly to routing, retrieval, and verification.

### C. Expand then collapse

- Build narrow workflows for high-value legal tasks.
- Then collapse them back into one product surface with good suggestions and orchestration.

### D. Process data matters more than generic legal text

- Reading legal documents is not enough.
- The product must encode how lawyers actually do tasks.
- Domain experts define steps; models execute within those steps.

### E. Blank-page avoidance and personalization matter

- Lawyers adopt AI faster when the UI suggests the right starting workflows.
- A pure empty chat box is not enough for real professional use.

## 4. Where your project is already strong

The current platform already has serious strengths.

- Strong system breadth:
  backend, internal workspace, client portal, voice, documents, retrieval, agents.
- Good legal product direction:
  case-centric workflows instead of a generic chatbot.
- Code-first legal search is now a big improvement over constitution-only search.
- There is already an orchestration layer and multiple specialized agents.
- The workspace already includes guided launchers and case intelligence UI.
- Retrieval grounding, source metadata, confidence, and fallback behavior are already present.
- The project is demoable end-to-end and far beyond a toy prototype.

This is important: the problem is not that the project is weak. The problem is that legal realism and trust mechanics are still shallower than the architecture itself.

## 5. Main gaps between real legal work and the current platform

### Gap 1. The product still answers too much like an assistant and not enough like a legal analyst

Current state:

- Legal search retrieves sources and generates grounded answers.
- The system infers case topic and retrieves relevant code articles.

Missing:

- A strict lawyer-style reasoning sequence:
  issue -> governing rule -> source explanation -> application to case facts -> counterpoints -> next steps.
- Strong separation between confirmed facts and assumptions.

Impact:

- Answers may sound good without fully reflecting how lawyers think through a matter.

### Gap 2. Citations exist, but trust is still snippet-level more than article-level verification

Current state:

- The app returns citations and source metadata.
- Legal search warns against fabricated articles.

Missing:

- Strong article-by-article claim mapping.
- A visible "which sentence comes from which article" experience.
- A final validation step checking that quoted rule statements really match the retrieved article text.

Impact:

- The system is grounded, but not yet at the trust level a lawyer wants for filing, advising, or forwarding.

### Gap 3. The app is broad, but the workflow packs are still not lawyer-specific enough

Current state:

- You have many agents and workflow services.

Missing:

- Narrow legal workflows with dedicated UX for:
  legal issue memo, case-law/code comparison, article applicability review, succession entitlement analysis, international private law conflict analysis, litigation position memo.

Impact:

- The platform has lots of capability, but not enough productized "do this legal task" moments.

### Gap 4. Your legal search is code-aware, but not yet full legal-method aware

Current state:

- Legal search can infer case topic and scope code families.

Missing:

- Procedural posture awareness.
- Distinction between substantive law question and procedural law question.
- Explicit "missing facts that may change the legal result."
- Counter-analysis section.

Impact:

- The system retrieves relevant law, but still needs stronger legal reasoning discipline.

### Gap 5. The product has intelligence panels, but trust UX is still underdeveloped

Current state:

- The workspace shows risks, missing info, evidence, and timeline.

Missing:

- A dedicated trust panel showing:
  answer confidence, legal basis, missing facts, contradictions, and verification status.
- A lawyer-facing "before you rely on this" checklist.

Impact:

- The backend may know uncertainty, but the UI does not yet turn that into decision support.

### Gap 6. There is limited encoded process data from practicing lawyers

Current state:

- The platform uses prompts, heuristics, retrieval, and agents.

Missing:

- Decision trees from real lawyers:
  when to look for notice clauses, when to compare chronology, when to isolate dispositive facts, when to ask for missing documents.
- Jurisdiction-specific playbooks from the cabinet you are working with.

Impact:

- The system knows legal text, but not enough of the firm's working method.

## 6. Product direction that fits your target cabinet

Because the cabinet mainly cares about:

- Code civil
- Code de succession
- Code international prive

your best strategy is not to be "AI for all law."

Your best strategy is:

- be the most trustworthy Tunisian code-based legal copilot for private practice matters
- help the lawyer understand the matter first
- help the lawyer locate the right articles
- help the lawyer test whether those articles actually fit the facts
- help the lawyer see what facts are still missing
- help the lawyer produce a useful internal note or client-facing next step

That is a much sharper and more credible product.

## 7. Recommended target workflow for legal search

The ideal legal-search flow should be:

1. Intake the question and case facts.
2. Classify the matter:
   civil obligation, succession, international private law, mixed.
3. Extract the legal issue.
4. Retrieve the most relevant code articles.
5. Build the governing rule from those articles.
6. Compare the rule against known facts in the case.
7. Surface missing facts and alternate interpretations.
8. Produce practical next steps for the lawyer.
9. Offer one-click follow-ups:
   draft memo, ask for missing documents, compare alternative interpretations, prepare client explanation.

This is much closer to both the legal-practice material and Harvey's workflow philosophy.

## 8. Concrete roadmap

### Priority 1. Make every legal answer follow legal method

Implement a default answer structure:

- Issue
- Relevant articles
- Rule
- Application to known facts
- Missing facts / uncertainty
- Counter-analysis
- Practical next steps

Status after this session:

- backend legal-search prompting has been updated toward this structure

### Priority 2. Add a trust layer in the UI

Add a visible panel for:

- confidence
- source type
- code family
- missing facts
- contradictions
- verification status

### Priority 3. Build workflow packs instead of only modes

Best first workflow packs:

- Civil dispute analysis
- Succession distribution analysis
- International private law conflict screening
- Legal memo from case facts
- Article applicability review

### Priority 4. Capture cabinet process data

You should sit with the cabinet and ask:

1. When a new case arrives, what are the first five questions you ask?
2. What makes you decide a case is weak or strong?
3. Which missing documents block legal advice most often?
4. How do you structure an internal legal note?
5. Which articles do you check first for common matter types?

That process data is more valuable than adding more generic AI features.

### Priority 5. Strengthen article-level verification

Add:

- claim-to-article mapping
- article text verification before final answer
- lawyer-visible warning when support is partial

## 9. What "perfect" should mean for this project

For this project, "perfect" should not mean:

- the biggest number of AI agents
- the flashiest interface
- the longest answer

It should mean:

- a lawyer can trust the flow
- the answer is grounded in the right code family
- the system distinguishes law from assumptions
- missing facts are surfaced clearly
- the AI helps unblock the next legal step

That is the right standard.

## 10. Best next build sequence

Recommended implementation order:

1. Trust-first legal answer structure
2. Missing-facts and counter-analysis surfacing
3. Article-to-claim traceability
4. Workflow packs for the three target legal domains
5. Lawyer-reviewed playbooks from the cabinet
6. Personalized landing actions by matter type

If executed well, this will make the platform feel much closer to real legal work than a normal "chat with your files" product.
