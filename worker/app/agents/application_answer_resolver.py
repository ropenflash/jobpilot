import re
from difflib import SequenceMatcher
from datetime import date, datetime
from typing import Any


TECHNOLOGY_PATTERNS = {
    "java": re.compile(r"\bjava\b|\bjdk\b|\bj2se\b", re.I),
    "spring_boot": re.compile(r"\bspring\s*boot\b|\bspringboot\b", re.I),
    "microservices": re.compile(r"\bmicroservices?\b", re.I),
    "kafka": re.compile(r"\bkafka\b", re.I),
    "gcp": re.compile(r"\bgcp\b|\bgoogle\s+cloud(?:\s+platform)?\b", re.I),
}

TECH_PROFILE_KEYS = {
    "java": "java_experience_years",
    "spring_boot": "spring_boot_experience_years",
    "microservices": "microservices_experience_years",
    "kafka": "kafka_experience_years",
    "gcp": "gcp_experience_years",
}

PROFILE_FIELD_LABELS = {
    "phone": "Phone number",
    "city": "City / location",
    "java_experience_years": "Java experience (years)",
    "spring_boot_experience_years": "Spring Boot experience (years)",
    "microservices_experience_years": "Microservices experience (years)",
    "kafka_experience_years": "Kafka experience (years)",
    "gcp_experience_years": "GCP experience (years)",
    "official_notice_period": "Official notice period",
    "currently_serving_notice": "Whether you are currently serving notice",
    "official_last_working_day": "Official last working day",
    "join_availability": "Joining availability",
    "current_ctc_lpa": "Current annual CTC (LPA)",
    "expected_ctc_lpa": "Expected annual CTC (LPA)",
}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    match = re.search(r"(?<!\w)(\d+(?:\.\d+)?)", str(value).replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _format_years(value: float) -> str:
    rounded = round(value, 1)
    if rounded.is_integer():
        return f"{int(rounded)} years"
    return f"{rounded:g} years"


def _month_index(value: str, *, is_end: bool = False) -> int | None:
    text = _clean(value).lower()
    if not text:
        return None
    if text in {"present", "current", "currently", "now", "ongoing", "till date", "to date"}:
        today = date.today()
        return today.year * 12 + today.month - 1

    iso_year_month = re.match(
        r"^(19\d{2}|20\d{2})[-/.](0?[1-9]|1[0-2])(?:[-/.]\d{1,2})?$",
        text,
    )
    if iso_year_month:
        return int(iso_year_month.group(1)) * 12 + int(iso_year_month.group(2)) - 1

    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if not year_match:
        return None
    year = int(year_match.group(1))

    month_match = re.search(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
        r"aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
        text,
        re.I,
    )
    if month_match:
        token = month_match.group(1)[:3].lower()
        month = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }[token]
    else:
        numeric_month = re.search(r"\b(?:0?[1-9]|1[0-2])[/.-](?:19|20)\d{2}\b", text)
        if numeric_month:
            month = int(re.split(r"[/.-]", numeric_month.group(0))[0])
        else:
            month = 12 if is_end else 1
    return year * 12 + month - 1


def _merge_month_ranges(ranges: list[tuple[int, int]]) -> int:
    if not ranges:
        return 0
    ranges = sorted(ranges)
    total = 0
    current_start, current_end = ranges[0]
    for start, end in ranges[1:]:
        if start <= current_end + 1:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start + 1
            current_start, current_end = start, end
    return total + current_end - current_start + 1


def _direct_technology_years(profile: dict, technology: str) -> tuple[float | None, str | None]:
    key = TECH_PROFILE_KEYS[technology]
    aliases = [key]
    nested = profile.get("technology_experience_years")
    if isinstance(nested, dict):
        aliases.extend([
            _clean(technology),
            technology.replace("_", ""),
            "springboot" if technology == "spring_boot" else technology,
        ])
    for alias in aliases:
        value = nested.get(alias) if alias != key and isinstance(nested, dict) else profile.get(alias)
        number = _number(value)
        if number is not None:
            return number, key if alias == key else f"technology_experience_years.{alias}"
    return None, None


