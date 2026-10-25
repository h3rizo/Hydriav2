"""Routes API de la synchronisation de fichiers.

Montage : ``/api/sync/...`` (urls.py) et ``/api/fichiers/...`` (urls_fichiers.py).
Format d'erreur unique : ``{"code": "...", "message": "..."}`` (messages en français).
"""
import mimetypes
import os
import re
import uuid

from django.db import IntegrityError, transaction
from django.db.models import Max, Q, Sum
from django.http import FileResponse
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import acces, entites, stockage
from .auth import (PREFIXE_APPAREIL, JetonSynchronisation, PeutSynchroniser, creer_paire_jetons)
from .models import (DOMAINES, ENTITY_TYPES, ORIGINE_DEPOT, ORIGINE_REMPLACEMENT, ORIGINE_RESTAURATION,
                     PORTEE_ENTITE, PORTEE_ORGANISATION, STATUT_COMPLET, CategorieFichier, Fichier,
                     FichierVersion, SyncChange, SyncDevice)

LIMITE_DEFAUT = 200
LIMITE_MAX = 1000

_STATUTS_STOCKAGE = {
    stockage.FichierTropVolumineux: status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    stockage.QuotaDepasse: status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    stockage.StockageIndisponible: status.HTTP_503_SERVICE_UNAVAILABLE,
    stockage.CheminInvalide: status.HTTP_400_BAD_REQUEST,
}


def erreur(code, message, statut=status.HTTP_400_BAD_REQUEST, **extra):
    return Response({'code': code, 'message': message, **extra}, status=statut)


def payload_fichier(fichier):
    return {
        'id': str(fichier.id),
        'nom': fichier.nom,
        'organisation': str(fichier.organisation_id),
        'portee': fichier.portee,
        'entity_type': fichier.entity_type,
        'entity_id': str(fichier.entity_id) if fichier.entity_id else None,
        'domaine': fichier.domaine,
        'categorie': fichier.categorie_id,
        'sha256': fichier.sha256,
        'taille': fichier.taille,
        'version': fichier.version,
        'statut': fichier.statut,
        'created_at': fichier.created_at.isoformat(),
        'updated_at': fichier.updated_at.isoformat(),
        'deleted_at': fichier.deleted_at.isoformat() if fichier.deleted_at else None,
        'telechargement': reverse('sync_fichiers:telechargement', args=[fichier.id]),
        'versions': reverse('sync_fichiers:versions', args=[fichier.id]),
    }


def payload_version(version, courante_numero=None):
    return {
        'numero': version.numero,
        'nom': version.nom,
        'sha256': version.sha256,
        'taille': version.taille,
        'origine': version.origine,
        'restaure_de': version.restaure_de,
        'courante': courante_numero == version.numero if courante_numero is not None else None,
        'depose_par': version.depose_par_id,
        'created_at': version.created_at.isoformat(),
        'telechargement': reverse('sync_fichiers:version_telechargement', args=[version.fichier_id, version.numero]),
    }


def _entier(valeur, defaut, nom, minimum=0, maximum=None):
    if valeur in (None, ''):
        return defaut
    try:
        nombre = int(valeur)
    except (TypeError, ValueError):
        raise acces.AccesRefuse(f"Paramètre '{nom}' invalide.", 'PARAMETRE_INVALIDE', 400)
    if nombre < minimum or (maximum is not None and nombre > maximum):
        raise acces.AccesRefuse(f"Paramètre '{nom}' hors limites.", 'PARAMETRE_INVALIDE', 400)
    return nombre


class VueSync(APIView):
    """Base : jeton de synchronisation OU session ; compte autorisé ; erreurs au format commun."""

    authentication_classes = [JetonSynchronisation, SessionAuthentication]
    permission_classes = [IsAuthenticated, PeutSynchroniser]

    def handle_exception(self, exc):
        if isinstance(exc, acces.AccesRefuse):
            return erreur(exc.code, exc.message, exc.statut)
        if isinstance(exc, stockage.ErreurStockage):
            return erreur(exc.code, exc.message, _STATUTS_STOCKAGE.get(type(exc), 500))
        return super().handle_exception(exc)


# --------------------------------------------------------------------------- authentification

