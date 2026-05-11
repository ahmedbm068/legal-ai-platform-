"""End-to-end test for the semantic cache.

What this does
--------------
1. Loads ``paraphrase-multilingual-MiniLM-L12-v2`` (the cache embedder).
2. Embeds a battery of legal-question paraphrase pairs across
   French / English / Arabic.
3. Computes cosine similarity for each pair.
4. Tells you:
     * Which pairs HIT at the current threshold (0.95).
     * Which pairs would HIT at a lower threshold (0.90, 0.85).
     * Which "negative pairs" (different legal questions that share
       keywords) would FALSE-HIT and at which threshold.
5. Recommends a threshold value.

Run::

    python scripts/test_semantic_cache.py

Takes ~60 seconds the first time (model download), <5 seconds after.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    sys.exit("missing dependency 'sentence-transformers' — install with: pip install sentence-transformers")


MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

# (label, question_a, question_b)  — these SHOULD hit (same question, different phrasing/language).
POSITIVE_PAIRS = [
    # — Same language, paraphrased —
    ("FR-FR (case summary)",
     "résume ce dossier",
     "donne-moi un résumé du dossier"),
    ("FR-FR (heir share)",
     "quelle est la part de la fille dans une succession",
     "quel pourcentage hérite la fille"),
    ("EN-EN (case summary)",
     "summarize this case",
     "give me a summary of this case"),
    ("EN-EN (article lookup)",
     "what does article 100 of the CSP say",
     "explain article 100 of the Tunisian personal status code"),
    ("AR-AR (case summary)",
     "لخص هذه القضية",
     "أعطني ملخص للقضية"),
    ("DE-DE (BGB lookup)",
     "was sagt § 1922 BGB",
     "erkläre mir Paragraph 1922 BGB"),

    # — Cross-language, same question (the headline demo) —
    ("FR-EN (case summary)",
     "résume ce dossier",
     "summarize this case"),
    ("AR-FR (case summary)",
     "لخص هذه القضية",
     "résume ce dossier"),
    ("AR-EN (case summary)",
     "لخص هذه القضية",
     "summarize this case"),
    ("FR-EN (heir share)",
     "quelle est la part de la fille",
     "what is the daughter's share"),
    ("AR-FR (inheritance)",
     "كيف يتم تقسيم الإرث بين الأبناء والبنات",
     "comment se répartit l'héritage entre fils et filles"),
]


# (label, question_a, question_b)  — these MUST NOT hit (different questions, may share keywords).
NEGATIVE_PAIRS = [
    ("Mother vs wife share",
     "quelle est la part de la mère",
     "quelle est la part de la femme"),
    ("Sons vs daughters",
     "quelle est la part des fils",
     "quelle est la part des filles"),
    ("Tunisia succession vs Germany succession",
     "succession tunisienne",
     "deutsches Erbrecht"),
    ("Summarize vs analyze",
     "résume ce dossier",
     "analyse les risques de ce dossier"),
    ("Different articles",
     "que dit l'article 100 du CSP",
     "que dit l'article 152 du CSP"),
    ("Different cases — same question shape",
     "résume le dossier 24",
     "résume le dossier 99"),
    ("Inheritance vs divorce",
     "comment fonctionne l'héritage en Tunisie",
     "comment fonctionne le divorce en Tunisie"),
    ("Article lookup vs general topic",
     "que dit l'article 100 du CSP",
     "donne-moi un cours sur le droit successoral tunisien"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def cosine(vec_a, vec_b) -> float:
    """Normalised vectors → cosine == dot product, but be defensive."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return dot / (norm_a * norm_b)


def load_model() -> SentenceTransformer:
    print(f"Loading {MODEL_NAME} ...")
    t0 = time.monotonic()
    model = SentenceTransformer(MODEL_NAME)
    print(f"  loaded in {time.monotonic() - t0:.1f}s\n")
    return model