def _inferred_technology_years(
    profile: dict,
    technology: str,
    evidence: list[dict],
) -> tuple[float | None, list[str]]:
    pattern = TECHNOLOGY_PATTERNS[technology]
    ranges = []
    refs = []
    for index, role in enumerate(profile.get("experience") or []):
        if not isinstance(role, dict):
            continue
        technologies = role.get("technologies") or []
        if isinstance(technologies, str):
            technologies = [technologies]
        searchable = " ".join([
            _clean(role.get("title")),
            _clean(role.get("description")),
            " ".join(_clean(item) for item in technologies),
        ])
        if not pattern.search(searchable):
            continue
        start = _month_index(_clean(role.get("start_date")))
        end = _month_index(_clean(role.get("end_date")), is_end=True)
        if start is None or end is None or end < start:
            continue
        ranges.append((start, end))
        for path in (
            f"experience[{index}].start_date",
            f"experience[{index}].end_date",
            f"experience[{index}].description",
            f"experience[{index}].technologies",
        ):
            ref = f"verified_profile:{path}"
            if any(item["id"] == ref for item in evidence):
                refs.append(ref)
    total_months = _merge_month_ranges(ranges)
    if not total_months:
        return None, []
    return round(total_months / 12, 1), list(dict.fromkeys(refs))


def _profile_evidence(refs: list[str], evidence: list[dict]) -> list[dict]:
    by_id = {item["id"]: item for item in evidence}
    return [
        {
            "source": by_id[ref]["source"],
            "path": by_id[ref]["path"],
            "detail": by_id[ref]["text"],
        }
        for ref in refs if ref in by_id
    ]


def _make_result(
    question: dict,
    *,
    status: str,
    reason: str,
    answer: str | None = None,
    evidence_refs: list[str] | None = None,
    evidence: list[dict] | None = None,
    missing_fields: list[str] | None = None,
    profile_improvement: str | None = None,
    answer_basis: str | None = None,
) -> dict:
    missing_fields = list(dict.fromkeys(missing_fields or []))
    required_missing_fields = missing_fields if question.get("required", True) else []
    return {
        "field_index": question["field_index"],
        "question": question["question"],
        "category": question["classification"],
        "evidence_status": status,
        "reason": reason,
        "evidence": _profile_evidence(evidence_refs or [], evidence or []),
        "suggested_answer": answer,
        "profile_improvement": profile_improvement,
        "needs_profile_update": bool(required_missing_fields),
        "profile_fields_needed": required_missing_fields,
        "answer_basis": answer_basis,
    }


def _resolve_technology_question(question: dict, profile: dict, evidence: list[dict]) -> dict | None:
    classification = question["classification"]
    mapping = {
        "years_java": ["java"],
        "years_spring_boot_microservices": ["spring_boot", "microservices"],
        "years_spring_boot": ["spring_boot"],
        "years_microservices": ["microservices"],
        "years_kafka": ["kafka"],
        "years_gcp": ["gcp"],
    }
    technologies = mapping.get(classification)
    if not technologies:
        return None

    resolved = {}
    missing = []
    evidence_refs = []
    bases = []
    for technology in technologies:
        years, source_path = _direct_technology_years(profile, technology)
        basis = "candidate-provided profile duration"
        refs = [f"verified_profile:{source_path}"] if source_path else []
        if years is None:
            years, refs = _inferred_technology_years(profile, technology, evidence)
            basis = "approximate calculation from dated roles that explicitly mention this technology"
        if years is None:
            missing.append(TECH_PROFILE_KEYS[technology])
        else:
            resolved[technology] = years
            evidence_refs.extend(refs)
            bases.append(basis)

    if missing:
        available = ", ".join(
            f"{technology.replace('_', ' ').title()}: {_format_years(years)}"
            for technology, years in resolved.items()
        )
        details = f" Available evidence: {available}." if available else ""
        missing_labels = [PROFILE_FIELD_LABELS[key] for key in missing]
        return _make_result(
            question,
            status="partial" if resolved else "not_found",
            reason=(
                "JobPilot could not establish every requested technology duration from verified profile data "
                "or dated work-history evidence." + details
            ),
            evidence_refs=evidence_refs,
            evidence=evidence,
            missing_fields=missing,
            profile_improvement=(
                "Add your actual years of experience for " + ", ".join(missing_labels)
                + " in the Application-specific details section of your career profile."
            ),
            answer_basis="Partial duration evidence; confirm all values before using them.",
        )

    if len(technologies) == 2:
        answer = (
            f"Spring Boot: {_format_years(resolved['spring_boot'])}; "
            f"Microservices: {_format_years(resolved['microservices'])}"
        )
    else:
        answer = _format_years(resolved[technologies[0]])
    basis = " and ".join(dict.fromkeys(bases))
    reason = (
        "Duration supplied in your verified profile."
        if all("candidate-provided" in item for item in bases)
        else "Approximate duration calculated from dated roles that explicitly mention the technology; overlapping roles were counted once."
    )
    return _make_result(
        question,
        status="supported",
        reason=reason,
        answer=answer,
        evidence_refs=evidence_refs,
        evidence=evidence,
        answer_basis=basis,
    )


