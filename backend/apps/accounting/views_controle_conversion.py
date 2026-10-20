"""
Vues pour le contrôle de conversion en comptabilité partie double
"""
from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Q
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from .models import BaseDiameX
from apps.organization.models import Journal, Base
from apps.organization.scoping import get_user_accessible_gestionnaire_ids
from apps.employees.models import Employe
from apps.billing.models import Fournisseur


def _get_user_organisation_id(user):
    if getattr(user, 'is_superuser', False):
        return None
    try:
        return user.employe.base.organisation_id
    except Exception:
        return None


def _get_user_scope_organisation_ids(user):
    gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
    if gestionnaire_ids is None:
        return None
    return [str(_id) for _id in gestionnaire_ids]


def _get_scoped_diamex_queryset(user):
    qs = BaseDiameX.objects.all()
    if getattr(user, 'is_superuser', False):
        return qs

    organisation_ids = _get_user_scope_organisation_ids(user)
    if not organisation_ids:
        return qs.none()

    allowed_progs = list(
        Base.objects.filter(organisation_id__in=organisation_ids)
        .exclude(prog_diamex__isnull=True)
        .exclude(prog_diamex='')
        .values_list('prog_diamex', flat=True)
        .distinct()
    )
    if not allowed_progs:
        return qs.none()
    return qs.filter(prog__in=allowed_progs)


@login_required
def controle_conversion_page(request):
    """Page de contrôle de conversion en partie double"""
    return render(request, 'accounting/controle_conversion.html', {
        'title': 'Contrôle Conversion Partie Double'
    })


