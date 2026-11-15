"""Lecture des sources brutes (data/raw/) et conversion au schéma commun.

Aucun filtrage ici, hormis les entrées inexploitables (réponse absente) : la sélection, le
dédoublonnage et l'anonymisation se font en aval, pour garder des comptages traçables.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from triage.data.schema import DPORecord, Message, Metadata, SFTRecord, record_id
from triage.prompts import SYSTEM_PROMPT

RAW_DIR = Path("data/raw")
LETTERS = ("a", "b", "c", "d", "e")

MCQ_INSTRUCTION_FR = "Répondez en donnant la ou les bonnes propositions."


def _read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _clean(text: str) -> str:
    """Normalise les espaces sans toucher à la mise en forme en listes."""
    text = text.replace("\r\n", "\n").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _conversation(user: str) -> list[Message]:
    return [Message(role="system", content=SYSTEM_PROMPT), Message(role="user", content=user)]


def _mcq_record(
    *,
    source: str,
    source_id: str,
    split: str,
    license: str,
    context: str | None,
    question: str,
    options: dict[str, str],
    correct: list[str],
    subject: str | None,
    extra: dict,
) -> SFTRecord | None:
    options = {k: _clean(v) for k, v in options.items() if v and v.strip()}
    correct = sorted(c.lower() for c in correct)
    if not correct or any(c not in options for c in correct):
        return None
    parts = []
    if context and context.strip():
        parts.append(f"Cas clinique :\n{_clean(context)}")
    parts.append(f"Question : {_clean(question)}")
    parts.append("\n".join(f"{k.upper()}. {v}" for k, v in options.items()))
    parts.append(MCQ_INSTRUCTION_FR)
    label = "Bonne réponse" if len(correct) == 1 else "Bonnes réponses"
    answer = f"{label} : {', '.join(c.upper() for c in correct)}\n" + "\n".join(
        f"- {c.upper()}. {options[c]}" for c in correct
    )
    return SFTRecord(
        id=record_id(source, source_id),
        prompt=_conversation("\n\n".join(parts)),
        completion=[Message(role="assistant", content=answer)],
        metadata=Metadata(
            source=source,
            source_id=source_id,
            source_split=split,
            license=license,
            language="fr",
            task="qcm",
            confidence="reference",
            medical_subject=subject,
            extra=extra,
        ),
    )


def load_mediqal(raw_dir: Path = RAW_DIR) -> Iterator[SFTRecord]:
    """MediQAl : QCM à réponse unique (mcqu) et multiple (mcqm), avec ou sans cas clinique.

    Le sous-ensemble à questions ouvertes (oeq) n'existe qu'en test : il sert à l'évaluation.
    """
    for subset in ("mcqu", "mcqm"):
        for split in ("train", "validation", "test"):
            for row in _read_jsonl(raw_dir / "mediqal" / subset / f"{split}.json"):
                record = _mcq_record(
                    source="mediqal",
                    source_id=f"{subset}-{row['id']}",
                    split=split,
                    license="CC-BY-4.0",
                    context=row.get("clinical_case"),
                    question=row["question"],
                    options={k: row.get(f"answer_{k}") or "" for k in LETTERS},
                    correct=row["correct_answers"].split(","),
                    subject=row.get("medical_subject"),
                    extra={
                        "subset": subset,
                        "question_type": row.get("question_type"),
                        "has_clinical_case": bool((row.get("clinical_case") or "").strip()),
                    },
                )
                if record:
                    yield record


def load_frenchmedmcqa(raw_dir: Path = RAW_DIR) -> Iterator[SFTRecord]:
    """FrenchMedMCQA (DEFT 2023) : QCM de pharmacie, lus directement dans l'archive du dépôt."""
    splits = {"train": "train", "dev": "validation", "test": "test"}
    with zipfile.ZipFile(raw_dir / "frenchmedmcqa" / "DEFT-2023-FULL.zip") as archive:
        for filename, split in splits.items():
            for row in json.loads(archive.read(f"{filename}.json")):
                record = _mcq_record(
                    source="frenchmedmcqa",
                    source_id=row["id"],
                    split=split,
                    license="Apache-2.0",
                    context=None,
                    question=row["question"],
                    options=row["answers"],
                    correct=row["correct_answers"],
                    subject=row.get("subject_name"),
                    extra={"nbr_correct_answers": row.get("nbr_correct_answers")},
                )
                if record:
                    yield record