def _resolve_profile_question(question: dict, profile: dict, evidence: list[dict]) -> dict | None:
    classification = question["classification"]
    if classification in {
        "years_java", "years_spring_boot_microservices", "years_spring_boot",
        "years_microservices", "years_kafka", "years_gcp",
    }:
        return _resolve_technology_question(question, profile, evidence)

    def value_for(keys: list[str]) -> tuple[str, str | None]:
        for key in keys:
            value = _clean(profile.get(key))
            if value:
                return value, key
        return "", None

    if classification == "phone":
        value, key = value_for(["phone", "mobile", "phone_number"])
        if not value:
            missing = ["phone"]
            return _make_result(
                question, status="not_found", reason="No phone number exists in the verified profile.",
                missing_fields=missing, evidence=evidence,
                profile_improvement="Add your reachable phone number to the career profile.",
            )
        return _make_result(
            question, status="supported", reason="Read from your verified career profile.",
            answer=value, evidence_refs=[f"verified_profile:{key}"], evidence=evidence,
            answer_basis="verified profile",
        )

    if classification == "city":
        city, key = value_for(["city", "location_city"])
        if not city:
            location, location_key = value_for(["location"])
            parts = [part.strip() for part in re.split(r"[,|]", location) if part.strip()]
            if len(parts) >= 2:
                city, key = parts[0], location_key
        if not city:
            return _make_result(
                question, status="not_found", reason="The verified profile does not identify a city clearly.",
                missing_fields=["city", "location"],
                evidence=evidence,
                profile_improvement="Add your city explicitly (for example, Greater Noida) in the career profile. Do not rely on a state or country-only location.",
            )
        return _make_result(
            question, status="supported", reason="Read from the city or multi-part location in your verified profile.",
            answer=city, evidence_refs=[f"verified_profile:{key}"], evidence=evidence,
            answer_basis="verified profile",
        )

    if classification == "unlabelled_field":
        return _make_result(
            question, status="manual_review",
            reason="The application exposes a required control without an accessible question label. JobPilot cannot determine what it asks. Inspect this control in Chromium and answer it yourself.",
            evidence=evidence,
            profile_improvement="No profile update can safely resolve an unidentified field. Inspect the corresponding control in the employer form.",
        )

    if classification == "notice_period":
        notice, notice_key = value_for(["official_notice_period", "notice_period", "notice_period_days"])
        serving, serving_key = value_for(["currently_serving_notice", "serving_notice"])
        last_day, last_day_key = value_for(["official_last_working_day", "last_working_day"])
        missing = []
        if not notice:
            missing.append("official_notice_period")
        if not serving:
            missing.append("currently_serving_notice")
        if serving.lower() in {"yes", "true", "1", "serving"} and not last_day:
            missing.append("official_last_working_day")
        if missing:
            labels = [PROFILE_FIELD_LABELS.get(key, key) for key in missing]
            return _make_result(
                question, status="partial" if notice or serving else "not_found",
                reason="Notice-period details are incomplete. JobPilot needs your official notice period and whether you are currently serving it.",
                answer=(
                    f"Official notice period: {notice}. Currently serving notice: {serving}."
                    if notice and serving else None
                ),
                evidence_refs=[
                    f"verified_profile:{notice_key}" if notice_key else "",
                    f"verified_profile:{serving_key}" if serving_key else "",
                ],
                evidence=evidence,
                missing_fields=missing,
                profile_improvement="Complete these profile fields: " + ", ".join(labels) + ".",
            )
        answer = f"Official notice period: {notice}. Currently serving notice: {serving}."
        refs = [f"verified_profile:{notice_key}", f"verified_profile:{serving_key}"]
        if serving.lower() in {"yes", "true", "1", "serving"}:
            answer += f" Official last working day: {last_day}."
            refs.append(f"verified_profile:{last_day_key}")
        return _make_result(
            question, status="supported", reason="Notice details are read from your verified profile.",
            answer=answer, evidence_refs=refs, evidence=evidence, answer_basis="verified profile",
        )

    if classification == "last_working_day":
        serving, serving_key = value_for(["currently_serving_notice", "serving_notice"])
        last_day, last_day_key = value_for(["official_last_working_day", "last_working_day"])
        if serving.lower() in {"no", "false", "0", "not serving"}:
            return _make_result(
                question, status="supported", reason="Your profile says you are not currently serving notice.",
                answer="Not currently serving notice.", evidence_refs=[f"verified_profile:{serving_key}"],
                evidence=evidence, answer_basis="verified profile",
            )
        if serving.lower() in {"yes", "true", "1", "serving"} and last_day:
            return _make_result(
                question, status="supported", reason="Read from your verified profile.",
                answer=last_day, evidence_refs=[f"verified_profile:{serving_key}", f"verified_profile:{last_day_key}"],
                evidence=evidence, answer_basis="verified profile",
            )
        missing = ["currently_serving_notice"]
        if serving.lower() in {"yes", "true", "1", "serving"} and not last_day:
            missing = ["official_last_working_day"]
        return _make_result(
            question, status="not_found", reason="JobPilot cannot establish whether you are serving notice or your official last working day.",
            evidence=evidence, missing_fields=missing,
            profile_improvement="Confirm your notice status and, only if currently serving notice, enter your official last working day.",
        )

    if classification == "join_availability":
        availability, availability_key = value_for(["join_availability", "availability_to_join"])
        if availability:
            return _make_result(
                question, status="supported", reason="Read from your explicit joining-availability profile entry.",
                answer=availability, evidence_refs=[f"verified_profile:{availability_key}"],
                evidence=evidence, answer_basis="candidate-confirmed availability",
            )
        serving, serving_key = value_for(["currently_serving_notice", "serving_notice"])
        last_day, last_day_key = value_for(["official_last_working_day", "last_working_day"])
        if serving.lower() in {"yes", "true", "1", "serving"} and last_day:
            return _make_result(
                question, status="partial",
                reason="Your recorded last working day is available. The date is a lower bound; confirm the actual joining date and any release or handover constraints.",
                answer=f"After official last working day ({last_day}), subject to release formalities.",
                evidence_refs=[f"verified_profile:{serving_key}", f"verified_profile:{last_day_key}"],
                evidence=evidence,
                missing_fields=["join_availability"],
                profile_improvement="Confirm the earliest date you can actually join in the career profile.",
            )
        return _make_result(
            question, status="not_found", reason="Joining availability is personal and cannot be safely inferred from a resume alone.",
            evidence=evidence, missing_fields=["join_availability"],
            profile_improvement="Enter your earliest confirmed joining date or a clear statement such as 'Immediately' or '30 days after offer acceptance'.",
        )

    if classification in {"current_ctc", "expected_ctc"}:
        key = "current_ctc_lpa" if classification == "current_ctc" else "expected_ctc_lpa"
        label = "current" if classification == "current_ctc" else "expected"
        raw, source_key = value_for([key])
        amount = _number(raw)
        if amount is None:
            return _make_result(
                question, status="not_found",
                reason=f"{label.title()} CTC is a personal compensation detail and is not inferred from your resume.",
                evidence=evidence, missing_fields=[key],
                profile_improvement=f"Enter your {label} annual CTC in LPA in the private Application-specific details section of your career profile.",
            )
        currency, currency_key = value_for(["ctc_currency"])
        currency = currency or "INR"
        pretty = str(amount).rstrip("0").rstrip(".") if "." in str(amount) else str(int(amount))
        answer = f"{currency} {pretty} LPA"
        refs = [f"verified_profile:{source_key}"]
        if currency_key:
            refs.append(f"verified_profile:{currency_key}")
        return _make_result(
            question, status="supported",
            reason=f"{label.title()} CTC was read from the candidate-confirmed profile value.",
            answer=answer, evidence_refs=refs, evidence=evidence,
            answer_basis="candidate-confirmed private profile value",
        )

    return None




