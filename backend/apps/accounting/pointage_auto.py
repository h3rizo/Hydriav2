from decimal import Decimal
from itertools import combinations
import re


AMOUNT_TOLERANCE = Decimal("0.01")
MAX_RELEVES_PER_GROUP = 4
MAX_CANDIDATE_RELEVES = 12


def _to_decimal(value):
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _normalize_str(value):
    return str(value or "").strip().lower()


def _parse_description_hint(description):
    text = str(description or "").strip()
    result = {
        "idxls_list": [],
        "expected_releve_count": None,
    }
    if not text:
        return result

    paren_matches = re.findall(r"\(([^()]*)\)\s*$", text)
    if not paren_matches:
        return result

    hint = paren_matches[-1].strip()
    if not hint:
        return result

    bf_matches = re.findall(r'BF"([^"]+)"', hint, flags=re.IGNORECASE)
    if bf_matches:
        cleaned_idxls = [part.strip() for part in bf_matches if part.strip()]
        if cleaned_idxls:
            result["idxls_list"] = cleaned_idxls
            return result

    idxls_parts = [part.strip() for part in hint.split(";") if part.strip()]
    if idxls_parts and all(part.isdigit() for part in idxls_parts):
        result["idxls_list"] = idxls_parts
        return result

    count_match = re.match(r"^\s*(\d+)\s+relev[eé]s?\s*$", hint, flags=re.IGNORECASE)
    if count_match:
        result["expected_releve_count"] = int(count_match.group(1))
        return result

    return result


def _idxls_num(releve):
    try:
        return int(str(releve.get("idxls") or "").strip())
    except Exception:
        return None


def _score_combo(combo, amount, candidate_count, releve_occurrences, hint_data):
    score = 0
    total = sum((_to_decimal(item.get("montant")) for item in combo), Decimal("0"))
    ecart = abs(total - amount)
    if ecart <= AMOUNT_TOLERANCE:
        score += 60

    if candidate_count == 1:
        score += 25
    elif candidate_count == 2:
        score += 10

    score += max(0, 18 - ((len(combo) - 1) * 4))

    idxls_values = [value for value in (_idxls_num(item) for item in combo) if value is not None]
    if len(idxls_values) == len(combo) and len(combo) > 1:
        span = max(idxls_values) - min(idxls_values)
        if span <= len(combo):
            score += 10
        elif span <= len(combo) * 3:
            score += 4
    elif len(combo) == 1:
        score += 6

    if any(releve_occurrences.get(str(item.get("id")), 0) > 1 for item in combo):
        score -= 20

    expected_releve_count = hint_data.get("expected_releve_count")
    if expected_releve_count is not None:
        if len(combo) == expected_releve_count:
            score += 35
        else:
            score -= 25

    hinted_idxls = hint_data.get("idxls_list") or []
    if hinted_idxls:
        combo_idxls = [str(item.get("idxls") or "").strip() for item in combo]
        if sorted(combo_idxls) == sorted(hinted_idxls):
            score += 60
        elif set(combo_idxls).intersection(hinted_idxls):
            score += 12
        else:
            score -= 30

    return score


