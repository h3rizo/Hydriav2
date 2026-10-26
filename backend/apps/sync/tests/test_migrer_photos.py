import base64
import json

from django.test import SimpleTestCase, override_settings

from apps.sync.management.commands.migrer_photos import (decoder_base64, extension_par_contenu, extraire_photos,
                                                          nom_de_photo)

JPEG = b'\xff\xd8\xff\xe0' + b'x' * 20
PNG = b'\x89PNG\r\n\x1a\n' + b'y' * 20


class ExtractionPhotosTests(SimpleTestCase):
    def test_extension_detectee_par_le_contenu(self):
        self.assertEqual(extension_par_contenu(JPEG), 'jpg')
        self.assertEqual(extension_par_contenu(PNG), 'png')
        self.assertEqual(extension_par_contenu(b'RIFF\x00\x00\x00\x00WEBPxx'), 'webp')
        self.assertEqual(extension_par_contenu(b'texte'), '')

    def test_base64_brut_et_data_uri(self):
        brut = base64.b64encode(JPEG).decode()
        self.assertEqual(decoder_base64(brut), JPEG)
        self.assertEqual(decoder_base64('data:image/jpeg;base64,' + brut), JPEG)
        self.assertIsNone(decoder_base64('data:image/jpeg,pas-base64'))
        self.assertIsNone(decoder_base64(''))

    def test_liste_de_dictionnaires_avec_data(self):
        valeur = [{'filename': 'pompe.jpg', 'data': base64.b64encode(JPEG).decode()}]
        self.assertEqual(extraire_photos(valeur), [('pompe.jpg', JPEG, '')])

    def test_json_sous_forme_de_texte_et_chaine_data_uri(self):
        brut = base64.b64encode(PNG).decode()
        self.assertEqual(extraire_photos(json.dumps(['data:image/png;base64,' + brut])), [('', PNG, '')])

    def test_structure_inconnue_et_valeur_vide(self):
        self.assertEqual(extraire_photos(None), [])
        self.assertEqual(extraire_photos([]), [])
        self.assertEqual(extraire_photos([{'truc': 1}]), [('', None, 'format')])
        self.assertEqual(extraire_photos(12), [('', None, 'format')])

    def test_url_vers_un_fichier_media(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as racine:
            (Path(racine) / 'photos').mkdir()
            (Path(racine) / 'photos' / 'a.jpg').write_bytes(JPEG)
            with override_settings(MEDIA_ROOT=racine, MEDIA_URL='/media/'):
                self.assertEqual(extraire_photos([{'url': '/media/photos/a.jpg'}]), [('a.jpg', JPEG, '')])
                self.assertEqual(extraire_photos([{'url': '/media/photos/absent.jpg'}])[0][1:], (None, 'absent'))
                # sortie de MEDIA_ROOT refusée
                self.assertEqual(extraire_photos([{'url': '/media/../secret.txt'}])[0][1:], (None, 'absent'))

    def test_nom_unique_et_sans_chemin(self):
        self.assertEqual(nom_de_photo('../dir/pompe.JPG', 'jpg', 'abcdef123'), 'pompe-abcdef.jpg')
        self.assertEqual(nom_de_photo('', 'png', '123456789'), 'photo-123456.png')