REUSABLE_ANSWER_CLASSIFICATIONS = {
    "phone", "city", "years_java", "years_spring_boot_microservices",
    "years_spring_boot", "years_microservices", "years_kafka", "years_gcp",
    "notice_period", "last_working_day", "join_availability",
    "current_ctc", "expected_ctc", "manual",
}
BLOCKED_REUSE_CLASSIFICATIONS = {
    "sensitive_or_eligibility", "checkbox_review", "unlabelled_field",
    "sensitive_or_candidate_decision",
}


def normalize_application_question(value: str) -> str:
    return re.sub(r"\\s+", " ", re.sub(r"[^a-z0-9]+", " ", _clean(value).lower())).strip()


def resolve_saved_application_answer(question: dict, profile: dict) -> dict | None:
    """Reuse only candidate-confirmed answers for the same classified or near-identical question."""
    classification = _clean(question.get("classification")).lower() or "manual"
    if classification in BLOCKED_REUSE_CLASSIFICATIONS or classification not in REUSABLE_ANSWER_CLASSIFICATIONS:
        return None

    current_question = _clean(question.get("question"))
    normalized = normalize_application_question(current_question)
    if not normalized or normalized == "unlabelled field":
        return None

    candidates = []
    for entry in profile.get("application_answers") or []:
        if not isinstance(entry, dict) or entry.get("candidate_confirmed") is not True:
            continue
        saved_classification = _clean(entry.get("classification")).lower() or "manual"
        if saved_classification != classification:
            continue

        saved_question = _clean(entry.get("question"))
        saved_normalized = _clean(entry.get("normalized_question")) or normalize_application_question(saved_question)
        if not saved_normalized:
            continue

        if classification == "manual":
            exact = normalized == saved_normalized
            token_count = len(set(normalized.split()) & set(saved_normalized.split()))
            similar = (
                token_count >= 4
                and SequenceMatcher(None, normalized, saved_normalized).ratio() >= 0.93
            )
            if not (exact or similar):
                continue

        answer = _clean(entry.get("answer"))
        if not answer:
            continue
        candidates.append((str(entry.get("updated_at") or ""), entry, answer))

    if not candidates:
        return None

    _updated, entry, answer = sorted(candidates, key=lambda item: item[0], reverse=True)[0]
    saved_question = _clean(entry.get("question"))
    return {
        "field_index": question.get("field_index", 0),
        "question": current_question,
        "category": classification,
        "evidence_status": "supported",
        "reason": "Reused a matching answer that you explicitly saved in your career profile.",
        "evidence": [{
            "source": "saved_application_answer",
            "path": saved_question,
            "detail": answer,
        }],
        "suggested_answer": answer,
        "profile_improvement": None,
        "needs_profile_update": False,
        "profile_fields_needed": [],
        "answer_basis": "previous user-confirmed answer in career profile",
        "saved_profile_answer": True,
        "filled": bool(question.get("filled", False)),
    }


def resolve_structured_question(
    question: dict,
    profile: dict,
    evidence: list[dict],
) -> dict | None:
    return _resolve_profile_question(question, profile or {}, evidence or [])