class ConnexionView(APIView):
    """POST /api/sync/auth/login : identifiant + mot de passe + device_id -> paire de jetons."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        from django.contrib.auth import authenticate

        donnees = request.data
        nom = str(donnees.get('username') or '').strip()
        mot_de_passe = str(donnees.get('password') or '')
        if not nom or not mot_de_passe:
            return erreur('IDENTIFIANTS_MANQUANTS', "Identifiant et mot de passe requis.")
        try:
            device_id = uuid.UUID(str(donnees.get('device_id') or ''))
        except (ValueError, TypeError):
            return erreur('DEVICE_ID_INVALIDE', "Identifiant d'appareil invalide.")
        user = authenticate(request, username=nom, password=mot_de_passe)
        if user is None or not user.is_active:
            return erreur('IDENTIFIANTS_INVALIDES', "Identifiants invalides.", status.HTTP_401_UNAUTHORIZED)
        if not acces.utilisateur_sync_autorise(user):
            return erreur('SYNC_NON_AUTORISEE', PeutSynchroniser.message, status.HTTP_403_FORBIDDEN)
        return Response(creer_paire_jetons(user, device_id, str(donnees.get('device_label') or '')))


class RenouvellementView(APIView):
    """POST /api/sync/auth/refresh : le jeton de renouvellement est à usage unique (rotation)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        from apps.core.models import MobileRefreshToken

        cle = str(request.data.get('refresh_token') or '').strip()
        if not cle:
            return erreur('JETON_MANQUANT', "Jeton de renouvellement requis.")
        with transaction.atomic():
            jeton = MobileRefreshToken.objects.select_for_update().select_related('user').filter(key=cle).first()
            if (jeton is None or not jeton.is_usable
                    or not jeton.device_label.startswith(PREFIXE_APPAREIL)
                    or not acces.utilisateur_sync_autorise(jeton.user)):
                return erreur('JETON_INVALIDE', "Jeton expiré ou révoqué.", status.HTTP_401_UNAUTHORIZED)
            maintenant = timezone.now()
            jeton.last_used_at = maintenant
            jeton.revoked_at = maintenant
            jeton.save(update_fields=['last_used_at', 'revoked_at'])
            libelle = jeton.device_label[len(PREFIXE_APPAREIL):]
            paire = creer_paire_jetons(jeton.user, jeton.device_id, libelle)
        return Response(paire)


# --------------------------------------------------------------------------- journal des changements

class ChangementsView(VueSync):
    """GET /api/sync/changes?since=<seq>&limit=&organisation=&appareil=

    Renvoie, par ordre de ``seq``, les changements visibles de l'utilisateur. ``next_seq`` est le
    curseur à rappeler ; ``has_more`` indique qu'il reste des pages.
    """

    def get(self, request):
        since = _entier(request.query_params.get('since'), 0, 'since')
        limite = _entier(request.query_params.get('limit'), LIMITE_DEFAUT, 'limit', 1, LIMITE_MAX)

        lignes = SyncChange.objects.filter(seq__gt=since).select_related('fichier')
        lisibles = acces.organisations_lisibles(request.user)
        organisation = request.query_params.get('organisation')
        if organisation:
            acces.organisation_depot(request.user, organisation)  # contrôle l'appartenance
            lignes = lignes.filter(Q(organisation_id=organisation) | Q(organisation__isnull=True))
        elif lisibles is not None:
            lignes = lignes.filter(Q(organisation_id__in=lisibles) | Q(organisation__isnull=True))

        interdits = [d for d in DOMAINES if d not in acces.domaines_lisibles(request.user)]
        if interdits:
            lignes = lignes.exclude(Q(portee=PORTEE_ORGANISATION) & Q(domaine__in=interdits))

        page = list(lignes.order_by('seq')[:limite + 1])
        a_suivre = len(page) > limite
        page = page[:limite]

        cache = {}
        elements = []
        for ligne in page:
            elements.append({
                'seq': ligne.seq,
                'action': ligne.action,
                'portee': ligne.portee,
                'organisation': str(ligne.organisation_id) if ligne.organisation_id else None,
                'domaine': ligne.domaine,
                'entity_type': ligne.entity_type,
                'entity_id': str(ligne.entity_id) if ligne.entity_id else None,
                'chemin': (entites.chemin(ligne.entity_type, ligne.entity_id, cache)
                           if ligne.entity_type and ligne.action != 'delete' else None),
                'fichier': payload_fichier(ligne.fichier) if ligne.fichier_id else None,
                'created_at': ligne.created_at.isoformat(),
            })

        suivant = page[-1].seq if page else since
        appareil = str(request.query_params.get('appareil') or '').strip()[:120]
        if appareil:
            self._noter_appareil(request.user, organisation, appareil, suivant)
        return Response({'since': since, 'next_seq': suivant, 'has_more': a_suivre, 'changes': elements})

    @staticmethod
    def _noter_appareil(user, organisation_id, nom, seq):
        from apps.organization.scoping import get_user_organisation
        organisation = organisation_id or getattr(get_user_organisation(user), 'id', None)
        appareil, _ = SyncDevice.objects.get_or_create(
            user=user, device_nom=nom, defaults={'organisation_id': organisation},
        )
        appareil.last_seq = max(appareil.last_seq, seq)
        appareil.last_seen_at = timezone.now()
        appareil.save(update_fields=['last_seq', 'last_seen_at'])


