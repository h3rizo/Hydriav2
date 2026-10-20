"""
Vues pour la gestion des frais médicaux et de scolarité des familles d'employés
"""
import json
import math
import unicodedata
from decimal import Decimal
from datetime import date, datetime, time, timedelta
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Sum, Q

from .models import Employe, FamilleEmploye, FraisMedicaux, FraisScolarite
from apps.organization.models import Organisation
from apps.accounting.models import DiameXTemporaire
from apps.planning.models import Planning


def _normalize_poste_name(value):
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value))
    return normalized.encode('ascii', errors='ignore').decode('ascii').lower().strip()


def _get_planning_scope(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return 'none'
    if getattr(user, 'is_superuser', False):
        return 'all'
    employe = getattr(user, 'employe', None)
    if not employe:
        return 'none'

    poste_nom = _normalize_poste_name(getattr(getattr(employe, 'poste', None), 'nom_poste', ''))
    if poste_nom == 'directeur':
        return 'all'

    organisation_postes = (
        'directeur adjoint',
        'responsable administratif',
        'responsable administratif et financier',
        'raf',
    )
    if any(p in poste_nom for p in organisation_postes):
        return 'organisation'
    return 'base'


def _filter_organisations_by_scope(queryset, user):
    scope = _get_planning_scope(user)
    if scope == 'all':
        return queryset
    if scope == 'none':
        return queryset.none()

    employe = getattr(user, 'employe', None)
    organisation_id = getattr(getattr(employe, 'base', None), 'organisation_id', None)
    if not organisation_id:
        return queryset.none()
    return queryset.filter(id=organisation_id)


def _filter_employes_by_scope(queryset, user):
    scope = _get_planning_scope(user)
    if scope == 'all':
        return queryset
    if scope == 'none':
        return queryset.none()

    employe = getattr(user, 'employe', None)
    if not employe:
        return queryset.none()

    if scope == 'organisation':
        organisation_id = getattr(getattr(employe, 'base', None), 'organisation_id', None)
        if not organisation_id:
            return queryset.none()
        return queryset.filter(base__organisation_id=organisation_id)

    base_id = getattr(employe, 'base_id', None)
    if not base_id:
        return queryset.none()
    return queryset.filter(base_id=base_id)


def _filter_famille_by_scope(queryset, user):
    scope = _get_planning_scope(user)
    if scope == 'all':
        return queryset
    if scope == 'none':
        return queryset.none()

    employe = getattr(user, 'employe', None)
    if not employe:
        return queryset.none()

    if scope == 'organisation':
        organisation_id = getattr(getattr(employe, 'base', None), 'organisation_id', None)
        if not organisation_id:
            return queryset.none()
        return queryset.filter(employe__base__organisation_id=organisation_id)

    base_id = getattr(employe, 'base_id', None)
    if not base_id:
        return queryset.none()
    return queryset.filter(employe__base_id=base_id)


def _filter_frais_medicaux_by_scope(queryset, user):
    scope = _get_planning_scope(user)
    if scope == 'all':
        return queryset
    if scope == 'none':
        return queryset.none()

    employe = getattr(user, 'employe', None)
    if not employe:
        return queryset.none()

    if scope == 'organisation':
        organisation_id = getattr(getattr(employe, 'base', None), 'organisation_id', None)
        if not organisation_id:
            return queryset.none()
        return queryset.filter(
            Q(membre_famille__employe__base__organisation_id=organisation_id) |
            Q(employe_beneficiaire__base__organisation_id=organisation_id)
        )

    base_id = getattr(employe, 'base_id', None)
    if not base_id:
        return queryset.none()
    return queryset.filter(
        Q(membre_famille__employe__base_id=base_id) |
        Q(employe_beneficiaire__base_id=base_id)
    )


def _filter_frais_scolarite_by_scope(queryset, user):
    scope = _get_planning_scope(user)
    if scope == 'all':
        return queryset
    if scope == 'none':
        return queryset.none()

    employe = getattr(user, 'employe', None)
    if not employe:
        return queryset.none()

    if scope == 'organisation':
        organisation_id = getattr(getattr(employe, 'base', None), 'organisation_id', None)
        if not organisation_id:
            return queryset.none()
        return queryset.filter(membre_famille__employe__base__organisation_id=organisation_id)

    base_id = getattr(employe, 'base_id', None)
    if not base_id:
        return queryset.none()
    return queryset.filter(membre_famille__employe__base_id=base_id)


def _user_is_directeur(user):
    employe = getattr(user, 'employe', None)
    if getattr(user, 'is_superuser', False):
        return True
    return bool(employe and getattr(employe, 'is_directeur', False))


def frais_medicaux_workflow(request):
    """
    Page de workflow pour les remboursements de frais médicaux.
    """
    organisations = Organisation.objects.all().order_by('nom_organisation')
    organisations = _filter_organisations_by_scope(organisations, request.user)

    # Employés actifs (sans date de débauchage)
    employes = Employe.objects.filter(
        date_debauchage__isnull=True
    ).select_related('poste', 'base').order_by('nom', 'prenom')
    employes = _filter_employes_by_scope(employes, request.user)

    context = {
        'organisations': organisations,
        'employes': employes,
        'user_is_directeur': _user_is_directeur(request.user),
    }
    return render(request, 'employees/frais_medicaux_workflow.html', context)


def frais_scolarite_workflow(request):
    """
    Page de workflow pour les remboursements de frais de scolarité.
    """
    organisations = Organisation.objects.all().order_by('nom_organisation')
    organisations = _filter_organisations_by_scope(organisations, request.user)

    # Employés actifs (sans date de débauchage)
    employes = Employe.objects.filter(
        date_debauchage__isnull=True
    ).select_related('poste', 'base').order_by('nom', 'prenom')
    employes = _filter_employes_by_scope(employes, request.user)

    # Années scolaires disponibles
    current_year = date.today().year
    annees_scolaires = [
        f"{year}-{year+1}" for year in range(current_year - 2, current_year + 2)
    ]

    context = {
        'organisations': organisations,
        'employes': employes,
        'annees_scolaires': annees_scolaires,
    }
    return render(request, 'employees/frais_scolarite_workflow.html', context)


@csrf_exempt
@require_http_methods(["GET"])
def api_famille_employe(request, employe_id):
    """
    API pour récupérer les membres de la famille d'un employé.
    """
    try:
        membres = FamilleEmploye.objects.filter(
            employe_id=employe_id,
            actif=True
        )
        membres = _filter_famille_by_scope(membres, request.user).values(
            'id', 'nom', 'date_naissance', 'lien_parente', 'ecole', 'classe'
        )

        return JsonResponse({
            'success': True,
            'membres': list(membres)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_ajouter_membre_famille(request):
    """
    API pour ajouter un membre de famille.
    """
    try:
        data = json.loads(request.body)

        employe_id = data.get('employe_id')
        nom = data.get('nom')
        date_naissance = data.get('date_naissance')
        lien_parente = (data.get('lien_parente', 'enfant') or 'enfant').strip().lower()
        ecole = data.get('ecole')
        classe = data.get('classe')

        if not employe_id or not nom:
            return JsonResponse({
                'success': False,
                'error': 'Employé et nom obligatoires'
            }, status=400)

        if lien_parente not in {'conjoint', 'enfant'}:
            return JsonResponse({
                'success': False,
                'error': 'Le lien de parenté doit Ãªtre Conjoint(e) ou Enfant'
            }, status=400)

        employe_qs = _filter_employes_by_scope(Employe.objects.all(), request.user)
        if not employe_qs.filter(id=employe_id).exists():
            return JsonResponse({
                'success': False,
                'error': 'Accès refusé à cet employé'
            }, status=403)

        membre = FamilleEmploye.objects.create(
            employe_id=employe_id,
            nom=nom,
            date_naissance=date_naissance if date_naissance else None,
            lien_parente=lien_parente,
            ecole=ecole,
            classe=classe
        )

        return JsonResponse({
            'success': True,
            'message': 'Membre ajouté avec succès',
            'membre_id': str(membre.id)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_modifier_membre_famille(request, membre_id):
    """API pour modifier un membre de famille."""
    try:
        if not _user_is_directeur(request.user):
            return JsonResponse({
                'success': False,
                'error': 'Seul le Directeur peut modifier un membre de famille'
            }, status=403)

        data = json.loads(request.body)
        membre = _filter_famille_by_scope(FamilleEmploye.objects.all(), request.user).get(id=membre_id)

        nom = (data.get('nom') or '').strip()
        lien_parente = (data.get('lien_parente', 'enfant') or 'enfant').strip().lower()

        if not nom:
            return JsonResponse({
                'success': False,
                'error': 'Le nom est obligatoire'
            }, status=400)

        if lien_parente not in {'conjoint', 'enfant'}:
            return JsonResponse({
                'success': False,
                'error': 'Le lien de parenté doit être Conjoint(e) ou Enfant'
            }, status=400)

        membre.nom = nom
        membre.date_naissance = data.get('date_naissance') or None
        membre.lien_parente = lien_parente
        membre.ecole = (data.get('ecole') or '').strip() or None
        membre.classe = (data.get('classe') or '').strip() or None
        membre.save()

        return JsonResponse({
            'success': True,
            'message': 'Membre modifié avec succès'
        })
    except FamilleEmploye.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Membre de famille non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_supprimer_membre_famille(request, membre_id):
    """Archive un membre de famille pour préserver l'historique."""
    try:
        if not _user_is_directeur(request.user):
            return JsonResponse({
                'success': False,
                'error': 'Seul le Directeur peut supprimer un membre de famille'
            }, status=403)

        membre = _filter_famille_by_scope(FamilleEmploye.objects.all(), request.user).get(id=membre_id)
        membre.actif = False
        membre.save(update_fields=['actif', 'updated_at'])

        return JsonResponse({
            'success': True,
            'message': 'Membre supprimé avec succès'
        })
    except FamilleEmploye.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Membre de famille non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_calculer_frais_medicaux(request):
    """
    API pour calculer le remboursement de frais médicaux.
    Supporte bénéficiaire = membre de famille OU employé lui-même.
    """
    try:
        data = json.loads(request.body)

        membre_id = data.get('membre_id')
        employe_id = data.get('employe_id')  # Si c'est l'employé lui-même
        montant_soins = data.get('montant_soins')
        type_soin = data.get('type_soin', 'soins')  # 'soins' ou 'lunettes'
        affection = data.get('affection')
        mois_concerne = data.get('mois_concerne')  # Format YYYY-MM

        if not all([montant_soins, affection, mois_concerne]):
            return JsonResponse({
                'success': False,
                'error': 'Tous les champs sont obligatoires'
            }, status=400)

        if not membre_id and not employe_id:
            return JsonResponse({
                'success': False,
                'error': 'Veuillez sélectionner un bénéficiaire'
            }, status=400)

        # Déterminer le bénéficiaire
        if membre_id:
            # Bénéficiaire = membre de famille
            membre = _filter_famille_by_scope(
                FamilleEmploye.objects.select_related('employe__poste__organisation'),
                request.user
            ).get(id=membre_id)
            employe = membre.employe
            nom_beneficiaire = membre.nom
            organisation = employe.poste.organisation

            # Vérifier si existe déjà
            mois_date = date(int(mois_concerne[:4]), int(mois_concerne[5:7]), 1)
            existe = FraisMedicaux.objects.filter(
                membre_famille_id=membre_id,
                mois_concerne=mois_date,
                affection__iexact=affection
            ).exists()
        else:
            # Bénéficiaire = employé lui-même
            employe = _filter_employes_by_scope(
                Employe.objects.select_related('poste__organisation'),
                request.user
            ).get(id=employe_id)
            nom_beneficiaire = employe.nom_complet
            organisation = employe.poste.organisation

            # Vérifier si existe déjà
            mois_date = date(int(mois_concerne[:4]), int(mois_concerne[5:7]), 1)
            existe = FraisMedicaux.objects.filter(
                employe_beneficiaire_id=employe_id,
                mois_concerne=mois_date,
                affection__iexact=affection
            ).exists()

        # Calculer le remboursement
        if type_soin == 'hospitalisation':
            montant_rembourse = Decimal('0')
            plafond_applique = 0
        else:
            montant_rembourse = FraisMedicaux.calculer_remboursement(
                montant_soins, type_soin, organisation
            )
            plafond_applique = float(
                organisation.plafond_lunettes if type_soin == 'lunettes'
                else organisation.plafond_soins_simples or 0
            )

        taux_remboursement = 0 if type_soin == 'hospitalisation' else 80

        return JsonResponse({
            'success': True,
            'montant_soins': float(montant_soins),
            'montant_rembourse': float(montant_rembourse),
            'taux_remboursement': taux_remboursement,
            'plafond_applique': float(plafond_applique),
            'deja_existe': existe,
            'membre': {
                'nom': nom_beneficiaire,
                'employe': employe.nom_complet
            }
        })
    except (FamilleEmploye.DoesNotExist, Employe.DoesNotExist):
        return JsonResponse({
            'success': False,
            'error': 'Bénéficiaire non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_enregistrer_frais_medicaux(request):
    """
    API pour enregistrer et imprimer un remboursement de frais médicaux.
    Supporte bénéficiaire = membre de famille OU employé lui-même.
    """
    try:
        if request.content_type and request.content_type.startswith('multipart/form-data'):
            data = request.POST
            membre_id = data.get('membre_id')
            employe_id = data.get('employe_id')
            montant_soins = Decimal(str(data.get('montant_soins') or 0))
            montant_rembourse = Decimal(str(data.get('montant_rembourse') or 0))
            type_soin = data.get('type_soin', 'soins')
            affection = data.get('affection')
            mois_concerne = data.get('mois_concerne')
            repos_medical = str(data.get('repos_medical')).lower() in ['true', '1', 'yes', 'on']
            repos_date_debut_raw = data.get('repos_date_debut')
            repos_nb_jours = data.get('repos_nb_jours')
            justificatif_hospitalisation = request.FILES.get('justificatif_hospitalisation')
        else:
            data = json.loads(request.body)
            membre_id = data.get('membre_id')
            employe_id = data.get('employe_id')
            montant_soins = Decimal(str(data.get('montant_soins')))
            montant_rembourse = Decimal(str(data.get('montant_rembourse')))
            type_soin = data.get('type_soin', 'soins')
            affection = data.get('affection')
            mois_concerne = data.get('mois_concerne')
            repos_medical = bool(data.get('repos_medical'))
            repos_date_debut_raw = data.get('repos_date_debut')
            repos_nb_jours = data.get('repos_nb_jours')
            justificatif_hospitalisation = None

        if type_soin == 'hospitalisation':
            montant_rembourse = Decimal('0')
            if not justificatif_hospitalisation:
                return JsonResponse({
                    'success': False,
                    'error': 'Veuillez joindre les justificatifs de l\'hospitalisation'
                }, status=400)

        repos_date_debut = None
        repos_nb_jours_val = None
        if repos_medical and employe_id:
            if not repos_date_debut_raw or not repos_nb_jours:
                return JsonResponse({
                    'success': False,
                    'error': 'Veuillez renseigner les dates de repos médical'
                }, status=400)

            repos_date_debut = date.fromisoformat(repos_date_debut_raw)
            repos_nb_jours_val = int(repos_nb_jours)
            if repos_nb_jours_val < 1:
                return JsonResponse({
                    'success': False,
                    'error': 'Le nombre de jours de repos doit être supérieur à 0'
                }, status=400)
        else:
            repos_medical = False

        mois_date = date(int(mois_concerne[:4]), int(mois_concerne[5:7]), 1)

        # Déterminer le bénéficiaire
        if membre_id:
            # Bénéficiaire = membre de famille
            membre = _filter_famille_by_scope(FamilleEmploye.objects.select_related(
                'employe__poste__organisation',
                'employe__poste__compte_salaire'
            ), request.user).get(id=membre_id)
            employe = membre.employe
            nom_beneficiaire = membre.nom
            lien_beneficiaire = membre.get_lien_parente_display()

            frais = FraisMedicaux.objects.create(
                membre_famille=membre,
                employe_beneficiaire=None,
                date=date.today(),
                mois_concerne=mois_date,
                affection=affection,
                type_soin=type_soin,
                montant_soins=montant_soins,
                montant_rembourse=montant_rembourse,
                repos_medical=False,
                repos_date_debut=None,
                repos_nb_jours=None,
                justificatif_hospitalisation=justificatif_hospitalisation,
                statut='en_attente'
            )
        else:
            # Bénéficiaire = employé lui-même
            employe = _filter_employes_by_scope(Employe.objects.select_related(
                'poste__organisation',
                'poste__compte_salaire'
            ), request.user).get(id=employe_id)
            nom_beneficiaire = employe.nom_complet
            lien_beneficiaire = "Employé"

            frais = FraisMedicaux.objects.create(
                membre_famille=None,
                employe_beneficiaire=employe,
                date=date.today(),
                mois_concerne=mois_date,
                affection=affection,
                type_soin=type_soin,
                montant_soins=montant_soins,
                montant_rembourse=montant_rembourse,
                repos_medical=repos_medical,
                repos_date_debut=repos_date_debut,
                repos_nb_jours=repos_nb_jours_val,
                justificatif_hospitalisation=justificatif_hospitalisation,
                statut='en_attente'
            )

            if repos_medical and repos_date_debut and repos_nb_jours_val:
                for offset in range(repos_nb_jours_val):
                    jour = repos_date_debut + timedelta(days=offset)
                    Planning.objects.create(
                        date=datetime.combine(jour, time.min),
                        employe=employe,
                        estvalide=True,
                        remarque=f"Repos médical - {affection}"
                    )

        organisation = employe.poste.organisation

        if type_soin == 'hospitalisation':
            return JsonResponse({
                'success': True,
                'frais_id': str(frais.id),
                'message': 'Demande d\'hospitalisation enregistrée. Le montant remboursé sera défini par la Direction.'
            })

        return JsonResponse({
            'success': True,
            'frais_id': str(frais.id),
            'facture': {
                'organisation': {
                    'nom': organisation.nom_organisation,
                    'logo': organisation.logo.url if organisation.logo else None
                },
                'employe': {
                    'nom': employe.nom_complet,
                    'poste': employe.poste.nom_poste if employe.poste else '',
                    'base': employe.base.nom_base if employe.base else ''
                },
                'membre': {
                    'nom': nom_beneficiaire,
                    'lien': lien_beneficiaire
                },
                'mois': mois_date.strftime('%B %Y'),
                'affection': affection,
                'type_soin': type_soin,
                'montant_soins': float(montant_soins),
                'montant_rembourse': float(montant_rembourse),
                'date': date.today().strftime('%d/%m/%Y')
            }
        })
    except FamilleEmploye.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Membre de famille non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_imprimer_frais_medicaux(request):
    """
    API pour marquer les frais médicaux comme imprimés et exporter vers DiameXTemporaire.
    """
    try:
        data = json.loads(request.body)
        frais_ids = data.get('frais_ids', [])

        if not frais_ids:
            return JsonResponse({
                'success': False,
                'error': 'Aucun frais fourni'
            }, status=400)

        frais_list = FraisMedicaux.objects.filter(
            id__in=frais_ids,
            statut='en_attente'
        ).select_related(
            'membre_famille__employe__poste__compte_salaire',
            'membre_famille__employe',
            'employe_beneficiaire__poste__compte_salaire',
            'employe_beneficiaire'
        )
        frais_list = _filter_frais_medicaux_by_scope(frais_list, request.user)

        nb_imprimes = 0
        nb_exportes = 0
        erreurs = []

        for frais in frais_list:
            try:
                # Déterminer l'employé (bénéficiaire ou parent)
                if frais.membre_famille:
                    employe = frais.membre_famille.employe
                    nom_beneficiaire = frais.membre_famille.nom
                elif frais.employe_beneficiaire:
                    employe = frais.employe_beneficiaire
                    nom_beneficiaire = employe.nom_complet
                else:
                    erreurs.append(f"Frais {frais.id}: Aucun bénéficiaire défini")
                    continue

                poste = employe.poste

                if not poste or not poste.compte_salaire:
                    erreurs.append(f"{employe.nom_complet}: Pas de compte salaire défini")
                    continue

                # Arrondir le montant
                montant_arrondi = Decimal(math.ceil(float(frais.montant_rembourse) / 100) * 100)

                # Format description
                prefixe = poste.prefixe if poste.prefixe else ''
                nom_complet = employe.nom_complet
                mois_num = f"{frais.mois_concerne.month:02d}"
                annee = frais.mois_concerne.year

                description = f"_{prefixe} {nom_complet}_Frais médicaux_{nom_beneficiaire}_{frais.affection}_{annee} {mois_num}"

                # Créer la ligne DiameXTemporaire
                DiameXTemporaire.objects.create(
                    type_transaction='depense',
                    description=description,
                    compte_code=poste.compte_salaire.compte,
                    detail=employe.surnom if employe.surnom else employe.prenom,
                    activ=employe.volet if employe.volet else '',
                    montant_out=float(montant_arrondi),
                    date_m=frais.date,
                    info='Hydria Frais Médicaux',
                    statut='en_attente'
                )
                nb_exportes += 1

                # Marquer comme imprimé
                frais.statut = 'imprime'
                frais.date_impression = timezone.now()
                frais.save()
                nb_imprimes += 1

            except Exception as e:
                erreurs.append(f"Erreur: {str(e)}")

        return JsonResponse({
            'success': True,
            'message': f'{nb_imprimes} frais marqué(s) comme imprimé(s), {nb_exportes} ligne(s) exportée(s)',
            'nb_imprimes': nb_imprimes,
            'nb_exportes': nb_exportes,
            'erreurs': erreurs
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_definir_montant_frais_medicaux(request):
    """
    API pour définir le montant remboursé (hospitalisation).
    """
    try:
        data = json.loads(request.body)
        frais_id = data.get('frais_id')
        montant_rembourse = data.get('montant_rembourse')

        if not frais_id or montant_rembourse is None:
            return JsonResponse({
                'success': False,
                'error': 'Paramètres manquants'
            }, status=400)

        frais = _filter_frais_medicaux_by_scope(FraisMedicaux.objects.all(), request.user).get(id=frais_id)
        if frais.type_soin != 'hospitalisation':
            return JsonResponse({
                'success': False,
                'error': 'Seules les hospitalisations sont modifiables manuellement'
            }, status=400)

        frais.montant_rembourse = Decimal(str(montant_rembourse))
        frais.save()

        return JsonResponse({
            'success': True,
            'montant_rembourse': float(frais.montant_rembourse)
        })
    except FraisMedicaux.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Frais non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_facture_frais_medicaux(request, frais_id):
    """
    API pour récupérer les données de facture d'un frais médical.
    """
    try:
        frais = _filter_frais_medicaux_by_scope(FraisMedicaux.objects.select_related(
            'membre_famille__employe__poste__organisation',
            'membre_famille__employe__base',
            'employe_beneficiaire__poste__organisation',
            'employe_beneficiaire__base'
        ), request.user).get(id=frais_id)

        if frais.membre_famille:
            employe = frais.membre_famille.employe
            nom_beneficiaire = frais.membre_famille.nom
            lien_beneficiaire = frais.membre_famille.get_lien_parente_display()
        elif frais.employe_beneficiaire:
            employe = frais.employe_beneficiaire
            nom_beneficiaire = employe.nom_complet
            lien_beneficiaire = "Employé"
        else:
            return JsonResponse({
                'success': False,
                'error': 'Bénéficiaire non trouvé'
            }, status=400)

        organisation = employe.poste.organisation if employe.poste else None

        return JsonResponse({
            'success': True,
            'facture': {
                'organisation': {
                    'nom': organisation.nom_organisation if organisation else '',
                    'logo': organisation.logo.url if organisation and organisation.logo else None
                },
                'employe': {
                    'nom': employe.nom_complet,
                    'poste': employe.poste.nom_poste if employe.poste else '',
                    'base': employe.base.nom_base if employe.base else ''
                },
                'membre': {
                    'nom': nom_beneficiaire,
                    'lien': lien_beneficiaire
                },
                'mois': frais.mois_concerne.strftime('%B %Y'),
                'affection': frais.affection,
                'type_soin': frais.type_soin,
                'montant_soins': float(frais.montant_soins),
                'montant_rembourse': float(frais.montant_rembourse),
                'date': frais.date.strftime('%d/%m/%Y')
            }
        })
    except FraisMedicaux.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Frais non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def api_calculer_frais_scolarite(request):
    """
    API pour calculer le remboursement de frais de scolarité.
    """
    try:
        data = json.loads(request.body)

        membre_id = data.get('membre_id')
        montant_frais = data.get('montant_frais')
        annee_scolaire = data.get('annee_scolaire')
        ecole = data.get('ecole')
        classe = data.get('classe')

        if not all([membre_id, montant_frais, annee_scolaire]):
            return JsonResponse({
                'success': False,
                'error': 'Tous les champs sont obligatoires'
            }, status=400)

        # Récupérer le membre
        membre = _filter_famille_by_scope(
            FamilleEmploye.objects.select_related('employe'),
            request.user
        ).get(id=membre_id)

        # Calculer le remboursement (50%)
        montant_rembourse = FraisScolarite.calculer_remboursement(montant_frais)

        # Vérifier si un remboursement existe déjà
        existe = _filter_frais_scolarite_by_scope(FraisScolarite.objects.filter(
            membre_famille_id=membre_id,
            annee_scolaire=annee_scolaire
        ), request.user).exists()

        return JsonResponse({
            'success': True,
            'montant_frais': float(montant_frais),
            'montant_rembourse': float(montant_rembourse),
            'taux_remboursement': 50,
            'deja_existe': existe,
            'membre': {
                'nom': membre.nom,
                'employe': membre.employe.nom_complet
            }
        })
    except FamilleEmploye.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Membre de famille non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_enregistrer_frais_scolarite(request):
    """
    API pour enregistrer et imprimer un remboursement de frais de scolarité.
    """
    try:
        data = json.loads(request.body)

        membre_id = data.get('membre_id')
        montant_frais = Decimal(str(data.get('montant_frais')))
        montant_rembourse = Decimal(str(data.get('montant_rembourse')))
        annee_scolaire = data.get('annee_scolaire')
        ecole = data.get('ecole', '')
        classe = data.get('classe', '')

        # Récupérer le membre
        membre = _filter_famille_by_scope(FamilleEmploye.objects.select_related(
            'employe__poste__organisation',
            'employe__poste__compte_salaire'
        ), request.user).get(id=membre_id)

        # Créer l'enregistrement
        frais = FraisScolarite.objects.create(
            membre_famille=membre,
            date=date.today(),
            annee_scolaire=annee_scolaire,
            ecole=ecole,
            classe=classe,
            montant_frais=montant_frais,
            montant_rembourse=montant_rembourse,
            statut='en_attente'
        )

        employe = membre.employe
        organisation = employe.poste.organisation

        return JsonResponse({
            'success': True,
            'frais_id': str(frais.id),
            'facture': {
                'organisation': {
                    'nom': organisation.nom_organisation,
                    'logo': organisation.logo.url if organisation.logo else None
                },
                'employe': {
                    'nom': employe.nom_complet,
                    'poste': employe.poste.nom_poste if employe.poste else '',
                    'base': employe.base.nom_base if employe.base else ''
                },
                'membre': {
                    'nom': membre.nom,
                    'lien': membre.get_lien_parente_display()
                },
                'annee_scolaire': annee_scolaire,
                'ecole': ecole,
                'classe': classe,
                'montant_frais': float(montant_frais),
                'montant_rembourse': float(montant_rembourse),
                'date': date.today().strftime('%d/%m/%Y')
            }
        })
    except FamilleEmploye.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Membre de famille non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_imprimer_frais_scolarite(request):
    """
    API pour marquer les frais de scolarité comme imprimés et exporter vers DiameXTemporaire.
    """
    try:
        data = json.loads(request.body)
        frais_ids = data.get('frais_ids', [])

        if not frais_ids:
            return JsonResponse({
                'success': False,
                'error': 'Aucun frais fourni'
            }, status=400)

        frais_list = FraisScolarite.objects.filter(
            id__in=frais_ids,
            statut='en_attente'
        ).select_related(
            'membre_famille__employe__poste__compte_salaire',
            'membre_famille__employe'
        )
        frais_list = _filter_frais_scolarite_by_scope(frais_list, request.user)

        nb_imprimes = 0
        nb_exportes = 0
        erreurs = []

        for frais in frais_list:
            try:
                employe = frais.membre_famille.employe
                poste = employe.poste

                if not poste or not poste.compte_salaire:
                    erreurs.append(f"{employe.nom_complet}: Pas de compte salaire défini")
                    continue

                # Arrondir le montant
                montant_arrondi = Decimal(math.ceil(float(frais.montant_rembourse) / 100) * 100)

                # Format description
                prefixe = poste.prefixe if poste.prefixe else ''
                nom_complet = employe.nom_complet

                description = f"_{prefixe} {nom_complet}_Frais scolarité_{frais.membre_famille.nom}_{frais.annee_scolaire}"

                # Créer la ligne DiameXTemporaire
                DiameXTemporaire.objects.create(
                    type_transaction='depense',
                    description=description,
                    compte_code=poste.compte_salaire.compte,
                    detail=employe.surnom if employe.surnom else employe.prenom,
                    activ=employe.volet if employe.volet else '',
                    montant_out=float(montant_arrondi),
                    date_m=frais.date,
                    info='Hydria Frais Scolarité',
                    statut='en_attente'
                )
                nb_exportes += 1

                # Marquer comme imprimé
                frais.statut = 'imprime'
                frais.date_impression = timezone.now()
                frais.save()
                nb_imprimes += 1

            except Exception as e:
                erreurs.append(f"Erreur: {str(e)}")

        return JsonResponse({
            'success': True,
            'message': f'{nb_imprimes} frais marqué(s) comme imprimé(s), {nb_exportes} ligne(s) exportée(s)',
            'nb_imprimes': nb_imprimes,
            'nb_exportes': nb_exportes,
            'erreurs': erreurs
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def liste_frais_medicaux(request):
    """
    Liste des frais médicaux avec filtres.
    """
    organisations = Organisation.objects.all().order_by('nom_organisation')
    organisations = _filter_organisations_by_scope(organisations, request.user)
    employes = Employe.objects.filter(date_debauchage__isnull=True).order_by('nom', 'prenom')
    employes = _filter_employes_by_scope(employes, request.user)

    context = {
        'organisations': organisations,
        'employes': employes,
        'user_is_directeur': _user_is_directeur(request.user),
    }
    return render(request, 'employees/liste_frais_medicaux.html', context)


def liste_frais_scolarite(request):
    """
    Liste des frais de scolarité avec filtres.
    """
    organisations = Organisation.objects.all().order_by('nom_organisation')
    organisations = _filter_organisations_by_scope(organisations, request.user)
    employes = Employe.objects.filter(date_debauchage__isnull=True).order_by('nom', 'prenom')
    employes = _filter_employes_by_scope(employes, request.user)

    context = {
        'organisations': organisations,
        'employes': employes,
    }
    return render(request, 'employees/liste_frais_scolarite.html', context)


@csrf_exempt
@require_http_methods(["GET"])
def api_liste_frais_medicaux(request):
    """
    API pour lister les frais médicaux avec filtres.
    """
    try:
        employe_id = request.GET.get('employe_id')
        mois = request.GET.get('mois')
        statut = request.GET.get('statut')

        queryset = FraisMedicaux.objects.select_related(
            'membre_famille__employe__poste',
            'membre_famille__employe__base',
            'employe_beneficiaire__poste',
            'employe_beneficiaire__base'
        ).order_by('-date')
        queryset = _filter_frais_medicaux_by_scope(queryset, request.user)

        if employe_id:
            # Filtrer par employé (soit parent via membre_famille, soit bénéficiaire direct)
            queryset = queryset.filter(
                Q(membre_famille__employe_id=employe_id) | Q(employe_beneficiaire_id=employe_id)
            )
        if mois:
            year, month = mois.split('-')
            queryset = queryset.filter(
                mois_concerne__year=int(year),
                mois_concerne__month=int(month)
            )
        if statut:
            queryset = queryset.filter(statut=statut)

        frais_list = []
        for frais in queryset[:100]:
            # Déterminer l'employé et le bénéficiaire
            if frais.membre_famille:
                employe_nom = frais.membre_famille.employe.surnom if frais.membre_famille.employe and frais.membre_famille.employe.surnom else frais.membre_famille.employe.nom_complet
                membre_nom = frais.membre_famille.nom
            elif frais.employe_beneficiaire:
                employe_nom = frais.employe_beneficiaire.surnom if frais.employe_beneficiaire and frais.employe_beneficiaire.surnom else frais.employe_beneficiaire.nom_complet
                membre_nom = f"{frais.employe_beneficiaire.nom_complet} (Employé)"
            else:
                continue  # Skip si aucun bénéficiaire

            frais_list.append({
                'id': str(frais.id),
                'employe': employe_nom,
                'membre': membre_nom,
                'membre_id': str(frais.membre_famille.id) if frais.membre_famille else '',
                'membre_nom': frais.membre_famille.nom if frais.membre_famille else '',
                'membre_date_naissance': frais.membre_famille.date_naissance.isoformat() if frais.membre_famille and frais.membre_famille.date_naissance else '',
                'membre_lien_parente': frais.membre_famille.lien_parente if frais.membre_famille else '',
                'membre_ecole': frais.membre_famille.ecole if frais.membre_famille and frais.membre_famille.ecole else '',
                'membre_classe': frais.membre_famille.classe if frais.membre_famille and frais.membre_famille.classe else '',
                'affection': frais.affection,
                'type_soin': frais.type_soin,
                'mois_concerne': frais.mois_concerne.strftime('%Y-%m'),
                'montant_soins': float(frais.montant_soins),
                'montant_rembourse': float(frais.montant_rembourse),
                'statut': frais.statut,
                'numero_diamex': frais.numero_diamex or '',
                'base_diamex': frais.base_diamex or '',
                'date': frais.date.strftime('%Y-%m-%d'),
                'justificatif_url': frais.justificatif_hospitalisation.url if frais.justificatif_hospitalisation else ''
            })

        return JsonResponse({
            'success': True,
            'frais': frais_list
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_liste_frais_scolarite(request):
    """
    API pour lister les frais de scolarité avec filtres.
    """
    try:
        employe_id = request.GET.get('employe_id')
        annee_scolaire = request.GET.get('annee_scolaire')
        statut = request.GET.get('statut')

        queryset = FraisScolarite.objects.select_related(
            'membre_famille__employe__poste',
            'membre_famille__employe__base'
        ).order_by('-date')
        queryset = _filter_frais_scolarite_by_scope(queryset, request.user)

        if employe_id:
            queryset = queryset.filter(membre_famille__employe_id=employe_id)
        if annee_scolaire:
            queryset = queryset.filter(annee_scolaire=annee_scolaire)
        if statut:
            queryset = queryset.filter(statut=statut)

        frais_list = []
        for frais in queryset[:100]:
            frais_list.append({
                'id': str(frais.id),
                'employe': frais.membre_famille.employe.nom_complet,
                'membre': frais.membre_famille.nom,
                'annee_scolaire': frais.annee_scolaire,
                'ecole': frais.ecole,
                'classe': frais.classe,
                'montant_frais': float(frais.montant_frais),
                'montant_rembourse': float(frais.montant_rembourse),
                'statut': frais.statut,
                'numero_diamex': frais.numero_diamex or '',
                'base_diamex': frais.base_diamex or '',
                'date': frais.date.strftime('%Y-%m-%d')
            })

        return JsonResponse({
            'success': True,
            'frais': frais_list
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
