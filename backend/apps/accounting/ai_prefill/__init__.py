"""
Pre-remplissage IA des justificatifs comptables (Phase 2).

Extraction brute (OCR / comprehension) d'un scan de justificatif via l'API Claude
vision, en sortie structuree. AUCUNE normalisation metier ici : on ne fait que
lire ce qui est visible sur la piece. La classification Journal / Compte /
Fournisseur (Phase 3-4) s'appuiera sur ces champs bruts + l'historique.

Point d'entree : `apps.accounting.ai_prefill.services.extract_receipt(file, filename=...)`.
"""