def score_pairs(model: SentenceTransformer, pairs):
    """Embed and score every pair, return list of (label, score)."""
    questions = [q for triple in pairs for q in (triple[1], triple[2])]
    embeddings = model.encode(questions, normalize_embeddings=True, convert_to_numpy=True)
    embeddings = embeddings.tolist()
    out = []
    for i, (label, _, _) in enumerate(pairs):
        score = cosine(embeddings[2 * i], embeddings[2 * i + 1])
        out.append((label, score))
    return out


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report(title, scored_pairs, *, expect_hit: bool, thresholds=(0.95, 0.90, 0.85, 0.80)):
    print("=" * 78)
    print(title)
    print("=" * 78)
    print(f"{'pair':<48s} {'cosine':>8s}   verdict at thresholds")
    print(f"{'':<48s} {'':>8s}   " + "  ".join(f"{t:.2f}" for t in thresholds))
    print("-" * 78)
    for label, score in scored_pairs:
        verdicts = []
        for t in thresholds:
            hit = score >= t
            ok = (hit == expect_hit)
            mark = "✅" if ok else "❌"
            verdicts.append(f"{mark}{'H' if hit else 'M'}")
        print(f"{label[:48]:<48s} {score:>8.4f}   " + "  ".join(f"{v:>4s}" for v in verdicts))
    print()


def recommend_threshold(positive_scores, negative_scores):
    """Pick the highest threshold that still catches all positives.
    If that threshold also rejects all negatives → great.
    If not, pick the lowest threshold that rejects all negatives → safest.
    """
    pos = sorted(s for _, s in positive_scores)
    neg = sorted((s for _, s in negative_scores), reverse=True)

    min_pos = pos[0] if pos else 0.0
    max_neg = neg[0] if neg else 0.0

    print("=" * 78)
    print("THRESHOLD RECOMMENDATION")
    print("=" * 78)
    print(f"lowest positive (must HIT):  {min_pos:.4f}")
    print(f"highest negative (must MISS): {max_neg:.4f}")
    print()

    if min_pos > max_neg:
        # Clean separation — there's a band that classifies everything correctly.
        chosen = round((min_pos + max_neg) / 2, 2)
        print(f"✅ clean separation — threshold {chosen} catches every positive")
        print(f"   and rejects every negative.")
        print()
        print(f"   Set in semantic_cache_service.py:")
        print(f"     DEFAULT_SIMILARITY_THRESHOLD = {chosen}")
    else:
        print(f"⚠ no perfect threshold exists for these examples.")
        print(f"   Some negatives score higher ({max_neg:.4f}) than the weakest positive ({min_pos:.4f}).")
        print()
        # Choose: maximise true negatives (safety) at the cost of some misses.
        safe_threshold = round(max_neg + 0.01, 2)
        print(f"   Safer choice (zero false hits, may miss cross-lingual paraphrases):")
        print(f"     DEFAULT_SIMILARITY_THRESHOLD = {safe_threshold}")
        # Choose: maximise true positives (recall) at the cost of some false hits.
        recall_threshold = round(min_pos - 0.01, 2)
        print(f"   Recall choice (catches all paraphrases, may merge a few similar questions):")
        print(f"     DEFAULT_SIMILARITY_THRESHOLD = {recall_threshold}")
        print()
        print("   For a legal product, prefer the SAFER threshold.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    model = load_model()

    print(f"Scoring {len(POSITIVE_PAIRS)} POSITIVE pairs (should HIT)...")
    pos_scored = score_pairs(model, POSITIVE_PAIRS)
    print(f"Scoring {len(NEGATIVE_PAIRS)} NEGATIVE pairs (should MISS)...\n")
    neg_scored = score_pairs(model, NEGATIVE_PAIRS)

    report("POSITIVE PAIRS — these MUST HIT (✅H = correct hit, ❌M = false miss)",
           pos_scored, expect_hit=True)
    report("NEGATIVE PAIRS — these MUST MISS (✅M = correct miss, ❌H = false hit)",
           neg_scored, expect_hit=False)

    recommend_threshold(pos_scored, neg_scored)
    return 0


if __name__ == "__main__":
    sys.exit(main())
