"""
Vues pour la gestion des candidats préconfigurés et des questions de test
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.core.mail import send_mail
from django.core.files.base import ContentFile
from django.conf import settings
from django.db import transaction
from .models import CandidatPreconfigure, QuestionTest, Candidat, SessionTest, EntretienQuestion, Entretien, EntretienReponse
from apps.employees.models import Poste, GrilleSalariale
import json
from urllib.parse import quote
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
import zipfile
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from datetime import datetime, date
from PIL import Image


def is_admin_or_staff(user):
    """V?rifier que l'utilisateur est admin ou staff"""
    return user.is_staff or user.is_superuser



def is_admin(user):
    """V?rifier que l'utilisateur est admin"""
    return user.is_superuser


def _parse_decimal_value(value):
    raw = (value or '').strip() if isinstance(value, str) else value
    if raw in (None, ''):
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _normalize_score_value(value):
    parsed = _parse_decimal_value(value)
    if parsed is None:
        return None
    if parsed < Decimal('0'):
        return Decimal('0')
    if parsed > Decimal('2'):
        return Decimal('2')
    return parsed


def _parse_pretention_milliers(value):
    parsed = _parse_decimal_value(value)
    if parsed is None:
        return None
    if parsed < Decimal('0'):
        return Decimal('0')
    return parsed


def _format_pretention_milliers(value):
    if value is None:
        return '-'
    return f"{Decimal(str(value)):,.0f}".replace(',', ' ') + ' kAr'


def _salary_ar_to_kariary(value):
    if value in (None, ''):
        return None
    try:
        return (Decimal(str(value)) / Decimal('1000')).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _get_salary_grid_comparison(poste, pretention_kariary):
    if not poste or pretention_kariary is None:
        return {
            'available': False,
            'status': '',
            'label': '',
            'class': '',
            'reference_display': '-',
            'embauche_min_kariary': None,
            'embauche_max_kariary': None,
        }

    # Un nouvel embauche demarre au niveau Junior : on compare a la grille Junior du poste.
    grille = GrilleSalariale.get_grille_junior_for_poste(poste)
    if not grille:
        return {
            'available': False,
            'status': '',
            'label': 'Grille Junior indisponible',
            'class': 'badge-ghost',
            'reference_display': '-',
            'embauche_min_kariary': None,
            'embauche_max_kariary': None,
        }

    embauche_min = _salary_ar_to_kariary(grille.get_fourchette_basse_for_anciennete(Decimal('0.00')))
    embauche_max = _salary_ar_to_kariary(grille.get_fourchette_haute_for_anciennete(Decimal('0.00')))
    if embauche_max is None:
        return {
            'available': False,
            'status': '',
            'label': 'Grille indisponible',
            'class': 'badge-ghost',
            'reference_display': '-',
            'embauche_min_kariary': float(embauche_min) if embauche_min is not None else None,
            'embauche_max_kariary': None,
        }

    pretention = Decimal(str(pretention_kariary))
    orange_limit = embauche_max * Decimal('1.5')
    if pretention <= embauche_max:
        status = 'ok'
        label = 'Dans grille'
        badge_class = 'badge-success'
    elif pretention <= orange_limit:
        status = 'warning'
        label = 'Jusqu a +50%'
        badge_class = 'badge-warning'
    else:
        status = 'danger'
        label = 'Au-dessus +50%'
        badge_class = 'badge-error'

    if embauche_min is not None:
        reference_display = f"{_format_pretention_milliers(embauche_min)} - {_format_pretention_milliers(embauche_max)}"
    else:
        reference_display = _format_pretention_milliers(embauche_max)

    return {
        'available': True,
        'status': status,
        'label': label,
        'class': badge_class,
        'reference_display': reference_display,
        'embauche_min_kariary': float(embauche_min) if embauche_min is not None else None,
        'embauche_max_kariary': float(embauche_max),
    }


def _normalize_screening_status(value):
    raw = (value or '').strip()
    if not raw:
        return 'a_analyser'

    mapping = {
        'analyse_en_cours': 'a_analyser',
        'pret_test': 'invite_test',
        'inscrit': 'a_analyser',
        'en_attente': 'a_analyser',
        'a_analyser': 'a_analyser',
        'invite_test': 'invite_test',
        'test_complete': 'test_complete',
        'invite_entretien': 'invite_entretien',
        'entretien_complete': 'entretien_complete',
        'elimine': 'elimine',
    }
    return mapping.get(raw, 'a_analyser')


def _parse_date_value(value):
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
    return None


def _format_date_iso(value):
    parsed = _parse_date_value(value)
    return parsed.isoformat() if parsed else ''


def _format_date_display(value):
    parsed = _parse_date_value(value)
    return parsed.strftime('%d/%m/%Y') if parsed else '-'


def _score_candidate_photo(width, height, page_coverage=None):
    if width < 120 or height < 120:
        return None

    ratio = width / float(height)
    pixel_area = width * height

    if pixel_area < 20_000:
        return None

    # Rejet des images qui ressemblent a une page scannee complete.
    if page_coverage is not None and page_coverage > 0.55:
        return None

    # Favoriser les portraits ou quasi carres, pas les bandeaux ou pages entieres.
    if ratio < 0.45 or ratio > 1.25:
        return None

    score = 0

    if 0.55 <= ratio <= 0.9:
        score += 80
    elif 0.9 < ratio <= 1.1:
        score += 45
    else:
        score += 20

    if 30_000 <= pixel_area <= 1_200_000:
        score += 50
    elif pixel_area <= 2_500_000:
        score += 20
    else:
        score -= 30

    if page_coverage is not None:
        if 0.02 <= page_coverage <= 0.20:
            score += 60
        elif page_coverage <= 0.35:
            score += 20
        else:
            score -= 20

    return score


def _pick_best_candidate_photo(images):
    best = None
    best_score = -1
    for image_bytes, extension, original_name, page_coverage in images:
        try:
            with Image.open(BytesIO(image_bytes)) as image:
                width, height = image.size
                score = _score_candidate_photo(width, height, page_coverage=page_coverage)
                if score is None:
                    continue
                if score > best_score:
                    best = (image_bytes, extension, original_name)
                    best_score = score
        except Exception:
            continue
    return best