def build_auto_pointage_suggestions(releves_data, transactions_data):
    releves = [
        {
            **releve,
            "montant_decimal": _to_decimal(releve.get("montant")),
        }
        for releve in (releves_data or [])
        if releve and not releve.get("already_pointed")
    ]
    transactions = [
        {
            **entry,
            "montant_decimal": _to_decimal(entry.get("montant_in")),
        }
        for entry in (transactions_data or [])
        if entry and not entry.get("already_pointed")
    ]

    all_candidates = []
    releve_occurrences = {}

    for tx in transactions:
        target = tx["montant_decimal"]
        if target <= 0:
            continue
        hint_data = _parse_description_hint(tx.get("description"))

        candidate_releves = [rel for rel in releves if rel["montant_decimal"] <= target + AMOUNT_TOLERANCE]
        if hint_data.get("idxls_list"):
            hinted_idxls = set(hint_data["idxls_list"])
            preferred_releves = [
                rel for rel in candidate_releves
                if str(rel.get("idxls") or "").strip() in hinted_idxls
            ]
            if preferred_releves:
                candidate_releves = preferred_releves
        candidate_releves.sort(
            key=lambda rel: (abs(rel["montant_decimal"] - target), rel["montant_decimal"], str(rel.get("id")))
        )
        candidate_releves = candidate_releves[:MAX_CANDIDATE_RELEVES]

        tx_candidates = []
        max_group_size = min(MAX_RELEVES_PER_GROUP, len(candidate_releves))
        for group_size in range(1, max_group_size + 1):
            for combo in combinations(candidate_releves, group_size):
                total = sum((item["montant_decimal"] for item in combo), Decimal("0"))
                if abs(total - target) <= AMOUNT_TOLERANCE:
                    tx_candidates.append(combo)

        if not tx_candidates:
            continue

        for combo in tx_candidates:
            for releve in combo:
                releve_id = str(releve.get("id"))
                releve_occurrences[releve_id] = releve_occurrences.get(releve_id, 0) + 1

        for combo in tx_candidates:
            all_candidates.append({
                "transaction": tx,
                "releves": combo,
                "candidate_count": len(tx_candidates),
                "hint_data": hint_data,
            })

    suggestions = []
    for candidate in all_candidates:
        tx = candidate["transaction"]
        combo = candidate["releves"]
        candidate_count = candidate["candidate_count"]
        hint_data = candidate.get("hint_data") or {}
        score = _score_combo(combo, tx["montant_decimal"], candidate_count, releve_occurrences, hint_data)
        unique_releve_set = all(releve_occurrences.get(str(item.get("id")), 0) == 1 for item in combo)

        confidence = "low"
        if score >= 105 and candidate_count == 1 and unique_releve_set:
            confidence = "high"
        elif score >= 75:
            confidence = "medium"

        if hint_data.get("idxls_list") and score >= 100 and unique_releve_set:
            confidence = "high"
        if hint_data.get("expected_releve_count") is not None and len(combo) == hint_data.get("expected_releve_count") and score >= 100 and unique_releve_set:
            confidence = "high"

        suggestions.append({
            "diamex_entry_id": tx.get("entry_id") or tx.get("id"),
            "diamex_numero": tx.get("id_access") or "",
            "diamex_base": tx.get("prog") or "",
            "diamex_montant": float(tx["montant_decimal"]),
            "releve_ids": [str(item.get("id")) for item in combo],
            "releve_idxls": [item.get("idxls") or "-" for item in combo],
            "releve_count": len(combo),
            "total_releves": float(sum((item["montant_decimal"] for item in combo), Decimal("0"))),
            "ecart": float(sum((item["montant_decimal"] for item in combo), Decimal("0")) - tx["montant_decimal"]),
            "score": score,
            "confidence": confidence,
            "hint_idxls": hint_data.get("idxls_list") or [],
            "hint_expected_releve_count": hint_data.get("expected_releve_count"),
            "is_unique_for_diamex": candidate_count == 1,
            "is_unique_for_releves": unique_releve_set,
            "reason": (
                "Somme exacte + IDXLS explicites du libelle"
                if hint_data.get("idxls_list") and score >= 100
                else (
                    "Somme exacte + nombre de releves conforme au libelle"
                    if hint_data.get("expected_releve_count") is not None and len(combo) == hint_data.get("expected_releve_count")
                    else (
                        "Somme exacte et combinaison unique"
                        if candidate_count == 1 and unique_releve_set
                        else "Somme exacte avec ambiguite restante"
                    )
                )
            ),
        })

    suggestions.sort(
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(item["confidence"], 3),
            -item["score"],
            item["releve_count"],
            item["diamex_montant"],
        )
    )

    auto_applicable = []
    used_releves = set()
    used_diamex = set()
    for suggestion in suggestions:
        if suggestion["confidence"] != "high":
            continue
        diamex_key = (_normalize_str(suggestion["diamex_numero"]), _normalize_str(suggestion["diamex_base"]))
        releve_ids = set(suggestion["releve_ids"])
        if diamex_key in used_diamex or releve_ids.intersection(used_releves):
            continue
        auto_applicable.append(suggestion)
        used_diamex.add(diamex_key)
        used_releves.update(releve_ids)

    return {
        "suggestions": suggestions,
        "auto_applicable": auto_applicable,
        "summary": {
            "suggestion_count": len(suggestions),
            "auto_applicable_count": len(auto_applicable),
            "high_count": sum(1 for item in suggestions if item["confidence"] == "high"),
            "medium_count": sum(1 for item in suggestions if item["confidence"] == "medium"),
            "low_count": sum(1 for item in suggestions if item["confidence"] == "low"),
        }
    }


