"""Schema de sortie de l'extraction d'un justificatif (sortie structuree Claude)."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

TYPE_PIECE = ("facture", "recu", "bon_livraison", "ticket", "devis", "bordereau", "autre")
SENS = ("depense", "recette", "indetermine")
LANGUE = ("fr", "mg", "mixte", "autre")
LISIBILITE = ("bonne", "partielle", "mauvaise")


class LigneArticle(BaseModel):
    designation: str = ""
    quantite: Optional[float] = None
    montant: Optional[float] = None


class ReceiptExtraction(BaseModel):
    """Champs BRUTS lus sur le justificatif. Pas de normalisation metier."""

    type_piece: str = Field("autre", description=f"Un de : {', '.join(TYPE_PIECE)}")
    date_piece: Optional[str] = Field(
        None, description="Date de la piece au format ISO AAAA-MM-JJ si lisible, sinon null"
    )
    numero_piece: Optional[str] = Field(None, description="Numero de facture / recu tel qu'ecrit")

    montant_total: Optional[float] = Field(
        None,
        description="Montant total a payer, en Ariary (MGA), entier, sans separateur de milliers. "
        "Null si aucun total lisible.",
    )
    devise: str = Field("MGA", description="Code devise ISO. MGA par defaut. 'FMG' si francs malgaches.")
    sens_probable: str = Field(
        "indetermine",
        description="depense = la piece est une depense pour l'organisation (achat a un fournisseur) ; "
        "recette = encaissement d'un client ; indetermine si le doute est reel.",
    )

    fournisseur_nom_brut: Optional[str] = Field(
        None, description="Raison sociale ou nom du fournisseur/emetteur, tel qu'ecrit sur la piece"
    )
    fournisseur_adresse: Optional[str] = None
    fournisseur_nif: Optional[str] = Field(None, description="Numero NIF si present (10 chiffres)")
    fournisseur_stat: Optional[str] = Field(None, description="Numero STAT si present")
    fournisseur_telephone: Optional[str] = None

    lignes: List[LigneArticle] = Field(
        default_factory=list, description="Lignes d'articles si detaillees et lisibles (sinon liste vide)"
    )

    langue: str = Field("fr", description=f"Langue dominante du document : {', '.join(LANGUE)}")
    manuscrit: bool = Field(False, description="True si l'essentiel des informations est manuscrit")
    lisibilite: str = Field("bonne", description=f"Qualite de lecture globale : {', '.join(LISIBILITE)}")

    confiance_montant: float = Field(0.0, ge=0.0, le=1.0)
    confiance_date: float = Field(0.0, ge=0.0, le=1.0)
    confiance_fournisseur: float = Field(0.0, ge=0.0, le=1.0)
    confiance_sens: float = Field(0.0, ge=0.0, le=1.0)

    texte_integral: str = Field(
        "",
        description="Transcription VERBATIM de tout le texte visible sur la piece (type OCR). "
        "Sert a la recherche par similarite : ne rien omettre, ne rien inventer.",
    )
    notes: str = Field(
        "", description="Anomalies : illisible, plusieurs totaux, ratures, total absent, devise douteuse, etc."
    )

    def confiance_globale(self) -> float:
        vals = [self.confiance_montant, self.confiance_date, self.confiance_fournisseur, self.confiance_sens]
        return round(sum(vals) / len(vals), 3)