# --------------------------------------------------------------------------- arborescence

class ArborescenceView(VueSync):
    """GET /api/sync/arborescence?organisation=<id> : branche territoire + branche organisation."""

    def get(self, request):
        from apps.billing.models import PointEau
        from apps.employees.permissions import filter_queryset_by_permissions
        from apps.geography.models import Commune, District, Fokontany, Region, Village
        from apps.infrastructure.models import EquipementConstitutif
        from apps.organization.models import Ouvrage
        from apps.planning.models import Activite

        organisation = acces.organisation_depot(request.user, request.query_params.get('organisation'))

        # --- branche organisation
        categories = list(CategorieFichier.objects.filter(actif=True))
        domaines = []
        for domaine in DOMAINES:
            domaines.append({
                'code': domaine,
                'acces': {
                    'lecture': acces.peut_domaine(request.user, domaine, 'lecture'),
                    'ecriture': acces.peut_domaine(request.user, domaine, 'ecriture'),
                },
                'categories': [
                    {'code': c.code, 'libelle': c.libelle, 'extensions': c.extensions}
                    for c in categories if c.portee == PORTEE_ORGANISATION and c.domaine == domaine
                ],
            })

        # --- branche territoire (référentiel complet + ouvrages visibles de l'utilisateur)
        ouvrages_qs = filter_queryset_by_permissions(Ouvrage.objects.all(), request.user)
        points_qs = filter_queryset_by_permissions(PointEau.objects.all(), request.user)
        ouvrages = list(ouvrages_qs.values('id', 'nom_ouvrage'))
        points = list(points_qs.values('id', 'nomabonne', 'ouvrage_id', 'parcelle__village_id'))
        equipements = list(
            EquipementConstitutif.objects.filter(ouvrage__in=ouvrages_qs.values('pk'))
            .values('id', 'nom', 'ouvrage_id')
        )

        noeuds_ouvrage = {
            o['id']: {'id': str(o['id']), 'nom': o['nom_ouvrage'], 'equipements': [], 'points_eau': []}
            for o in ouvrages
        }
        village_de_ouvrage = {}
        points_libres = {}
        for p in sorted(points, key=lambda x: str(x['id'])):
            noeud = {'id': str(p['id']), 'nom': p['nomabonne']}
            if p['ouvrage_id'] in noeuds_ouvrage:
                noeuds_ouvrage[p['ouvrage_id']]['points_eau'].append(noeud)
                if p['parcelle__village_id'] and p['ouvrage_id'] not in village_de_ouvrage:
                    village_de_ouvrage[p['ouvrage_id']] = p['parcelle__village_id']
            elif not p['ouvrage_id'] and p['parcelle__village_id']:
                points_libres.setdefault(p['parcelle__village_id'], []).append(noeud)
        for e in equipements:
            if e['ouvrage_id'] in noeuds_ouvrage:
                noeuds_ouvrage[e['ouvrage_id']]['equipements'].append({'id': str(e['id']), 'nom': e['nom']})

        ouvrages_par_village = {}
        sans_village = []
        for ouvrage_id, noeud in noeuds_ouvrage.items():
            village_id = village_de_ouvrage.get(ouvrage_id)
            if village_id:
                ouvrages_par_village.setdefault(village_id, []).append(noeud)
            else:
                sans_village.append(noeud)

        def grouper(modele, parent_attr, nom_attr):
            resultat = {}
            for ligne in modele.objects.order_by(nom_attr).values('id', nom_attr, parent_attr):
                resultat.setdefault(ligne[parent_attr], []).append(ligne)
            return resultat

        villages = grouper(Village, 'fokontany_id', 'nom_village')
        fokontanys = grouper(Fokontany, 'commune_id', 'nom_fokontany')
        communes = grouper(Commune, 'district_id', 'nom_commune')
        districts = grouper(District, 'region_id', 'nom_district')

        def noeud_village(v):
            return {'id': str(v['id']), 'nom': v['nom_village'],
                    'ouvrages': ouvrages_par_village.get(v['id'], []),
                    'points_eau': points_libres.get(v['id'], [])}

        regions = []
        for r in Region.objects.order_by('nom_region').values('id', 'nom_region'):
            districts_r = []
            for d in districts.get(r['id'], []):
                communes_d = []
                for c in communes.get(d['id'], []):
                    communes_d.append({
                        'id': str(c['id']), 'nom': c['nom_commune'],
                        'fokontany': [
                            {'id': str(f['id']), 'nom': f['nom_fokontany'],
                             'villages': [noeud_village(v) for v in villages.get(f['id'], [])]}
                            for f in fokontanys.get(c['id'], [])
                        ],
                    })
                districts_r.append({'id': str(d['id']), 'nom': d['nom_district'], 'communes': communes_d})
            regions.append({'id': str(r['id']), 'nom': r['nom_region'], 'districts': districts_r})

        activites = {}
        for a in Activite.objects.filter(is_active=True).select_related('type_activite').order_by('type_activite__nomtype', 'nom'):
            groupe = activites.setdefault(a.type_activite_id, {
                'id': str(a.type_activite_id), 'nom': a.type_activite.nomtype, 'activites': []})
            groupe['activites'].append({'id': str(a.id), 'nom': a.nom})

        return Response({
            'organisation': {'id': str(organisation.id), 'nom': organisation.nom_organisation},
            'territoire': {
                'niveaux': ['region', 'district', 'commune', 'fokontany', 'village', 'ouvrage',
                            'equipement', 'point_eau'],
                'regions': regions,
                'ouvrages_sans_village': sans_village,
                'activites': list(activites.values()),
            },
            'organisation_branche': {'domaines': domaines},
            'categories_entite': [
                {'code': c.code, 'libelle': c.libelle, 'entity_types': c.entity_types, 'extensions': c.extensions}
                for c in categories if c.portee == PORTEE_ENTITE
            ],
        })


