"""Retrieve passages from a small synthetic scheduling handbook."""

from dataclasses import dataclass
import json
import os
import re
import sqlite3
from time import perf_counter
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Procedure:
    identifier: str
    title: str
    text: str


PROCEDURES = (
    Procedure("REM-01", "Reminder timing",
              "Send the first appointment reminder 48 hours before the visit. Skip appointments already cancelled."),
    Procedure("REM-02", "No answer",
              "If the patient does not answer a reminder call, record no contact. Make one retry on the next business day."),
    Procedure("REM-03", "Contact corrections",
              "If a telephone number is wrong, mark it unverified and send the correction request to Registration."),
    Procedure("RES-01", "Rescheduling requests",
              "Check the next available slot. Confirm the new slot before cancelling the original booking."),
    Procedure("CAN-01", "Cancellation requests",
              "Record the requested cancellation in scheduling and release the slot after confirmation."),
    Procedure("REV-01", "Reminder review queue",
              "Review the ten highest-scored booked appointments first. A coordinator reviews the list before any outreach."),
    Procedure("ERP-01", "Cost center mismatch",
              "If a department has no cost center mapping, route the correction to the Finance Systems team."),
    Procedure("SYS-01", "Scheduling feed outage",
              "When the scheduling feed is unavailable, mark the snapshot stale and alert the scheduling systems desk."),
    Procedure("EMR-01", "Appointment record mismatch",
              "If the scheduling record and appointment feed disagree, hold the record and ask Health Information Management to reconcile it."),
    Procedure("ACC-01", "Accessibility requests",
              "Route interpreter or wheelchair requests to Patient Access before the scheduled visit."),
)
STOP = set("a an and are at be can do does for how i if in is it of on or our should that the this to we what when where which who will with would you your".split())


def retrieve(question, limit=3):
    tokens = sorted(set(re.findall(r"[a-z0-9]+", question.casefold())) - STOP)
    if not tokens:
        return []
    query = " OR ".join(f'"{word}"' for word in tokens)
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE VIRTUAL TABLE handbook USING fts5(identifier UNINDEXED, title, body, tokenize='porter')")
        db.executemany("INSERT INTO handbook VALUES (?, ?, ?)", [
            (procedure.identifier, procedure.title, procedure.text) for procedure in PROCEDURES
        ])
        rows = db.execute(
            "SELECT identifier, title, body FROM handbook WHERE handbook MATCH ? ORDER BY bm25(handbook), identifier LIMIT ?",
            (query, limit),
        ).fetchall()
    return [Procedure(*row) for row in rows]


def completion(endpoint, system, message, max_tokens=80):
    if not endpoint:
        raise ValueError("Configure MODEL_URL to use the local language model.")
    payload = {
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": message}],
        "temperature": 0, "max_tokens": max_tokens, "seed": 581,
    }
    headers = {"Content-Type": "application/json"}
    if api_key := os.getenv("MODEL_API_KEY"):
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(
        endpoint.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode(), headers=headers,
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)["choices"][0]["message"]["content"].strip()


def abstention(reason):
    return {"answer": None, "citations": [], "reason": reason}


def grounded_answer(question, passages, endpoint):
    if not passages:
        return abstention("No relevant handbook passage was found.")
    system = """Answer questions using source text. Copy a short answer exactly from the text.
If the answer is missing, write UNKNOWN. For a yes/no question, copy the rule that answers it.
Text: The staff room opens at 7 a.m. Employees must sign in using a staff card.
Question: What time does the staff room open?
Answer: 7 a.m.
Text: Orders are shipped on Mondays. Paper invoices go to Accounting.
Question: How much does shipping cost?
Answer: UNKNOWN
Text: Volunteers must check in at the front desk. The desk closes at noon.
Question: Who must check in?
Answer: Volunteers"""
    prompt = " ".join(passage.text for passage in passages)
    raw = completion(endpoint, system, f"Text: {prompt}\nQuestion: {question}\nAnswer:", max_tokens=40)
    quote = raw.strip().strip('".').casefold()
    if quote.startswith("the "):
        quote = quote[4:]
    if len(quote) < 3 or quote in {"unknown", "yes", "no"}:
        return abstention("The handbook does not support an answer.")

    # Show the full evidence sentence, preserving its wording and context.
    pattern = re.compile(r"(?<!\w)" + re.escape(quote) + r"(?!\w)", re.IGNORECASE)
    matches = [
        (passage.identifier, sentence)
        for passage in passages
        for sentence in re.split(r"(?<=[.!?])\s+", passage.text)
        if pattern.search(sentence)
    ]
    if len(matches) != 1 or matches[0][0] != passages[0].identifier:
        return abstention("The model's answer could not be verified against the top handbook result.")
    identifier, sentence = matches[0]
    return {"answer": sentence, "citations": [identifier], "reason": None}


def evaluate(endpoint=None):
    from outpatient.questions import QUESTIONS

    modes = ["retrieval_only"] if not endpoint else ["retrieval_only", "model_only", "retrieval_augmented"]
    results = {mode: [] for mode in modes}
    for question, expected_id, expected_terms in QUESTIONS:
        retrieval_started = perf_counter()
        passages = retrieve(question)
        retrieval_ms = (perf_counter() - retrieval_started) * 1000
        for mode in modes:
            start = perf_counter()
            if mode == "retrieval_only":
                result = (
                    {"answer": passages[0].text, "citations": [passages[0].identifier]}
                    if passages else abstention("No relevant passage.")
                )
            elif mode == "model_only":
                answer = completion(endpoint, "Answer briefly. Say UNKNOWN whenever the answer is uncertain.", question)
                result = {"answer": None if answer.strip(".").upper() == "UNKNOWN" else answer, "citations": []}
            else:
                result = grounded_answer(question, passages, endpoint)
            elapsed = (perf_counter() - start) * 1000
            if mode != "model_only":
                elapsed += retrieval_ms
            elapsed = round(elapsed, 1)
            answer, citations = result["answer"], result["citations"]
            hit = bool(expected_id and any(p.identifier == expected_id for p in passages))
            correct = (
                answer is not None and all(term.casefold() in answer.casefold() for term in expected_terms)
                if expected_id else answer is None
            )
            results[mode].append({
                "question": question, "expected_source": expected_id, "expected_terms": expected_terms,
                "answer": answer, "citations": citations,
                "citation_on_target": bool(expected_id and expected_id in citations),
                "retrieval_hit_at_3": hit if mode != "model_only" and expected_id else None,
                "correct_by_expected_terms": correct, "abstained": answer is None, "response_ms": elapsed,
            })
    totals = {}
    for mode, rows in results.items():
        answerable = [row for row in rows if row["expected_source"]]
        latencies = sorted(row["response_ms"] for row in rows)
        totals[mode] = {
            "questions": len(rows), "answerable": len(answerable),
            "correct_by_expected_terms": sum(row["correct_by_expected_terms"] for row in rows),
            "correct_answerable": sum(row["correct_by_expected_terms"] for row in answerable),
            "correct_abstentions": sum(row["abstained"] and not row["expected_source"] for row in rows),
            "citation_on_target": sum(row["citation_on_target"] for row in rows),
            "retrieval_hits_at_3": None if mode == "model_only" else sum(row["retrieval_hit_at_3"] for row in answerable),
            "p50_response_ms": latencies[len(rows) // 2],
        }
    return {"summary": totals, "cases": results}
