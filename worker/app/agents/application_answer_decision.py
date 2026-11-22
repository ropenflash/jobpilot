"""Evidence-grounded decisions for filling live application controls.

This module is deliberately deterministic. AI-generated text is never an autofill
source; every automatic answer must come from verified profile data or a
candidate-confirmed saved answer, survive conflict checks, and fit the live control.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from datetime import date
from urllib.parse import urlparse
from typing import Any


SENSITIVE_CLASSIFICATIONS = {
    "sensitive_or_eligibility",
    "checkbox_review",
    "sensitive_or_candidate_decision",
    "unlabelled_field",
}
SAFE_TEXT_TYPES = {"text", "email", "tel", "url", "textarea", "number", "date"}
RANGE_CLASSIFICATIONS = {
    "experience_range",
    "years_java",
    "years_spring_boot",
    "years_spring_boot_microservices",
    "years_microservices",
    "years_kafka",
    "years_gcp",
    "current_ctc",
    "expected_ctc",
}
PROFILE_KEYS = {
    "full_name": ("full_name",),
    "first_name": ("first_name", "full_name"),
    "last_name": ("last_name", "full_name"),
    "email": ("email",),
    "phone": ("phone", "mobile"),
    "phone_country_code": ("phone", "mobile"),
    "linkedin": ("linkedin_url", "linkedin"),
    "github": ("github_url", "github"),
    "website": ("website", "portfolio_url"),
    "city": ("city", "location_city", "location"),
    "country": ("country", "location"),
    "experience_range": ("total_experience_years", "years_of_experience"),
    "years_java": ("java_experience_years", "technology_experience_years.java"),
    "years_spring_boot": ("spring_boot_experience_years", "technology_experience_years.spring_boot"),
    "years_spring_boot_microservices": (
        "spring_boot_experience_years", "microservices_experience_years",
        "technology_experience_years.spring_boot", "technology_experience_years.microservices",
    ),
    "years_microservices": ("microservices_experience_years", "technology_experience_years.microservices"),
    "years_kafka": ("kafka_experience_years", "technology_experience_years.kafka"),
    "years_gcp": ("gcp_experience_years", "technology_experience_years.gcp"),
    "notice_period": ("official_notice_period", "notice_period", "notice_period_days"),
    "last_working_day": ("official_last_working_day", "last_working_day", "currently_serving_notice", "serving_notice"),
    "join_availability": ("join_availability", "availability_to_join"),
    "current_ctc": ("current_ctc_lpa", "current_ctc"),
    "expected_ctc": ("expected_ctc_lpa", "expected_ctc"),
}
RESUME_CONFLICT_KEYS = {
    "full_name": ("full_name", "name", "candidate_name"),
    "first_name": ("first_name", "firstname"),
    "last_name": ("last_name", "lastname", "surname"),
    "email": ("email", "email_address"),
    "phone": ("phone", "mobile", "telephone"),
    "linkedin": ("linkedin",),
    "github": ("github",),
    "website": ("website", "portfolio"),
    "city": ("city",),
    "country": ("country",),
    "experience_range": ("total_experience_years", "years_of_experience"),
    "years_java": ("java_experience_years", "years_java", "java_years"),
    "years_spring_boot": ("spring_boot_experience_years", "years_spring_boot", "spring_boot_years"),
    "years_spring_boot_microservices": ("spring_boot_experience_years", "years_spring_boot", "microservices_experience_years", "years_microservices"),
    "years_microservices": ("microservices_experience_years", "years_microservices", "microservices_years"),
    "years_kafka": ("kafka_experience_years", "years_kafka", "kafka_years"),
    "years_gcp": ("gcp_experience_years", "years_gcp", "gcp_years"),
    "notice_period": ("official_notice_period", "notice_period"),
    "last_working_day": ("official_last_working_day", "last_working_day"),
    "join_availability": ("join_availability", "availability_to_join"),
    "current_ctc": ("current_ctc_lpa", "current_ctc"),
    "expected_ctc": ("expected_ctc_lpa", "expected_ctc"),
}
TECHNOLOGY_TERMS = {
    "years_java": r"\bjava\b",
    "years_spring_boot": r"\bspring[\s-]*boot\b",
    "years_spring_boot_microservices": r"\bspring[\s-]*boot\b|\bmicroservices?\b",
    "years_microservices": r"\bmicroservices?\b",
    "years_kafka": r"\bkafka\b",
    "years_gcp": r"\b(?:gcp|google cloud)\b",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _clean(value).lower())


def _number(value: Any) -> float | None:
    match = re.search(r"(?<!\w)(\d+(?:\.\d+)?)", _clean(value).replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _flatten(value: Any, path: str = "") -> list[dict]:
    output: list[dict] = []
    if isinstance(value, dict):
        for key, child in value.items():
            next_path = f"{path}.{key}" if path else str(key)
            output.extend(_flatten(child, next_path))
        return output
    if isinstance(value, list):
        for index, child in enumerate(value):
            output.extend(_flatten(child, f"{path}[{index}]"))
        return output
    if value is None or isinstance(value, bool):
        return output
    text = _clean(value)
    if text:
        output.append({"path": path or "root", "detail": text[:500]})
    return output


def _source_profile(profile: dict | None) -> list[dict]:
    return _flatten(profile or {})


def _source_resume(resume: dict | None) -> list[dict]:
    root = resume or {}
    if isinstance(root, dict) and isinstance(root.get("resume"), dict):
        root = root["resume"]
    return _flatten(root)


def _path_matches(path: str, aliases: tuple[str, ...]) -> bool:
    normalized_path = _normalize(path.replace(".", " "))
    return any(_normalize(alias) in normalized_path for alias in aliases)


def _same_value(candidate: str, source_value: str) -> bool:
    left = _normalize(candidate)
    right = _normalize(source_value)
    if not left or not right:
        return False
    if left == right:
        return True
    left_number = _number(candidate)
    right_number = _number(source_value)
    if left_number is not None and right_number is not None:
        if left_number == right_number:
            return True
        # Phone numbers may include a country prefix in one source but not another.
        if left.isdigit() and right.isdigit():
            return (len(left) >= 6 and right.endswith(left)) or (len(right) >= 6 and left.endswith(right))
        return False
    return left in right or right in left


def _profile_supports(
    classification: str,
    candidate: str,
    profile: dict | None,
) -> tuple[bool, list[dict]]:
    entries = _source_profile(profile)
    aliases = PROFILE_KEYS.get(classification, ())
    related = [
        {"source": "verified_profile", **entry}
        for entry in entries if _path_matches(entry["path"], aliases)
    ]
    if classification in {"phone", "phone_country_code"}:
        digits = re.sub(r"\D", "", candidate)
        for entry in related:
            phone_digits = re.sub(r"\D", "", entry["detail"])
            if digits and (
                phone_digits == digits
                or phone_digits.startswith(digits)
                or phone_digits.endswith(digits)
                or digits.endswith(phone_digits)
            ):
                return True, [entry]
    if classification == "years_spring_boot_microservices":
        candidate_numbers = {
            float(value) for value in re.findall(r"(?<!\w)(\d+(?:\.\d+)?)", candidate.replace(",", ""))
        }
        matching_components = [
            item for item in related
            if _number(item["detail"]) in candidate_numbers
        ]
        if len(matching_components) >= 2:
            return True, matching_components
    if classification == "last_working_day" and _normalize(candidate) == "notcurrentlyservingnotice":
        if any(_normalize(entry["detail"]) in {"no", "false", "0", "notserving"} for entry in related):
            return True, related
    matching = [
        item for item in related
        if _same_value(candidate, item["detail"])
    ]
    if matching:
        return True, matching

    # A candidate value may be a formatted combination of multiple profile facts,
    # such as notice period + serving status + official last working day.
    if related and classification in {"notice_period", "last_working_day"}:
        candidate_number = _number(candidate)
        relevant_numbers = [_number(item["detail"]) for item in related]
        if candidate_number is not None and candidate_number in relevant_numbers:
            return True, related

    # Technology duration can be derived from dated roles, but a skills-list mention
    # alone is not evidence of years. The caller's resolver only supplies a value
    # after its dated-role calculation succeeds.
    if classification in TECHNOLOGY_TERMS:
        pattern = re.compile(TECHNOLOGY_TERMS[classification], re.I)
        roles = (profile or {}).get("experience") or []
        if isinstance(roles, list):
            matching_roles = []
            for index, role in enumerate(roles):
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
                if pattern.search(searchable) and role.get("start_date") and role.get("end_date"):
                    matching_roles.append({
                        "source": "verified_profile",
                        "path": f"experience[{index}]",
                        "detail": searchable[:500],
                    })
            if matching_roles:
                return True, matching_roles
    return False, related


def _saved_answer_supports(
    candidate: str,
    profile: dict | None,
    classification: str,
    question: str,
) -> tuple[bool, list[dict]]:
    normalized_question = _normalize(question)
    for item in (profile or {}).get("application_answers") or []:
        if not isinstance(item, dict) or item.get("candidate_confirmed") is not True:
            continue
        answer = _clean(item.get("answer"))
        item_classification = _clean(item.get("classification"))
        saved_question = _normalize(item.get("normalized_question") or item.get("question"))
        same_category = bool(classification and item_classification == classification and classification != "manual")
        same_question = bool(
            normalized_question and saved_question
            and (
                normalized_question == saved_question
                or SequenceMatcher(None, normalized_question, saved_question).ratio() >= 0.93
            )
        )
        if answer and _same_value(candidate, answer) and (same_category or same_question):
            return True, [{
                "source": "saved_application_answer",
                "path": item.get("question") or "application_answers",
                "detail": answer[:500],
            }]
    return False, []


def _resume_conflicts(classification: str, candidate: str, resume: dict | None) -> list[dict]:
    entries = _source_resume(resume)
    aliases = RESUME_CONFLICT_KEYS.get(classification, ())
    related = [item for item in entries if _path_matches(item["path"], aliases)]
    conflicts = []
    candidate_numbers = {
        float(value) for value in re.findall(r"(?<!\w)(\d+(?:\.\d+)?)", candidate.replace(",", ""))
    }
    for item in related:
        value = item["detail"]
        if not value:
            continue
        normalized_candidate = _normalize(candidate)
        normalized_resume = _normalize(value)
        matches = normalized_candidate == normalized_resume
        if classification == "phone":
            candidate_digits = re.sub(r"\D", "", candidate)
            resume_digits = re.sub(r"\D", "", value)
            matches = bool(candidate_digits and resume_digits) and (
                candidate_digits == resume_digits
                or candidate_digits.endswith(resume_digits)
                or resume_digits.endswith(candidate_digits)
            )
        elif classification in {"city", "country", "website", "linkedin", "github", "join_availability", "last_working_day", "notice_period"}:
            matches = bool(normalized_candidate and normalized_resume) and (
                normalized_candidate in normalized_resume or normalized_resume in normalized_candidate
            )
        elif classification in RANGE_CLASSIFICATIONS:
            resume_number = _number(value)
            matches = resume_number is not None and resume_number in candidate_numbers
        if not matches:
            conflicts.append({"source": "tailored_resume", **item})

    # Catch explicit duration claims in resume prose for technology-specific fields.
    term = TECHNOLOGY_TERMS.get(classification)
    if term:
        for item in entries:
            if not re.search(term, item["detail"], re.I):
                continue
            patterns = (
                rf"(\d+(?:\.\d+)?)\s*\+?\s*years?\s+(?:of\s+)?(?:experience\s+)?(?:with\s+|in\s+)?(?:{term})",
                rf"(?:{term}).{{0,35}}?(\d+(?:\.\d+)?)\s*\+?\s*years?",
            )
            for pattern in patterns:
                match = re.search(pattern, item["detail"], re.I)
                if match:
                    resume_years = float(match.group(1))
                    candidate_years = _number(candidate)
                    candidate_year_numbers = {
                        float(value) for value in re.findall(r"(?<!\w)(\d+(?:\.\d+)?)", candidate.replace(",", ""))
                    }
                    if candidate_years is not None and resume_years not in candidate_year_numbers:
                        conflicts.append({
                            "source": "tailored_resume",
                            "path": item["path"],
                            "detail": item["detail"][:500],
                        })
                    break
    return conflicts


def _option_for_answer(
    answer: str,
    classification: str,
    options: list[dict] | None,
) -> dict | None:
    normalized = _normalize(answer)
    if not normalized:
        return None
    cleaned_options = []
    for option in options or []:
        if not isinstance(option, dict):
            continue
        value = _clean(option.get("value"))
        label = _clean(option.get("text") or option.get("label"))
        if value and (normalized == _normalize(value) or normalized == _normalize(label)):
            cleaned_options.append({"value": value, "label": label})
    if len(cleaned_options) == 1:
        return cleaned_options[0]

    if classification not in RANGE_CLASSIFICATIONS:
        return None
    candidate_number = _number(answer)
    if candidate_number is None:
        return None
    range_matches = []
    for option in options or []:
        if not isinstance(option, dict):
            continue
        label = _clean(option.get("text") or option.get("label")).lower()
        value = _clean(option.get("value"))
        if not value or not label:
            continue
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)", label)
        if match and float(match.group(1)) <= candidate_number <= float(match.group(2)):
            range_matches.append({"value": value, "label": _clean(option.get("text") or option.get("label"))})
            continue
        plus = re.search(r"(\d+(?:\.\d+)?)\s*\+", label)
        if plus and candidate_number >= float(plus.group(1)):
            range_matches.append({"value": value, "label": _clean(option.get("text") or option.get("label"))})
    return range_matches[0] if len(range_matches) == 1 else None


def _validate_control_answer(field: dict, answer: str, options: list[dict] | None) -> tuple[str | None, dict | None, str | None]:
    input_type = _clean(field.get("type")).lower()
    classification = _clean(field.get("classification"))
    if input_type == "select":
        option = _option_for_answer(answer, classification, options)
        if option is None:
            return None, None, "There is no single exact or compatible option in the live dropdown."
        return option["value"], option, None
    if input_type not in SAFE_TEXT_TYPES:
        return None, None, f"The {input_type or 'unknown'} control needs manual interaction."

    if input_type == "email":
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", answer):
            return None, None, "The answer is not a valid email address."
    elif input_type == "tel":
        if len(re.sub(r"\D", "", answer)) < 6:
            return None, None, "The phone number does not contain enough digits."
    elif input_type == "url":
        parsed = urlparse(answer if "://" in answer else "https://" + answer)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or "." not in parsed.netloc:
            return None, None, "The answer is not a valid website URL."
        if "://" not in answer:
            answer = "https://" + answer
    elif input_type == "number":
        numeric = _number(answer)
        if numeric is None:
            return None, None, "The answer is not numeric."
        minimum = _number(field.get("min")) if field.get("min") is not None else None
        maximum = _number(field.get("max")) if field.get("max") is not None else None
        if minimum is not None and numeric < minimum:
            return None, None, f"The answer is below the field minimum ({minimum:g})."
        if maximum is not None and numeric > maximum:
            return None, None, f"The answer is above the field maximum ({maximum:g})."
        answer = str(int(numeric)) if numeric.is_integer() else str(numeric)
    elif input_type == "date":
        try:
            date.fromisoformat(answer)
        except ValueError:
            return None, None, "The date must be an unambiguous YYYY-MM-DD value."
    else:
        if len(answer) > 5000:
            return None, None, "The answer exceeds the supported text length."
        minimum_length = field.get("minLength")
        maximum_length = field.get("maxLength")
        if minimum_length is not None and len(answer) < int(minimum_length):
            return None, None, f"The answer is shorter than the field minimum length ({minimum_length})."
        if maximum_length is not None and len(answer) > int(maximum_length):
            return None, None, f"The answer exceeds the field maximum length ({maximum_length})."
        pattern = _clean(field.get("pattern"))
        if pattern:
            try:
                if re.fullmatch(pattern, answer) is None:
                    return None, None, "The answer does not match the field's required format."
            except re.error:
                return None, None, "The field has a format rule JobPilot cannot safely validate."
    return answer, None, None


def decide_application_answer(
    field: dict,
    candidate_answer: str | None,
    answer_source: str | None,
    career_profile: dict | None,
    tailored_resume: dict | None,
    options: list[dict] | None = None,
) -> dict:
    """Return a traceable fill/ask/manual decision for one live Greenhouse field."""
    index = int(field.get("index", field.get("field_index", -1)))
    question = _clean(field.get("label") or field.get("question") or "Unlabelled field")
    classification = _clean(field.get("classification") or "manual")
    input_type = _clean(field.get("type") or field.get("control_type")).lower()

    def result(action: str, reason: str, **extra) -> dict:
        return {
            "field_index": index,
            "question": question,
            "classification": classification,
            "control_type": input_type,
            "action": action,
            "answer": None,
            "answer_source": answer_source or "none",
            "confidence": 0.0,
            "reason": reason,
            "evidence": [],
            "conflicts": [],
            "applied": False,
            **extra,
        }

    if field.get("filled"):
        return result("preserve_existing", "The field already contains an answer; JobPilot leaves existing values untouched.")
    if classification in SENSITIVE_CLASSIFICATIONS or input_type in {"checkbox", "radio", "file", "button", "hidden"}:
        return result("manual_review", "This field represents a sensitive decision or control that must remain under the candidate's direct control.")
    candidate = _clean(candidate_answer)
    if not candidate:
        return result("ask_candidate", "No supported answer is available in the verified profile or saved candidate answers.")
    if answer_source == "ai_draft":
        return result("candidate_confirmation", "AI-generated text is a draft only and cannot be entered automatically.")

    if answer_source == "saved_application_answer":
        supported, evidence = _saved_answer_supports(candidate, career_profile, classification, question)
    elif answer_source == "verified_profile":
        supported, evidence = _profile_supports(classification, candidate, career_profile)
    else:
        supported, evidence = False, []
    if not supported:
        return result(
            "manual_review",
            "JobPilot could not trace this proposed value to the stated trusted source, so it will not autofill it.",
            evidence=evidence,
        )

    conflicts = _resume_conflicts(classification, candidate, tailored_resume)
    if conflicts:
        return result(
            "manual_review",
            "The verified profile and tailored resume contain conflicting values for this field. Confirm the correct value before continuing.",
            evidence=evidence,
            conflicts=conflicts,
        )

    validated_answer, option, validation_error = _validate_control_answer(field, candidate, options)
    if validation_error:
        return result(
            "manual_review",
            validation_error + " JobPilot will leave the control unchanged.",
            evidence=evidence,
        )

    confidence = 0.99 if answer_source == "saved_application_answer" else 0.96
    return {
        "field_index": index,
        "question": question,
        "classification": classification,
        "control_type": input_type,
        "action": "autofill",
        "answer": validated_answer,
        "answer_source": answer_source,
        "confidence": confidence,
        "reason": (
            "A candidate-confirmed answer matches this question and is compatible with the live control."
            if answer_source == "saved_application_answer"
            else "The answer is traceable to the verified career profile, has no conflicting tailored-resume value, and fits the live control."
        ),
        "evidence": evidence,
        "conflicts": [],
        "option": option,
        "applied": False,
    }