# --------------------------------------------------------------------------- fichiers

def _nom_nettoye(nom):
    nom = os.path.basename(str(nom or '').replace('\\', '/')).strip()
    nom = re.sub(r'[\x00-\x1f]', '', nom)
    return nom[:255]


def _verifier_extension(categorie, nom):
    extension = stockage.extension_de(nom)
    if categorie.extensions and extension not in categorie.extensions:
        raise acces.AccesRefuse(
            f"Type de fichier « .{extension or '?'} » incohérent avec la catégorie « {categorie.libelle} » "
            f"(extensions acceptées : {', '.join(categorie.extensions)}).",
            'TYPE_FICHIER_INCOHERENT', 400,
        )
    return extension


def _octets_utilises(organisation_id):
    """Espace disque réellement occupé : TOUTES les versions des fichiers non supprimés (décision Q12)."""
    return (FichierVersion.objects.filter(fichier__organisation_id=organisation_id, fichier__deleted_at__isnull=True)
            .aggregate(total=Sum('taille'))['total'] or 0)


def _quota_restant(organisation_id):
    restant = stockage.quota_organisation_octets() - _octets_utilises(organisation_id)
    if restant <= 0:
        raise stockage.QuotaDepasse("Quota de stockage de l'organisation atteint.")
    return restant


