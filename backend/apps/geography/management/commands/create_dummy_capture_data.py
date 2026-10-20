from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.billing.models import PointEau, TypePointEau
from apps.geography.models import Commune, District, Fokontany, Region, Village, Parcelle
from apps.infrastructure.models import EquipementConstitutif, TypeEquipement
from apps.organization.models import Ouvrage, TypeOuvrage


class Command(BaseCommand):
    help = (
        "Cree un village/parcelle/point d'eau/ouvrage/equipement factice proche des "
        "coordonnees fournies pour tester l'atelier de capture de donnees."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--latitude",
            type=float,
            default=-18.9146,
            help="Latitude du village fictif (ex: -18.9146).",
        )
        parser.add_argument(
            "--longitude",
            type=float,
            default=47.5316,
            help="Longitude du village fictif (ex: 47.5316).",
        )
        parser.add_argument(
            "--village-name",
            default="Village GPS Test",
            help="Nom a utiliser pour le village factice.",
        )
        parser.add_argument(
            "--region",
            default="Region de test",
            help="Nom de la region de rattachement.",
        )
        parser.add_argument(
            "--district",
            default="District de test",
            help="Nom du district de rattachement.",
        )
        parser.add_argument(
            "--commune",
            default="Commune de test",
            help="Nom de la commune de rattachement.",
        )
        parser.add_argument(
            "--fokontany",
            default="Fokontany test",
            help="Nom du fokontany lie au village.",
        )
        parser.add_argument(
            "--parcelle-name",
            default="Parcelle GPS 1",
            help="Nom de la parcelle test qui sera creee pour le village.",
        )

    def handle(self, *args, **options):
        lat = Decimal(str(options["latitude"]))
        lon = Decimal(str(options["longitude"]))
        village_name = options["village_name"]

        with transaction.atomic():
            region, _ = Region.objects.get_or_create(nom_region=options["region"])
            district, _ = District.objects.get_or_create(
                nom_district=options["district"], region=region
            )
            commune, _ = Commune.objects.get_or_create(
                nom_commune=options["commune"], district=district
            )
            fokontany, _ = Fokontany.objects.get_or_create(
                nom_fokontany=options["fokontany"], commune=commune
            )

            village_defaults = {
                "fokontany": fokontany,
                "latitude": lat,
                "longitude": lon,
                "accessibilite": "pied",
            }
            village, village_created = Village.objects.update_or_create(
                nom_village=village_name,
                fokontany=fokontany,
                defaults=village_defaults,
            )

            parcelle, parcelle_created = Parcelle.objects.get_or_create(
                village=village,
                reference_parcelle=options["parcelle_name"],
            )

            type_point_eau, _ = TypePointEau.objects.get_or_create(nom_type="Forage test")
            type_ouvrage, _ = TypeOuvrage.objects.get_or_create(nom_type_ouvrage="Forage")
            type_equipement, _ = TypeEquipement.objects.get_or_create(nom_type="Pompe test")

            ouvrage, ouvrage_created = Ouvrage.objects.get_or_create(
                nom_ouvrage=f"{village_name} - Point central",
                defaults={"type_ouvrage": type_ouvrage},
            )

            point_eau, point_created = PointEau.objects.get_or_create(
                nomabonne=f"{village_name} - Point d'eau",
                defaults={
                    "type_point_eau": type_point_eau,
                    "parcelle": parcelle,
                    "latitude": float(lat + Decimal("0.0002")),
                    "longitude": float(lon + Decimal("0.0002")),
                    "ouvrage": ouvrage,
                },
            )

            equipement, equip_created = EquipementConstitutif.objects.get_or_create(
                nom=f"{village_name} - Pompe test",
                ouvrage=ouvrage,
                defaults={
                    "type_equipement": type_equipement,
                    "latitude": lat,
                    "longitude": lon,
                    "statut": "operationnel",
                },
            )

        self.stdout.write(self.style.SUCCESS("Donnees factices creees :"))
        self.stdout.write(f"  Region: {region}")
        self.stdout.write(f"  District: {district}")
        self.stdout.write(f"  Commune: {commune}")
        self.stdout.write(f"  Fokontany: {fokontany}")
        self.stdout.write(f"  Village: {village} (ID={village.id})")
        self.stdout.write(f"  Parcelle: {parcelle.reference_parcelle} (ID={parcelle.id})")
        self.stdout.write(f"  Point d'eau: {point_eau.nomabonne} (ID={point_eau.id})")
        self.stdout.write(f"  Ouvrage : {ouvrage.nom_ouvrage} (ID={ouvrage.id})")
        self.stdout.write(f"  Equipement : {equipement.nom} (ID={equipement.id})")
        self.stdout.write("")
        self.stdout.write(
            "Relancez ensuite le serveur, rechargez "
            "`/geography/capture-donnees/` et reprenez la capture autour de ces "
            "coordonnees."
        )
