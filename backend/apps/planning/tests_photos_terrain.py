from django.test import SimpleTestCase

from apps.planning.views_preparation_tournee import MAX_MOBILE_PHOTOS, _append_mobile_photo


class AppendMobilePhotoTests(SimpleTestCase):
    """Les photos terrain s'ajoutent à la fiche au lieu de s'écraser."""

    def test_second_photo_keeps_first(self):
        photos = _append_mobile_photo(None, {'local_uuid': 'a'})
        photos = _append_mobile_photo(photos, {'local_uuid': 'b'})
        self.assertEqual([p['local_uuid'] for p in photos], ['a', 'b'])

    def test_keeps_photos_added_from_the_website(self):
        web = [{'url': '/media/photos/1.jpg', 'filename': '1.jpg'}]
        photos = _append_mobile_photo(web, {'local_uuid': 'a'})
        self.assertEqual(len(photos), 2)
        self.assertEqual(photos[0]['filename'], '1.jpg')

    def test_wraps_legacy_single_dict_and_ignores_empty_values(self):
        self.assertEqual(len(_append_mobile_photo({'url': 'x'}, {'local_uuid': 'a'})), 2)
        for empty in (None, {}, [], ''):
            self.assertEqual(len(_append_mobile_photo(empty, {'local_uuid': 'a'})), 1)

    def test_does_not_mutate_input_and_caps_to_latest(self):
        original = [{'local_uuid': str(i)} for i in range(MAX_MOBILE_PHOTOS)]
        result = _append_mobile_photo(original, {'local_uuid': 'new'})
        self.assertEqual(len(original), MAX_MOBILE_PHOTOS)
        self.assertEqual(len(result), MAX_MOBILE_PHOTOS)
        self.assertEqual(result[-1]['local_uuid'], 'new')
        self.assertEqual(result[0]['local_uuid'], '1')