@login_required
@require_http_methods(["GET"])
def api_controle_conversion(request):
    """
    API pour vérifier la convertibilité en partie double.

    Règles:
    - Colonne Journal:
      * 00PERS → chercher dans PERS (employe.surnom ou fournisseur.idxls)
      * Autre code → chercher dans table journaux (code)

    - Colonne Cat (compte):
      * 6 chiffres → déjà un code comptable
      * 00BOOK → chercher code dans colonne Journal
      * 00FND1 → code 742200 (Subventions d'exploitation)
      * 00FND2 → code 742210 (Autres subventions d'exploitation)
      * 00PERS → chercher dans PERS (employe.code_tiers ou fournisseur.code_tiers)

    - Colonne PERS:
      * Si Journal=00PERS et PERS=00SPLIT → code par défaut 401000
      * Sinon tenter employe.surnom → code_tiers ou fournisseur.idxls → code_tiers
    """
    try:
        # Récupérer les triplets uniques avec les objets liés
        # Utiliser annotate pour créer des triplets distincts basés sur les codes textuels
        from django.db.models import F

        # Utiliser les champs texte bruts au lieu des ForeignKeys
        triplets_raw = _get_scoped_diamex_queryset(request.user).values(
            'journal_code',
            'compte_code',
            'pers'
        ).distinct()

        # Préparer les données de référence (insensibles à la casse pour PERS)
        journaux_qs = Journal.objects.all()
        employes_qs = Employe.objects.all()
        organisation_ids = _get_user_scope_organisation_ids(request.user)
        if organisation_ids is not None:
            if organisation_ids:
                journaux_qs = journaux_qs.filter(base__organisation_id__in=organisation_ids)
                employes_qs = employes_qs.filter(base__organisation_id__in=organisation_ids)
            else:
                journaux_qs = journaux_qs.none()
                employes_qs = employes_qs.none()

        journaux = {j.code: j.compte for j in journaux_qs if j.code}
        employes_surnom = {e.surnom.lower(): e.code_tiers for e in employes_qs.exclude(surnom__isnull=True).exclude(surnom='')}
        employes_code_tiers = {e.code_tiers for e in employes_qs.exclude(code_tiers__isnull=True).exclude(code_tiers='')}
        fournisseurs_idxls = {str(f.idxls).lower(): f.code_tiers for f in Fournisseur.objects.exclude(idxls__isnull=True).exclude(code_tiers__isnull=True).exclude(code_tiers='')}
        fournisseurs_code_tiers = {f.code_tiers for f in Fournisseur.objects.exclude(code_tiers__isnull=True).exclude(code_tiers='')}

        resultats = []
        stats = {
            'total': 0,
            'convertibles': 0,
            'non_convertibles': 0,
            'erreurs_journal': 0,
            'erreurs_cat': 0,
            'erreurs_pers': 0
        }

        for triplet in triplets_raw:
            # Récupérer les codes textuels bruts
            journal_val = triplet['journal_code'] or ''
            compte_val = triplet['compte_code'] or ''
            pers_val = triplet['pers'] or ''

            stats['total'] += 1

            # Vérifier Journal
            code_journal = None
            erreur_journal = None

            if not journal_val:
                # Journal vide = erreur
                erreur_journal = "Journal vide"
            elif journal_val == '00PERS':
                # Utiliser PERS pour trouver le code (insensible à la casse)
                pers_lower = pers_val.lower()
                if pers_val == '00SPLIT':
                    code_journal = '401000'  # Code par défaut
                elif pers_lower in employes_surnom:
                    code_journal = employes_surnom[pers_lower]
                    # Vérifier que code_tiers n'est pas NULL
                    if code_journal is None:
                        erreur_journal = f"PERS '{pers_val}' trouvé comme employé mais code_tiers est NULL"
                        code_journal = None
                elif pers_lower in fournisseurs_idxls:
                    code_journal = fournisseurs_idxls[pers_lower]
                    # Vérifier que code_tiers n'est pas NULL
                    if code_journal is None:
                        erreur_journal = f"PERS '{pers_val}' trouvé comme fournisseur mais code_tiers est NULL"
                        code_journal = None
                else:
                    erreur_journal = f"PERS '{pers_val}' introuvable (ni employé.surnom ni fournisseur.idxls)"
            elif journal_val in journaux:
                code_journal = journaux[journal_val]
            else:
                erreur_journal = f"Code journal '{journal_val}' introuvable dans table journaux"

            # Vérifier Cat (compte)
            code_cat = None
            erreur_cat = None

            if compte_val and len(compte_val) == 6 and compte_val.isdigit():
                # Déjà un code comptable
                code_cat = compte_val
            elif compte_val == '00BOOK':
                # Utiliser le code de la colonne Journal
                code_cat = code_journal
            elif compte_val == '00FND1':
                # Code spécial FND1 → Subventions d'exploitation
                code_cat = '742200'
            elif compte_val == '00FND2':
                # Code spécial FND2 → Autres subventions d'exploitation
                code_cat = '742210'
            elif compte_val == '00PERS':
                # Utiliser PERS pour trouver le code_tiers (insensible à la casse)
                pers_lower = pers_val.lower()
                if pers_val == '00SPLIT':
                    code_cat = '401000'  # Code par défaut
                elif pers_lower in employes_surnom:
                    code_cat = employes_surnom[pers_lower]
                    # Vérifier que code_tiers n'est pas NULL
                    if code_cat is None:
                        erreur_cat = f"PERS '{pers_val}' trouvé comme employé mais code_tiers est NULL"
                        code_cat = None
                elif pers_lower in fournisseurs_idxls:
                    code_cat = fournisseurs_idxls[pers_lower]
                    # Vérifier que code_tiers n'est pas NULL
                    if code_cat is None:
                        erreur_cat = f"PERS '{pers_val}' trouvé comme fournisseur mais code_tiers est NULL"
                        code_cat = None
                else:
                    erreur_cat = f"PERS '{pers_val}' introuvable pour Cat=00PERS"
            elif compte_val:
                erreur_cat = f"Cat '{compte_val}' invalide (ni 6 chiffres, ni 00BOOK, ni 00FND1, ni 00FND2, ni 00PERS)"
            else:
                erreur_cat = "Cat vide"

            # Vérifier PERS (pour info, insensible à la casse)
            code_pers_info = None
            erreur_pers = None

            if pers_val:
                pers_lower = pers_val.lower()
                if pers_val == '00SPLIT':
                    code_pers_info = '401000'
                elif pers_lower in employes_surnom:
                    code_pers_info = employes_surnom[pers_lower]
                    # Vérifier que code_tiers n'est pas NULL
                    if code_pers_info is None:
                        erreur_pers = f"PERS '{pers_val}' trouvé comme employé mais code_tiers est NULL"
                        code_pers_info = None
                elif pers_lower in fournisseurs_idxls:
                    code_pers_info = fournisseurs_idxls[pers_lower]
                    # Vérifier que code_tiers n'est pas NULL
                    if code_pers_info is None:
                        erreur_pers = f"PERS '{pers_val}' trouvé comme fournisseur mais code_tiers est NULL"
                        code_pers_info = None
                else:
                    erreur_pers = f"PERS '{pers_val}' non identifié"

            # Déterminer si convertible
            convertible = not (erreur_journal or erreur_cat)

            if convertible:
                stats['convertibles'] += 1
            else:
                stats['non_convertibles'] += 1
                if erreur_journal:
                    stats['erreurs_journal'] += 1
                if erreur_cat:
                    stats['erreurs_cat'] += 1
                if erreur_pers:
                    stats['erreurs_pers'] += 1

            resultats.append({
                'journal': journal_val,
                'cat': compte_val,
                'pers': pers_val,
                'code_journal': code_journal,
                'code_cat': code_cat,
                'code_pers_info': code_pers_info,
                'erreur_journal': erreur_journal,
                'erreur_cat': erreur_cat,
                'erreur_pers': erreur_pers,
                'convertible': convertible
            })

        return JsonResponse({
            'success': True,
            'stats': stats,
            'resultats': resultats
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
