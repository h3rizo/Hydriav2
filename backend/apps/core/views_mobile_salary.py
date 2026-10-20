import hashlib
import json

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.core.views_mobile_auth import mobile_auth_required
from apps.employees.models import ConfigSalaire, ConfigTrancheIRSA


FORMULA_VERSION = 1


def _decimal(value):
    return format(value, "f")


def build_salary_calculation_config():
    config = ConfigSalaire.get_config()
    tranches = list(ConfigTrancheIRSA.objects.all().order_by("ordre", "tranche_superieure"))
    latest_update = max([config.updated_at] + [tranche.updated_at for tranche in tranches])
    payload = {
        "configuration_id": str(config.id),
        "organisation": "global",
        "version": latest_update.strftime("%Y%m%d%H%M%S%f"),
        "formula_version": FORMULA_VERSION,
        "effective_from": config.created_at.date().isoformat(),
        "effective_until": None,
        "server_updated_at": latest_update.isoformat(),
        "status": "active",
        "parameters": {
            "minimum_salary": _decimal(config.salaire_minimum),
            "cnaps_ceiling_multiplier": "8",
            "cnaps_employee_rate": "0.01",
            "health_mutual_matches_cnaps": True,
            "dependent_irsa_deduction": _decimal(config.deduction_irsa),
            "minimum_irsa": _decimal(config.minimum_irsa),
            "prorata_reference_days": "30",
            "daily_salary_multiplier": "worked_days",
            "guardian_reference_hours": "240",
            "employee_reference_hours": "173.33",
            "guardian_default_night_hours": "56",
            "night_rate": "0.30",
            "sunday_rate": "0.40",
            "official_holiday_rate": "0.50",
            "decree_paid_holiday_rate": "0.30",
            "may_first_rate": "1.00",
            "guardian_replacement_rate": "1.00",
            "guardian_ordinary_replacement_extra_rate": "0.30",
            "taxable_base_floor_increment": "100",
            "net_rounding_increment": "100",
            "net_rounding_mode": "HALF_UP",
            "taxable_base_rounding_mode": "FLOOR",
            "guardian_calendar_priority": ["may_first", "official_holiday", "decree_paid_holiday", "sunday", "night", "ordinary"],
        },
        "irsa_brackets": [
            {
                "id": str(tranche.id),
                "order": tranche.ordre,
                "upper_bound": _decimal(tranche.tranche_superieure),
                "rate_percent": _decimal(tranche.pourcentage),
                "server_updated_at": tranche.updated_at.isoformat(),
            }
            for tranche in tranches
        ],
        "future_configurations": [],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["checksum"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


@require_GET
@mobile_auth_required
def mobile_salary_calculation_config(request):
    payload = build_salary_calculation_config()
    known_checksum = request.GET.get("checksum", "").strip().lower()
    if known_checksum and known_checksum == payload["checksum"]:
        return JsonResponse({
            "success": True,
            "unchanged": True,
            "checksum": payload["checksum"],
            "version": payload["version"],
            "formula_version": payload["formula_version"],
        })
    return JsonResponse({"success": True, "unchanged": False, "configuration": payload})
