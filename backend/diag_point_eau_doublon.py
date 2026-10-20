"""
Diagnostic : point d'eau occupant le code 'Andranolava_1'.
Usage sur le VPS :
    cd /home/soakoja/hydria/backend
    /home/soakoja/hydria/venv/bin/python diag_point_eau_doublon.py
"""
import os
import sys
import django

sys.path.insert(0, '/home/soakoja/hydria/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.billing.models import PointEau, Releve  # noqa: E402

CODE = 'Andranolava_1'

print("\n=== POINT(S) D'EAU AVEC LE CODE", CODE, "===\n")

matches = list(
    PointEau.objects
    .select_related('ouvrage', 'type_point_eau', 'parcelle__village')
    .filter(code_point_eau=CODE)
)
print("Nombre de correspondances exactes :", len(matches))
for m in matches:
    print("   -", m.pk, "| nom:", repr(m.nomabonne), "| ouvrage:", m.ouvrage)

if not matches:
    print("\n>>> Plus aucun point d'eau ne porte ce code. Vous pouvez creer le votre.\n")
    print("Codes existants commencant par 'Andranolava' :")
    for q in PointEau.objects.filter(code_point_eau__startswith='Andranolava').order_by('code_point_eau'):
        print(f"   {q.code_point_eau:<20} | ouvrage: {q.ouvrage} | id: {q.pk}")
    sys.exit(0)

p = matches[0]

print("id                :", p.pk)
print("code_point_eau    :", repr(p.code_point_eau))
print("nomabonne         :", repr(p.nomabonne))
print("ouvrage           :", p.ouvrage, "(id:", getattr(p.ouvrage, 'pk', None), ")")
print("type_point_eau    :", p.type_point_eau)
print("parcelle          :", p.parcelle)
print("idxls             :", repr(p.idxls))
print("numeroteleph      :", repr(p.numeroteleph))
print("tarifforfaitaire  :", p.tarifforfaitaire)
print("latitude/longitude:", p.latitude, "/", p.longitude)
print("createdat         :", p.createdat)
print("updatedat         :", p.updatedat)

nb_releves = Releve.objects.filter(point_eau=p).count()
print("\nRelevés rattachés :", nb_releves)
if nb_releves:
    for r in Releve.objects.filter(point_eau=p).order_by('datereleve')[:10]:
        print("   -", r.datereleve, "| montant:", r.montant, "| diamex:", r.numeroDiameX)

# Autres relations éventuelles
for rel in p._meta.related_objects:
    try:
        accessor = rel.get_accessor_name()
        mgr = getattr(p, accessor, None)
        if mgr is None:
            continue
        cnt = mgr.count()
        if cnt:
            print(f"Relation {accessor:<35} : {cnt}")
    except Exception:
        pass

print("\n=== TOUS LES POINTS D'EAU DE L'OUVRAGE", p.ouvrage, "AVEC UN CODE COMMENÇANT PAR 'Andranolava' ===\n")
for q in PointEau.objects.filter(ouvrage=p.ouvrage, code_point_eau__startswith='Andranolava').order_by('code_point_eau'):
    print(f"   {q.code_point_eau:<20} | nom: {q.nomabonne!r:<30} | idxls: {q.idxls!r} | id: {q.pk}")

print()