def _version_attendue(request, obligatoire):
    entete = request.headers.get('If-Match')
    if entete is None or not entete.strip():
        if obligatoire:
            raise acces.AccesRefuse("L'en-tête If-Match (version attendue) est obligatoire.",
                                    'VERSION_REQUISE', status.HTTP_428_PRECONDITION_REQUIRED)
        return None
    brut = entete.strip()
    if brut.startswith('W/'):
        brut = brut[2:]
    brut = brut.strip('"')
    if not brut.isdigit():
        raise acces.AccesRefuse("If-Match doit contenir un numéro de version.", 'VERSION_INVALIDE', 400)
    return int(brut)


def _conflit(fichier):
    return erreur('CONFLIT_VERSION', "Le fichier a été modifié depuis votre version.",
                  status.HTTP_409_CONFLICT, version_actuelle=fichier.version, fichier=payload_fichier(fichier))


class DepotView(VueSync):
    """POST /api/sync/upload (multipart).

    Champs : ``fichier`` + ``categorie`` + soit (``entity_type``, ``entity_id``), soit ``domaine``.
    Optionnels : ``nom`` (nom d'origine), ``organisation`` (si le compte en gère plusieurs).
    """

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        donnees = request.data
        televerse = request.FILES.get('fichier')
        if televerse is None:
            return erreur('FICHIER_MANQUANT', "Aucun fichier reçu (champ « fichier »).")

        code_categorie = str(donnees.get('categorie') or '').strip()
        categorie = CategorieFichier.objects.filter(code=code_categorie, actif=True).first()
        if categorie is None:
            return erreur('CATEGORIE_INCONNUE', "Catégorie de fichier inconnue ou désactivée.")

        entity_type = str(donnees.get('entity_type') or '').strip() or None
        entity_id = str(donnees.get('entity_id') or '').strip() or None
        domaine = str(donnees.get('domaine') or '').strip() or None
        if (entity_type or entity_id) and domaine:
            return erreur('PORTEE_AMBIGUE', "Précisez (entity_type, entity_id) OU domaine, pas les deux.")

        if entity_type or entity_id:
            portee = PORTEE_ENTITE
            if categorie.portee != portee:
                return erreur('CATEGORIE_INCOHERENTE', "Cette catégorie n'est pas une catégorie d'entité.")
            if entity_type not in ENTITY_TYPES:
                return erreur('ENTITE_INVALIDE', "Type d'entité inconnu.")
            if categorie.entity_types and entity_type not in categorie.entity_types:
                return erreur('CATEGORIE_INCOHERENTE',
                              f"La catégorie « {categorie.libelle} » n'accepte pas le type « {entity_type} ».")
            try:
                entity_id = str(uuid.UUID(str(entity_id)))
            except (ValueError, TypeError):
                return erreur('ENTITE_INVALIDE', "Identifiant d'entité invalide.")
            if not acces.entite_visible(request.user, entity_type, entity_id):
                return erreur('ENTITE_INTROUVABLE', "Entité introuvable ou inaccessible.", status.HTTP_404_NOT_FOUND)
        elif domaine:
            portee = PORTEE_ORGANISATION
            if domaine not in DOMAINES:
                return erreur('DOMAINE_INVALIDE', "Domaine inconnu.")
            if categorie.portee != portee or categorie.domaine != domaine:
                return erreur('CATEGORIE_INCOHERENTE',
                              f"La catégorie « {categorie.libelle} » n'appartient pas au domaine « {domaine} ».")
            if not acces.peut_domaine(request.user, domaine, 'ecriture'):
                return erreur('DOMAINE_INTERDIT', "Vous n'avez pas le droit d'écrire dans ce domaine.",
                              status.HTTP_403_FORBIDDEN)
        else:
            return erreur('PORTEE_MANQUANTE', "Précisez (entity_type, entity_id) ou domaine.")

        organisation = acces.organisation_depot(request.user, donnees.get('organisation'))
        nom = _nom_nettoye(donnees.get('nom') or televerse.name) or 'fichier'
        extension = _verifier_extension(categorie, nom)

        restant = _quota_restant(organisation.id)
        if televerse.size is not None and televerse.size > restant:
            raise stockage.QuotaDepasse("Quota de stockage de l'organisation dépassé.")

        id_fichier = uuid.uuid4()
        if portee == PORTEE_ENTITE:
            chemin = stockage.chemin_relatif_entite(entity_type, entity_id, categorie.code, id_fichier, extension)
        else:
            chemin = stockage.chemin_relatif_organisation(organisation.id, domaine, categorie.code, id_fichier, extension)

        sha256, taille = stockage.ecrire(stockage.blocs(televerse), chemin, quota_restant=restant)
        try:
            with transaction.atomic():
                fichier = Fichier.objects.create(
                    id=id_fichier, organisation=organisation, portee=portee,
                    entity_type=entity_type, entity_id=entity_id, domaine=domaine,
                    categorie=categorie, nom=nom, storage_path=chemin, sha256=sha256, taille=taille,
                    version=1, statut=STATUT_COMPLET, depose_par=request.user,
                )
                FichierVersion.objects.create(
                    fichier=fichier, numero=1, nom=nom, storage_path=chemin, sha256=sha256, taille=taille,
                    origine=ORIGINE_DEPOT, depose_par=request.user,
                )
        except IntegrityError as exc:
            stockage.supprimer_definitivement_temporaire(chemin)
            return erreur('FICHIER_REFUSE', f"Fichier refusé par la base : {exc}")
        except Exception:
            stockage.supprimer_definitivement_temporaire(chemin)
            raise
        return Response(payload_fichier(fichier), status=status.HTTP_201_CREATED)


