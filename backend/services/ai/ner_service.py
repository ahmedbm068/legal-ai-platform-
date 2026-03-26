import spacy

nlp = spacy.load("en_core_web_sm")


def extract_entities(text: str) -> list[dict]:
    if not text:
        return []

    doc = nlp(text)
    entities = []
    seen = set()

    for ent in doc.ents:
        normalized_value = ent.text.strip()
        if not normalized_value:
            continue

        key = (ent.label_, normalized_value, ent.start_char, ent.end_char)
        if key in seen:
            continue
        seen.add(key)

        entities.append({
            "label": ent.label_,
            "value": normalized_value,
            "start_char": ent.start_char,
            "end_char": ent.end_char
        })

    return entities