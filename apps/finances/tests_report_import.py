"""Tests for third-party funding report Übersicht import."""

from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from openpyxl import Workbook

from apps.accounts.models import CustomUser
from apps.accounts.permissions import assign_permissions_to_groups
from apps.finances.models import (
    ContactPerson,
    CostCenter,
    WBSElement,
    WBSElementObligo,
    WBSElementTrueYearlySpending,
    WBSElementYearEstimate,
)
from apps.finances.report_import.parsers import detect_and_parse
from apps.finances.report_import.parsers.gesamtbericht import (
    GesamtberichtPspParser,
    report_date_from_filename,
)
from apps.finances.report_import.parsers.personalkosten import extract_beleg_date_range
from apps.finances.report_import.parsers.uebersicht import UebersichtPspParser
from apps.core.import_tracking import (
    is_report_older_than_last_import,
    record_data_import,
    remaining_scopes_for_hash,
    sha256_bytes,
)
from apps.core.models import DataImportLog
from apps.finances.report_import.service import (
    analyze_uploaded_files,
    apply_import_plan,
    merge_user_decisions,
    normalize_import_scopes,
)


def _build_sample_workbook() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = 'Übersicht'
    ws['F3'] = 'Förderkennzeichen:  DFG - TEST-1'
    ws['B4'] = 'Projektdefinition:  DFG - TEST-1'
    ws['B5'] = 'Ansprechpartner:  Muster, Erika'
    ws['B7'] = 'Projektleiter:        Doe, Jane'
    ws['B8'] = 'Projektlaufzeit:     01.01.2026 bis  31.12.2028'
    ws['H8'] = 'Geplantes Projektende'
    ws['H9'] = date(2028, 12, 31)
    ws['B10'] = 'Projekt'
    ws['C10'] = 'Kostenstelle'
    ws['D10'] = 'Erstes Buchungsdatum'
    ws['F10'] = 'Letztes Buchungsdatum'
    ws['B12'] = 'T-100.0001'
    ws['C12'] = '0001/991000'
    ws['F12'] = date(2026, 6, 1)
    ws['B13'] = 'T-100.0001.1'
    ws['C13'] = '0001/991000'
    ws['F13'] = date(2026, 6, 15)
    ws['B14'] = 'T-100.0001.2'
    ws['C14'] = '0001/991000'
    ws['F14'] = date(2027, 1, 10)  # after 2026 for year check
    ws['B17'] = 'Projekt'
    ws['C17'] = 'PSP Bezeichnung'
    ws['E17'] = 'Freigegebenes Budget'
    ws['F17'] = 'Ist-Kosten'
    ws['G17'] = 'Obligo'
    ws['I17'] = 'Personalobligo'
    ws['K17'] = 'Verfügt'
    ws['B18'] = 'T-100.0001'
    ws['C18'] = 'DFG Parent Designation'
    ws['E18'] = 0
    ws['F18'] = 0
    ws['G18'] = 0
    ws['I18'] = 0
    ws['K18'] = 0
    ws['B19'] = 'T-100.0001.1'
    ws['C19'] = 'Sachaufwendungen'
    ws['E19'] = 10000
    ws['F19'] = 1000
    ws['G19'] = 200
    ws['I19'] = 0
    ws['K19'] = 1200
    ws['B20'] = 'T-100.0001.2'
    ws['C20'] = 'Personalaufwendungen'
    ws['E20'] = 50000
    ws['F20'] = 5000
    ws['G20'] = 0
    ws['I20'] = 8000
    ws['K20'] = 13000
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_workbook_with_personalkosten() -> bytes:
    """Sample Übersicht + Personalkosten with Belegdatum range."""
    wb = Workbook()
    ws = wb.active
    ws.title = 'Übersicht'
    ws['F3'] = 'Förderkennzeichen:  DFG - TEST-1'
    ws['B4'] = 'Projektdefinition:  DFG - TEST-1'
    ws['B5'] = 'Ansprechpartner:  Muster, Erika'
    ws['B8'] = 'Projektlaufzeit:     01.01.2026 bis  31.12.2028'
    ws['H9'] = date(2028, 12, 31)
    ws['B10'] = 'Projekt'
    ws['C10'] = 'Kostenstelle'
    ws['F10'] = 'Letztes Buchungsdatum'
    ws['B12'] = 'T-200.0001'
    ws['C12'] = '0001/991000'
    ws['F12'] = date(2026, 6, 1)
    ws['B13'] = 'T-200.0001.2'
    ws['C13'] = '0001/991000'
    ws['F13'] = date(2026, 6, 1)
    ws['B17'] = 'Projekt'
    ws['C17'] = 'PSP Bezeichnung'
    ws['E17'] = 'Freigegebenes Budget'
    ws['F17'] = 'Ist-Kosten'
    ws['G17'] = 'Obligo'
    ws['I17'] = 'Personalobligo'
    ws['K17'] = 'Verfügt'
    ws['B18'] = 'T-200.0001'
    ws['C18'] = 'Parent'
    ws['E18'] = 0
    ws['F18'] = 0
    ws['G18'] = 0
    ws['I18'] = 0
    ws['K18'] = 0
    ws['B19'] = 'T-200.0001.2'
    ws['C19'] = 'Personal'
    ws['E19'] = 10000
    ws['F19'] = 1000
    ws['G19'] = 0
    ws['I19'] = 500
    ws['K19'] = 1200

    pk = wb.create_sheet('Personalkosten')
    # Row 2 headers (index 1): B=PSP, C=Kostenart, G=Belegdatum, H=Personalnummer, I=Personalkosten
    pk['B2'] = 'PSP'
    pk['C2'] = 'Kostenart'
    pk['G2'] = 'Belegdatum'
    pk['H2'] = 'Personalnummer'
    pk['I2'] = 'Personalkosten'
    pk['B3'] = 'T-200.0001.2'
    pk['C3'] = '60003000'
    pk['G3'] = date(2026, 1, 15)
    pk['H3'] = '50001001'
    pk['I3'] = 1000
    pk['B4'] = 'T-200.0001.2'
    pk['C4'] = '60003000'
    pk['G4'] = date(2026, 3, 28)
    pk['H4'] = '50001002'
    pk['I4'] = 2000
    # Other cost type with earlier date — still counts for coverage range
    pk['B5'] = 'T-200.0001.2'
    pk['C5'] = '60001000'
    pk['G5'] = date(2025, 12, 1)
    pk['H5'] = '50001003'
    pk['I5'] = 50

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_sap_personalkosten_only_workbook():
    """Real SAP column order including Buchungstext + Buchungsdatum + Personalkosten."""
    from openpyxl import Workbook

    wb = Workbook()
    # Minimal Übersicht so detect_and_parse does not fail hard
    ws = wb.active
    ws.title = 'Übersicht'
    ws['B12'] = 'S-100.0001'
    ws['C12'] = '0001/991000'

    pk = wb.create_sheet('Personalkosten')
    pk['B2'] = 'PSP'
    pk['C2'] = 'Kostenart'
    pk['D2'] = 'KOA Bezeichnung'
    pk['E2'] = 'Buchungstext'
    pk['F2'] = 'Buchungs-\ndatum'
    pk['G2'] = 'Beleg-\ndatum'
    pk['H2'] = 'Personal-\nnummer'
    pk['I2'] = 'Personalkosten'
    pk['B3'] = 'S-100.0001.2'
    pk['C3'] = '60003000'
    pk['D3'] = 'Lohn/Gehalt DA 03'
    pk['E3'] = 'MUSTERSCHMIDT ANNA - Für-Periode 06 - 2026'
    pk['F3'] = '30.06.2026'
    pk['G3'] = '22.06.2026'
    pk['H3'] = '50999001'
    pk['I3'] = 1234.56
    pk['B4'] = 'S-100.0001.2'
    pk['C4'] = '60003500'
    pk['E4'] = 'OTHER PERSON - Für-Periode 06 - 2026'
    pk['F4'] = '30.06.2026'
    pk['H4'] = '50999002'
    pk['I4'] = 9999.00  # DA 35 base salary — included
    pk['B5'] = 'S-100.0001.2'
    pk['C5'] = '61003500'
    pk['E5'] = 'OTHER PERSON - social'
    pk['F5'] = '30.06.2026'
    pk['H5'] = '50999002'
    pk['I5'] = 500.00  # Sozialabgaben — ignored

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