class FichiersView(VueSync):
    """GET /api/fichiers/?entity_type=&entity_id=  ou  ?domaine=[&categorie=]  : liste (pages Hydria)."""

    def get(self, request):
        parametres = request.query_params
        entity_type, entity_id = parametres.get('entity_type'), parametres.get('entity_id')
        domaine = parametres.get('domaine')
        if bool(entity_type and entity_id) == bool(domaine):
            return erreur('PORTEE_MANQUANTE', "Précisez (entity_type, entity_id) OU domaine.")
        fichiers = Fichier.objects.filter(deleted_at__isnull=True, statut=STATUT_COMPLET)
        if domaine:
            if domaine not in DOMAINES or not acces.peut_domaine(request.user, domaine, 'lecture'):
                return erreur('DOMAINE_INTERDIT', "Domaine inconnu ou non autorisé.", status.HTTP_403_FORBIDDEN)
            fichiers = fichiers.filter(portee=PORTEE_ORGANISATION, domaine=domaine)
        else:
            try:
                entity_id = str(uuid.UUID(str(entity_id)))
            except (ValueError, TypeError):
                return erreur('ENTITE_INVALIDE', "Identifiant d'entité invalide.")
            fichiers = fichiers.filter(portee=PORTEE_ENTITE, entity_type=entity_type, entity_id=entity_id)
        if parametres.get('categorie'):
            fichiers = fichiers.filter(categorie_id=parametres['categorie'])
        lisibles = acces.organisations_lisibles(request.user)
        if lisibles is not None and domaine:
            fichiers = fichiers.filter(organisation_id__in=lisibles)
        visibles = [f for f in fichiers.order_by('-created_at')[:500] if acces.peut_lire_fichier(request.user, f)]
        return Response({'fichiers': [payload_fichier(f) for f in visibles]})


def _chemin_stockage(fichier, ident, extension):
    if fichier.portee == PORTEE_ENTITE:
        return stockage.chemin_relatif_entite(
            fichier.entity_type, fichier.entity_id, fichier.categorie_id, ident, extension)
    return stockage.chemin_relatif_organisation(
        fichier.organisation_id, fichier.domaine, fichier.categorie_id, ident, extension)


def _ajouter_version(fichier, *, nom, chemin, sha256, taille, origine, utilisateur, restaure_de=None):
    """Enregistre une nouvelle version de CONTENU et la recopie dans le fichier (version courante)."""
    dernier = fichier.versions.aggregate(m=Max('numero'))['m'] or 0
    version = FichierVersion.objects.create(
        fichier=fichier, numero=dernier + 1, nom=nom, storage_path=chemin, sha256=sha256, taille=taille,
        origine=origine, restaure_de=restaure_de, depose_par=utilisateur,
    )
    fichier.nom, fichier.storage_path, fichier.sha256, fichier.taille = nom, chemin, sha256, taille
    return version


def _elaguer_versions(fichier):
    """Supprime les plus anciennes versions au-delà de HYDRIA_VERSIONS_MAX.

    Retourne les chemins à déplacer dans ``_corbeille`` (à faire une fois la transaction validée)."""
    a_deplacer = []
    for ancienne in list(fichier.versions.order_by('-numero')[stockage.versions_max():]):
        a_deplacer.append(ancienne.storage_path)
        ancienne.delete()
    return a_deplacer


