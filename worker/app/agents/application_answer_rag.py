"""Small, transparent retrieval layer for application-question answering.

Candidate facts are retrieved only from the verified career profile and tailored resume.
The stored job analysis is context for interpreting what a question means, never evidence
that the candidate has a skill or experience.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


MAX_JOB_DESCRIPTION_CHARS = 5000
MAX_CONTEXT_LIST_ITEMS = 15
DEFAULT_TOP_K = 8

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by", "can",
    "could", "did", "do", "does", "for", "from", "had", "has", "have", "how",
    "i", "in", "into", "is", "it", "its", "me", "my", "of", "on", "or", "our",
    "please", "role", "the", "their", "them", "there", "these", "they", "this",
    "to", "us", "was", "we", "were", "what", "when", "where", "which", "who",
    "why", "will", "with", "would", "you", "your", "years", "year", "experience",
    "describe", "explain", "tell", "about",
}

# These expansions help bridge wording differences between a form question and a resume.
# They are retrieval hints only; they do not establish that the candidate has the skill.
QUERY_EXPANSIONS = {
    "distributed systems": (
        "microservices", "event driven", "event-driven", "messaging", "kafka",
        "distributed architecture", "scalability", "fault tolerance",
    ),
    "microservices": (
        "distributed systems", "service architecture", "spring boot", "event driven",
    ),
    "system design": (
        "architecture", "scalable", "high availability", "distributed systems",
        "services", "components", "tradeoffs",
    ),
    "architecture": (
        "system design", "technical design", "distributed systems", "microservices",
        "platform design",
    ),
    "leadership": (
        "led", "mentored", "guided", "managed", "technical direction", "ownership",
        "cross functional", "cross-team",
    ),
    "performance": (
        "latency", "throughput", "optimization", "scaling", "load", "capacity",
    ),
    "reliability": (
        "availability", "resilience", "fault tolerance", "monitoring", "recovery",
        "production support",
    ),
    "cloud": ("gcp", "google cloud", "aws", "azure", "kubernetes", "docker"),
    "data pipeline": ("kafka", "streaming", "event processing", "etl", "batch processing"),
    "api": ("rest", "graphql", "service integration", "backend"),
}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _tokens(value: str) -> list[str]:
    raw = re.findall(r"[a-z0-9][a-z0-9+#.-]*", _clean(value).lower())
    tokens = []
    for token in raw:
        token = token.strip(".-")
        if len(token) < 2 or token in STOPWORDS:
            continue
        tokens.append(token)
        # A small suffix normalizer handles common resume/question wording differences.
        if len(token) > 5 and token.endswith("ing"):
            tokens.append(token[:-3])
        elif len(token) > 4 and token.endswith("ies"):
            tokens.append(token[:-3] + "y")
        elif len(token) > 4 and token.endswith("ed"):
            tokens.append(token[:-2])
        elif len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
            tokens.append(token[:-1])
    return tokens


def build_job_context(raw_context: dict | None) -> dict:
    """Whitelist and bound the job data used to interpret question intent."""
    raw = raw_context or {}
    job = raw.get("job") if isinstance(raw.get("job"), dict) else raw
    requirements = raw.get("requirements") if isinstance(raw.get("requirements"), dict) else {}

    def list_value(key: str) -> list[str]:
        value = requirements.get(key) or []
        if isinstance(value, str):
            value = [value]
        return [_clean(item)[:300] for item in value if _clean(item)][:MAX_CONTEXT_LIST_ITEMS]

    description = _clean(job.get("description"))[:MAX_JOB_DESCRIPTION_CHARS]
    visual = raw.get("visual_inspection") if isinstance(raw.get("visual_inspection"), dict) else {}
    findings = visual.get("findings") or []
    if isinstance(findings, str):
        findings = [findings]

    return {
        "title": _clean(job.get("title"))[:240],
        "company": _clean(job.get("company"))[:180],
        "location": _clean(job.get("location"))[:180],
        "summary": _clean(requirements.get("summary"))[:1200],
        "responsibilities": list_value("responsibilities"),
        "required_skills": list_value("required_skills"),
        "preferred_skills": list_value("preferred_skills"),
        "qualifications": list_value("qualifications"),
        "employment_type": _clean(requirements.get("employment_type"))[:120],
        "salary_range": _clean(requirements.get("salary_range"))[:120],
        "description_excerpt": description,
        "visual_findings": [_clean(item)[:300] for item in findings if _clean(item)][:8],
    }


def _weighted_query(question: dict, job_context: dict) -> dict[str, float]:
    question_text = " ".join((
        _clean(question.get("question")),
        _clean(question.get("classification")).replace("_", " "),
    ))
    query: dict[str, float] = {}
    for token in set(_tokens(question_text)):
        query[token] = max(query.get(token, 0.0), 1.0)

    question_lower = question_text.lower()
    for phrase, expansions in QUERY_EXPANSIONS.items():
        if phrase in question_lower:
            for token in set(_tokens(" ".join(expansions))):
                query[token] = max(query.get(token, 0.0), 0.65)

    # For broad questions, job requirements help identify which candidate evidence matters.
    # Their weight is intentionally low and they are never placed in the candidate evidence set.
    broad_question = len(query) <= 5 or any(
        phrase in question_lower
        for phrase in ("this role", "this position", "relevant experience", "fit for")
    )
    if broad_question:
        role_text = " ".join([
            job_context.get("title", ""),
            job_context.get("summary", ""),
            " ".join(job_context.get("required_skills", [])),
            " ".join(job_context.get("responsibilities", [])),
        ])
        for token in set(_tokens(role_text)):
            query[token] = max(query.get(token, 0.0), 0.25)
    return query


def retrieve_question_evidence(
    question: dict,
    candidate_evidence: list[dict],
    job_context: dict | None = None,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> dict:
    """Rank candidate-only evidence snippets for one question using a BM25-style scorer."""
    context = build_job_context(job_context)
    query = _weighted_query(question, context)
    docs = []
    document_frequency: Counter[str] = Counter()
    total_length = 0

    for item in candidate_evidence or []:
        text = _clean(item.get("text") or item.get("detail"))
        if not text:
            continue
        tokens = _tokens(text)
        if not tokens:
            continue
        counts = Counter(tokens)
        document_frequency.update(counts.keys())
        total_length += len(tokens)
        docs.append((item, tokens, counts))

    if not docs or not query:
        return {
            "question": _clean(question.get("question")),
            "items": [],
            "retrieved_count": 0,
            "query_terms": sorted(query),
            "job_context": context,
        }

    count = len(docs)
    average_length = max(1.0, total_length / count)
    scored = []
    k1 = 1.5
    b = 0.75

    for item, tokens, counts in docs:
        score = 0.0
        length_factor = k1 * (1 - b + b * len(tokens) / average_length)
        for term, weight in query.items():
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            inverse_frequency = math.log(
                1 + (count - document_frequency[term] + 0.5)
                / (document_frequency[term] + 0.5)
            )
            score += weight * inverse_frequency * (
                frequency * (k1 + 1) / (frequency + length_factor)
            )

        question_phrase = " ".join(_tokens(_clean(question.get("question"))))
        normalized_text = " ".join(tokens)
        if len(question_phrase) > 8 and question_phrase in normalized_text:
            score += 2.0

        path = _clean(item.get("path")).lower()
        if any(section in path for section in ("experience", "projects", "certifications", "education")):
            score *= 1.12
        if _clean(item.get("source")) == "tailored_resume":
            score *= 1.04

        if score > 0:
            scored.append((score, item))

    scored.sort(
        key=lambda pair: (
            pair[0],
            _clean(pair[1].get("source")) == "verified_profile",
            _clean(pair[1].get("path")),
        ),
        reverse=True,
    )

    selected = []
    seen_ids = set()
    for score, item in scored:
        evidence_id = _clean(item.get("id"))
        if not evidence_id or evidence_id in seen_ids:
            continue
        seen_ids.add(evidence_id)
        selected.append({
            "id": evidence_id,
            "source": _clean(item.get("source")),
            "path": _clean(item.get("path")),
            "text": _clean(item.get("text") or item.get("detail"))[:900],
            "retrieval_score": round(score, 4),
        })
        if len(selected) >= max(1, min(int(top_k), 12)):
            break

    return {
        "question": _clean(question.get("question")),
        "items": selected,
        "retrieved_count": len(selected),
        "query_terms": sorted(query),
        "job_context": context,
    }