class SapPersonalkostenLayoutTests(TestCase):
    def test_parses_sap_layout_with_amount_column(self):
        from apps.finances.report_import.parsers.personalkosten import (
            parse_personalkosten_sheet,
        )

        data = _build_sap_personalkosten_only_workbook()
        entries = parse_personalkosten_sheet(data, 'sap.xlsx')
        by_pn = {e.personalnummer: e for e in entries}
        self.assertEqual(set(by_pn), {'50999001', '50999002'})
        self.assertEqual(by_pn['50999001'].personalkosten, Decimal('1234.56'))
        self.assertEqual(by_pn['50999001'].buchungsdatum, date(2026, 6, 30))
        self.assertIn('MUSTERSCHMIDT', by_pn['50999001'].buchungstext)
        # DA 35 included; social contribution not used instead
        self.assertEqual(by_pn['50999002'].kostenart, '60003500')
        self.assertEqual(by_pn['50999002'].personalkosten, Decimal('9999.00'))


class BelegDateRangeTests(TestCase):
    def test_extract_beleg_from_to(self):
        data = _build_workbook_with_personalkosten()
        beleg_from, beleg_to = extract_beleg_date_range(data)
        self.assertEqual(beleg_from, date(2025, 12, 1))
        self.assertEqual(beleg_to, date(2026, 3, 28))

    def test_analyze_stores_beleg_range_on_meta(self):
        data = _build_workbook_with_personalkosten()
        upload = SimpleUploadedFile('with-pk.xlsx', data)
        plan = analyze_uploaded_files([upload], import_year=2026)
        meta = plan['upload_meta'][0]
        self.assertEqual(meta.get('beleg_from'), '2025-12-01')
        self.assertEqual(meta.get('beleg_to'), '2026-03-28')