def _servir(nom, chemin, etag, sha256):
    try:
        flux = stockage.ouvrir(chemin)
    except FileNotFoundError:
        return erreur('CONTENU_ABSENT', "Le contenu du fichier est introuvable sur le serveur.",
                      status.HTTP_404_NOT_FOUND)
    type_mime = mimetypes.guess_type(nom)[0] or 'application/octet-stream'
    reponse = FileResponse(flux, as_attachment=True, filename=nom, content_type=type_mime)
    reponse['X-Content-Type-Options'] = 'nosniff'
    reponse['Cache-Control'] = 'private, no-store'
    reponse['ETag'] = f'"{etag}"'
    reponse['X-Fichier-Sha256'] = sha256
    return reponse


class ChargeFichier:
    """Chargement d'un fichier avec contrôle des droits (404 si invisible, 403 si lecture seule)."""

    def _charger(self, request, pk, verrou=False, ecriture=True):
        requete = Fichier.objects.select_related('categorie')
        if verrou:
            requete = requete.select_for_update()
        fichier = requete.filter(pk=pk, deleted_at__isnull=True).first()
        if fichier is None or not acces.peut_lire_fichier(request.user, fichier):
            raise acces.AccesRefuse("Fichier introuvable.", 'FICHIER_INTROUVABLE', 404)
        if ecriture and not acces.peut_ecrire_fichier(request.user, fichier):
            raise acces.AccesRefuse("Vous n'avez pas le droit de modifier ce fichier.", 'ECRITURE_INTERDITE')
        return fichier


class FichierView(ChargeFichier, VueSync):
    """PATCH / DELETE /api/fichiers/<id>/ ."""

    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def patch(self, request, pk):
        """Renomme (``nom``) et/ou remplace le contenu (``fichier``, nouvelle version) ; ``If-Match`` obligatoire."""
        attendue = _version_attendue(request, obligatoire=True)
        nouveau_contenu = request.FILES.get('fichier')
        nouveau_nom = request.data.get('nom')
        if nouveau_contenu is None and nouveau_nom in (None, ''):
            return erreur('RIEN_A_MODIFIER', "Fournissez « nom » et/ou « fichier ».")

        a_deplacer = []
        nouveau_chemin = None
        try:
            with transaction.atomic():
                fichier = self._charger(request, pk, verrou=True)
                if fichier.version != attendue:
                    return _conflit(fichier)
                if nouveau_nom not in (None, ''):
                    fichier.nom = _nom_nettoye(nouveau_nom) or fichier.nom
                if nouveau_contenu is not None:
                    extension = _verifier_extension(fichier.categorie, fichier.nom)
                    restant = _quota_restant(fichier.organisation_id)
                    nouveau_chemin = _chemin_stockage(fichier, uuid.uuid4(), extension)
                    sha256, taille = stockage.ecrire(
                        stockage.blocs(nouveau_contenu), nouveau_chemin, quota_restant=restant)
                    _ajouter_version(fichier, nom=fichier.nom, chemin=nouveau_chemin, sha256=sha256, taille=taille,
                                     origine=ORIGINE_REMPLACEMENT, utilisateur=request.user)
                    a_deplacer = _elaguer_versions(fichier)
                else:  # renommage seul : la version courante garde son contenu, on aligne son nom
                    fichier.versions.filter(
                        numero=fichier.versions.aggregate(m=Max('numero'))['m']).update(nom=fichier.nom)
                fichier.version += 1
                fichier.save()
        except Exception:
            if nouveau_chemin:
                stockage.supprimer_definitivement_temporaire(nouveau_chemin)
            raise
        for chemin in a_deplacer:
            stockage.mettre_a_la_corbeille(chemin)
        reponse = Response(payload_fichier(fichier))
        reponse['ETag'] = f'"{fichier.version}"'
        return reponse

    def delete(self, request, pk):
        """Suppression logique : tout le contenu (toutes les versions) part dans ``_corbeille``."""
        attendue = _version_attendue(request, obligatoire=False)
        with transaction.atomic():
            fichier = self._charger(request, pk, verrou=True)
            if attendue is not None and fichier.version != attendue:
                return _conflit(fichier)
            courante = None
            for version in fichier.versions.order_by('-numero'):
                en_corbeille = stockage.mettre_a_la_corbeille(version.storage_path)
                if en_corbeille:
                    version.storage_path = en_corbeille
                    version.save(update_fields=['storage_path'])
                courante = courante or version.storage_path
            if courante:
                fichier.storage_path = courante
            fichier.deleted_at = timezone.now()
            fichier.version += 1
            fichier.save()
        return Response(payload_fichier(fichier))