def _extract_candidate_photo_from_cv(uploaded_file):
    if not uploaded_file:
        return None, None

    suffix = Path(uploaded_file.name or '').suffix.lower()
    uploaded_file.seek(0)
    file_bytes = uploaded_file.read()
    uploaded_file.seek(0)

    if not file_bytes:
        return None, None

    try:
        if suffix == '.pdf':
            import fitz

            images = []
            with fitz.open(stream=file_bytes, filetype='pdf') as document:
                for page_number in range(len(document)):
                    page = document.load_page(page_number)
                    page_area = max(float(page.rect.width * page.rect.height), 1.0)
                    for image_index, image_info in enumerate(page.get_images(full=True), start=1):
                        xref = image_info[0]
                        image_dict = document.extract_image(xref)
                        image_bytes = image_dict.get('image')
                        extension = (image_dict.get('ext') or 'png').lower()
                        if image_bytes:
                            rects = page.get_image_rects(xref)
                            rect_area = max((rect.width * rect.height for rect in rects), default=0.0)
                            page_coverage = rect_area / page_area if rect_area else None
                            images.append((image_bytes, extension, f"page_{page_number + 1}_image_{image_index}", page_coverage))
            return _pick_best_candidate_photo(images)

        if suffix == '.docx':
            images = []
            with zipfile.ZipFile(BytesIO(file_bytes), 'r') as archive:
                media_entries = [name for name in archive.namelist() if name.startswith('word/media/')]
                for internal_name in media_entries:
                    extension = Path(internal_name).suffix.lower().lstrip('.')
                    if extension not in {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tif', 'tiff', 'webp'}:
                        continue
                    image_bytes = archive.read(internal_name)
                    images.append((image_bytes, extension, internal_name, None))
            return _pick_best_candidate_photo(images)
    except Exception:
        return None, None

    return None, None


def _assign_auto_photo_from_cv(candidat_preconfig, cv_file, replace_existing=False):
    if not cv_file:
        return False
    if candidat_preconfig.photo_candidat and not replace_existing:
        return False

    extracted = _extract_candidate_photo_from_cv(cv_file)
    if not extracted:
        return False

    image_bytes, extension, _ = extracted
    source_stem = Path(cv_file.name or 'cv').stem
    photo_name = f"{source_stem}_photo_auto.{extension.lower().lstrip('.')}"
    candidat_preconfig.photo_candidat.save(photo_name, ContentFile(image_bytes), save=False)
    return True


def _get_candidate_screening_status(candidat_preconfig):
    normalized_status = _normalize_screening_status(candidat_preconfig.screening_statut)
    if normalized_status == 'elimine':
        return 'Éliminé'
    if normalized_status == 'entretien_complete':
        return 'Entretien complete'
    if normalized_status == 'invite_entretien':
        return 'Invité à l\'entretien'
    if candidat_preconfig.test_complete or normalized_status == 'test_complete':
        return 'Test complété'
    if normalized_status == 'invite_test' or candidat_preconfig.invite_test_envoyee:
        return 'Invité au test'
    return dict(CandidatPreconfigure._meta.get_field('screening_statut').choices).get(
        normalized_status,
        'A analyser',
    )


def _get_candidate_effective_status_code(candidat_preconfig):
    linked_candidat = candidat_preconfig.candidat or Candidat.objects.filter(
        email__iexact=candidat_preconfig.email
    ).first()
    normalized_status = _normalize_screening_status(candidat_preconfig.screening_statut)
    has_completed_test = candidat_preconfig.test_complete
    if not has_completed_test and linked_candidat:
        has_completed_test = SessionTest.objects.filter(
            candidat=linked_candidat,
            statut__in=['termine', 'expire']
        ).exists() or linked_candidat.statut == 'test_termine'

    if normalized_status == 'elimine':
        return 'elimine'
    if normalized_status == 'entretien_complete':
        return 'entretien_complete'
    if normalized_status == 'invite_entretien':
        return 'invite_entretien'
    if normalized_status == 'test_complete':
        return 'test_complete'
    if has_completed_test:
        return 'test_complete'
    if normalized_status == 'invite_test' or candidat_preconfig.invite_test_envoyee:
        return 'invite_test'
    return normalized_status or 'a_analyser'


def _serialize_candidat_preconfigure(c):
    normalized_status = _normalize_screening_status(c.screening_statut)
    pieces = []
    if c.photo_candidat:
        pieces.append({
            'label': 'Photo',
            'url': c.photo_candidat.url,
            'type': 'image',
        })
    if c.cv:
        pieces.append({
            'label': 'CV',
            'url': c.cv.url,
            'type': 'file',
        })
    if c.lettre_motivation:
        pieces.append({
            'label': 'Lettre',
            'url': c.lettre_motivation.url,
            'type': 'file',
        })

    return {
        'id': str(c.id),
        'nom': c.nom_complet,
        'nom_seul': c.nom,
        'prenom': c.prenom,
        'email': c.email,
        'poste': c.poste.nom_poste,
        'poste_id': str(c.poste.id),
        'date_creation': c.date_creation.strftime('%d/%m/%Y %H:%M'),
        'date_creation_sort': c.date_creation.isoformat(),
        'screening_statut': normalized_status,
        'statut': _get_candidate_screening_status(c),
        'test_complete': c.test_complete,
        'invite_test_envoyee': c.invite_test_envoyee,
        'candidat_nom': f"{c.candidat.prenom} {c.candidat.nom}" if c.candidat else None,
        'domicile': c.domicile or '',
        'date_naissance': _format_date_iso(c.date_naissance),
        'date_naissance_display': _format_date_display(c.date_naissance),
        'age': c.age,
        'formation': c.formation or '',
        'experience_poste': c.experience_poste or '',
        'autre_experience': c.autre_experience or '',
        'pretention_salariale': float(c.pretention_salariale) if c.pretention_salariale is not None else None,
        'pretention_salariale_display': _format_pretention_milliers(c.pretention_salariale),
        'permis_conduire': c.permis_conduire,
        'photo_url': c.photo_candidat.url if c.photo_candidat else '',
        'cv_url': c.cv.url if c.cv else '',
        'lettre_url': c.lettre_motivation.url if c.lettre_motivation else '',
        'pieces': pieces,
        'commentaire_analyse': c.commentaire_analyse or '',
        'note_domicile': float(c.note_domicile) if c.note_domicile is not None else None,
        'note_age': float(c.note_age) if c.note_age is not None else None,
        'note_formation': float(c.note_formation) if c.note_formation is not None else None,
        'note_experience': float(c.note_experience) if c.note_experience is not None else None,
        'note_pretention': float(c.note_pretention) if c.note_pretention is not None else None,
        'note_permis': float(c.note_permis) if c.note_permis is not None else None,
        'note_globale': c.note_globale,
        'lien_inscription': f"/recrutement/inscription/?email={quote(c.email)}",
    }


def _get_filtered_candidats_workflow(request):
    search = request.GET.get('search', '')
    poste_id = request.GET.get('poste', '')
    creation_month = request.GET.get('creation_month', '').strip()
    min_note_globale = request.GET.get('min_note_globale', '').strip()
    sort_by = request.GET.get('sort_by', '').strip()
    statuts = [s for s in request.GET.getlist('statut') if s]

    candidats = CandidatPreconfigure.objects.select_related('poste', 'candidat').all()

    if search:
        candidats = candidats.filter(
            Q(email__icontains=search) |
            Q(nom__icontains=search) |
            Q(prenom__icontains=search)
        )

    if poste_id:
        candidats = candidats.filter(poste_id=poste_id)

    if creation_month:
        try:
            year_str, month_str = creation_month.split('-')
            candidats = candidats.filter(
                date_creation__year=int(year_str),
                date_creation__month=int(month_str),
            )
        except (TypeError, ValueError):
            pass

    data = [_serialize_candidat_preconfigure(c) for c in candidats]

    if statuts:
        data = [item for item in data if item.get('effective_status_code') in statuts]

    if min_note_globale:
        try:
            threshold = float(min_note_globale)
            data = [
                item for item in data
                if item.get('note_globale') is not None and float(item.get('note_globale')) >= threshold
            ]
        except (TypeError, ValueError):
            pass

    if sort_by == 'note_desc':
        data.sort(key=lambda item: (item.get('note_globale') is None, -(item.get('note_globale') or 0), item.get('nom') or ''))
    elif sort_by == 'note_asc':
        data.sort(key=lambda item: (item.get('note_globale') is None, item.get('note_globale') or 0, item.get('nom') or ''))
    elif sort_by == 'date_asc':
        data.sort(key=lambda item: item.get('date_creation_sort') or '')
    else:
        data.sort(key=lambda item: item.get('date_creation_sort') or '', reverse=True)

    return data


AGENT_RECOUVREMENT_QUESTIONS = [
    {
        'type_question': 'qcm',
        'texte_question': "Raha misy client manana facture 4 tsy voaloa ary milaza fa iray ihany no zakany aloa androany, inona no fomba fiasa matihanina indrindra ?",
        'options_qcm': "Mandray ny vola nefa tsy manoratra fanazavana|Manamarina ny antontan-taratasy rehetra, mandray ny ampahany voaloa araka ny procedure, ary manoratra mazava ny ambiny sy ny fifanekena|Mamafa ny trosa taloha mba hanamorana ny resaka|Miala eo noho eo satria tsy afaka mandoa manontolo ny client",
        'reponse_correcte': "manamarina ny antontan-taratasy rehetra, mandray ny ampahany voaloa araka ny procedure, ary manoratra mazava ny ambiny sy ny fifanekena",
        'points': 3,
        'ordre': 1,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Inona no loza lehibe indrindra raha mandray vola ianao nefa tsy manome porofo sy tsy mandrakitra avy hatrany ?",
        'options_qcm': "Tsy misy loza satria mbola tadidinao ihany|Mety hisy tsy fitoviana amin'ny caisse, fitarainan'ny client, ary olana amin'ny audit|Mampitombo automatique ny taux de recouvrement|Manamora ny asa eny an-kianja",
        'reponse_correcte': "mety hisy tsy fitoviana amin'ny caisse, fitarainan'ny client, ary olana amin'ny audit",
        'points': 3,
        'ordre': 2,
    },
    {
        'type_question': 'chiffres',
        'texte_question': "Client iray no manana facture 18500 Ar, 22000 Ar ary 14500 Ar. Nandoa 30000 Ar izy androany. Firy ny ambiny mbola tokony haloany ?",
        'reponse_correcte': '25000',
        'points': 3,
        'ordre': 3,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Raha manohitra ny montant ao amin'ny facture ny client, inona no dingana voalohany marina indrindra ?",
        'options_qcm': "Miteny avy hatrany fa tsy maintsy mandoa izy|Manamarina ny reference, ny facture ary ny tantara voarakitra alohan'ny hanapahana hevitra|Manafoana avy hatrany ny trosa|Maka vola amin'izay montant tian'ny client haloha",
        'reponse_correcte': "manamarina ny reference, ny facture ary ny tantara voarakitra alohan'ny hanapahana hevitra",
        'points': 3,
        'ordre': 4,
    },
    {
        'type_question': 'chiffres',
        'texte_question': "Nitsidika client 28 ianao androany. 17 no nandoa, 6 no nanao fifanekena handoa afaka 3 andro, ary ny ambiny tsy tratra. Firy ny client tsy tratra ?",
        'reponse_correcte': '5',
        'points': 2,
        'ordre': 5,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Raha hita fa tsy mitovy ny vola voaray sy ny vola voarakitra amin'ny faran'ny andro, inona no fihetsika tokony hatao voalohany ?",
        'options_qcm': "Miandry rahampitso sao mazava ho azy|Mamerina mijery avy hatrany ny receipt, ny reference client, ny enregistrement ary mampandre ny tompon'andraikitra|Mampiditra vola avy am-paosy mba hitovy|Mamafa ny enregistrement rehetra",
        'reponse_correcte': "mamerina mijery avy hatrany ny receipt, ny reference client, ny enregistrement ary mampandre ny tompon'andraikitra",
        'points': 3,
        'ordre': 6,
    },
    {
        'type_question': 'texte_libre',
        'texte_question': "Lazao ny fepetra 3 manan-danja amin'ny fitantanana recouvrement tsara eny an-kianja.",
        'reponse_correcte': 'fahitsiana,porofo,fanarahana',
        'points': 3,
        'ordre': 7,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Inona avy ireo singa tokony hifanaraka tsara rehefa mandray vola amin'ny client ?",
        'options_qcm': "Anaran'ny client fotsiny|Reference client na facture, montant voaray, daty, ary porofon'ny fandoavana|Lokon'ny trano sy nomeraon-telefaonina|Soniavan'ny mpifanolo-bodirindrina",
        'reponse_correcte': "reference client na facture, montant voaray, daty, ary porofon'ny fandoavana",
        'points': 3,
        'ordre': 8,
    },
    {
        'type_question': 'oui_non',
        'texte_question': "Azo ovaina am-bava ve ny montant ao amin'ny facture raha mangataka fihenam-bidy ny client nefa tsy misy fanomezan-dalana ofisialy ?",
        'reponse_correcte': 'tsia',
        'points': 2,
        'ordre': 9,
    },
    {
        'type_question': 'texte_libre',
        'texte_question': "Hazavao amin'ny dingana fohy izay ataonao raha misy client mandà handoa ary miakatra ny fifandirana.",
        'reponse_correcte': 'mihaino,manamarina,mampandre',
        'points': 4,
        'ordre': 10,
    },
    {
        'type_question': 'chiffres',
        'texte_question': "Misy client 3 nandoa androany: 12500 Ar, 37500 Ar ary 22000 Ar. Ohatrinona ny totalim-bola voaray ?",
        'reponse_correcte': '72000',
        'points': 2,
        'ordre': 11,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Raha tsy eo ny tompon-trano fa misy havany te-handoa, inona no tokony hataon'ny agent de recouvrement ?",
        'options_qcm': "Mandray vola fotsiny tsy manamarina|Manamarina ny lien amin'ilay dossier, ny reference client, ary manome porofo mazava amin'ny fandoavana|Mandà foana na inona na inona|Mangataka vola fanampiny alohan'ny handraisana ny paiement",
        'reponse_correcte': "manamarina ny lien amin'ilay dossier, ny reference client, ary manome porofo mazava amin'ny fandoavana",
        'points': 3,
        'ordre': 12,
    },
    {
        'type_question': 'oui_non',
        'texte_question': "Raha mbola tsy voamarina ny reference client, azo raisina ve ny paiement dia ahitsy any aoriana ?",
        'reponse_correcte': 'tsia',
        'points': 2,
        'ordre': 13,
    },
    {
        'type_question': 'texte_libre',
        'texte_question': "Lazao ireo dingana 4 tokony hatao mba hiantohana ny traçabilité tsara rehefa vita ny encaissement.",
        'reponse_correcte': 'manamarina,mandrakitra,porofo,tatitra',
        'points': 4,
        'ordre': 14,
    },
    {
        'type_question': 'chiffres',
        'texte_question': "Raha 64 ny client tao anatin'ny parcours, 18 tsy tratra, 11 nanao engagement, ary ny ambiny nandoa, firy ny client tena nandoa ?",
        'reponse_correcte': '35',
        'points': 3,
        'ordre': 15,
    },
]

AGENT_RECOUVREMENT_ENTRETIEN_QUESTIONS = [
    {'ordre': 1, 'texte_question': "Hazavao ny fomba handanjaljanao ny tanjon'ny recouvrement sy ny fitazonana fifandraisana tsara amin'ny client."},
    {'ordre': 2, 'texte_question': "Raha client iray no tezitra sy mandrahona tsy handoa mihitsy, ahoana no fomba fitondranao ny resaka sy ny porofo tazoninao ?"},
    {'ordre': 3, 'texte_question': "Ahoana no hamantaranao fa tokony hampiakatra dossier any amin'ny tompon'andraikitra fa tsy hanapa-kevitra irery ?"},
    {'ordre': 4, 'texte_question': "Omeo ohatra ny fomba handaminanao parcours recouvrement raha be ny client, voafetra ny fotoana, ary mila marina ny traçabilité."},
    {'ordre': 5, 'texte_question': "Raha misy elanelana eo amin'ny caisse sy ny enregistrement, inona avy ireo fanamarinana hataonao alohan'ny hitaterana izany ?"},
    {'ordre': 6, 'texte_question': "Inona no fomba hanazavanao amin'ny client iray ny antony tsy ahafahana manova facture am-bava na manome fihenam-bidy tsy ara-dalàna ?"},
    {'ordre': 7, 'texte_question': "Ahoana no handrefesanao ny fahombiazan'ny asanao amin'ny recouvrement, ankoatra ny vola voaangona ?"},
    {'ordre': 8, 'texte_question': "Inona no ataonao mba hisorohana hosoka, fahadisoam-panoratana, na fitarainana avy amin'ny client mandritra ny recouvrement ?"},
    {'ordre': 9, 'texte_question': "Raha maro ny client mitaraina noho ny erreur mitovy amin'ny facture, ahoana no fomba handraisanao izany sy handefasanao feedback any amin'ny equipe concernée ?"},
    {'ordre': 10, 'texte_question': "Ahoana no handaminanao ny priorités raha mitambatra ny objectifs de collecte, ny engagements à suivre, ary ny dossiers litigieux ?"},
    {'ordre': 11, 'texte_question': "Inona no indicateurs hampiasainao hahafantarana fa nihatsara tokoa ny qualité de recouvrement-nao tao anatin'ny iray volana ?"},
    {'ordre': 12, 'texte_question': "Hazavao ny fomba fihetsikao raha misy olona manolotra vola tsy ara-dalàna mba hanafoanana trosa na hanovana enregistrement."},
]

ASSISTANT_ADMIN_QUESTIONS = [
    {
        'type_question': 'qcm',
        'texte_question': "Vous recevez 3 pièces pour une même dépense: un bon de commande à 420 000 Ar, une facture à 420 000 Ar et un reçu à 390 000 Ar. Quelle est la meilleure action initiale ?",
        'options_qcm': "Enregistrer 420 000 Ar pour aller vite|Enregistrer 390 000 Ar car c'est le reçu|Bloquer la saisie, rapprocher les 3 pièces et signaler l'écart avant validation|Moyenner les deux montants",
        'reponse_correcte': "bloquer la saisie, rapprocher les 3 pièces et signaler l'écart avant validation",
        'points': 4,
        'ordre': 1,
    },
    {
        'type_question': 'texte_libre',
        'texte_question': "Citez 4 contrôles indispensables avant de saisir une facture fournisseur dans le système.",
        'reponse_correcte': "date,montant,reference,imputation",
        'points': 4,
        'ordre': 2,
    },
    {
        'type_question': 'chiffres',
        'texte_question': "Une facture de 1 248 500 Ar comprend 3 lignes: 425 000 Ar, 398 500 Ar et 425 000 Ar. Quel est le montant de la 2e ligne ?",
        'reponse_correcte': '398500',
        'points': 3,
        'ordre': 3,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Un responsable vous demande de modifier la date d'une pièce pour la faire entrer dans un mois déjà clôturé, sans justification écrite. Que faites-vous ?",
        'options_qcm': "J'exécute la demande immédiatement|Je modifie la date puis j'informe plus tard|Je refuse la modification informelle, demande une validation conforme et escalade si nécessaire|Je supprime simplement la pièce",
        'reponse_correcte': "je refuse la modification informelle, demande une validation conforme et escalade si nécessaire",
        'points': 4,
        'ordre': 4,
    },
    {
        'type_question': 'oui_non',
        'texte_question': "Peut-on valider une saisie si la pièce est illisible sur le montant mais que le fournisseur est identifiable ?",
        'reponse_correcte': 'non',
        'points': 2,
        'ordre': 5,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Quel risque est le plus critique si un assistant admin saisit une même facture deux fois sous deux références légèrement différentes ?",
        'options_qcm': "Aucun si les montants sont identiques|Risque de double paiement et de distorsion des états comptables|Seulement un problème esthétique dans le libellé|Simple retard de classement papier",
        'reponse_correcte': "risque de double paiement et de distorsion des états comptables",
        'points': 4,
        'ordre': 6,
    },
    {
        'type_question': 'chiffres',
        'texte_question': "Vous avez 125 pièces à saisir. 18 sont rejetées pour pièces manquantes, 9 sont des doublons, 11 restent en attente de validation. Combien peuvent être saisies correctement maintenant ?",
        'reponse_correcte': '87',
        'points': 3,
        'ordre': 7,
    },
    {
        'type_question': 'texte_libre',
        'texte_question': "Expliquez la différence entre rapidité de saisie et qualité de saisie, et comment vous arbitrez entre les deux sous pression.",
        'reponse_correcte': "controle,fiabilite,priorisation,traçabilite",
        'points': 4,
        'ordre': 8,
    },
    {
        'type_question': 'qcm',
        'texte_question': "En fin de journée, vous constatez un écart entre votre tableau de suivi et le système. Quelle est la meilleure séquence d'action ?",
        'options_qcm': "Corriger directement le tableau local|Attendre le lendemain pour voir si l'écart disparaît|Comparer les références, reprendre les pièces sources, isoler les écritures concernées puis documenter l'écart|Supprimer les écritures du jour",
        'reponse_correcte': "comparer les références, reprendre les pièces sources, isoler les écritures concernées puis documenter l'écart",
        'points': 4,
        'ordre': 9,
    },
    {
        'type_question': 'texte_libre',
        'texte_question': "Donnez 3 indicateurs concrets permettant d'évaluer la performance d'un assistant admin en saisie documentaire et comptable.",
        'reponse_correcte': "erreur,delai,volume",
        'points': 3,
        'ordre': 10,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Quelle pratique améliore le plus la traçabilité d'une opération saisie ?",
        'options_qcm': "Mémoriser les références importantes|Utiliser un libellé standard, relier la pièce justificative et conserver la référence exacte|Réduire les détails pour gagner du temps|Renommer librement les fournisseurs à chaque saisie",
        'reponse_correcte': "utiliser un libellé standard, relier la pièce justificative et conserver la référence exacte",
        'points': 3,
        'ordre': 11,
    },
    {
        'type_question': 'chiffres',
        'texte_question': "Une avance de 780 000 Ar est justifiée par 4 dépenses: 215 000 Ar, 180 000 Ar, 96 500 Ar et 221 500 Ar. Quel est le reliquat non justifié ?",
        'reponse_correcte': '67000',
        'points': 4,
        'ordre': 12,
    },
]

ASSISTANT_ADMIN_ENTRETIEN_QUESTIONS = [
    {'ordre': 1, 'texte_question': "Décrivez votre méthode pour traiter un lot important de pièces tout en maintenant un faible taux d'erreur."},
    {'ordre': 2, 'texte_question': "Parlez d'une situation où vous avez détecté une incohérence documentaire ou comptable avant validation. Qu'avez-vous fait concrètement ?"},
    {'ordre': 3, 'texte_question': "Comment réagissez-vous lorsqu'un supérieur vous demande une saisie non conforme à la procédure mais urgente ?"},
    {'ordre': 4, 'texte_question': "Quels contrôles mettez-vous en place pour éviter les doublons, les erreurs de montant et les mauvaises imputations ?"},
    {'ordre': 5, 'texte_question': "Comment organisez-vous vos priorités entre urgences, volume de saisie, classement des pièces et demandes imprévues ?"},
    {'ordre': 6, 'texte_question': "Si vous découvrez après validation qu'une pièce a été mal saisie, comment gérez-vous la correction et la traçabilité ?"},
    {'ordre': 7, 'texte_question': "Quels outils ou méthodes utilisez-vous pour suivre votre productivité sans dégrader la qualité ?"},
    {'ordre': 8, 'texte_question': "Comment expliquez-vous à un collègue non administratif qu'une pièce ne peut pas être traitée en l'état ?"},
    {'ordre': 9, 'texte_question': "Quelles informations doivent absolument apparaître dans un bon commentaire ou une note de suivi lorsqu'un dossier est bloqué ?"},
    {'ordre': 10, 'texte_question': "Comment contribueriez-vous à améliorer durablement l'organisation documentaire et la fiabilité des données dans l'équipe ?"},
]


RESPONSABLE_OPERATIONNEL_QUESTIONS = [
    {
        'type_question': 'qcm',
        'texte_question': "Une panne de pompe touche 3 ouvrages le meme matin, avec une equipe limitee et des clients deja en attente. Quelle est la meilleure logique de priorisation ?",
        'options_qcm': "Intervenir d'abord sur l'ouvrage le plus proche|Prioriser selon impact usagers, risque d'interruption, securite, disponibilite des pieces et plan de continuite|Laisser chaque technicien choisir librement sa mission|Attendre la reunion hebdomadaire pour arbitrer",
        'reponse_correcte': "prioriser selon impact usagers, risque d'interruption, securite, disponibilite des pieces et plan de continuite",
        'points': 5,
        'ordre': 1,
    },
    {
        'type_question': 'texte_libre',
        'texte_question': "Citez 5 indicateurs que doit suivre un Responsable operationnel pour piloter exploitation, maintenance et qualite de service.",
        'reponse_correcte': "disponibilite,pannes,delai,qualite,cout",
        'points': 5,
        'ordre': 2,
    },
    {
        'type_question': 'chiffres',
        'texte_question': "Une base gere 18 ouvrages. 4 sont a l'arret, 3 tournent avec performance degradee, les autres sont pleinement operationnels. Quel est le nombre d'ouvrages pleinement operationnels ?",
        'reponse_correcte': '11',
        'points': 3,
        'ordre': 3,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Un chef de base annonce que tout va bien, mais les rapports montrent une hausse des pannes recurrentes et des retards de maintenance preventive. Que faites-vous d'abord ?",
        'options_qcm': "Faire confiance sans verifier|Demander un rapport plus optimiste|Croiser les donnees, challenger les causes, verifier terrain si necessaire et definir un plan correctif date|Sanctionner immediatement toute l'equipe",
        'reponse_correcte': "croiser les donnees, challenger les causes, verifier terrain si necessaire et definir un plan correctif date",
        'points': 5,
        'ordre': 4,
    },
    {
        'type_question': 'oui_non',
        'texte_question': "Peut-on differer une maintenance preventive critique simplement pour tenir un objectif court terme de cout sans analyse de risque ?",
        'reponse_correcte': 'non',
        'points': 3,
        'ordre': 5,
    },
    {
        'type_question': 'chiffres',
        'texte_question': "Le budget mensuel maintenance est de 12 500 000 Ar. Trois interventions urgentes coutent 1 850 000 Ar, 2 400 000 Ar et 975 000 Ar. Quel budget reste disponible ?",
        'reponse_correcte': '7275000',
        'points': 4,
        'ordre': 6,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Quel comportement correspond le mieux a une posture de manager coach dans une equipe terrain en difficulte ?",
        'options_qcm': "Donner uniquement des ordres et controler chaque detail|Poser un cadre clair, faire analyser les causes par l'equipe, debloquer les obstacles et suivre les engagements|Eviter les feedbacks pour conserver une bonne ambiance|Remplacer l'equipe sans chercher a comprendre",
        'reponse_correcte': "poser un cadre clair, faire analyser les causes par l'equipe, debloquer les obstacles et suivre les engagements",
        'points': 5,
        'ordre': 7,
    },
    {
        'type_question': 'texte_libre',
        'texte_question': "Expliquez comment vous distinguez un probleme de discipline, un probleme de competence et un probleme d'organisation dans une equipe operationnelle.",
        'reponse_correcte': "faits,analyse,accompagnement,mesure",
        'points': 5,
        'ordre': 8,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Une meme panne revient 5 fois en 2 mois sur le meme ouvrage. Quelle est l'approche la plus solide ?",
        'options_qcm': "Changer la piece a chaque fois sans autre analyse|Faire une analyse de cause racine, verifier execution maintenance, competences, usage, pieces et mettre une action preventive|Blamer uniquement le technicien|Attendre une panne plus grave pour agir",
        'reponse_correcte': "faire une analyse de cause racine, verifier execution maintenance, competences, usage, pieces et mettre une action preventive",
        'points': 5,
        'ordre': 9,
    },
    {
        'type_question': 'chiffres',
        'texte_question': "Sur 240 interventions prevues dans le mois, 198 ont ete faites dans les delais, 24 en retard et 6 annulees. Combien d'interventions n'ont pas ete faites dans les delais ?",
        'reponse_correcte': '42',
        'points': 4,
        'ordre': 10,
    },
    {
        'type_question': 'texte_libre',
        'texte_question': "Donnez 4 elements indispensables d'un bon compte rendu operationnel hebdomadaire a adresser a la direction.",
        'reponse_correcte': "resultats,ecarts,causes,actions",
        'points': 4,
        'ordre': 11,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Un technicien performant cree pourtant une mauvaise ambiance et ne transmet pas son savoir. Quelle est la meilleure reponse manageriale ?",
        'options_qcm': "L'ignorer car il est performant|Le recadrer sur les comportements attendus, fixer des attentes de transmission et suivre l'evolution|Le promouvoir rapidement|Transferer le conflit a l'equipe RH sans entretien prealable",
        'reponse_correcte': "le recadrer sur les comportements attendus, fixer des attentes de transmission et suivre l'evolution",
        'points': 5,
        'ordre': 12,
    },
    {
        'type_question': 'oui_non',
        'texte_question': "Un Responsable operationnel peut-il valider une information terrain critique sans verifier la source ni la coherence des donnees ?",
        'reponse_correcte': 'non',
        'points': 3,
        'ordre': 13,
    },
    {
        'type_question': 'chiffres',
        'texte_question': "Une zone compte 12 chefs de base. 3 depassent leur budget de plus de 10 %, 2 sont exactement au budget, les autres sont en dessous. Combien sont en dessous du budget ?",
        'reponse_correcte': '7',
        'points': 3,
        'ordre': 14,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Quelle decision est la plus pertinente si vous constatez que la qualite de l'eau est conforme sur le papier mais que les reclamations clients augmentent fortement ?",
        'options_qcm': "Ignorer les reclamations puisque les rapports sont conformes|Ouvrir une verification croisee terrain-donnees-clients pour identifier l'ecart entre conformite declaree et experience reelle|Communiquer uniquement sur les bons chiffres|Reporter le sujet a la fin du trimestre",
        'reponse_correcte': "ouvrir une verification croisee terrain-donnees-clients pour identifier l'ecart entre conformite declaree et experience reelle",
        'points': 5,
        'ordre': 15,
    },
    {
        'type_question': 'texte_libre',
        'texte_question': "Comment organisez-vous un point de performance avec des chefs de base pour qu'il soit a la fois exigeant, factuel et coachant ?",
        'reponse_correcte': "indicateurs,ecoute,feedback,engagements",
        'points': 5,
        'ordre': 16,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Parmi ces options, quelle action aide le plus a departager des chefs de base solides de ceux qui pilotent uniquement par intuition ?",
        'options_qcm': "Leur demander s'ils se sentent confiants|Comparer leur capacite a expliquer les resultats par indicateurs, causes et plan d'action concret|Mesurer uniquement leur anciennete|Regarder seulement leur aisance orale",
        'reponse_correcte': "comparer leur capacite a expliquer les resultats par indicateurs, causes et plan d'action concret",
        'points': 4,
        'ordre': 17,
    },
    {
        'type_question': 'texte_libre',
        'texte_question': "Vous hereditez d'une equipe demotivee, reactive et peu rigoureuse. Quelles 4 priorites lancez-vous dans les 30 premiers jours ?",
        'reponse_correcte': "diagnostic,cadre,priorites,accompagnement",
        'points': 5,
        'ordre': 18,
    },
]


RESPONSABLE_OPERATIONNEL_ENTRETIEN_QUESTIONS = [
    {'ordre': 1, 'texte_question': "Racontez une situation ou vous avez du redresser une operation en retard ou degradee. Comment avez-vous diagnostique, arbitre et execute ?"},
    {'ordre': 2, 'texte_question': "Comment pilotez-vous une equipe de chefs de base ou superviseurs avec des niveaux tres differents, sans tomber dans le micro-management ?"},
    {'ordre': 3, 'texte_question': "Donnez un exemple concret de posture manager coach: comment faites-vous progresser un collaborateur fiable mais limite dans son analyse ?"},
    {'ordre': 4, 'texte_question': "Quand les chiffres remontes par le terrain paraissent bons mais que votre intuition dit l'inverse, que faites-vous exactement ?"},
    {'ordre': 5, 'texte_question': "Comment decidez-vous entre une urgence technique immediate et une action preventive importante mais moins visible ?"},
    {'ordre': 6, 'texte_question': "Quels indicateurs regardez-vous chaque semaine pour piloter exploitation, maintenance, securite et satisfaction usagers ?"},
    {'ordre': 7, 'texte_question': "Comment recadrez-vous un responsable local qui atteint ses resultats mais detruit la cohesion de son equipe ?"},
    {'ordre': 8, 'texte_question': "Parlez d'une decision impopulaire que vous avez prise pour proteger la qualite de service ou la rigueur operationnelle."},
    {'ordre': 9, 'texte_question': "Quelle est votre methode pour transformer une suite de pannes repetitives en plan d'amelioration durable ?"},
    {'ordre': 10, 'texte_question': "Comment conduisez-vous une reunion d'analyse de performance pour faire parler les faits, responsabiliser et faire emerger des solutions du terrain ?"},
    {'ordre': 11, 'texte_question': "Decrivez votre facon de gerer un conflit entre exploitation, maintenance et finance quand chacun protege son propre objectif."},
    {'ordre': 12, 'texte_question': "Comment distinguez-vous un collaborateur qui manque de volonte d'un collaborateur qui manque d'outils, de methode ou de coaching ?"},
    {'ordre': 13, 'texte_question': "Si vous prenez le poste demain, quelles 5 questions poseriez-vous dans la premiere semaine pour comprendre les vrais leviers de performance ?"},
    {'ordre': 14, 'texte_question': "Comment feriez-vous grandir vos relais manageriaux pour que l'organisation depende moins de vous au quotidien ?"},
]


SUPERVISEUR_TECHNIQUE_QUESTIONS = [
    {
        'type_question': 'qcm',
        'texte_question': "Quelle est la priorite principale d'un Superviseur technique chez Hydria ?",
        'options_qcm': "Remplacer le Responsable operationnel dans toutes ses fonctions|Superviser les operations techniques terrain, encadrer les MI et garantir la conformite des ouvrages|Faire uniquement des achats de pieces|Se limiter a rediger des rapports mensuels",
        'reponse_correcte': "superviser les operations techniques terrain, encadrer les mi et garantir la conformite des ouvrages",
        'points': 3,
        'ordre': 1,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Quel support Hydria est explicitement cite pour verifier la maintenance, la proprete et l'etat des ouvrages ?",
        'options_qcm': "Le journal de caisse|Le cahier fanarahamaso|La fiche de paie|Le grand livre comptable",
        'reponse_correcte': "le cahier fanarahamaso",
        'points': 3,
        'ordre': 2,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Dans l'organisation Hydria, le Superviseur technique rend compte directement a quel role ?",
        'options_qcm': "Directeur adjoint|Responsable operationnel d'antenne|Caissiere|Chef comptable",
        'reponse_correcte': "responsable operationnel d'antenne",
        'points': 2,
        'ordre': 3,
    },
    {
        'type_question': 'texte_libre',
        'texte_question': "Citez 4 responsabilites cles du Superviseur technique mentionnees dans la fiche de poste.",
        'reponse_correcte': "supervision,planning,stock,rapport",
        'points': 4,
        'ordre': 4,
    },
    {
        'type_question': 'chiffres',
        'texte_question': "Un ST planifie 18 interventions sur le mois. 11 sont terminees, 4 sont reportees faute de pieces, 2 sont en attente de validation et 1 annulee. Combien d'interventions ne sont pas terminees ?",
        'reponse_correcte': '7',
        'points': 3,
        'ordre': 5,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Si un ouvrage presente un risque technique eleve et qu'une equipe MI n'a pas la competence suffisante, quelle action est la plus correcte ?",
        'options_qcm': "Laisser l'equipe intervenir seule pour gagner du temps|Reporter sans information aux usagers|Appuyer techniquement l'equipe, securiser l'intervention, replanifier si necessaire et remonter l'alerte|Demander aux usagers de reparer eux-memes",
        'reponse_correcte': "appuyer techniquement l'equipe, securiser l'intervention, replanifier si necessaire et remonter l'alerte",
        'points': 4,
        'ordre': 6,
    },
    {
        'type_question': 'oui_non',
        'texte_question': "Le Superviseur technique peut-il venir en appui a l'ARS en cas de besoin ?",
        'reponse_correcte': 'oui',
        'points': 2,
        'ordre': 7,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Quel enchainement est le plus coherent pour bien suivre les stocks techniques ?",
        'options_qcm': "Attendre la rupture avant de verifier|Suivre les fiches de stock, controler l'etat du stock periodiquement, alerter sur le seuil minimum et verifier la disponibilite pour les MI|Commander du materiel sans verifier le stock reel|Laisser chaque MI gerer seul son propre stock",
        'reponse_correcte': "suivre les fiches de stock, controler l'etat du stock periodiquement, alerter sur le seuil minimum et verifier la disponibilite pour les mi",
        'points': 4,
        'ordre': 8,
    },
    {
        'type_question': 'chiffres',
        'texte_question': "Le controle bimestriel releve 26 references en stock. 5 sont sous seuil minimum, 3 sont en rupture et 2 sont defectueuses. Combien de references restent disponibles sans alerte immediate ?",
        'reponse_correcte': '16',
        'points': 3,
        'ordre': 9,
    },
    {
        'type_question': 'texte_libre',
        'texte_question': "Quels elements doivent apparaitre dans un bon rapport d'observation technique apres visite d'ouvrage ?",
        'reponse_correcte': "constat,risque,solution,priorite",
        'points': 4,
        'ordre': 10,
    },
    {
        'type_question': 'qcm',
        'texte_question': "La fiche de poste fixe aussi un objectif sur les ouvrages de grade B. Lequel ?",
        'options_qcm': "Les supprimer sous 6 mois|Les convertir en grade A d'ici 2 ans|Les confier uniquement aux IA|Les sortir du planning mensuel",
        'reponse_correcte': "les convertir en grade a d'ici 2 ans",
        'points': 3,
        'ordre': 11,
    },
    {
        'type_question': 'qcm',
        'texte_question': "D'apres les regles Hydria, quelle visibilite operationnelle a un Superviseur technique ?",
        'options_qcm': "Seulement ses propres ouvrages et plannings|Tous les ouvrages, plannings et employes de sa base|Tous les ouvrages de l'organisation nationale|Uniquement les stocks du siege",
        'reponse_correcte': "tous les ouvrages, plannings et employes de sa base",
        'points': 4,
        'ordre': 12,
    },
]


SUPERVISEUR_TECHNIQUE_ENTRETIEN_QUESTIONS = [
    {'ordre': 1, 'texte_question': "Expliquez comment vous organiseriez un planning mensuel de renforcement des MI a partir des competences disponibles et des besoins constates sur les ouvrages."},
    {'ordre': 2, 'texte_question': "Donnez un exemple concret de situation ou vous devez arbitrer entre urgence technique, disponibilite des pieces et impact usagers. Comment decidez-vous ?"},
    {'ordre': 3, 'texte_question': "Comment utilisez-vous le cahier fanarahamaso pour transformer une simple visite terrain en suivi technique exploitable par l'antenne ?"},
    {'ordre': 4, 'texte_question': "Quelle methode mettez-vous en place pour faire progresser les ouvrages de grade B vers le grade A sur un horizon de 2 ans ?"},
    {'ordre': 5, 'texte_question': "Comment encadrez-vous une equipe MI heterogene sans faire a leur place, tout en maintenant un niveau de conformite eleve ?"},
    {'ordre': 6, 'texte_question': "Que faites-vous quand une intervention est mal executee par une equipe ou un IA: reprise immediate, formation, rapport, responsabilisation ? Detaillez."},
    {'ordre': 7, 'texte_question': "Comment suivez-vous les stocks techniques, les devis, les achats et les livraisons pour eviter qu'un probleme de logistique bloque la maintenance ?"},
    {'ordre': 8, 'texte_question': "Quelles informations faites-vous remonter au Responsable operationnel apres une tournee technique, et sous quel format pour aider a la priorisation ?"},
    {'ordre': 9, 'texte_question': "Dans quels cas le ST doit-il venir en appui a l'ARS ou a une autre antenne, et comment garder la priorite sur sa propre base ?"},
    {'ordre': 10, 'texte_question': "Quels indicateurs suivriez-vous chaque mois pour piloter la qualite technique de votre base: ouvrages conformes, delais, ruptures de stock, reinterventions, autres ?"},
]


DIRECTEUR_ADJOINT_QUESTIONS = [
    {
        'type_question': 'qcm',
        'texte_question': "En tant que Directeur adjoint, quel arbitrage est le plus pertinent si la croissance de la couverture compromet la qualite de service et la capacite interne ?",
        'options_qcm': "Continuer la croissance sans reserve|Geler toute activite commerciale pendant un an|Reprioriser selon impact strategique, capacite d'execution, risque qualite et plan de renforcement managerial|Laisser chaque departement decider seul",
        'reponse_correcte': "reprioriser selon impact strategique, capacite d'execution, risque qualite et plan de renforcement managerial",
        'points': 5,
        'ordre': 1,
    },
    {
        'type_question': 'texte_libre',
        'texte_question': "Citez 5 indicateurs de pilotage qu'un Directeur adjoint doit suivre pour seconder efficacement le Directeur.",
        'reponse_correcte': "cash,service,productivite,risques,execution",
        'points': 5,
        'ordre': 2,
    },
    {
        'type_question': 'chiffres',
        'texte_question': "Le plan trimestriel prevoit 24 chantiers prioritaires. 9 sont termines, 7 sont dans les delais, 4 sont en retard critique. Combien n'ont pas encore demarre ?",
        'reponse_correcte': '4',
        'points': 4,
        'ordre': 3,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Le Directeur est absent pendant une semaine et deux responsables vous remontent des versions contradictoires sur un sujet sensible. Que faites-vous ?",
        'options_qcm': "Choisir la version du plus ancien|Reporter la decision jusqu'au retour du Directeur|Rassembler les faits, verifier les donnees, entendre les parties et trancher avec tracabilite selon l'interet de l'organisation|Prendre une decision intuitive sans justification",
        'reponse_correcte': "rassembler les faits, verifier les donnees, entendre les parties et trancher avec tracabilite selon l'interet de l'organisation",
        'points': 5,
        'ordre': 4,
    },
    {
        'type_question': 'oui_non',
        'texte_question': "Un Directeur adjoint doit-il proteger l'organisation d'une mauvaise decision meme si celle-ci vient d'un manager influent ?",
        'reponse_correcte': 'oui',
        'points': 3,
        'ordre': 5,
    },
    {
        'type_question': 'chiffres',
        'texte_question': "Un budget annuel de 480 000 000 Ar est consomme a 38 % au 30 avril. Quel montant a deja ete consomme ?",
        'reponse_correcte': '182400000',
        'points': 4,
        'ordre': 6,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Laquelle de ces actions releve le plus d'un Directeur adjoint en posture de manager coach ?",
        'options_qcm': "Centraliser toutes les decisions pour aller plus vite|Faire grandir les responsables en clarifiant attentes, questionnant leur analyse, donnant du feedback exigeant et suivant les engagements|Eviter les feedbacks difficiles|Corriger soi-meme tous les dossiers complexes",
        'reponse_correcte': "faire grandir les responsables en clarifiant attentes, questionnant leur analyse, donnant du feedback exigeant et suivant les engagements",
        'points': 5,
        'ordre': 7,
    },
    {
        'type_question': 'texte_libre',
        'texte_question': "Expliquez comment vous gerez l'equilibre entre loyaute au Directeur, autonomie de decision et remontee d'alerte.",
        'reponse_correcte': "alignement,initiative,alerte,transparence",
        'points': 5,
        'ordre': 8,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Une direction depense beaucoup d'energie en urgences repetitives. Quelle est la meilleure reponse de pilotage ?",
        'options_qcm': "Accepter que ce soit la norme|Traiter les urgences puis lancer une revue structurelle des causes, des responsabilites, des priorites et des routines de pilotage|Changer tous les managers d'un coup|Communiquer seulement sur les succes",
        'reponse_correcte': "traiter les urgences puis lancer une revue structurelle des causes, des responsabilites, des priorites et des routines de pilotage",
        'points': 5,
        'ordre': 9,
    },
    {
        'type_question': 'chiffres',
        'texte_question': "Sur 15 responsables, 4 sont autonomes, 6 progressent avec coaching, 3 sont en alerte et 2 sont vacants. Combien ont besoin d'un accompagnement actif ou d'une action manageriale forte ?",
        'reponse_correcte': '11',
        'points': 4,
        'ordre': 10,
    },
    {
        'type_question': 'texte_libre',
        'texte_question': "Donnez 4 signes qu'une organisation est mal pilotee meme si les tableaux de bord paraissent rassurants.",
        'reponse_correcte': "contradictions,repetitions,retards,dependance",
        'points': 4,
        'ordre': 11,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Quel est le meilleur usage d'un comite de direction hebdomadaire ?",
        'options_qcm': "Partager uniquement des informations generales|Revoir les ecarts majeurs, arbitrer, responsabiliser les leaders et decider des actions datees avec suivi|Rappeler les procedures sans debat|Laisser chaque manager lire son rapport",
        'reponse_correcte': "revoir les ecarts majeurs, arbitrer, responsabiliser les leaders et decider des actions datees avec suivi",
        'points': 4,
        'ordre': 12,
    },
    {
        'type_question': 'oui_non',
        'texte_question': "Peut-on juger qu'un manager est solide seulement parce qu'il rassure bien en reunion, sans verifier sa capacite a tenir les engagements ?",
        'reponse_correcte': 'non',
        'points': 3,
        'ordre': 13,
    },
    {
        'type_question': 'chiffres',
        'texte_question': "Le chiffre d'affaires mensuel cible est de 96 000 000 Ar. Les trois premiers mois realisent respectivement 88 000 000 Ar, 102 000 000 Ar et 91 000 000 Ar. Quel est l'ecart cumule par rapport a 3 mois de cible ?",
        'reponse_correcte': '-7000000',
        'points': 5,
        'ordre': 14,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Vous identifiez un manager tres loyal mais faible en arbitrage et en courage managerial. Quelle approche est la plus juste ?",
        'options_qcm': "Le laisser en place sans accompagnement car il est loyal|Le coacher sur cas reels, clarifier les standards de decision, observer ses progres et reevaluer objectivement|Le remplacer immediatement sans feedback|Lui retirer toutes ses responsabilites sans explication",
        'reponse_correcte': "le coacher sur cas reels, clarifier les standards de decision, observer ses progres et reevaluer objectivement",
        'points': 5,
        'ordre': 15,
    },
    {
        'type_question': 'texte_libre',
        'texte_question': "Quelles 4 composantes doivent figurer dans un bon plan d'execution strategique trimestriel ?",
        'reponse_correcte': "priorites,responsables,echeances,indicateurs",
        'points': 4,
        'ordre': 16,
    },
    {
        'type_question': 'qcm',
        'texte_question': "Quelle situation devrait alerter en priorite un Directeur adjoint ?",
        'options_qcm': "Une equipe tres demandante en feedback|Des ecarts repetes entre discours, chiffres et execution sur plusieurs services|Un manager qui pose beaucoup de questions|Un report trop detaille",
        'reponse_correcte': "des ecarts repetes entre discours, chiffres et execution sur plusieurs services",
        'points': 4,
        'ordre': 17,
    },
    {
        'type_question': 'texte_libre',
        'texte_question': "Si le poste de Directeur adjoint a la meme fiche que Directeur, quelles competences devez-vous demontrer des les 90 premiers jours pour etre credible ?",
        'reponse_correcte': "vision,arbitrage,pilotage,leadership",
        'points': 5,
        'ordre': 18,
    },
]


DIRECTEUR_ADJOINT_ENTRETIEN_QUESTIONS = [
    {'ordre': 1, 'texte_question': "Le poste de Directeur adjoint reprend la meme fiche de poste que Directeur. Qu'est-ce que cela change, selon vous, dans le niveau d'exigence attendu au quotidien ?"},
    {'ordre': 2, 'texte_question': "Parlez d'une situation ou vous avez du porter une decision strategique sensible en l'absence du decideur principal."},
    {'ordre': 3, 'texte_question': "Comment faites-vous progresser des managers intermediaires sans les rendre dependants de vous ?"},
    {'ordre': 4, 'texte_question': "Quel est votre style pour challenger un responsable qui produit des explications mais peu de resultats ?"},
    {'ordre': 5, 'texte_question': "Comment tenez-vous ensemble execution court terme, discipline financiere et vision long terme ?"},
    {'ordre': 6, 'texte_question': "Donnez un exemple ou vous avez alerte votre hierarchie sur un risque important, alors qu'il etait plus confortable de ne rien dire."},
    {'ordre': 7, 'texte_question': "Comment animez-vous un collectif de managers avec des ego forts, des priorites concurrentes et peu d'habitude du travail transverse ?"},
    {'ordre': 8, 'texte_question': "Decrivez une experience concrete de manager coach: comment avez-vous fait grandir un manager faible en posture ou en analyse ?"},
    {'ordre': 9, 'texte_question': "Quels signaux vous font dire qu'une organisation est en train de perdre la maitrise, meme si elle continue a produire ?"},
    {'ordre': 10, 'texte_question': "Comment arbitrez-vous lorsqu'un service atteint ses objectifs au detriment des autres ou de l'interet global ?"},
    {'ordre': 11, 'texte_question': "Quelle est votre methode pour faire vivre des revues de performance utiles, exigeantes et non bureaucratiques ?"},
    {'ordre': 12, 'texte_question': "Comment gereriez-vous un Directeur tres present qui laisse peu d'autonomie, tout en restant pleinement utile au poste de Directeur adjoint ?"},
    {'ordre': 13, 'texte_question': "Si vous prenez ce poste demain, quels diagnostics lanceriez-vous durant les 30 premiers jours sur les personnes, les chiffres et l'execution ?"},
    {'ordre': 14, 'texte_question': "Comment saurez-vous, apres 6 mois, que vous avez vraiment joue un role de Directeur adjoint et pas seulement de super-coordinateur ?"},
]


def _find_poste_by_names(*names):
    query = Q()
    for name in names:
        query |= Q(nom_poste__iexact=name)
    return Poste.objects.filter(query).first()


def _create_question_series_for_poste(poste, payloads):
    created_count = 0
    skipped_count = 0

    for payload in payloads:
        exists = QuestionTest.objects.filter(
            poste=poste,
            texte_question=payload['texte_question'],
        ).exists()
        if exists:
            skipped_count += 1
            continue

        QuestionTest.objects.create(
            poste=poste,
            type_question=payload['type_question'],
            texte_question=payload['texte_question'],
            options_qcm=payload.get('options_qcm') if payload['type_question'] == 'qcm' else None,
            reponse_correcte=payload['reponse_correcte'],
            points=payload['points'],
            ordre=payload['ordre'],
            active=True,
        )
        created_count += 1

    return created_count, skipped_count


def _create_entretien_series_for_poste(poste, payloads):
    created_count = 0
    skipped_count = 0

    for payload in payloads:
        exists = EntretienQuestion.objects.filter(
            poste=poste,
            texte_question=payload['texte_question'],
        ).exists()
        if exists:
            skipped_count += 1
            continue

        EntretienQuestion.objects.create(
            poste=poste,
            texte_question=payload['texte_question'],
            ordre=payload['ordre'],
            active=True,
        )
        created_count += 1

    return created_count, skipped_count



@login_required
@user_passes_test(is_admin_or_staff)
def gestion_candidats(request):
    """
    Page de gestion des candidats préconfigurés
    """
    # Limiter le filtre aux postes qui ont réellement des candidats dans le workflow
    poste_ids = (
        CandidatPreconfigure.objects
        .exclude(poste__isnull=True)
        .values_list('poste_id', flat=True)
        .distinct()
    )
    filter_postes = Poste.objects.filter(id__in=poste_ids).order_by('ordre_affichage', 'nom_poste')
    user_organisation = getattr(getattr(getattr(request.user, 'employe', None), 'base', None), 'organisation', None)
    if user_organisation:
        form_postes = Poste.objects.filter(organisation=user_organisation).order_by('ordre_affichage', 'nom_poste')
    elif getattr(request.user, 'is_superuser', False):
        form_postes = Poste.objects.all().order_by('organisation__nom_organisation', 'ordre_affichage', 'nom_poste')
    else:
        form_postes = filter_postes
    creation_months = (
        CandidatPreconfigure.objects
        .dates('date_creation', 'month', order='DESC')
    )

    month_labels = [
        'Janvier', 'Fevrier', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Decembre'
    ]
    creation_month_choices = [
        {
            'value': month.strftime('%Y-%m'),
            'label': f"{month_labels[month.month - 1]} {month.year}",
        }
        for month in creation_months
    ]

    context = {
        'postes': filter_postes,
        'form_postes': form_postes,
        'creation_month_choices': creation_month_choices,
    }

    return render(request, 'recrutement/gestion_candidats.html', context)


@login_required
@user_passes_test(is_admin_or_staff)
def gestion_questions(request):
    """
    Page de gestion des questions de test
    """
    # Récupérer tous les postes pour le formulaire
    postes = Poste.objects.all().order_by('ordre_affichage', 'nom_poste')

    context = {
        'postes': postes,
    }

    return render(request, 'recrutement/gestion_questions.html', context)


@login_required
@user_passes_test(is_admin_or_staff)
def gestion_resultats(request):
    # Filtres
    poste_id = request.GET.get('poste', '')
    statut_filter = request.GET.get('statut', '')
    score_min = request.GET.get('score_min', '').strip()
    score_max = request.GET.get('score_max', '').strip()
    date_test = request.GET.get('date_test', '').strip()

    postes = Poste.objects.all().order_by('ordre_affichage', 'nom_poste')
    candidats_qs = Candidat.objects.select_related('poste_souhaite').prefetch_related('sessions_test').order_by('-date_candidature')
    if poste_id:
        candidats_qs = candidats_qs.filter(poste_souhaite_id=poste_id)

    data = []
    for candidat in candidats_qs:
        session = candidat.sessions_test.order_by('-date_debut').first()
        statut_code = candidat.statut
        pourcentage = session.pourcentage if session else None
        data.append({
            'id': candidat.id,
            'nom_complet': candidat.nom_complet,
            'email': candidat.email,
            'telephone': candidat.telephone,
            'adresse': candidat.adresse,
            'date_naissance': candidat.date_naissance,
            'base': getattr(candidat, 'base', ''),
            'poste': candidat.poste_souhaite.nom_poste if candidat.poste_souhaite else 'N/A',
            'statut': candidat.get_statut_display() if hasattr(candidat, 'get_statut_display') else candidat.statut,
            'statut_code': statut_code,
            'date_candidature': candidat.date_candidature,
            'date_test': session.date_debut.date() if session and session.date_debut else None,
            'convocation': candidat.convocation_entretien,
            'dernier_score': session.score_obtenu if session else None,
            'score_total': session.score_total if session else None,
            'pourcentage': pourcentage,
            'session_id': session.id if session else None,
        })

    # Filtrer par statut
    if statut_filter:
        data = [c for c in data if c.get('statut_code') == statut_filter]

    # Filtrer par score (pourcentage)
    def _to_float(value):
        try:
            return float(value)
        except Exception:
            return None

    min_val = _to_float(score_min) if score_min else None
    max_val = _to_float(score_max) if score_max else None
    if min_val is not None or max_val is not None:
        filtered = []
        for c in data:
            p = c.get('pourcentage')
            if p is None:
                continue
            p_val = float(p)
            if min_val is not None and p_val < min_val:
                continue
            if max_val is not None and p_val > max_val:
                continue
            filtered.append(c)
        data = filtered

    # Filtrer par date du test (date de debut de la derniere session)
    if date_test:
        filtered = []
        for c in data:
            test_date = c.get('date_test')
            if test_date and test_date.isoformat() == date_test:
                filtered.append(c)
        data = filtered

    # Regrouper par poste
    groupes = {}
    for c in data:
        groupes.setdefault(c['poste'], []).append(c)
    groupes_list = [{'poste': k, 'candidats': v} for k, v in groupes.items()]
    groupes_list.sort(key=lambda x: x['poste'])

    # === STATISTIQUES ===

    # 1. Compter candidats par poste
    stats_par_poste = {}
    for c in data:
        poste_nom = c['poste']
        stats_par_poste[poste_nom] = stats_par_poste.get(poste_nom, 0) + 1

    # 2. Compter par statut
    stats_par_statut = {}
    for c in data:
        statut = c['statut_code']
        stats_par_statut[statut] = stats_par_statut.get(statut, 0) + 1

    # 3. Définir catégories de note et compter
    # Catégories basées sur pourcentage:
    # - En dessous de la moyenne: < 50%
    # - Moyenne: 50-69%
    # - Au dessus: 70-84%
    # - Bien au dessus: >= 85%

    categories_note = {
        'en_dessous_moyenne': {'label': 'En dessous de la moyenne (<50%)', 'count': 0},
        'moyenne': {'label': 'Moyenne (50-69%)', 'count': 0},
        'au_dessus': {'label': 'Au dessus (70-84%)', 'count': 0},
        'bien_au_dessus': {'label': 'Bien au dessus (≥85%)', 'count': 0},
        'sans_note': {'label': 'Sans note', 'count': 0},
    }

    for c in data:
        p = c.get('pourcentage')
        if p is None:
            categories_note['sans_note']['count'] += 1
        else:
            p_val = float(p)
            if p_val < 50:
                categories_note['en_dessous_moyenne']['count'] += 1
            elif p_val < 70:
                categories_note['moyenne']['count'] += 1
            elif p_val < 85:
                categories_note['au_dessus']['count'] += 1
            else:
                categories_note['bien_au_dessus']['count'] += 1

    return render(request, 'recrutement/gestion_resultats.html', {
        'candidats': data,
        'postes': postes,
        'groupes': groupes_list,
        'filters': {
            'poste': poste_id,
            'statut': statut_filter,
            'score_min': score_min,
            'score_max': score_max,
            'date_test': date_test,
        },
        'stats_par_poste': stats_par_poste,
        'stats_par_statut': stats_par_statut,
        'categories_note': categories_note,
        'total_candidats': len(data),
    })


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def gestion_convocation(request, candidat_id):
    candidat = get_object_or_404(Candidat, id=candidat_id)
    action = request.POST.get('action', 'select')
    candidat.convocation_entretien = (action == 'select')
    candidat.save(update_fields=['convocation_entretien'])
    return redirect('recrutement:gestion_resultats')


# ===== APIs pour Candidats Préconfigurés =====

@csrf_exempt
@require_http_methods(["GET"])
def api_liste_candidats(request):
    """
    API pour lister les candidats préconfigurés avec filtres
    """
    # Filtres
    search = request.GET.get('search', '')
    poste_id = request.GET.get('poste', '')
    statut = request.GET.get('statut', '')  # 'en_attente', 'inscrit', 'test_complete'

    # Requête de base
    candidats = CandidatPreconfigure.objects.select_related('poste', 'candidat').all()

    # Appliquer les filtres
    if search:
        candidats = candidats.filter(
            Q(email__icontains=search)
        )

    if poste_id:
        candidats = candidats.filter(poste_id=poste_id)

    if statut == 'en_attente':
        candidats = candidats.filter(candidat__isnull=True)
    elif statut == 'inscrit':
        candidats = candidats.filter(candidat__isnull=False, test_complete=False)
    elif statut == 'test_complete':
        candidats = candidats.filter(test_complete=True)

    # Préparer les données
    data = []
    for c in candidats:
        data.append({
            'id': str(c.id),
            'email': c.email,
            'poste': c.poste.nom_poste,
            'poste_id': str(c.poste.id),
            'date_creation': c.date_creation.strftime('%d/%m/%Y %H:%M'),
            'date_creation_sort': c.date_creation.isoformat(),
            'test_complete': c.test_complete,
            'candidat_nom': f"{c.candidat.prenom} {c.candidat.nom}" if c.candidat else None,
            'statut': 'Test complété' if c.test_complete else ('Inscrit' if c.candidat else 'En attente'),
        })

    return JsonResponse({
        'success': True,
        'candidats': data,
        'total': len(data)
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_creer_candidat_preconfig(request):
    """
    API pour créer un candidat préconfiguré
    """
    try:
        data = json.loads(request.body)

        email = data.get('email', '').strip()
        email_normalized = email.lower()
        poste_id = data.get('poste_id', '')

        # Validation
        if not email or not poste_id:
            return JsonResponse({
                'success': False,
                'error': 'Email et poste sont obligatoires'
            }, status=400)

        # Vérifier que l'email n'existe pas déjà
        if CandidatPreconfigure.objects.filter(email__iexact=email_normalized).exists():
            return JsonResponse({
                'success': False,
                'error': 'Cet email est deja preconfigure'
            }, status=400)


        if Candidat.objects.filter(email__iexact=email_normalized).exists():
            return JsonResponse({
                'success': False,
                'error': 'Cet email est deja utilise par un candidat'
            }, status=400)
        # Vérifier que le poste existe
        try:
            poste = Poste.objects.get(id=poste_id)
        except Poste.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Poste introuvable'
            }, status=404)

        # Créer le candidat préconfiguré
        candidat_preconfig = CandidatPreconfigure.objects.create(
            email=email_normalized,
            poste=poste
        )

        return JsonResponse({
            'success': True,
            'message': f'Candidat preconfigure cree avec succes. Lien d\'inscription : /recrutement/inscription/?email={email_normalized}',
            'candidat': {
                'id': str(candidat_preconfig.id),
                'email': candidat_preconfig.email,
                'poste': candidat_preconfig.poste.nom_poste,
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_supprimer_candidat_preconfig(request, candidat_id):
    """
    API pour supprimer un candidat préconfiguré
    """
    try:
        candidat = CandidatPreconfigure.objects.get(id=candidat_id)

        # Ne pas supprimer si le candidat s'est déjà inscrit
        if candidat.candidat:
            return JsonResponse({
                'success': False,
                'error': 'Impossible de supprimer : le candidat s\'est déjà inscrit'
            }, status=400)

        candidat.delete()

        return JsonResponse({
            'success': True,
            'message': 'Candidat préconfiguré supprimé avec succès'
        })

    except CandidatPreconfigure.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Candidat introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# ===== API envoi email en masse =====

@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_envoyer_email_candidats(request):
    """
    API pour envoyer un email aux candidats sélectionnés
    """
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Données invalides'}, status=400)

    ids = data.get('ids', [])
    subject = (data.get('subject') or '').strip()
    message = (data.get('message') or '').strip()

    if not ids or not isinstance(ids, list):
        return JsonResponse({'success': False, 'error': 'Aucun candidat sélectionné'}, status=400)
    if not subject or not message:
        return JsonResponse({'success': False, 'error': 'Objet et message obligatoires'}, status=400)

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None)
    if not from_email:
        return JsonResponse({'success': False, 'error': "Adresse expéditeur non configurée"}, status=500)

    candidats = CandidatPreconfigure.objects.select_related('poste').filter(id__in=ids)
    if not candidats.exists():
        return JsonResponse({'success': False, 'error': 'Candidats introuvables'}, status=404)

    sent = 0
    erreurs = []
    for candidat in candidats:
        email = (candidat.email or '').strip()
        if not email:
            erreurs.append({'id': str(candidat.id), 'error': 'Email manquant'})
            continue

        lien = request.build_absolute_uri(
            f"/recrutement/inscription/?email={quote(email)}"
        )
        body = (
            message
            .replace('{lien}', lien)
            .replace('{email}', email)
            .replace('{poste}', candidat.poste.nom_poste if candidat.poste else '')
        )

        try:
            send_mail(subject, body, from_email, [email], fail_silently=False)
            sent += 1
        except Exception as e:
            erreurs.append({'id': str(candidat.id), 'error': str(e)})

    msg = f'Emails envoyés: {sent}'
    if erreurs:
        msg += f' | Erreurs: {len(erreurs)}'

    return JsonResponse({
        'success': True,
        'message': msg,
        'sent': sent,
        'errors': erreurs
    })


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_envoyer_email_entretien(request, candidat_id):
    """API pour envoyer un email d'entretien à un candidat."""
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Données invalides'}, status=400)

    subject = (data.get('subject') or '').strip()
    message = (data.get('message') or '').strip()

    if not subject or not message:
        return JsonResponse({'success': False, 'error': 'Objet et message obligatoires'}, status=400)

    candidat = get_object_or_404(Candidat, id=candidat_id)
    email = (candidat.email or '').strip()
    if not email:
        return JsonResponse({'success': False, 'error': 'Email manquant'}, status=400)

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None)
    if not from_email:
        return JsonResponse({'success': False, 'error': "Adresse expéditeur non configurée"}, status=500)

    body = (
        message
        .replace('{nom}', candidat.nom_complet)
        .replace('{email}', email)
        .replace('{poste}', candidat.poste_souhaite.nom_poste if candidat.poste_souhaite else '')
    )

    try:
        send_mail(subject, body, from_email, [email], fail_silently=False)
        preconfig = CandidatPreconfigure.objects.filter(candidat=candidat).first() or CandidatPreconfigure.objects.filter(email__iexact=candidat.email).first()
        if preconfig and preconfig.screening_statut != 'elimine':
            preconfig.screening_statut = 'invite_entretien'
            preconfig.save(update_fields=['screening_statut'])
        return JsonResponse({'success': True, 'message': 'Email envoyé.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["GET"])
def api_resultats_session(request, session_id):
    """API pour récupérer le détail d'une session de test (admin)."""
    session = get_object_or_404(
        SessionTest.objects.select_related('candidat', 'candidat__poste_souhaite'),
        id=session_id
    )

    reponses_qs = session.reponses.select_related('question').order_by('question__ordre')
    reponses = []
    for rep in reponses_qs:
        reponses.append({
            'question': rep.question.texte_question,
            'ordre': rep.question.ordre,
            'points': rep.question.points,
            'reponse_donnee': rep.reponse_donnee,
            'est_correcte': rep.est_correcte,
            'points_obtenus': rep.points_obtenus,
        })

    return JsonResponse({
        'success': True,
        'session': {
            'id': str(session.id),
            'statut': session.statut,
            'score_obtenu': session.score_obtenu,
            'score_total': session.score_total,
            'pourcentage': float(session.pourcentage or 0),
            'date_debut': session.date_debut.strftime('%Y-%m-%d %H:%M') if session.date_debut else '',
            'date_fin': session.date_fin.strftime('%Y-%m-%d %H:%M') if session.date_fin else '',
        },
        'candidat': {
            'nom': session.candidat.nom_complet,
            'email': session.candidat.email,
            'poste': session.candidat.poste_souhaite.nom_poste if session.candidat.poste_souhaite else '',
            'date_naissance': session.candidat.date_naissance.strftime('%Y-%m-%d') if session.candidat.date_naissance else '',
            'adresse': session.candidat.adresse or '',
            'telephone': session.candidat.telephone or '',
            'experience': session.candidat.experience or '',
            'formation': session.candidat.formation or '',
            'cv_url': request.build_absolute_uri(session.candidat.cv.url) if session.candidat.cv else '',
            'cv_name': session.candidat.cv.name.split('/')[-1] if session.candidat.cv else '',
            'lettre_url': request.build_absolute_uri(session.candidat.lettre_motivation.url) if session.candidat.lettre_motivation else '',
            'lettre_name': session.candidat.lettre_motivation.name.split('/')[-1] if session.candidat.lettre_motivation else '',
        },
        'reponses': reponses,
    })


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_reset_test_candidat(request, candidat_id):
    """API pour réinitialiser le test d'un candidat (admin)."""
    candidat = get_object_or_404(Candidat, id=candidat_id)

    # Supprimer toutes les sessions de test (réponses en cascade)
    SessionTest.objects.filter(candidat=candidat).delete()

    # Remettre le statut candidat à en_attente et retirer convocation
    candidat.statut = 'en_attente'
    candidat.convocation_entretien = False
    candidat.save(update_fields=['statut', 'convocation_entretien'])

    # Réouvrir la préconfiguration si existante
    CandidatPreconfigure.objects.filter(candidat=candidat).update(test_complete=False)

    return JsonResponse({'success': True, 'message': 'Test réinitialisé. Le candidat peut le repasser.'})


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_update_candidat_base(request, candidat_id):
    """API pour mettre à jour la base d'un candidat (admin)."""
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Données invalides'}, status=400)

    base_value = (data.get('base') or '').strip()
    if len(base_value) > 100:
        return JsonResponse({'success': False, 'error': 'Base trop longue (max 100)'}, status=400)

    candidat = get_object_or_404(Candidat, id=candidat_id)
    candidat.base = base_value
    candidat.save(update_fields=['base'])

    return JsonResponse({'success': True, 'message': 'Base mise à jour.'})


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_supprimer_candidat_inscrit(request, candidat_id):
    """API pour supprimer un candidat inscrit (compte + candidature + sessions)."""
    # Accepte soit un candidat_id, soit un id de préconfiguration
    candidat = Candidat.objects.filter(id=candidat_id).first()
    if not candidat:
        preconfig = CandidatPreconfigure.objects.filter(id=candidat_id).select_related('candidat').first()
        if not preconfig or not preconfig.candidat:
            return JsonResponse({'success': False, 'error': 'Candidat introuvable'}, status=404)
        candidat = preconfig.candidat

    # Supprimer toutes les sessions de test (réponses en cascade)
    SessionTest.objects.filter(candidat=candidat).delete()

    # Supprimer préconfiguration si existante
    CandidatPreconfigure.objects.filter(candidat=candidat).delete()

    # Supprimer le compte utilisateur si présent
    user = candidat.user
    candidat.delete()
    if user:
        user.delete()

    return JsonResponse({'success': True, 'message': 'Candidat supprimé (compte, candidature, sessions et préconfiguration).'})


# ===== APIs pour Questions de Test =====

@csrf_exempt
@require_http_methods(["GET"])
def api_liste_questions(request):
    """
    API pour lister les questions de test avec filtres
    """
    # Filtres
    search = request.GET.get('search', '')
    poste_id = request.GET.get('poste', '')
    type_question = request.GET.get('type', '')
    active = request.GET.get('active', '')

    # Requête de base
    questions = QuestionTest.objects.select_related('poste').all()

    # Appliquer les filtres
    if search:
        questions = questions.filter(
            Q(texte_question__icontains=search)
        )

    if poste_id:
        questions = questions.filter(poste_id=poste_id)

    if type_question:
        questions = questions.filter(type_question=type_question)

    if active == 'true':
        questions = questions.filter(active=True)
    elif active == 'false':
        questions = questions.filter(active=False)

    # Trier par poste et ordre
    questions = questions.order_by('poste__ordre_affichage', 'poste__nom_poste', 'ordre')

    # Préparer les données
    data = []
    for q in questions:
        data.append({
            'id': str(q.id),
            'poste': q.poste.nom_poste,
            'poste_id': str(q.poste.id),
            'type_question': q.type_question,
            'type_question_display': q.get_type_question_display(),
            'texte_question': q.texte_question,
            'options_qcm': q.options_qcm or '',
            'reponse_correcte': q.reponse_correcte,
            'points': q.points,
            'ordre': q.ordre,
            'active': q.active,
        })

    return JsonResponse({
        'success': True,
        'questions': data,
        'total': len(data)
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_creer_question(request):
    """
    API pour créer une question de test
    """
    try:
        data = json.loads(request.body)

        poste_id = data.get('poste_id', '')
        type_question = data.get('type_question', '')
        texte_question = data.get('texte_question', '').strip()
        options_qcm = data.get('options_qcm', '').strip()
        reponse_correcte = data.get('reponse_correcte', '').strip()
        points = data.get('points', 1)
        ordre = data.get('ordre', 1)
        active = data.get('active', True)

        # Validation
        if not all([poste_id, type_question, texte_question, reponse_correcte]):
            return JsonResponse({
                'success': False,
                'error': 'Tous les champs obligatoires doivent être remplis'
            }, status=400)

        # Vérifier que le poste existe
        try:
            poste = Poste.objects.get(id=poste_id)
        except Poste.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Poste introuvable'
            }, status=404)

        # Créer la question
        question = QuestionTest.objects.create(
            poste=poste,
            type_question=type_question,
            texte_question=texte_question,
            options_qcm=options_qcm if type_question == 'qcm' else None,
            reponse_correcte=reponse_correcte,
            points=points,
            ordre=ordre,
            active=active
        )

        return JsonResponse({
            'success': True,
            'message': 'Question créée avec succès',
            'question': {
                'id': str(question.id),
                'texte_question': question.texte_question,
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_creer_serie_agent_recouvrement(request):
    """Crée une série prédéfinie de questions pour le poste Agent de recouvrement."""
    try:
        poste = Poste.objects.filter(nom_poste__iexact='Agent de recouvrement').first()
        if not poste:
            return JsonResponse({
                'success': False,
                'error': 'Poste "Agent de recouvrement" introuvable'
            }, status=404)

        created_count, skipped_count = _create_question_series_for_poste(poste, AGENT_RECOUVREMENT_QUESTIONS)

        return JsonResponse({
            'success': True,
            'message': f'Serie Agent de recouvrement terminee. Creees: {created_count}. Ignorees: {skipped_count}.',
            'created_count': created_count,
            'skipped_count': skipped_count,
            'poste_id': str(poste.id),
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_creer_serie_entretien_agent_recouvrement(request):
    """Crée une série prédéfinie de questions d'entretien pour Agent de recouvrement."""
    try:
        poste = Poste.objects.filter(nom_poste__iexact='Agent de recouvrement').first()
        if not poste:
            return JsonResponse({
                'success': False,
                'error': 'Poste "Agent de recouvrement" introuvable'
            }, status=404)

        created_count, skipped_count = _create_entretien_series_for_poste(poste, AGENT_RECOUVREMENT_ENTRETIEN_QUESTIONS)

        return JsonResponse({
            'success': True,
            'message': f'Serie entretien Agent de recouvrement terminee. Creees: {created_count}. Ignorees: {skipped_count}.',
            'created_count': created_count,
            'skipped_count': skipped_count,
            'poste_id': str(poste.id),
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_creer_serie_assistant_admin(request):
    """Crée une série prédéfinie de questions difficiles pour Assistant(e) admin."""
    try:
        poste = _find_poste_by_names('Assistant(e) admin', 'Assistant admin')
        if not poste:
            return JsonResponse({
                'success': False,
                'error': 'Poste "Assistant(e) admin" introuvable'
            }, status=404)

        created_count, skipped_count = _create_question_series_for_poste(poste, ASSISTANT_ADMIN_QUESTIONS)

        return JsonResponse({
            'success': True,
            'message': f'Serie Assistant admin terminee. Creees: {created_count}. Ignorees: {skipped_count}.',
            'created_count': created_count,
            'skipped_count': skipped_count,
            'poste_id': str(poste.id),
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_creer_serie_entretien_assistant_admin(request):
    """Crée une série prédéfinie de questions d'entretien pour Assistant(e) admin."""
    try:
        poste = _find_poste_by_names('Assistant(e) admin', 'Assistant admin')
        if not poste:
            return JsonResponse({
                'success': False,
                'error': 'Poste "Assistant(e) admin" introuvable'
            }, status=404)

        created_count, skipped_count = _create_entretien_series_for_poste(poste, ASSISTANT_ADMIN_ENTRETIEN_QUESTIONS)

        return JsonResponse({
            'success': True,
            'message': f'Serie entretien Assistant admin terminee. Creees: {created_count}. Ignorees: {skipped_count}.',
            'created_count': created_count,
            'skipped_count': skipped_count,
            'poste_id': str(poste.id),
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_creer_serie_responsable_operationnel(request):
    """Crée une série prédéfinie de questions pour le poste Responsable operationnel."""
    try:
        poste = _find_poste_by_names('Responsable opérationnel', 'Responsable operationnel')
        if not poste:
            return JsonResponse({
                'success': False,
                'error': 'Poste "Responsable operationnel" introuvable'
            }, status=404)

        created_count, skipped_count = _create_question_series_for_poste(poste, RESPONSABLE_OPERATIONNEL_QUESTIONS)

        return JsonResponse({
            'success': True,
            'message': f'Serie Responsable operationnel terminee. Creees: {created_count}. Ignorees: {skipped_count}.',
            'created_count': created_count,
            'skipped_count': skipped_count,
            'poste_id': str(poste.id),
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_creer_serie_entretien_responsable_operationnel(request):
    """Crée une série d'entretien pour le poste Responsable operationnel."""
    try:
        poste = _find_poste_by_names('Responsable opérationnel', 'Responsable operationnel')
        if not poste:
            return JsonResponse({
                'success': False,
                'error': 'Poste "Responsable operationnel" introuvable'
            }, status=404)

        created_count, skipped_count = _create_entretien_series_for_poste(poste, RESPONSABLE_OPERATIONNEL_ENTRETIEN_QUESTIONS)

        return JsonResponse({
            'success': True,
            'message': f'Serie entretien Responsable operationnel terminee. Creees: {created_count}. Ignorees: {skipped_count}.',
            'created_count': created_count,
            'skipped_count': skipped_count,
            'poste_id': str(poste.id),
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_creer_serie_superviseur_technique(request):
    """Cree une serie predefinie de questions pour le poste Superviseur technique."""
    try:
        poste = _find_poste_by_names('Superviseur technique')
        if not poste:
            return JsonResponse({
                'success': False,
                'error': 'Poste "Superviseur technique" introuvable'
            }, status=404)

        created_count, skipped_count = _create_question_series_for_poste(poste, SUPERVISEUR_TECHNIQUE_QUESTIONS)

        return JsonResponse({
            'success': True,
            'message': f'Serie Superviseur technique terminee. Creees: {created_count}. Ignorees: {skipped_count}.',
            'created_count': created_count,
            'skipped_count': skipped_count,
            'poste_id': str(poste.id),
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_creer_serie_entretien_superviseur_technique(request):
    """Cree une serie d'entretien pour le poste Superviseur technique."""
    try:
        poste = _find_poste_by_names('Superviseur technique')
        if not poste:
            return JsonResponse({
                'success': False,
                'error': 'Poste "Superviseur technique" introuvable'
            }, status=404)

        created_count, skipped_count = _create_entretien_series_for_poste(poste, SUPERVISEUR_TECHNIQUE_ENTRETIEN_QUESTIONS)

        return JsonResponse({
            'success': True,
            'message': f'Serie entretien Superviseur technique terminee. Creees: {created_count}. Ignorees: {skipped_count}.',
            'created_count': created_count,
            'skipped_count': skipped_count,
            'poste_id': str(poste.id),
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_creer_serie_directeur_adjoint(request):
    """Crée une série prédéfinie de questions pour le poste Directeur adjoint."""
    try:
        poste = _find_poste_by_names('Directeur adjoint', 'Directeur Adjoint')
        if not poste:
            return JsonResponse({
                'success': False,
                'error': 'Poste "Directeur adjoint" introuvable'
            }, status=404)

        created_count, skipped_count = _create_question_series_for_poste(poste, DIRECTEUR_ADJOINT_QUESTIONS)

        return JsonResponse({
            'success': True,
            'message': f'Serie Directeur adjoint terminee. Creees: {created_count}. Ignorees: {skipped_count}.',
            'created_count': created_count,
            'skipped_count': skipped_count,
            'poste_id': str(poste.id),
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_creer_serie_entretien_directeur_adjoint(request):
    """Crée une série d'entretien pour le poste Directeur adjoint."""
    try:
        poste = _find_poste_by_names('Directeur adjoint', 'Directeur Adjoint')
        if not poste:
            return JsonResponse({
                'success': False,
                'error': 'Poste "Directeur adjoint" introuvable'
            }, status=404)

        created_count, skipped_count = _create_entretien_series_for_poste(poste, DIRECTEUR_ADJOINT_ENTRETIEN_QUESTIONS)

        return JsonResponse({
            'success': True,
            'message': f'Serie entretien Directeur adjoint terminee. Creees: {created_count}. Ignorees: {skipped_count}.',
            'created_count': created_count,
            'skipped_count': skipped_count,
            'poste_id': str(poste.id),
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_modifier_question(request, question_id):
    """
    API pour modifier une question de test
    """
    try:
        question = QuestionTest.objects.get(id=question_id)
        data = json.loads(request.body)

        # Mettre à jour les champs
        if 'texte_question' in data:
            question.texte_question = data['texte_question']
        if 'options_qcm' in data:
            question.options_qcm = data['options_qcm']
        if 'reponse_correcte' in data:
            question.reponse_correcte = data['reponse_correcte']
        if 'points' in data:
            question.points = data['points']
        if 'ordre' in data:
            question.ordre = data['ordre']
        if 'active' in data:
            question.active = data['active']
        if 'poste_id' in data:
            try:
                poste = Poste.objects.get(id=data['poste_id'])
                question.poste = poste
            except Poste.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Poste introuvable'
                }, status=404)

        question.save()

        return JsonResponse({
            'success': True,
            'message': 'Question modifiée avec succès'
        })

    except QuestionTest.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Question introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_supprimer_question(request, question_id):
    """
    API pour supprimer une question de test
    """
    try:
        question = QuestionTest.objects.get(id=question_id)
        question.delete()

        return JsonResponse({
            'success': True,
            'message': 'Question supprimée avec succès'
        })

    except QuestionTest.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Question introuvable'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# ===== APIs pour Questions d'Entretien =====

@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["GET"])
def api_liste_questions_entretien(request):
    # API pour lister les questions d'entretien avec filtres
    search = request.GET.get('search', '')
    poste_id = request.GET.get('poste', '')
    active = request.GET.get('active', '')

    questions = EntretienQuestion.objects.select_related('poste').all()

    if search:
        questions = questions.filter(texte_question__icontains=search)
    if poste_id:
        questions = questions.filter(poste_id=poste_id)
    if active == 'true':
        questions = questions.filter(active=True)
    elif active == 'false':
        questions = questions.filter(active=False)

    questions = questions.order_by('poste__ordre_affichage', 'poste__nom_poste', 'ordre')

    data = []
    for q in questions:
        data.append({
            'id': str(q.id),
            'poste': q.poste.nom_poste,
            'poste_id': str(q.poste.id),
            'texte_question': q.texte_question,
            'ordre': q.ordre,
            'active': q.active,
        })

    return JsonResponse({
        'success': True,
        'questions': data,
        'total': len(data)
    })


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_creer_question_entretien(request):
    # API pour creer une question d'entretien
    try:
        data = json.loads(request.body)
        poste_id = data.get('poste_id', '')
        texte_question = (data.get('texte_question') or '').strip()
        ordre = data.get('ordre', 1)
        active = data.get('active', True)

        if not poste_id or not texte_question:
            return JsonResponse({'success': False, 'error': 'Poste et question obligatoires'}, status=400)

        try:
            poste = Poste.objects.get(id=poste_id)
        except Poste.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Poste introuvable'}, status=404)

        question = EntretienQuestion.objects.create(
            poste=poste,
            texte_question=texte_question,
            ordre=ordre,
            active=active
        )

        return JsonResponse({
            'success': True,
            'message': 'Question d\'entretien creee avec succes',
            'question': {'id': str(question.id)}
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_modifier_question_entretien(request, question_id):
    # API pour modifier une question d'entretien
    try:
        question = EntretienQuestion.objects.get(id=question_id)
        data = json.loads(request.body)

        if 'texte_question' in data:
            question.texte_question = data['texte_question']
        if 'ordre' in data:
            question.ordre = data['ordre']
        if 'active' in data:
            question.active = data['active']
        if 'poste_id' in data:
            try:
                poste = Poste.objects.get(id=data['poste_id'])
                question.poste = poste
            except Poste.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Poste introuvable'}, status=404)

        question.save()
        return JsonResponse({'success': True, 'message': 'Question d\'entretien modifiee avec succes'})
    except EntretienQuestion.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Question introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_supprimer_question_entretien(request, question_id):
    # API pour supprimer une question d'entretien
    try:
        question = EntretienQuestion.objects.get(id=question_id)
        question.delete()
        return JsonResponse({'success': True, 'message': 'Question d\'entretien supprimee avec succes'})
    except EntretienQuestion.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Question introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def api_entretien_detail(request, candidat_id):
    # API pour recuperer les questions et reponses d'entretien d'un candidat.
    candidat = get_object_or_404(Candidat, id=candidat_id)
    poste = candidat.poste_souhaite

    questions = []
    if poste:
        qs = EntretienQuestion.objects.filter(poste=poste, active=True).order_by('ordre')
        for q in qs:
            questions.append({
                'id': str(q.id),
                'texte': q.texte_question,
                'ordre': q.ordre,
            })

    entretien = Entretien.objects.filter(candidat=candidat).first()
    entretien_data = None
    reponses_map = {}
    if entretien:
        entretien_data = {
            'id': str(entretien.id),
            'date_entretien': entretien.date_entretien.strftime('%Y-%m-%d') if entretien.date_entretien else '',
            'decision': entretien.decision or '',
            'notes_generales': entretien.notes_generales or '',
        }
        for rep in entretien.reponses.select_related('question').all():
            reponses_map[str(rep.question_id)] = {
                'reponse_candidat': rep.reponse_candidat or '',
                'remarque': rep.remarque or '',
            }

    return JsonResponse({
        'success': True,
        'candidat': {
            'id': str(candidat.id),
            'nom': candidat.nom_complet,
            'poste': poste.nom_poste if poste else '',
        },
        'questions': questions,
        'entretien': entretien_data,
        'reponses': reponses_map,
    })


@login_required
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def api_entretien_save(request, candidat_id):
    # API pour enregistrer l'entretien (admin).
    try:
        candidat = get_object_or_404(Candidat, id=candidat_id)
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Donnees invalides'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

    try:
        date_entretien = data.get('date_entretien') or None
        decision = (data.get('decision') or '').strip()
        notes_generales = (data.get('notes_generales') or '').strip()
        reponses = data.get('reponses') or []

        entretien, _ = Entretien.objects.get_or_create(
            candidat=candidat,
            defaults={'poste': candidat.poste_souhaite}
        )
        entretien.poste = candidat.poste_souhaite
        entretien.notes_generales = notes_generales
        entretien.decision = decision
        if date_entretien:
            try:
                from datetime import datetime
                entretien.date_entretien = datetime.strptime(date_entretien, '%Y-%m-%d').date()
            except Exception:
                return JsonResponse({'success': False, 'error': 'Date invalide'}, status=400)
        else:
            entretien.date_entretien = None
        entretien.save()

        for rep in reponses:
            qid = rep.get('question_id')
            if not qid:
                continue
            question = EntretienQuestion.objects.filter(id=qid).first()
            if not question:
                continue
            EntretienReponse.objects.update_or_create(
                entretien=entretien,
                question=question,
                defaults={
                    'reponse_candidat': (rep.get('reponse_candidat') or '').strip(),
                    'remarque': (rep.get('remarque') or '').strip(),
                }
            )

        preconfig = CandidatPreconfigure.objects.filter(candidat=candidat).first() or CandidatPreconfigure.objects.filter(email__iexact=candidat.email).first()
        if preconfig and preconfig.screening_statut != 'elimine':
            preconfig.screening_statut = 'entretien_complete'
            preconfig.save(update_fields=['screening_statut'])

        return JsonResponse({'success': True, 'message': 'Entretien enregistre.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def _get_candidate_screening_status(candidat_preconfig):
    linked_candidat = candidat_preconfig.candidat or Candidat.objects.filter(
        email__iexact=candidat_preconfig.email
    ).first()
    normalized_status = _normalize_screening_status(candidat_preconfig.screening_statut)
    has_completed_test = candidat_preconfig.test_complete
    if not has_completed_test and linked_candidat:
        has_completed_test = SessionTest.objects.filter(
            candidat=linked_candidat,
            statut__in=['termine', 'expire']
        ).exists() or linked_candidat.statut == 'test_termine'

    if normalized_status == 'elimine':
        return 'Elimine'
    if normalized_status == 'entretien_complete':
        return 'Entretien complete'
    if normalized_status == 'invite_entretien':
        return 'Invite a l\'entretien'
    if normalized_status == 'test_complete':
        return 'Test complete'
    if has_completed_test:
        return 'Test complete'
    if normalized_status == 'invite_test' or candidat_preconfig.invite_test_envoyee:
        return 'Invite au test'
    return dict(CandidatPreconfigure._meta.get_field('screening_statut').choices).get(
        normalized_status,
        'A analyser',
    )


def _serialize_candidat_preconfigure(c):
    linked_candidat = c.candidat or Candidat.objects.filter(email__iexact=c.email).first()
    normalized_status = _normalize_screening_status(c.screening_statut)
    has_completed_test = c.test_complete
    latest_session = None
    entretien = None
    if not has_completed_test and linked_candidat:
        has_completed_test = SessionTest.objects.filter(
            candidat=linked_candidat,
            statut__in=['termine', 'expire']
        ).exists() or linked_candidat.statut == 'test_termine'
    if linked_candidat:
        latest_session = SessionTest.objects.filter(candidat=linked_candidat).order_by('-date_fin', '-date_debut', '-created_at').first()
        entretien = Entretien.objects.filter(candidat=linked_candidat).first()
    salary_grid_comparison = _get_salary_grid_comparison(c.poste, c.pretention_salariale)

    nom_value = c.nom or (linked_candidat.nom if linked_candidat else '')
    prenom_value = c.prenom or (linked_candidat.prenom if linked_candidat else '')
    domicile_value = c.domicile or (linked_candidat.adresse if linked_candidat else '') or ''
    date_naissance_value = c.date_naissance or (linked_candidat.date_naissance if linked_candidat else None)
    formation_value = c.formation or (linked_candidat.formation if linked_candidat else '') or ''
    experience_poste_value = c.experience_poste or (linked_candidat.experience if linked_candidat else '') or ''
    cv_value = c.cv or (linked_candidat.cv if linked_candidat else None)
    lettre_value = c.lettre_motivation or (linked_candidat.lettre_motivation if linked_candidat else None)
    base_value = (linked_candidat.base if linked_candidat else '') or ''
    convocation_value = bool(linked_candidat.convocation_entretien) if linked_candidat else False
    telephone_value = (linked_candidat.telephone if linked_candidat else '') or ''

    pieces = []
    if c.photo_candidat:
        pieces.append({'label': 'Photo', 'url': c.photo_candidat.url, 'type': 'image'})
    if cv_value:
        pieces.append({'label': 'CV', 'url': cv_value.url, 'type': 'file'})
    if lettre_value:
        pieces.append({'label': 'Lettre', 'url': lettre_value.url, 'type': 'file'})

    return {
        'id': str(c.id),
        'nom': f"{prenom_value} {nom_value}".strip() or c.email,
        'nom_seul': nom_value,
        'prenom': prenom_value,
        'email': c.email,
        'poste': c.poste.nom_poste,
        'poste_id': str(c.poste.id),
        'date_creation': c.date_creation.strftime('%d/%m/%Y %H:%M'),
        'date_creation_sort': c.date_creation.isoformat(),
        'screening_statut': normalized_status,
        'effective_status_code': _get_candidate_effective_status_code(c),
        'statut': _get_candidate_screening_status(c),
        'test_complete': has_completed_test,
        'invite_test_envoyee': c.invite_test_envoyee,
        'candidat_nom': f"{linked_candidat.prenom} {linked_candidat.nom}" if linked_candidat else None,
        'candidat_id': str(linked_candidat.id) if linked_candidat else '',
        'session_id': str(latest_session.id) if latest_session else '',
        'domicile': domicile_value,
        'date_naissance': date_naissance_value.isoformat() if date_naissance_value else '',
        'date_naissance_display': date_naissance_value.strftime('%d/%m/%Y') if date_naissance_value else '-',
        'age': c.age if c.date_naissance else (
            (date.today().year - date_naissance_value.year - ((date.today().month, date.today().day) < (date_naissance_value.month, date_naissance_value.day)))
            if date_naissance_value else None
        ),
        'telephone': telephone_value,
        'formation': formation_value,
        'experience_poste': experience_poste_value,
        'autre_experience': c.autre_experience or '',
        'pretention_salariale': float(Decimal(str(c.pretention_salariale))) if c.pretention_salariale is not None else None,
        'pretention_salariale_display': _format_pretention_milliers(c.pretention_salariale),
        'pretention_grille_ok': salary_grid_comparison['available'],
        'pretention_grille_status': salary_grid_comparison['status'],
        'pretention_grille_label': salary_grid_comparison['label'],
        'pretention_grille_badge_class': salary_grid_comparison['class'],
        'pretention_grille_reference_display': salary_grid_comparison['reference_display'],
        'pretention_grille_embauche_min_kariary': salary_grid_comparison['embauche_min_kariary'],
        'pretention_grille_embauche_max_kariary': salary_grid_comparison['embauche_max_kariary'],
        'permis_conduire': c.permis_conduire,
        'photo_url': c.photo_candidat.url if c.photo_candidat else '',
        'cv_url': cv_value.url if cv_value else '',
        'lettre_url': lettre_value.url if lettre_value else '',
        'pieces': pieces,
        'commentaire_analyse': c.commentaire_analyse or '',
        'base': base_value,
        'convocation_entretien': convocation_value,
        'note_domicile': float(c.note_domicile) if c.note_domicile is not None else None,
        'note_age': float(c.note_age) if c.note_age is not None else None,
        'note_formation': float(c.note_formation) if c.note_formation is not None else None,
        'note_experience': float(c.note_experience) if c.note_experience is not None else None,
        'note_pretention': float(c.note_pretention) if c.note_pretention is not None else None,
        'note_permis': float(c.note_permis) if c.note_permis is not None else None,
        'note_globale': c.note_globale,
        'test_score': float(latest_session.pourcentage) if latest_session and latest_session.pourcentage is not None else None,
        'test_score_display': f"{round(float(latest_session.pourcentage))}%" if latest_session and latest_session.pourcentage is not None else '-',
        'entretien_decision': entretien.get_decision_display() if entretien and entretien.decision else '',
        'entretien_notes': entretien.notes_generales if entretien and entretien.notes_generales else '',
        'entretien_note_display': (
            entretien.get_decision_display()
            if entretien and entretien.decision
            else (entretien.notes_generales[:80] + ('...' if len(entretien.notes_generales) > 80 else '') if entretien and entretien.notes_generales else '-')
        ),
        'lien_inscription': f"/recrutement/inscription/?email={quote(c.email)}",
    }


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["GET"])
def api_liste_candidats_v2(request):
    data = _get_filtered_candidats_workflow(request)
    return JsonResponse({'success': True, 'candidats': data, 'total': len(data)})


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["GET"])
def exporter_candidats_excel(request):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Candidats'

    headers = [
        'Nom', 'Email', 'Poste', 'Date de creation', 'Statut', 'Domicile',
        'Date de naissance', 'Age', 'Formation', 'Experience sur le poste',
        'Autre experience', 'Pretention salariale', 'Permis de conduire',
        'Note domicile', 'Note age', 'Note formation', 'Note experience',
        'Note pretention', 'Note permis', 'Note globale', 'Commentaire analyse',
        'Lien inscription',
    ]
    ws.append(headers)

    header_fill = PatternFill(fill_type='solid', fgColor='D9EAF7')
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')

    is_template = request.GET.get('template') == '1'
    if is_template:
        ws.append([
            'Nom Prenom', 'email@exemple.com', 'Nom du poste', '', 'a_analyser', 'Ville / quartier',
            '', '', 'Formation principale', 'Experience principale', 'Autre experience',
            0, 'Non', '', '', '', '', '', '', '', 'Commentaire', '',
        ])
        guide = wb.create_sheet('Guide')
        guide.append(['Champ', 'Instruction'])
        guide.append(['Nom', 'Vous pouvez saisir nom et prenom dans la meme cellule.'])
        guide.append(['Poste', 'Le libelle doit correspondre exactement a un poste Hydria existant.'])
        guide.append(['Statut', 'Valeurs acceptees: a_analyser, invite_test, test_complete, invite_entretien, entretien_complete, elimine'])
        guide.append(['Permis de conduire', 'Oui ou Non'])
        guide.append(['Pretention salariale', 'Saisir en milliers d Ariary (ex: 450 pour 450 000 Ar)'])
        guide.append(['Notes', 'Valeurs conseillees entre 0 et 2'])
        guide.append(['Pieces', 'Les fichiers ne sont pas importes par Excel, seulement les donnees texte/numeriques.'])
    else:
        candidats = _get_filtered_candidats_workflow(request)
        for item in candidats:
            ws.append([
                item['nom'],
                item['email'],
                item['poste'],
                item['date_creation'],
                item['effective_status_code'],
                item['domicile'],
                item['date_naissance_display'],
                item['age'],
                item['formation'],
                item['experience_poste'],
                item['autre_experience'],
                item['pretention_salariale'],
                'Oui' if item['permis_conduire'] else 'Non',
                item['note_domicile'],
                item['note_age'],
                item['note_formation'],
                item['note_experience'],
                item['note_pretention'],
                item['note_permis'],
                item['note_globale'],
                item['commentaire_analyse'],
                item['lien_inscription'],
            ])

    widths = {
        'A': 28, 'B': 34, 'C': 28, 'D': 20, 'E': 18, 'F': 28, 'G': 18, 'H': 10,
        'I': 30, 'J': 30, 'K': 30, 'L': 18, 'M': 14, 'N': 14, 'O': 12, 'P': 16,
        'Q': 16, 'R': 16, 'S': 14, 'T': 14, 'U': 40, 'V': 42,
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical='top', wrap_text=True)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = 'modele_workflow_candidats.xlsx' if is_template else 'workflow_candidats.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def importer_candidats_excel(request):
    excel_file = request.FILES.get('excel_file')
    if not excel_file:
        return JsonResponse({'success': False, 'error': 'Fichier Excel manquant'}, status=400)

    try:
        workbook = load_workbook(excel_file, data_only=True)
        sheet = workbook.active
    except Exception as exc:
        return JsonResponse({'success': False, 'error': f'Fichier Excel invalide: {exc}'}, status=400)

    created = 0
    updated = 0
    errors = []

    poste_cache = {p.nom_poste.strip().lower(): p for p in Poste.objects.all()}

    for idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        if not row or not any(row):
            continue

        nom = (row[0] or '').strip() if isinstance(row[0], str) else (row[0] or '')
        email = (row[1] or '').strip().lower() if isinstance(row[1], str) else ''
        poste_label = (row[2] or '').strip() if isinstance(row[2], str) else ''
        screening_statut = (row[4] or '').strip() if isinstance(row[4], str) else ''
        domicile = (row[5] or '').strip() if isinstance(row[5], str) else ''
        date_naissance = _parse_date_value(row[6] if len(row) > 6 else None)
        formation = (row[8] or '').strip() if isinstance(row[8], str) else ''
        experience_poste = (row[9] or '').strip() if isinstance(row[9], str) else ''
        autre_experience = (row[10] or '').strip() if isinstance(row[10], str) else ''
        pretention = _parse_pretention_milliers(row[11])
        permis = str(row[12] or '').strip().lower() in {'oui', 'true', '1', 'yes'}
        note_domicile = _normalize_score_value(row[13] if len(row) > 13 else None)
        note_age = _normalize_score_value(row[14] if len(row) > 14 else None)
        note_formation = _normalize_score_value(row[15] if len(row) > 15 else None)
        note_experience = _normalize_score_value(row[16] if len(row) > 16 else None)
        note_pretention = _normalize_score_value(row[17] if len(row) > 17 else None)
        note_permis = _normalize_score_value(row[18] if len(row) > 18 else None)
        commentaire = (row[20] or '').strip() if len(row) > 20 and isinstance(row[20], str) else ''

        if not email or not poste_label:
            errors.append(f'Ligne {idx}: email ou poste manquant')
            continue

        poste = poste_cache.get(poste_label.lower())
        if not poste:
            errors.append(f'Ligne {idx}: poste introuvable "{poste_label}"')
            continue

        defaults = {
            'poste': poste,
            'nom': nom,
            'domicile': domicile,
            'date_naissance': date_naissance,
            'formation': formation,
            'experience_poste': experience_poste,
            'autre_experience': autre_experience,
            'pretention_salariale': pretention,
            'permis_conduire': permis,
            'commentaire_analyse': commentaire,
            'note_domicile': note_domicile,
            'note_age': note_age,
            'note_formation': note_formation,
            'note_experience': note_experience,
            'note_pretention': note_pretention,
            'note_permis': note_permis,
        }
        defaults['screening_statut'] = _normalize_screening_status(screening_statut)

        prenom = ''
        if isinstance(nom, str) and nom.strip():
            parts = nom.strip().split()
            if len(parts) > 1:
                prenom = ' '.join(parts[:-1])
                defaults['nom'] = parts[-1]
            else:
                defaults['nom'] = nom.strip()
        defaults['prenom'] = prenom

        obj, created_flag = CandidatPreconfigure.objects.update_or_create(
            email=email,
            defaults=defaults,
        )
        if created_flag:
            created += 1
        else:
            updated += 1

    return JsonResponse({
        'success': True,
        'message': f'Import termine. Crees: {created}, mis a jour: {updated}',
        'created': created,
        'updated': updated,
        'errors': errors[:20],
    })


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_creer_candidat_preconfig_v2(request):
    try:
        data = request.POST
        email = (data.get('email') or '').strip().lower()
        poste_id = data.get('poste_id', '')

        if not email or not poste_id:
            return JsonResponse({'success': False, 'error': 'Email et poste sont obligatoires'}, status=400)

        if CandidatPreconfigure.objects.filter(email__iexact=email).exists():
            return JsonResponse({'success': False, 'error': 'Cet email est deja preconfigure'}, status=400)

        if Candidat.objects.filter(email__iexact=email).exists():
            return JsonResponse({'success': False, 'error': 'Cet email est deja utilise par un candidat'}, status=400)

        poste = get_object_or_404(Poste, id=poste_id)
        candidat_preconfig = CandidatPreconfigure.objects.create(
            email=email,
            poste=poste,
            nom=(data.get('nom') or '').strip(),
            prenom=(data.get('prenom') or '').strip(),
            domicile=(data.get('domicile') or '').strip(),
            date_naissance=_parse_date_value(data.get('date_naissance')),
            formation=(data.get('formation') or '').strip(),
            experience_poste=(data.get('experience_poste') or '').strip(),
            autre_experience=(data.get('autre_experience') or '').strip(),
            pretention_salariale=_parse_pretention_milliers(data.get('pretention_salariale')),
            permis_conduire=(data.get('permis_conduire') == 'true'),
            screening_statut=_normalize_screening_status(data.get('screening_statut') or 'a_analyser'),
            commentaire_analyse=(data.get('commentaire_analyse') or '').strip(),
            note_domicile=_normalize_score_value(data.get('note_domicile')),
            note_age=_normalize_score_value(data.get('note_age')),
            note_formation=_normalize_score_value(data.get('note_formation')),
            note_experience=_normalize_score_value(data.get('note_experience')),
            note_pretention=_normalize_score_value(data.get('note_pretention')),
            note_permis=_normalize_score_value(data.get('note_permis')),
        )

        auto_photo = False
        if request.FILES.get('photo_candidat'):
            candidat_preconfig.photo_candidat = request.FILES['photo_candidat']
        if request.FILES.get('cv'):
            candidat_preconfig.cv = request.FILES['cv']
            auto_photo = _assign_auto_photo_from_cv(candidat_preconfig, request.FILES['cv'])
        if request.FILES.get('lettre_motivation'):
            candidat_preconfig.lettre_motivation = request.FILES['lettre_motivation']
        candidat_preconfig.save()

        return JsonResponse({
            'success': True,
            'message': 'Candidat cree avec succes' + (' - photo extraite automatiquement du CV' if auto_photo else ''),
            'photo_auto_extraite': auto_photo,
            'candidat': _serialize_candidat_preconfigure(candidat_preconfig),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_modifier_candidat_preconfig_v2(request, candidat_id):
    try:
        candidat = get_object_or_404(CandidatPreconfigure, id=candidat_id)
        data = request.POST
        email = (data.get('email') or candidat.email).strip().lower()

        if CandidatPreconfigure.objects.exclude(id=candidat.id).filter(email__iexact=email).exists():
            return JsonResponse({'success': False, 'error': 'Cet email est deja utilise'}, status=400)
        if Candidat.objects.exclude(id=getattr(candidat.candidat, 'id', None)).filter(email__iexact=email).exists():
            return JsonResponse({'success': False, 'error': 'Cet email est deja utilise par un candidat'}, status=400)

        poste_id = data.get('poste_id', '')
        if poste_id:
            candidat.poste = get_object_or_404(Poste, id=poste_id)

        candidat.email = email
        candidat.nom = (data.get('nom') or '').strip()
        candidat.prenom = (data.get('prenom') or '').strip()
        candidat.domicile = (data.get('domicile') or '').strip()
        candidat.date_naissance = _parse_date_value(data.get('date_naissance'))
        candidat.formation = (data.get('formation') or '').strip()
        candidat.experience_poste = (data.get('experience_poste') or '').strip()
        candidat.autre_experience = (data.get('autre_experience') or '').strip()
        candidat.pretention_salariale = _parse_pretention_milliers(data.get('pretention_salariale'))
        candidat.permis_conduire = (data.get('permis_conduire') == 'true')
        candidat.screening_statut = _normalize_screening_status(data.get('screening_statut') or candidat.screening_statut)
        candidat.commentaire_analyse = (data.get('commentaire_analyse') or '').strip()
        candidat.note_domicile = _normalize_score_value(data.get('note_domicile'))
        candidat.note_age = _normalize_score_value(data.get('note_age'))
        candidat.note_formation = _normalize_score_value(data.get('note_formation'))
        candidat.note_experience = _normalize_score_value(data.get('note_experience'))
        candidat.note_pretention = _normalize_score_value(data.get('note_pretention'))
        candidat.note_permis = _normalize_score_value(data.get('note_permis'))

        auto_photo = False
        if request.FILES.get('photo_candidat'):
            candidat.photo_candidat = request.FILES['photo_candidat']
        if request.FILES.get('cv'):
            candidat.cv = request.FILES['cv']
            auto_photo = _assign_auto_photo_from_cv(candidat, request.FILES['cv'])
        if request.FILES.get('lettre_motivation'):
            candidat.lettre_motivation = request.FILES['lettre_motivation']

        candidat.save()
        return JsonResponse({
            'success': True,
            'message': 'Candidat mis a jour' + (' - photo extraite automatiquement du CV' if auto_photo else ''),
            'photo_auto_extraite': auto_photo,
            'candidat': _serialize_candidat_preconfigure(candidat),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin_or_staff)
@require_http_methods(["POST"])
def api_inviter_candidat_test_v2(request, candidat_id):
    candidat = get_object_or_404(CandidatPreconfigure.objects.select_related('poste', 'candidat'), id=candidat_id)

    if candidat.screening_statut == 'elimine':
        return JsonResponse({'success': False, 'error': 'Candidat elimine: invitation impossible'}, status=400)

    candidat.invite_test_envoyee = True
    if candidat.screening_statut not in {'invite_test', 'test_complete'}:
        candidat.screening_statut = 'invite_test'
    candidat.save(update_fields=['invite_test_envoyee', 'screening_statut'])

    return JsonResponse({
        'success': True,
        'message': 'Candidat marque comme invite au test',
        'candidat': _serialize_candidat_preconfigure(candidat),
    })
