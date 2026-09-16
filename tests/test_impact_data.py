import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from impact_data import prepare_snapshot, merge_impact
from build_data import build
from test_build import ad, lead
from test_impact_attribution import action


class ImpactDataTests(unittest.TestCase):
    def snapshot(self):
        trial = action(date='2026-09-17 12:00:00')
        sale = action(ident='sale-1', date='2026-09-20 12:00:00')
        sale['Event Type'] = 'Paid Trial'
        return prepare_snapshot([trial, sale], [lead()], [ad()])

    def test_later_conversions_keep_lead_origin_and_own_event_date(self):
        result = self.snapshot()
        self.assertEqual(sum(r['freeTrials'] for r in result['records'] if r['date'] == '2026-09-17'), 1)
        self.assertEqual(sum(r['sales'] for r in result['records'] if r['date'] == '2026-09-20'), 1)
        cohort = next(r for r in result['records'] if r['cohortContacts'])
        self.assertEqual(cohort['date'], '2026-09-16')
        self.assertEqual((cohort['trialContacts'], cohort['trialSalesContacts']), (1, 1))
        self.assertEqual(cohort['ad'], '33333333333333')

    def test_multiple_actions_do_not_inflate_contact_conversion_rates(self):
        rows = [action(ident='trial-1'), action(ident='trial-2')]
        result = prepare_snapshot(rows, [lead(), lead()], [ad()])
        self.assertEqual(sum(r['freeTrials'] for r in result['records']), 2)
        self.assertEqual(sum(r['trialContacts'] for r in result['records']), 1)
        self.assertEqual(sum(r['cohortContacts'] for r in result['records']), 1)

    def test_prior_events_count_but_do_not_enter_cohort_rates(self):
        rows = [action(ident='old', date='2026-09-15 12:00:00'), action(ident='new', date='2026-09-18 12:00:00')]
        rows[1]['Event Type'] = 'Paid Trial'
        result = prepare_snapshot(rows, [lead()], [ad()])
        self.assertEqual(sum(r['freeTrials'] for r in result['records']), 1)
        self.assertEqual(sum(r['dateIssues'] for r in result['records']), 1)
        self.assertEqual(sum(r['trialContacts'] for r in result['records']), 0)
        self.assertEqual(sum(r['trialSalesContacts'] for r in result['records']), 0)

    def test_sale_before_trial_not_counted_as_progression(self):
        rows = [action(ident='trial', date='2026-09-19 12:00:00'), action(ident='sale', date='2026-09-18 12:00:00')]
        rows[1]['Event Type'] = 'Paid Trial'
        result = prepare_snapshot(rows, [lead()], [ad()])
        self.assertEqual(sum(r['trialSalesContacts'] for r in result['records']), 0)

    def test_public_merge_preserves_media_totals_and_strips_extra_fields(self):
        snapshot = self.snapshot()
        snapshot['private'] = 'private@example.test'
        snapshot['records'][0]['email'] = 'hidden@example.test'
        result = merge_impact(build([ad()], [lead()]), snapshot)
        self.assertEqual(result['schema'], 2)
        self.assertEqual(sum(r['spend'] for r in result['records']), 10.5)
        self.assertEqual(sum(r['leads'] for r in result['records']), 1)
        self.assertEqual(sum(r['sales'] for r in result['records']), 1)
        self.assertNotIn('@', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
