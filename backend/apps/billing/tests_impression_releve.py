from types import SimpleNamespace
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from apps.billing.views_releves import _motifs_blocage_impression


def _user(directeur=False):
    groups = MagicMock()
    groups.filter.return_value.exists.return_value = directeur
    return SimpleNamespace(
        is_authenticated=True,
        employe=SimpleNamespace(is_directeur=directeur),
        groups=groups,
    )


def _analyse(depassement=False, ecart=12.0, moyenne=10.0):
    return {
        'depassement_50': depassement,
        'ecart_pourcentage': ecart,
        'moyenne_consommation': moyenne,
    }


class MotifsBlocageImpressionTests(SimpleTestCase):
    def test_agent_dans_la_marge_sans_non_facture_peut_imprimer(self):
        self.assertEqual(_motifs_blocage_impression(_analyse(), 0, _user()), [])

    def test_agent_hors_marge_50_pourcent_est_bloque(self):
        motifs = _motifs_blocage_impression(_analyse(True, 80.0, 10.0), 0, _user())
        self.assertEqual(len(motifs), 1)
        self.assertIn('±50', motifs[0])

    def test_agent_avec_volume_non_facture_est_bloque(self):
        motifs = _motifs_blocage_impression(_analyse(), 0.5, _user())
        self.assertEqual(len(motifs), 1)
        self.assertIn('non facturé', motifs[0])

    def test_les_deux_motifs_sont_cumules(self):
        motifs = _motifs_blocage_impression(_analyse(True, 80.0), 1, _user())
        self.assertEqual(len(motifs), 2)

    def test_directeur_jamais_bloque(self):
        self.assertEqual(
            _motifs_blocage_impression(_analyse(True, 80.0), 3, _user(directeur=True)), []
        )
