import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_impact_attribution import audit
from test_build import ad, lead


def action(email='never-publish@example.test', ident='action-1', date='2026-09-17 12:00:00'):
    return {'Action Id': ident, 'Action Date': date, 'Event Type': 'Free Trial', 'Status': 'Pending', 'Sub Id 3': email}


class ImpactAttributionTests(unittest.TestCase):
    def test_normalization_and_private_fields_not_exported(self):
        result = audit([action(' NEVER-PUBLISH@example.test ')], [lead()], [ad()])
        self.assertEqual(result['events']['Free Trial']['mediaCandidates'], 1)
        self.assertEqual(result['records'][0]['ad'], '33333333333333')
        self.assertNotIn('never-publish', json.dumps(result).lower())
        self.assertNotIn('action-1', json.dumps(result))
        self.assertTrue(result['records'][0]['provisional'])

    def test_duplicate_registrations_do_not_duplicate_actions(self):
        result = audit([action()], [lead(), lead()], [ad()])
        self.assertEqual(sum(row['actions'] for row in result['records']), 1)
        self.assertEqual(result['events']['Free Trial']['multipleRegistrations'], 1)

    def test_different_origins_remain_unassigned(self):
        other = lead(c='44444444444444', s='55555555555555', a='66666666666666')
        result = audit([action()], [lead(), other], [ad(), ad(c='44444444444444', s='55555555555555', a='66666666666666')])
        self.assertEqual(result['records'][0]['attribution'], 'ambiguous_origin')
        self.assertEqual(result['records'][0]['campaign'], '')

    def test_future_registration_is_flagged_and_never_validated(self):
        result = audit([action(date='2026-09-14 12:00:00')], [lead()], [ad()])
        self.assertEqual(result['records'][0]['registration_date_relation'], 'registration_later_date')
        self.assertTrue(result['provisional'])
        self.assertEqual(result['events']['Free Trial']['eventOver24HoursBeforeRegistrationNaive'], 1)

    def test_email_alias_is_not_merged(self):
        result = audit([action('never-publish+other@example.test')], [lead()], [ad()])
        self.assertEqual(result['events']['Free Trial']['noEmailMatch'], 1)

    def test_duplicate_actions_fail_instead_of_double_counting(self):
        with self.assertRaises(ValueError):
            audit([action(), action()], [lead()], [ad()])


if __name__ == '__main__':
    unittest.main()
