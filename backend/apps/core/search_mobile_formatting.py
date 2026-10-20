def has_coordinates(instance):
    return getattr(instance, "latitude", None) is not None and getattr(instance, "longitude", None) is not None


def point_type_pictogram(type_name):
    # Aligné sur la page web /facturation/releves/ : kiosque = boutique,
    # borne/BI = robinet, branchement/BP/privé = maison, autres = goutte.
    normalized = str(type_name or "").strip().casefold()
    if "kiosque" in normalized:
        return "🏪"
    if "borne" in normalized or "robinet" in normalized or "bi volume" in normalized or normalized == "bi":
        return "🚰"
    if "fontaine" in normalized:
        return "⛲"
    if "puits" in normalized or "forage" in normalized:
        return "🪣"
    if "branche" in normalized or "domicile" in normalized or "priv" in normalized or normalized == "bp":
        return "🏠"
    return "💧"


def without_zero_values(values):
    return {key: value for key, value in values.items() if value != 0}
