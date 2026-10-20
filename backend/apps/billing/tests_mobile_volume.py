"""Focused workflow tests, no connection to the operational database."""
import inspect
import json
import uuid
from contextlib import nullcontext
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, RequestFactory
from . import views_mobile_volume as views


class MobileVolumeTests(SimpleTestCase):
    def setUp(self):
        self.id = str(uuid.uuid4())
        self.record = SimpleNamespace(pk=self.id, montant=Decimal('1200.00'),
            numeroDiameX='', datepaiement=None, montantpaye=None, facture_imprimee=False, save=MagicMock())
        self.entry = SimpleNamespace(pk=12, compte_code='707401', id_access=90, prog='BASE')
        self.segments = {('work', '2026-09'): Decimal('1200.00')}
        self.previously_pointed = []
        self.quote = {'id': self.id, 'version': 'quote-v1', 'montant': '1200.00',
                      'ouvrage_id': 'work', 'mois': '2026-09', 'ouvrage': 'Village', 'erreur_calcul': ''}
        self.payload = {'local_uuid': str(uuid.uuid4()), 'action': 'collect', 'date': '2026-01-01',
                        'factures': [{'id': self.id, 'version': 'quote-v1'}]}
        self.user = SimpleNamespace(pk=42, employe=SimpleNamespace(nom='Agent', base=SimpleNamespace(
            volet='EAU', prog_diamex='BASE', nom_base='Base')))

    def invoke(self, receipt=None, records=None):
        request = RequestFactory().post('/', data=json.dumps(self.payload), content_type='application/json')
        request.user = self.user
        with patch.object(views.transaction, 'atomic', return_value=nullcontext()), \
             patch.object(views, 'get_user_model'), \
             patch.object(views, '_get_allowed_ouvrage_ids', return_value=['work']), \
             patch.object(views, 'invoice_data', return_value=self.quote), \
             patch.object(views, 'available_journals', return_value=[{'code': '00PERS', 'nom': 'Personnel'}]), \
             patch.object(views.MobileVolumeOperation, 'objects') as ledger, \
             patch.object(views.MobileVolumeInvoiceSnapshot, 'objects'), \
             patch.object(views.Releve, 'objects') as readings, \
             patch.object(views.BaseDiameX, 'objects') as entries, \
             patch.object(views, 'entry_segments', return_value=self.segments), \
             patch.object(views.DiameXTemporaire, 'objects') as cash:
            ledger.filter.return_value.first.return_value = receipt
            readings.select_for_update.return_value.filter.return_value.order_by.return_value = (
                [self.record] if records is None else records)
            cash.create.return_value = SimpleNamespace(pk=8)
            readings.filter.return_value = self.previously_pointed
            entries.select_for_update.return_value.get.return_value = self.entry
            response = inspect.unwrap(views.sync_operation)(request)
            self.cash_calls = cash.create.call_count
            self.ledger_calls = ledger.create.call_count
            return response.status_code, json.loads(response.content)

    def test_collect_creates_one_receipt_without_pointing(self):
        code, body = self.invoke()
        self.assertEqual(code, 200)
        self.assertEqual(body['diamex_temporaire_id'], 8)
        self.assertEqual(self.record.montantpaye, Decimal('1200.00'))
        self.assertEqual(self.record.numeroDiameX, '')
        self.assertEqual((self.cash_calls, self.ledger_calls), (1, 1))

    def test_response_loss_replays_receipt_without_second_cash_entry(self):
        saved = {'success': True, 'local_uuid': self.payload['local_uuid']}
        receipt = SimpleNamespace(user_id=42, payload_hash=views.digest(self.payload), response=saved)
        code, body = self.invoke(receipt)
        self.assertEqual((code, body), (200, saved))
        self.assertEqual((self.cash_calls, self.ledger_calls), (0, 0))

    def test_changed_payload_cannot_reuse_uuid(self):
        receipt = SimpleNamespace(user_id=42, payload_hash='other', response={})
        self.assertEqual(self.invoke(receipt)[0], 409)
        self.assertEqual(self.cash_calls, 0)

    def test_stale_quote_never_creates_cash(self):
        self.payload['factures'][0]['version'] = 'obsolete'
        self.assertEqual(self.invoke()[0], 409)
        self.assertEqual(self.cash_calls, 0)

    def test_already_collected_and_out_of_scope_are_rejected(self):
        self.record.datepaiement = date(2026, 1, 1)
        self.assertEqual(self.invoke()[0], 409)
        self.assertEqual(self.cash_calls, 0)
        self.assertEqual(self.invoke(records=[])[0], 409)
        self.assertEqual(self.cash_calls, 0)

    def test_duplicate_invoice_ids_are_rejected(self):
        self.payload['factures'] *= 2
        self.assertEqual(self.invoke()[0], 409)
        self.assertEqual(self.cash_calls, 0)

    def test_point_uses_real_diamex_segment_and_sets_reference(self):
        self.payload.update(action='point', diamex_id='12')
        self.assertEqual(self.invoke()[0], 200)
        self.assertEqual((self.record.numeroDiameX, self.record.baseDiameX), ('90', 'BASE'))
        self.assertEqual(self.cash_calls, 0)

    def test_point_rejects_wrong_amount_work_or_account(self):
        self.payload.update(action='point', diamex_id='12', montant_diamex_selection='1200')
        for segments in ({('work', '2026-09'): Decimal('999')}, {('other', '2026-09'): Decimal('1200')}):
            self.segments = segments
            self.assertEqual(self.invoke()[0], 409)
            self.record.save.assert_not_called()
        self.segments = {('work', '2026-09'): Decimal('1200')}
        self.entry.compte_code = '707402'
        self.assertEqual(self.invoke()[0], 409)

    def test_point_cannot_reuse_an_already_assigned_segment(self):
        self.payload.update(action='point', diamex_id='12')
        self.previously_pointed = [SimpleNamespace(datereleve=date(2026, 8, 31))]
        self.assertEqual(self.invoke()[0], 409)
        self.record.save.assert_not_called()

    def test_cash_rejects_foreign_journal(self):
        self.payload['journal_code'] = 'OTHER'
        self.assertEqual(self.invoke()[0], 409)
        self.assertEqual(self.cash_calls, 0)

    def test_print_confirmation_does_not_collect(self):
        self.payload['action'] = 'printed'
        self.assertEqual(self.invoke()[0], 200)
        self.assertTrue(self.record.facture_imprimee)
        self.assertIsNone(self.record.datepaiement)
        self.assertEqual(self.cash_calls, 0)

    def test_quote_fingerprint_survives_decimal_storage_scale(self):
        record = SimpleNamespace(pk=self.id, montant=None, point_eau_id='point',
            point_eau=SimpleNamespace(nomabonne='Client', ouvrage_id='work',
                                     ouvrage=SimpleNamespace(nom_ouvrage='Village')),
            datereleve=date(2026, 8, 31), ancienindex=Decimal('10'), nouvelindex=Decimal('12'),
            numero_facture='F1', facture_imprimee=False, datepaiement=None, numeroDiameX='', baseDiameX='')
        with patch.object(views, 'calculer_montant_releve', return_value={
            'success': True, 'montant_total': 1200.0, 'detail': {'volume_calcule': 2.0}}):
            before = views.invoice_data(record)
            record.montant = Decimal('1200.00')
            after = views.invoice_data(record)
            self.assertEqual(before['version'], after['version'])

    def test_segments_with_same_work_and_month_are_aggregated(self):
        extraction = {'ouvrage_obj': SimpleNamespace(pk='w'), 'annee': 2026, 'mois': 9}
        entry = SimpleNamespace(description='a;b', compte_code='707401', montant_in=300)
        with patch.object(views, 'diviser_paiement_volume_multi', return_value=[
            {'extraction': extraction, 'montant': '100.10'},
            {'extraction': extraction, 'montant': '199.90'},
        ]):
            self.assertEqual(views.entry_segments(entry), {('w', '2026-09'): Decimal('300.00')})

    def test_printed_invoice_keeps_frozen_breakdown_after_tariff_change(self):
        record = SimpleNamespace(pk=self.id, montant=Decimal('1200.00'), point_eau_id='point',
            point_eau=SimpleNamespace(nomabonne='Client', ouvrage_id='work',
                                     ouvrage=SimpleNamespace(nom_ouvrage='Village')),
            datereleve=date(2026, 8, 31), ancienindex=Decimal('10'), nouvelindex=Decimal('12'),
            numero_facture='F1', facture_imprimee=False, datepaiement=None, numeroDiameX='', baseDiameX='')
        with patch.object(views, 'calculer_montant_releve', return_value={
            'success': True, 'montant_total': 1200.0, 'detail': {'abonnement': 200, 'montant_volume': 1000}}):
            before = views.invoice_data(record)
        record.facture_imprimee = True
        with patch.object(views, 'calculer_montant_releve', return_value={
            'success': True, 'montant_total': 2400.0, 'detail': {'abonnement': 400, 'montant_volume': 2000}}), \
             patch.object(views.MobileVolumeInvoiceSnapshot, 'objects') as snapshots:
            snapshots.filter.return_value.first.return_value = SimpleNamespace(data=before)
            after = views.invoice_data(record)
        self.assertEqual(after['montant'], '1200.00')
        self.assertEqual(before['detail'], after['detail'])
        self.assertEqual(before['version'], after['version'])

    def test_print_fields_match_web_facturation_shape(self):
        """Le Desktop imprime avec print_factures_a4.js : memes cles que api_calculer_factures."""
        record = SimpleNamespace(pk=self.id, id=self.id, numero_facture='F1', abonne='Client', volume_facture=Decimal('2'),
            ancienindex=Decimal('10'), nouvelindex=Decimal('12'), datereleve=date(2026, 8, 31),
            point_eau=SimpleNamespace(ouvrage_id='work', ouvrage=SimpleNamespace(nom_ouvrage='Village'),
                code_point_eau='BP-7', nomabonne='Client', idxls='7',
                parcelle=SimpleNamespace(reference_parcelle='P12'), type_point_eau=SimpleNamespace(nom_type='BP')))
        with patch.object(views, 'serialize_segments', return_value=[]):
            fields = views.print_fields(record, {'nom': 'Rakoto', 'telephone': '034'})
        self.assertEqual(fields['qr_payload'], f'HYDRIA|FACTURE|{self.id}|F1|2026-09|work')
        self.assertEqual(fields['parcelle'], 'P12')
        self.assertEqual(fields['responsable_ouvrage_nom'], 'Rakoto')
        self.assertEqual(fields['ancienindex'], 10.0)
        self.assertNotIn('version', fields)