def _forfaitaire_idxls_value(paiement):
    return str(paiement.get("point_eau_idxls") or "").strip()


def _score_forfaitaire_combo(combo, amount, candidate_count, paiement_occurrences, hint_data):
    score = 0
    total = sum((_to_decimal(item.get("montant")) for item in combo), Decimal("0"))
    ecart = abs(total - amount)
    if ecart <= AMOUNT_TOLERANCE:
        score += 60

    if candidate_count == 1:
        score += 25
    elif candidate_count == 2:
        score += 10

    score += max(0, 18 - ((len(combo) - 1) * 4))

    if any(paiement_occurrences.get(str(item.get("id")), 0) > 1 for item in combo):
        score -= 20

    hinted_idxls = hint_data.get("idxls_list") or []
    if hinted_idxls:
        combo_idxls = [_forfaitaire_idxls_value(item) for item in combo]
        if sorted(combo_idxls) == sorted(hinted_idxls):
            score += 60
        elif set(combo_idxls).intersection(hinted_idxls):
            score += 12
        else:
            score -= 30

    return score


def build_auto_pointage_forfaitaire_suggestions(paiements_data, transactions_data):
    paiements = [
        {
            **paiement,
            "montant_decimal": _to_decimal(paiement.get("montant")),
        }
        for paiement in (paiements_data or [])
        if paiement and not paiement.get("est_pointe")
    ]
    transactions = [
        {
            **entry,
            "montant_decimal": _to_decimal(entry.get("montant_in")),
        }
        for entry in (transactions_data or [])
        if entry and not entry.get("already_pointed")
    ]

    all_candidates = []
    paiement_occurrences = {}

    for tx in transactions:
        target = tx["montant_decimal"]
        tx_month = tx.get("mois")
        if target <= 0 or not tx_month:
            continue

        hint_data = _parse_description_hint(tx.get("description"))
        candidate_paiements = [
            paiement for paiement in paiements
            if paiement.get("mois") == tx_month and paiement["montant_decimal"] <= target + AMOUNT_TOLERANCE
        ]
        if hint_data.get("idxls_list"):
            hinted_idxls = set(hint_data["idxls_list"])
            preferred_paiements = [
                paiement for paiement in candidate_paiements
                if _forfaitaire_idxls_value(paiement) in hinted_idxls
            ]
            if preferred_paiements:
                candidate_paiements = preferred_paiements

        candidate_paiements.sort(
            key=lambda paiement: (
                abs(paiement["montant_decimal"] - target),
                paiement["montant_decimal"],
                str(paiement.get("id")),
            )
        )
        candidate_paiements = candidate_paiements[:MAX_CANDIDATE_RELEVES]

        tx_candidates = []
        max_group_size = min(MAX_RELEVES_PER_GROUP, len(candidate_paiements))
        for group_size in range(1, max_group_size + 1):
            for combo in combinations(candidate_paiements, group_size):
                total = sum((item["montant_decimal"] for item in combo), Decimal("0"))
                if abs(total - target) <= AMOUNT_TOLERANCE:
                    tx_candidates.append(combo)

        if not tx_candidates:
            continue

        for combo in tx_candidates:
            for paiement in combo:
                paiement_id = str(paiement.get("id"))
                paiement_occurrences[paiement_id] = paiement_occurrences.get(paiement_id, 0) + 1

        for combo in tx_candidates:
            all_candidates.append({
                "transaction": tx,
                "paiements": combo,
                "candidate_count": len(tx_candidates),
                "hint_data": hint_data,
            })

    suggestions = []
    for candidate in all_candidates:
        tx = candidate["transaction"]
        combo = candidate["paiements"]
        candidate_count = candidate["candidate_count"]
        hint_data = candidate.get("hint_data") or {}
        score = _score_forfaitaire_combo(combo, tx["montant_decimal"], candidate_count, paiement_occurrences, hint_data)
        unique_paiement_set = all(paiement_occurrences.get(str(item.get("id")), 0) == 1 for item in combo)

        confidence = "low"
        if score >= 105 and candidate_count == 1 and unique_paiement_set:
            confidence = "high"
        elif score >= 75:
            confidence = "medium"

        if hint_data.get("idxls_list") and score >= 100 and unique_paiement_set:
            confidence = "high"

        suggestions.append({
            "diamex_entry_id": tx.get("entry_id") or tx.get("id"),
            "diamex_numero": tx.get("id_access") or "",
            "diamex_base": tx.get("prog") or "",
            "diamex_montant": float(tx["montant_decimal"]),
            "mois": tx.get("mois"),
            "paiement_ids": [str(item.get("id")) for item in combo],
            "paiement_idxls": [_forfaitaire_idxls_value(item) or "-" for item in combo],
            "paiement_count": len(combo),
            "total_paiements": float(sum((item["montant_decimal"] for item in combo), Decimal("0"))),
            "ecart": float(sum((item["montant_decimal"] for item in combo), Decimal("0")) - tx["montant_decimal"]),
            "score": score,
            "confidence": confidence,
            "hint_idxls": hint_data.get("idxls_list") or [],
            "is_unique_for_diamex": candidate_count == 1,
            "is_unique_for_paiements": unique_paiement_set,
            "reason": (
                "Somme exacte + points d eau explicites du libelle"
                if hint_data.get("idxls_list") and score >= 100
                else (
                    "Somme exacte et combinaison unique sur le meme mois"
                    if candidate_count == 1 and unique_paiement_set
                    else "Somme exacte sur le meme mois avec ambiguite restante"
                )
            ),
        })

    suggestions.sort(
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(item["confidence"], 3),
            item.get("mois") or 99,
            -item["score"],
            item["paiement_count"],
            item["diamex_montant"],
        )
    )

    auto_applicable = []
    used_paiements = set()
    used_diamex = set()
    for suggestion in suggestions:
        if suggestion["confidence"] != "high":
            continue
        diamex_key = (_normalize_str(suggestion["diamex_numero"]), _normalize_str(suggestion["diamex_base"]))
        paiement_ids = set(suggestion["paiement_ids"])
        if diamex_key in used_diamex or paiement_ids.intersection(used_paiements):
            continue
        auto_applicable.append(suggestion)
        used_diamex.add(diamex_key)
        used_paiements.update(paiement_ids)

    return {
        "suggestions": suggestions,
        "auto_applicable": auto_applicable,
        "summary": {
            "suggestion_count": len(suggestions),
            "auto_applicable_count": len(auto_applicable),
            "high_count": sum(1 for item in suggestions if item["confidence"] == "high"),
            "medium_count": sum(1 for item in suggestions if item["confidence"] == "medium"),
            "low_count": sum(1 for item in suggestions if item["confidence"] == "low"),
        }
    }