class UebersichtParserTests(TestCase):
    def test_parses_parent_and_cost_types(self):
        data = _build_sample_workbook()
        result = UebersichtPspParser().parse(data, 'sample.xlsx')
        self.assertFalse(result.errors)
        self.assertEqual(len(result.parents), 1)
        parent = result.parents[0]
        self.assertEqual(parent.wbs_code, 'T-100.0001')
        self.assertEqual(parent.third_party_funder_identifier, 'DFG Parent Designation')
        self.assertEqual(parent.cost_center_code, '0001/991000')
        self.assertEqual(parent.period_start, date(2026, 1, 1))
        self.assertEqual(parent.period_end, date(2028, 12, 31))
        self.assertEqual(parent.contact.last_name, 'Muster')
        self.assertEqual(parent.contact.first_name, 'Erika')
        self.assertIn('1', parent.cost_types)
        self.assertIn('2', parent.cost_types)
        self.assertEqual(parent.cost_types['1'].approved_budget, Decimal('10000'))
        self.assertEqual(parent.cost_types['1'].verfuegt, Decimal('1200'))
        self.assertEqual(parent.cost_types['2'].personal_obligo, Decimal('8000'))
        self.assertIn(2027, parent.last_booking_years)


class CostCenterLookupTests(TestCase):
    def test_creates_with_code_after_slash(self):
        from apps.finances.report_import.service import get_or_create_cost_center

        cc, created = get_or_create_cost_center('0001/991000')
        self.assertTrue(created)
        self.assertEqual(cc.cost_center, '991000')

        again, created_again = get_or_create_cost_center('0001/991000')
        self.assertFalse(created_again)
        self.assertEqual(again.pk, cc.pk)
        self.assertEqual(CostCenter.objects.filter(cost_center__contains='991000').count(), 1)

    def test_matches_short_code_when_file_has_prefix(self):
        from apps.finances.report_import.service import find_cost_center, get_or_create_cost_center

        existing = CostCenter.objects.create(cost_center='991000')
        match = find_cost_center('0001/991000')
        self.assertEqual(match.pk, existing.pk)

        cc, created = get_or_create_cost_center('0001/991000')
        self.assertFalse(created)
        self.assertEqual(cc.pk, existing.pk)
        self.assertEqual(CostCenter.objects.filter(cost_center__contains='991000').count(), 1)

    def test_matches_prefixed_db_code_when_file_has_short(self):
        from apps.finances.report_import.service import find_cost_center

        existing = CostCenter.objects.create(cost_center='0001/991000')
        match = find_cost_center('991000')
        self.assertEqual(match.pk, existing.pk)

    def test_analyze_reuses_short_cost_center(self):
        CostCenter.objects.create(cost_center='991000')
        data = _build_sample_workbook()  # file uses 0001/991000
        upload = SimpleUploadedFile('sample.xlsx', data)
        plan = analyze_uploaded_files([upload], import_year=2026)
        parent = plan['parents'][0]
        self.assertTrue(parent['cost_center']['exists_in_db'])
        self.assertFalse(parent['cost_center']['will_create'])
        self.assertEqual(parent['cost_center']['matched_code'], '991000')
        self.assertEqual(parent['cost_center']['matched_via'], 'prefix_stripped')