def load_medquad(raw_dir: Path = RAW_DIR) -> Iterator[SFTRecord]:
    """MedQuAD : questions-réponses issues de 12 sites des NIH.

    Les sous-corpus MedlinePlus ADAM, Drugs et Herbs n'ont pas de réponse (retirées pour respecter
    le copyright) : ils sont ignorés.
    """
    seen: Counter[str] = Counter()
    for path in sorted((raw_dir / "medquad").glob("*/*.xml")):
        root = ET.parse(path).getroot()
        focus = _clean(root.findtext("Focus") or "")
        # L'attribut id manque dans certains sous-corpus : le nom de fichier est unique.
        document_id = f"{path.parent.name}/{path.stem}"
        for pair in root.iter("QAPair"):
            answer = _clean(pair.findtext("Answer") or "")
            question = pair.find("Question")
            if not answer or question is None or not (question.text or "").strip():
                continue
            # Les qid repartent de 1 dans chaque sous-corpus : on les préfixe.
            qid = f"{path.parent.name}/{question.get('qid') or path.stem + '-' + pair.get('pid')}"
            # Quelques documents réutilisent un même qid pour des questions différentes.
            seen[qid] += 1
            if seen[qid] > 1:
                qid = f"{qid}#{seen[qid]}"
            yield SFTRecord(
                id=record_id("medquad", qid),
                prompt=_conversation(_clean(question.text)),
                completion=[Message(role="assistant", content=answer)],
                metadata=Metadata(
                    source="medquad",
                    source_id=qid,
                    license="CC-BY-4.0",
                    language="en",
                    task="qa",
                    confidence="reference",
                    medical_subject=focus or None,
                    extra={
                        "subset": path.parent.name,
                        "document_id": document_id,
                        "qtype": question.get("qtype"),
                        "url": root.get("url"),
                    },
                ),
            )


def load_ultramedical(raw_dir: Path = RAW_DIR) -> Iterator[DPORecord]:
    """UltraMedical-Preference : paires de préférences en anglais.

    Chaque fichier est lu séparément : test.json n'a pas la colonne « feedback ». La question,
    répétée dans « chosen » et « rejected », n'est gardée que dans le prompt.
    """
    splits = {"train": "train", "dev": "validation", "test": "test"}
    # Un même prompt_id porte souvent plusieurs paires (types différents) : on les numérote.
    seen: Counter[str] = Counter()
    for filename, split in splits.items():
        path = raw_dir / "ultramedical_preference" / "data" / f"{filename}.json"
        for row in json.loads(path.read_text(encoding="utf-8")):
            chosen = _clean(row["chosen"][-1]["content"])
            rejected = _clean(row["rejected"][-1]["content"])
            prompt = _clean(row["prompt"])
            if not (chosen and rejected and prompt) or chosen == rejected:
                continue
            meta = row.get("metadata") or {}
            chosen_meta = meta.get("chosen") or {}
            rejected_meta = meta.get("rejected") or {}
            label_type = row["label_type"]
            occurrence = f"{split}|{row['prompt_id']}"
            seen[occurrence] += 1
            yield DPORecord(
                id=record_id("ultramedical", row["prompt_id"], f"{occurrence}|{seen[occurrence]}"),
                prompt=_conversation(prompt),
                chosen=[Message(role="assistant", content=chosen)],
                rejected=[Message(role="assistant", content=rejected)],
                metadata=Metadata(
                    source="ultramedical_preference",
                    source_id=row["prompt_id"],
                    source_split=split,
                    license="MIT",
                    language="en",
                    task="preference",
                    confidence="human_preference" if label_type == "human" else "model_judged",
                    extra={
                        "label_type": label_type,
                        "prompt_source": row["prompt_id"].split(",")[0],
                        "chosen_model": chosen_meta.get("model"),
                        "rejected_model": rejected_meta.get("model"),
                        "chosen_score": chosen_meta.get("score"),
                        "rejected_score": rejected_meta.get("score"),
                    },
                ),
            )
