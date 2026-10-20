"""
Vue pour import hybride depuis Access:
- Le client (navigateur) lit le fichier Access localement via un script Python
- Le client envoie les données en JSON au serveur
- Le serveur traite et stocke dans PostgreSQL
"""
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.utils import timezone
from .models import BaseDiameX, SoldesReels, Journal, Compte
import os


@csrf_exempt
@require_http_methods(["POST"])
def import_from_client_data(request):
    """
    Reçoit les données lues par le client et les importe dans PostgreSQL.
    """
    try:
        # Récupérer les données JSON
        data_json = request.body.decode('utf-8')
        data = json.loads(data_json)

        fichier_nom = data.get('fichier_nom', 'Inconnu')
        data_rows = data.get('data_rows', [])
        soldes_rows = data.get('soldes_rows', [])

        if not data_rows:
            return JsonResponse({
                'success': False,
                'error': 'Aucune donnée DATA fournie'
            })

        # Statistiques
        imported_count = 0
        updated_count = 0
        deleted_count = 0
        errors = []

        with transaction.atomic():
            # ÉTAPE 1 : Collecter tous les IDs présents
            access_ids = set()

            for row_data in data_rows:
                try:
                    id_access = row_data.get('ID')
                    prog = row_data.get('Prog')

                    if not id_access:
                        continue

                    access_ids.add((prog, id_access))

                    # Chercher une entrée existante
                    existing = BaseDiameX.objects.filter(
                        prog=prog,
                        id_access=id_access
                    ).first()

                    # Préparer les données
                    entry_data = {
                        'fichier_source': fichier_nom,
                        'id_access': id_access,
                        'journal_code': row_data.get('Journal'),
                        'date_m': row_data.get('DateM'),
                        'rec': row_data.get('Rec'),
                        'date_rec': row_data.get('DateRec'),
                        'description': row_data.get('Description'),
                        'montant_in': float(row_data.get('In') or 0),
                        'montant_out': float(row_data.get('Out') or 0),
                        'compte_code': row_data.get('Cat'),
                        'pers': row_data.get('PERS'),
                        'detail': row_data.get('Detail'),
                        'info': row_data.get('Info'),
                        'fin': row_data.get('Fin'),
                        'activ': row_data.get('Activ'),
                        'scan': row_data.get('Scan'),
                        'prog': prog,
                        'fournisseur': row_data.get('Fournisseur'),
                        'date_input': row_data.get('DateInput'),
                        'is_checked': bool(row_data.get('Check')),
                        'match': row_data.get('Match'),
                        'bank_rec': row_data.get('BankRec'),
                    }

                    # Relier au journal si possible
                    if entry_data['journal_code']:
                        journal = Journal.objects.filter(code=entry_data['journal_code']).first()
                        if journal:
                            entry_data['journal'] = journal

                    # Relier au compte si possible
                    if entry_data['compte_code']:
                        compte = Compte.objects.filter(compte=entry_data['compte_code']).first()
                        if compte:
                            entry_data['compte'] = compte

                    # Créer ou mettre à jour
                    if existing:
                        for key, value in entry_data.items():
                            setattr(existing, key, value)
                        existing.save()
                        updated_count += 1
                    else:
                        BaseDiameX.objects.create(**entry_data)
                        imported_count += 1

                except Exception as e:
                    errors.append(f"Erreur ID {id_access}: {str(e)}")

            # ÉTAPE 2 : Supprimer les entrées qui n'existent plus
            existing_entries = BaseDiameX.objects.filter(fichier_source=fichier_nom)

            for entry in existing_entries:
                if (entry.prog, entry.id_access) not in access_ids:
                    entry.delete()
                    deleted_count += 1

        # Import SoldesReels si fourni
        soldes_imported = 0
        soldes_updated = 0

        if soldes_rows:
            with transaction.atomic():
                soldes_keys = set()

                for row_data in soldes_rows:
                    try:
                        journal_code = row_data.get('Journal')
                        date_m = row_data.get('DateM')
                        rec = row_data.get('Rec')

                        if not all([journal_code, date_m, rec]):
                            continue

                        soldes_keys.add((journal_code, date_m, rec))

                        existing_solde = SoldesReels.objects.filter(
                            journal_code=journal_code,
                            date_m=date_m,
                            rec=rec
                        ).first()

                        solde_data = {
                            'fichier_source': fichier_nom,
                            'journal_code': journal_code,
                            'date_m': date_m,
                            'rec': rec,
                            'solde_initial': float(row_data.get('SoldeInitial') or 0),
                            'solde_final': float(row_data.get('SoldeFinal') or 0),
                            'scan': row_data.get('Scan'),
                        }

                        if existing_solde:
                            for key, value in solde_data.items():
                                setattr(existing_solde, key, value)
                            existing_solde.save()
                            soldes_updated += 1
                        else:
                            SoldesReels.objects.create(**solde_data)
                            soldes_imported += 1

                    except Exception as e:
                        errors.append(f"Erreur SoldesReels: {str(e)}")

        return JsonResponse({
            'success': True,
            'message': f'Import terminé: {imported_count} nouveaux, {updated_count} mis à jour, {deleted_count} supprimés',
            'stats': {
                'data': {
                    'imported': imported_count,
                    'updated': updated_count,
                    'deleted': deleted_count
                },
                'soldes': {
                    'imported': soldes_imported,
                    'updated': soldes_updated
                }
            },
            'errors': errors[:10]  # Limiter à 10 erreurs
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