class ReportImportServiceTests(TestCase):
    def test_normalize_import_scopes(self):
        defaults = normalize_import_scopes(None)
        self.assertTrue(defaults['psp'])
        self.assertTrue(defaults['personnel'])
        self.assertFalse(defaults['orders'])

        from_form = normalize_import_scopes({'scope_psp': 'on'})
        self.assertTrue(from_form['psp'])
        self.assertFalse(from_form['personnel'])

        personnel_only = normalize_import_scopes({'scope_personnel': 'on'})
        self.assertFalse(personnel_only['psp'])
        self.assertTrue(personnel_only['personnel'])

    def test_analyze_and_commit_create_flow(self):
        data = _build_sample_workbook()
        upload = SimpleUploadedFile(
            'sample.xlsx',
            data,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        plan = analyze_uploaded_files([upload], import_year=2026)
        self.assertEqual(len(plan['parents']), 1)
        self.assertTrue(plan['import_scopes']['psp'])
        parent = plan['parents'][0]
        self.assertEqual(parent['action'], 'create')
        self.assertTrue(parent['needs_title'])
        self.assertTrue(parent['year_plausibility_warning'])

        post = {
            'title__T-100.0001': 'Test Project Title',
            'confirm_import_year': 'on',
        }
        plan, errors = merge_user_decisions(plan, post)
        self.assertEqual(errors, [])
        summary = apply_import_plan(plan)
        self.assertEqual(summary['psp_created'], 1)

        wbs = WBSElement.objects.get(wbs_code='T-100.0001')
        self.assertEqual(wbs.title, 'Test Project Title')
        self.assertEqual(wbs.third_party_funder_identifier, 'DFG Parent Designation')
        self.assertFalse(wbs.subject_to_annual_recurrence)
        self.assertTrue(wbs.has_material_costs)
        self.assertTrue(wbs.has_personnel_costs)
        self.assertEqual(wbs.cost_center.cost_center, '991000')
        self.assertEqual(wbs.contact_person.last_name, 'Muster')

        # Non-annual: single lifetime plan (technical year = project start year 2026)
        self.assertEqual(wbs.year_estimates.count(), 1)
        ye = wbs.year_estimates.get()
        self.assertEqual(ye.year, 2026)
        self.assertEqual(ye.material_costs, Decimal('10000'))
        self.assertEqual(ye.personnel_costs, Decimal('50000'))

    def test_psp_scope_only_skips_personnel(self):
        data = _build_sample_workbook()
        upload = SimpleUploadedFile('sample.xlsx', data)
        plan = analyze_uploaded_files(
            [upload],
            import_year=2026,
            import_scopes={'psp': True, 'personnel': False},
        )
        self.assertEqual(plan['personnel_checks'], [])
        self.assertFalse(plan['requires_personnel_resolution'])
        plan, errors = merge_user_decisions(plan, {
            'title__T-100.0001': 'Only PSP',
            'confirm_import_year': 'on',
        })
        self.assertEqual(errors, [])
        summary = apply_import_plan(plan)
        self.assertEqual(summary['psp_created'], 1)
        self.assertEqual(summary['personnel_notes'], [])

    def test_personnel_scope_only_does_not_create_psp(self):
        data = _build_sample_workbook()
        upload = SimpleUploadedFile('sample.xlsx', data)
        plan = analyze_uploaded_files(
            [upload],
            import_year=2026,
            import_scopes={'psp': False, 'personnel': True},
        )
        self.assertFalse(plan['import_scopes']['psp'])
        self.assertFalse(plan['requires_year_confirmation'])
        # No title required when PSP scope off
        plan, errors = merge_user_decisions(plan, {})
        self.assertEqual(errors, [])
        summary = apply_import_plan(plan)
        self.assertEqual(summary['psp_created'], 0)
        self.assertFalse(WBSElement.objects.filter(wbs_code='T-100.0001').exists())

    def test_same_file_hash_blocks_already_imported_scopes(self):
        data = _build_sample_workbook()
        file_hash = sha256_bytes(data)
        record_data_import(
            kind=DataImportLog.Kind.THIRD_PARTY_FUNDING_REPORT,
            uploaded_by=None,
            original_filename='prev.xlsx',
            file_sha256=file_hash,
            file_size=len(data),
            report_created_on=date(2026, 1, 15),
            status=DataImportLog.Status.COMPLETED,
            summary='scopes=psp,personnel; test prior full import',
        )
        already, remaining, requested = remaining_scopes_for_hash(
            DataImportLog.Kind.THIRD_PARTY_FUNDING_REPORT,
            file_hash,
            {'psp': True, 'personnel': True},
        )
        self.assertEqual(already, {'psp', 'personnel'})
        self.assertEqual(remaining, set())

        upload = SimpleUploadedFile('sample.xlsx', data)
        plan = analyze_uploaded_files([upload], import_year=2026)
        self.assertTrue(plan['has_duplicate_files'])
        self.assertTrue(plan['upload_meta'][0]['is_duplicate'])

    def test_partial_scope_reimport_allowed_for_same_hash(self):
        data = _build_sample_workbook()
        file_hash = sha256_bytes(data)
        record_data_import(
            kind=DataImportLog.Kind.THIRD_PARTY_FUNDING_REPORT,
            uploaded_by=None,
            original_filename='prev.xlsx',
            file_sha256=file_hash,
            file_size=len(data),
            report_created_on=date(2026, 1, 15),
            status=DataImportLog.Status.COMPLETED,
            summary='scopes=psp; only psp before',
        )
        upload = SimpleUploadedFile('sample.xlsx', data)
        plan = analyze_uploaded_files(
            [upload],
            import_year=2026,
            import_scopes={'psp': True, 'personnel': True},
        )
        self.assertFalse(plan['has_duplicate_files'])
        self.assertEqual(plan['upload_meta'][0]['scopes_already_imported'], ['psp'])
        self.assertIn('personnel', plan['upload_meta'][0]['scopes_remaining'])

    def test_older_report_creation_date_is_blocked(self):
        record_data_import(
            kind=DataImportLog.Kind.THIRD_PARTY_FUNDING_REPORT,
            uploaded_by=None,
            original_filename='newer.xlsx',
            file_sha256='a' * 64,
            report_created_on=date(2026, 6, 1),
            status=DataImportLog.Status.COMPLETED,
            summary='scopes=psp,personnel; psp_codes=T-100.0001',
        )
        is_older, upload_date, prior, prior_date = is_report_older_than_last_import(
            DataImportLog.Kind.THIRD_PARTY_FUNDING_REPORT,
            report_created_on=date(2026, 3, 1),
            psp_codes={'T-100.0001'},
        )
        self.assertTrue(is_older)
        self.assertEqual(upload_date, date(2026, 3, 1))
        self.assertEqual(prior_date, date(2026, 6, 1))

        is_ok, _, _, _ = is_report_older_than_last_import(
            DataImportLog.Kind.THIRD_PARTY_FUNDING_REPORT,
            report_created_on=date(2026, 6, 1),
            psp_codes={'T-100.0001'},
        )
        self.assertFalse(is_ok)

        is_newer, _, _, _ = is_report_older_than_last_import(
            DataImportLog.Kind.THIRD_PARTY_FUNDING_REPORT,
            report_created_on=date(2026, 7, 1),
            psp_codes={'T-100.0001'},
        )
        self.assertFalse(is_newer)

    def test_older_report_for_other_psp_is_allowed(self):
        record_data_import(
            kind=DataImportLog.Kind.THIRD_PARTY_FUNDING_REPORT,
            uploaded_by=None,
            original_filename='psp-x.xlsx',
            file_sha256='b' * 64,
            report_created_on=date(2026, 1, 1),
            status=DataImportLog.Status.COMPLETED,
            summary='scopes=psp,personnel; psp_codes=T-X.0001',
        )
        is_older, _, _, _ = is_report_older_than_last_import(
            DataImportLog.Kind.THIRD_PARTY_FUNDING_REPORT,
            report_created_on=date(2025, 12, 1),
            psp_codes={'T-Y.0001'},
        )
        self.assertFalse(is_older)
        is_same_psp_older, _, _, prior_date = is_report_older_than_last_import(
            DataImportLog.Kind.THIRD_PARTY_FUNDING_REPORT,
            report_created_on=date(2025, 12, 1),
            psp_codes={'T-X.0001'},
        )
        self.assertTrue(is_same_psp_older)
        self.assertEqual(prior_date, date(2026, 1, 1))

    def test_lifetime_plan_overwrites_single_row_not_import_year_key(self):
        """Re-import updates the one lifetime row even if technical year ≠ import year."""
        cc = CostCenter.objects.create(cost_center='0001/991000')
        wbs = WBSElement.objects.create(
            wbs_code='T-100.0001',
            title='Existing',
            cost_center=cc,
            period_start=date(2025, 1, 1),
            period_end=date(2028, 12, 31),
            subject_to_annual_recurrence=False,
            has_material_costs=True,
        )
        WBSElementYearEstimate.objects.create(
            wbs_element=wbs,
            year=2025,
            material_costs=Decimal('1.00'),
            personnel_costs=Decimal('2.00'),
        )
        data = _build_sample_workbook()
        upload = SimpleUploadedFile('sample.xlsx', data)
        plan = analyze_uploaded_files([upload], import_year=2026)
        plan, errors = merge_user_decisions(plan, {
            'confirm_import_year': 'on',
            'update_existing_snapshots': 'on',
        })
        self.assertEqual(errors, [])
        apply_import_plan(plan)
        self.assertEqual(wbs.year_estimates.count(), 1)
        ye = wbs.year_estimates.get()
        self.assertEqual(ye.year, 2025)  # existing technical key kept
        self.assertEqual(ye.material_costs, Decimal('10000'))
        self.assertEqual(ye.personnel_costs, Decimal('50000'))

        true = WBSElementTrueYearlySpending.objects.get(
            wbs_element=wbs, date_of_update=date.today()
        )
        self.assertEqual(true.material_costs, Decimal('1200'))
        self.assertEqual(true.personnel_costs, Decimal('13000'))

        obligo = WBSElementObligo.objects.get(
            wbs_element=wbs, date_of_update=date.today()
        )
        self.assertEqual(obligo.material_costs, Decimal('200'))
        self.assertEqual(obligo.personal, Decimal('8000'))

    def test_snapshot_conflict_requires_update_flag(self):
        CostCenter.objects.create(cost_center='0001/991000')
        wbs = WBSElement.objects.create(
            wbs_code='T-100.0001',
            title='Existing',
            cost_center=CostCenter.objects.get(cost_center='0001/991000'),
        )
        WBSElementTrueYearlySpending.objects.create(
            wbs_element=wbs,
            date_of_update=date.today(),
            material_costs=1,
        )
        data = _build_sample_workbook()
        upload = SimpleUploadedFile('sample.xlsx', data)
        plan = analyze_uploaded_files([upload], import_year=2026)
        self.assertTrue(plan['requires_snapshot_update_option'])
        plan, errors = merge_user_decisions(plan, {'confirm_import_year': 'on'})
        self.assertTrue(errors)
        plan, errors = merge_user_decisions(plan, {
            'confirm_import_year': 'on',
            'update_existing_snapshots': 'on',
        })
        self.assertEqual(errors, [])
        apply_import_plan(plan)
        true = WBSElementTrueYearlySpending.objects.get(
            wbs_element=wbs, date_of_update=date.today()
        )
        self.assertEqual(true.material_costs, Decimal('1200'))


class ReportImportViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        assign_permissions_to_groups()

    def setUp(self):
        self.user = CustomUser.objects.create_user('importer', password='test')
        self.user.password_changed = True
        self.user.save(update_fields=['password_changed'])
        perm = Permission.objects.filter(
            codename='import_third_party_funding_report'
        ).first()
        if perm:
            self.user.user_permissions.add(perm)
        self.client = Client()
        self.client.login(username='importer', password='test')

    def test_upload_page_requires_permission(self):
        other = CustomUser.objects.create_user('nope', password='test')
        other.password_changed = True
        other.save(update_fields=['password_changed'])
        c = Client()
        c.login(username='nope', password='test')
        response = c.get('/finances/import/third-party-funding/')
        self.assertEqual(response.status_code, 403)

    def test_upload_page_ok_for_permission(self):
        response = self.client.get('/finances/import/third-party-funding/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Reference year')


def _write_budget_header(ws, row: int):
    ws.cell(row, 2, 'Projekt')
    ws.cell(row, 3, 'PSP Bezeichnung')
    ws.cell(row, 5, 'Freigegebenes Budget')
    ws.cell(row, 6, 'Ist-Kosten')
    ws.cell(row, 8, 'Obligo')
    ws.cell(row, 9, 'Personalobligo')
    ws.cell(row, 10, 'Restaufplan')
    ws.cell(row, 11, 'Verfügt')
    ws.cell(row, 12, 'Verfügbar')


def _build_gesamtbericht_workbook() -> bytes:
    """Two parents: one with .1/.2 children, one parent-only with placeholder CC."""
    wb = Workbook()
    ws = wb.active
    ws.title = 'Übersicht'
    ws['B2'] = 'Projekt'
    ws['C2'] = 'Kostenstelle'
    ws['D2'] = 'Text'
    ws['G2'] = 'Projektdefinition'
    ws['J2'] = 'Projektende'
    ws['K2'] = 'Projektleitung'

    ws['B3'] = 'G-100.0001'
    ws['C3'] = '0001/991000'
    ws['D3'] = 'Gesamt Parent One'
    ws['G3'] = 'DFG-ABC'
    ws['J3'] = date(2028, 12, 31)
    ws['B4'] = 'G-100.0001.1'
    ws['C4'] = '0001/991000'
    ws['D4'] = 'Sachaufwendungen'
    ws['G4'] = 'DFG-ABC'
    ws['J4'] = date(2028, 12, 31)
    ws['B5'] = 'G-100.0001.2'
    ws['C5'] = '0001/991000'
    ws['D5'] = 'Personalaufwendungen'
    ws['G5'] = 'DFG-ABC'
    ws['J5'] = date(2028, 12, 31)

    ws['B6'] = 'G-200.0002'
    ws['C6'] = '0001/#'
    ws['D6'] = 'Parent Only Title'
    ws['G6'] = 'Other Funder'
    ws['J6'] = '#'

    _write_budget_header(ws, 8)
    ws['B9'] = 'G-100.0001'
    ws['C9'] = 'Gesamt Parent One'
    ws['E9'] = 0
    ws['F9'] = 0
    ws['H9'] = 0
    ws['I9'] = 0
    ws['K9'] = 0
    ws['B10'] = 'G-100.0001.1'
    ws['C10'] = 'Sachaufwendungen'
    ws['E10'] = 10000
    ws['F10'] = 1000
    ws['H10'] = 200
    ws['I10'] = 0
    ws['K10'] = 1200
    ws['B11'] = 'G-100.0001.2'
    ws['C11'] = 'Personalaufwendungen'
    ws['E11'] = 50000
    ws['F11'] = 5000
    ws['H11'] = 0
    ws['I11'] = 8000
    ws['K11'] = 13000
    ws['E12'] = 60000
    ws['F12'] = 6000
    ws['H12'] = 200
    ws['I12'] = 8000
    ws['K12'] = 14200

    _write_budget_header(ws, 14)
    ws['B15'] = 'G-200.0002'
    ws['C15'] = 'Parent Only Title'
    ws['E15'] = 99999
    ws['F15'] = 1
    ws['H15'] = 2
    ws['I15'] = 3
    ws['K15'] = 4
    ws['E16'] = 99999
    ws['F16'] = 1
    ws['H16'] = 2
    ws['I16'] = 3
    ws['K16'] = 4

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


class GesamtberichtParserTests(TestCase):
    def test_filename_date(self):
        self.assertEqual(
            report_date_from_filename('Drittmittelbericht Gesamtbericht070926.xlsx'),
            date(2026, 9, 7),
        )

    def test_detects_gesamtbericht_by_filename_and_headers(self):
        data = _build_gesamtbericht_workbook()
        by_name = detect_and_parse(data, 'Drittmittelbericht Gesamtbericht070926.xlsx')
        self.assertEqual(by_name.report_kind, 'psp_gesamtbericht')
        self.assertFalse(by_name.errors)

        by_header = detect_and_parse(data, 'summary.xlsx')
        self.assertEqual(by_header.report_kind, 'psp_gesamtbericht')

        einzel = detect_and_parse(_build_sample_workbook(), 'sample.xlsx')
        self.assertEqual(einzel.report_kind, 'psp_uebersicht')
        self.assertEqual(len(einzel.parents), 1)

    def test_parses_parents_children_and_skips_parent_totals(self):
        data = _build_gesamtbericht_workbook()
        result = GesamtberichtPspParser().parse(
            data, 'Drittmittelbericht Gesamtbericht070926.xlsx'
        )
        self.assertFalse(result.errors)
        self.assertEqual(len(result.parents), 2)
        by_code = {p.wbs_code: p for p in result.parents}

        one = by_code['G-100.0001']
        self.assertEqual(one.title, 'DFG-ABC')
        self.assertEqual(one.third_party_funder_identifier, '')
        self.assertEqual(one.cost_center_code, '0001/991000')
        self.assertFalse(one.cost_center_is_placeholder)
        self.assertEqual(one.period_end, date(2028, 12, 31))
        self.assertEqual(one.report_created_on, date(2026, 9, 7))
        self.assertEqual(one.cost_types['1'].approved_budget, Decimal('10000'))
        self.assertEqual(one.cost_types['1'].verfuegt, Decimal('1200'))
        self.assertEqual(one.cost_types['1'].obligo, Decimal('200'))
        self.assertEqual(one.cost_types['2'].personal_obligo, Decimal('8000'))
        self.assertNotIn('parent_total', one.cost_types)

        two = by_code['G-200.0002']
        self.assertEqual(two.title, 'Other Funder')
        self.assertEqual(two.third_party_funder_identifier, '')
        self.assertTrue(two.cost_center_is_placeholder)
        self.assertIsNone(two.period_end)
        self.assertEqual(two.cost_types, {})


class GesamtberichtImportServiceTests(TestCase):
    def test_create_uses_title_from_file_without_post(self):
        data = _build_gesamtbericht_workbook()
        upload = SimpleUploadedFile(
            'Drittmittelbericht Gesamtbericht070926.xlsx', data
        )
        plan = analyze_uploaded_files(
            [upload],
            import_year=2026,
            import_scopes={'psp': True, 'personnel': False},
        )
        self.assertEqual(len(plan['parents']), 2)
        one = next(p for p in plan['parents'] if p['wbs_code'] == 'G-100.0001')
        self.assertEqual(one['action'], 'create')
        self.assertFalse(one['needs_title'])
        self.assertEqual(one['proposed_title'], 'DFG-ABC')
        self.assertTrue(one['fill_empty_only'])
        self.assertTrue(one['has_financials'])
        two = next(p for p in plan['parents'] if p['wbs_code'] == 'G-200.0002')
        self.assertFalse(two['has_financials'])
        self.assertFalse(two['cost_center']['needs_user_choice'])

        plan, errors = merge_user_decisions(plan, {})
        self.assertEqual(errors, [])
        summary = apply_import_plan(plan)
        self.assertEqual(summary['psp_created'], 2)

        wbs = WBSElement.objects.get(wbs_code='G-100.0001')
        self.assertEqual(wbs.title, 'DFG-ABC')
        self.assertEqual(wbs.third_party_funder_identifier, '')
        self.assertEqual(wbs.cost_center.cost_center, '991000')
        self.assertTrue(wbs.has_material_costs)
        self.assertTrue(wbs.has_personnel_costs)
        self.assertEqual(wbs.year_estimates.get().material_costs, Decimal('10000'))
        true = WBSElementTrueYearlySpending.objects.get(wbs_element=wbs)
        self.assertEqual(true.material_costs, Decimal('1200'))

        stub = WBSElement.objects.get(wbs_code='G-200.0002')
        self.assertEqual(stub.title, 'Other Funder')
        self.assertIsNone(stub.cost_center)
        self.assertFalse(stub.year_estimates.exists())
        self.assertFalse(
            WBSElementTrueYearlySpending.objects.filter(wbs_element=stub).exists()
        )

    def test_update_fills_empty_master_data_only(self):
        cc_old = CostCenter.objects.create(cost_center='888888')
        rich = WBSElement.objects.create(
            wbs_code='G-100.0001',
            title='Rich Title',
            cost_center=cc_old,
            third_party_funder_identifier='RICH-FUNDER',
            period_end=date(2030, 1, 1),
            subject_to_annual_recurrence=True,
        )
        empty = WBSElement.objects.create(
            wbs_code='G-200.0002',
            title='Keep Empty Title',
        )
        data = _build_gesamtbericht_workbook()
        upload = SimpleUploadedFile(
            'Drittmittelbericht Gesamtbericht070926.xlsx', data
        )
        plan = analyze_uploaded_files(
            [upload],
            import_year=2026,
            import_scopes={'psp': True, 'personnel': False},
        )
        rich_plan = next(p for p in plan['parents'] if p['wbs_code'] == 'G-100.0001')
        self.assertEqual(rich_plan['action'], 'update')
        self.assertFalse(rich_plan['needs_title'])
        self.assertEqual(rich_plan['field_diffs'], [])

        empty_plan = next(p for p in plan['parents'] if p['wbs_code'] == 'G-200.0002')
        diff_fields = {d['field'] for d in empty_plan['field_diffs']}
        self.assertNotIn('third_party_funder_identifier', diff_fields)

        plan, errors = merge_user_decisions(plan, {})
        self.assertEqual(errors, [])
        apply_import_plan(plan)

        rich.refresh_from_db()
        self.assertEqual(rich.title, 'Rich Title')
        self.assertEqual(rich.third_party_funder_identifier, 'RICH-FUNDER')
        self.assertEqual(rich.period_end, date(2030, 1, 1))
        self.assertEqual(rich.cost_center_id, cc_old.pk)
        self.assertTrue(rich.subject_to_annual_recurrence)
        self.assertTrue(rich.has_material_costs)
        self.assertTrue(rich.has_personnel_costs)

        empty.refresh_from_db()
        self.assertEqual(empty.title, 'Keep Empty Title')
        self.assertEqual(empty.third_party_funder_identifier, '')
        self.assertIsNone(empty.period_end)
        self.assertIsNone(empty.cost_center)

    def test_past_projektende_sets_inactive(self):
        wb = Workbook()
        ws = wb.active
        ws.title = 'Übersicht'
        ws['B2'] = 'Projekt'
        ws['C2'] = 'Kostenstelle'
        ws['D2'] = 'Text'
        ws['G2'] = 'Projektdefinition'
        ws['J2'] = 'Projektende'
        ws['B3'] = 'G-300.0003'
        ws['C3'] = '0001/991000'
        ws['D3'] = 'Ended Project'
        ws['G3'] = 'Funder X'
        ws['J3'] = date(2020, 6, 1)
        buf = BytesIO()
        wb.save(buf)
        data = buf.getvalue()

        upload = SimpleUploadedFile('Gesamtbericht010120.xlsx', data)
        plan = analyze_uploaded_files(
            [upload],
            import_year=2026,
            import_scopes={'psp': True, 'personnel': False},
        )
        parent = plan['parents'][0]
        self.assertTrue(parent['will_set_inactive'])
        plan, errors = merge_user_decisions(plan, {})
        self.assertEqual(errors, [])
        apply_import_plan(plan)
        wbs = WBSElement.objects.get(wbs_code='G-300.0003')
        self.assertTrue(wbs.is_inactive)
        self.assertEqual(wbs.period_end, date(2020, 6, 1))

        # Existing future end is kept (fill-empty) → stay active
        rich = WBSElement.objects.create(
            wbs_code='G-300.0004',
            title='Still running',
            period_end=date(2030, 1, 1),
        )
        wb2 = Workbook()
        ws2 = wb2.active
        ws2.title = 'Übersicht'
        ws2['B2'] = 'Projekt'
        ws2['C2'] = 'Kostenstelle'
        ws2['D2'] = 'Text'
        ws2['G2'] = 'Projektdefinition'
        ws2['J2'] = 'Projektende'
        ws2['B3'] = 'G-300.0004'
        ws2['C3'] = '0001/991000'
        ws2['D3'] = 'Ended in file'
        ws2['G3'] = 'Funder X'
        ws2['J3'] = date(2020, 1, 1)
        buf2 = BytesIO()
        wb2.save(buf2)
        upload2 = SimpleUploadedFile('Gesamtbericht010121.xlsx', buf2.getvalue())
        plan2 = analyze_uploaded_files(
            [upload2],
            import_year=2026,
            import_scopes={'psp': True, 'personnel': False},
        )
        rich_plan = plan2['parents'][0]
        self.assertFalse(rich_plan['will_set_inactive'])
        plan2, errors = merge_user_decisions(plan2, {})
        self.assertEqual(errors, [])
        apply_import_plan(plan2)
        rich.refresh_from_db()
        self.assertEqual(rich.period_end, date(2030, 1, 1))
        self.assertFalse(rich.is_inactive)

        # Existing past end, still active → inactivate
        old = WBSElement.objects.create(
            wbs_code='G-300.0005',
            title='Already ended',
            period_end=date(2019, 12, 31),
            is_inactive=False,
        )
        wb3 = Workbook()
        ws3 = wb3.active
        ws3.title = 'Übersicht'
        ws3['B2'] = 'Projekt'
        ws3['C2'] = 'Kostenstelle'
        ws3['D2'] = 'Text'
        ws3['G2'] = 'Projektdefinition'
        ws3['J2'] = 'Projektende'
        ws3['B3'] = 'G-300.0005'
        ws3['C3'] = '0001/991000'
        ws3['D3'] = 'Already ended'
        ws3['G3'] = 'Funder X'
        ws3['J3'] = date(2019, 12, 31)
        buf3 = BytesIO()
        wb3.save(buf3)
        upload3 = SimpleUploadedFile('Gesamtbericht010122.xlsx', buf3.getvalue())
        plan3 = analyze_uploaded_files(
            [upload3],
            import_year=2026,
            import_scopes={'psp': True, 'personnel': False},
        )
        self.assertTrue(plan3['parents'][0]['will_set_inactive'])
        plan3, errors = merge_user_decisions(plan3, {})
        self.assertEqual(errors, [])
        apply_import_plan(plan3)
        old.refresh_from_db()
        self.assertTrue(old.is_inactive)
