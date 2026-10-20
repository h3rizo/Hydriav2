from decimal import Decimal

from django.core.exceptions import ValidationError

from .models import ChangementCompteurAbonne, SegmentConsommationReleve


ZERO = Decimal('0')


def as_decimal(value):
    return Decimal(str(value or 0))


def pending_changes(point_eau, date_releve):
    return list(
        ChangementCompteurAbonne.objects.select_related(
            'ancien_compteur', 'nouveau_compteur', 'releve_precedent'
        ).filter(
            point_eau=point_eau,
            releve_facture__isnull=True,
            date_changement__lte=date_releve,
        ).order_by('date_changement', 'created_at')
    )


def build_consumption_segments(point_eau, previous_releve, date_releve, nouvel_index):
    """Calcule une periode sans jamais soustraire les index de deux compteurs."""
    nouvel_index = as_decimal(nouvel_index)
    compteur_actuel = point_eau.compteur_abonne_actuel
    if not compteur_actuel:
        ancien_index = as_decimal(previous_releve.nouvelindex if previous_releve else 0)
        return {
            'managed': False,
            'ancien_index': ancien_index,
            'volume_total': nouvel_index - ancien_index,
            'segments': [],
            'changements': [],
            'compteur': None,
        }

    changements = pending_changes(point_eau, date_releve)
    segments = []
    ordre = 1

    for changement in changements:
        volume = as_decimal(changement.volume_ancien)
        if volume < 0:
            raise ValidationError('La consommation avant changement ne peut pas etre negative.')
        segments.append({
            'ordre': ordre,
            'compteur': changement.ancien_compteur,
            'type_segment': 'estime' if changement.ancien_compteur_illisible else 'avant_changement',
            'date_debut': changement.releve_precedent.datereleve if changement.releve_precedent else None,
            'date_fin': changement.date_changement,
            'index_debut': changement.index_reference_ancien,
            'index_fin': changement.index_retrait,
            'volume': volume,
            'est_estime': changement.ancien_compteur_illisible,
        })
        ordre += 1

    if changements:
        dernier_changement = changements[-1]
        compteur_periode = dernier_changement.nouveau_compteur
        index_debut = as_decimal(dernier_changement.index_initial_nouveau)
        date_debut = dernier_changement.date_changement
        type_segment = 'apres_changement'
    else:
        compteur_periode = compteur_actuel
        if previous_releve and previous_releve.compteur_abonne_id == compteur_periode.id:
            index_debut = as_decimal(previous_releve.nouvelindex)
            date_debut = previous_releve.datereleve
        else:
            index_debut = as_decimal(compteur_periode.index_initial)
            date_debut = compteur_periode.date_installation
        type_segment = 'normal'

    if compteur_periode.id != compteur_actuel.id:
        raise ValidationError("Le compteur actuel ne correspond pas au dernier changement en attente.")
    if nouvel_index < index_debut:
        raise ValidationError(
            f"Le nouvel index ({nouvel_index}) est inferieur a l'index initial du compteur "
            f"{compteur_periode.numero} ({index_debut})."
        )

    segments.append({
        'ordre': ordre,
        'compteur': compteur_periode,
        'type_segment': type_segment,
        'date_debut': date_debut,
        'date_fin': date_releve,
        'index_debut': index_debut,
        'index_fin': nouvel_index,
        'volume': nouvel_index - index_debut,
        'est_estime': False,
    })

    return {
        'managed': True,
        'ancien_index': index_debut,
        'volume_total': sum((segment['volume'] for segment in segments), ZERO),
        'volume_avant_compteur': sum((segment['volume'] for segment in segments[:-1]), ZERO),
        'segments': segments,
        'changements': changements,
        'compteur': compteur_periode,
    }


def save_consumption_segments(releve, calculation):
    if not calculation.get('managed'):
        return

    SegmentConsommationReleve.objects.filter(releve=releve).delete()
    SegmentConsommationReleve.objects.bulk_create([
        SegmentConsommationReleve(releve=releve, **segment)
        for segment in calculation['segments']
    ])
    changement_ids = [changement.id for changement in calculation['changements']]
    if changement_ids:
        ChangementCompteurAbonne.objects.filter(
            id__in=changement_ids, releve_facture__isnull=True
        ).update(releve_facture=releve)


def serialize_segments(releve):
    return [
        {
            'compteur_numero': segment.compteur.numero,
            'type': segment.type_segment,
            'index_debut': float(segment.index_debut),
            'index_fin': float(segment.index_fin),
            'volume': float(segment.volume),
            'est_estime': segment.est_estime,
            'date_debut': segment.date_debut.isoformat() if segment.date_debut else None,
            'date_fin': segment.date_fin.isoformat() if segment.date_fin else None,
        }
        for segment in releve.segments_consommation.select_related('compteur').all()
    ]
