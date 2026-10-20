"""Resolution d'un scan : la copie serveur (VPS) prime sur le chemin local.

Un scan est consultable sur le web s'il existe une copie `scan_importe` dans le stockage
du serveur. Le chemin local (`scan`, ex. G:\\...\\Scans\\x.pdf) ne vaut que pour le poste
qui l'a ecrit : sur le VPS il n'existe jamais, donc ne pas s'y fier en premier.
"""


def copie_serveur_existe(entry):
    """True si la ligne a une copie serveur (`scan_importe`) reellement presente dans le stockage."""
    champ = getattr(entry, 'scan_importe', None)
    nom = (getattr(champ, 'name', '') or '').strip()
    if not nom:
        return False
    try:
        return bool(champ.storage.exists(nom))
    except Exception:  # noqa: BLE001 - stockage indisponible : on retombe sur le chemin local
        return False