class TelechargementView(VueSync):
    """GET /api/fichiers/<id>/telechargement : version courante, droits vérifiés, jamais de lien public."""

    def get(self, request, pk):
        fichier = Fichier.objects.filter(pk=pk, deleted_at__isnull=True, statut=STATUT_COMPLET).first()
        if fichier is None or not acces.peut_lire_fichier(request.user, fichier):
            return erreur('FICHIER_INTROUVABLE', "Fichier introuvable.", status.HTTP_404_NOT_FOUND)
        return _servir(fichier.nom, fichier.storage_path, fichier.version, fichier.sha256)


class VersionsView(ChargeFichier, VueSync):
    """GET /api/fichiers/<id>/versions/ : historique du contenu, de la plus récente à la plus ancienne."""

    def get(self, request, pk):
        fichier = self._charger(request, pk, ecriture=False)
        versions = list(fichier.versions.order_by('-numero'))
        courante = versions[0].numero if versions else None
        return Response({
            'fichier': payload_fichier(fichier),
            'versions': [payload_version(v, courante) for v in versions],
        })


class VersionTelechargementView(ChargeFichier, VueSync):
    """GET /api/fichiers/<id>/versions/<n>/telechargement : contenu d'une ancienne version."""

    def get(self, request, pk, numero):
        fichier = self._charger(request, pk, ecriture=False)
        version = fichier.versions.filter(numero=numero).first()
        if version is None:
            return erreur('VERSION_INTROUVABLE', "Version introuvable.", status.HTTP_404_NOT_FOUND)
        return _servir(version.nom, version.storage_path, f'{fichier.version}-v{version.numero}', version.sha256)


class RestaurerVersionView(ChargeFichier, VueSync):
    """POST /api/fichiers/<id>/versions/<n>/restaurer : recopie une ancienne version comme nouvelle version
    courante (l'historique n'est jamais réécrit). ``If-Match`` obligatoire."""

    def post(self, request, pk, numero):
        attendue = _version_attendue(request, obligatoire=True)
        nouveau_chemin = None
        a_deplacer = []
        try:
            with transaction.atomic():
                fichier = self._charger(request, pk, verrou=True)
                if fichier.version != attendue:
                    return _conflit(fichier)
                source = fichier.versions.filter(numero=numero).first()
                if source is None:
                    return erreur('VERSION_INTROUVABLE', "Version introuvable.", status.HTTP_404_NOT_FOUND)
                if source.storage_path == fichier.storage_path:
                    return erreur('DEJA_COURANTE', "Cette version est déjà la version courante.")
                restant = _quota_restant(fichier.organisation_id)
                nouveau_chemin = _chemin_stockage(fichier, uuid.uuid4(), stockage.extension_de(source.nom))
                try:
                    sha256, taille = stockage.copier(source.storage_path, nouveau_chemin, quota_restant=restant)
                except FileNotFoundError:
                    return erreur('CONTENU_ABSENT', "Le contenu de cette version est introuvable sur le serveur.",
                                  status.HTTP_404_NOT_FOUND)
                _ajouter_version(fichier, nom=source.nom, chemin=nouveau_chemin, sha256=sha256, taille=taille,
                                 origine=ORIGINE_RESTAURATION, utilisateur=request.user, restaure_de=source.numero)
                a_deplacer = _elaguer_versions(fichier)
                fichier.version += 1
                fichier.save()
        except Exception:
            if nouveau_chemin:
                stockage.supprimer_definitivement_temporaire(nouveau_chemin)
            raise
        for chemin in a_deplacer:
            stockage.mettre_a_la_corbeille(chemin)
        reponse = Response(payload_fichier(fichier))
        reponse['ETag'] = f'"{fichier.version}"'
        return reponse
