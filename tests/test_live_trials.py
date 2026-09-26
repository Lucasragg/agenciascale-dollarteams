import csv
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from live_trials import normalize_actions, prepare_live_snapshot, fetch_actions, FIELDS
from build_data import build, fetch_source, REQUIRED
from impact_data import merge_impact
from test_build import lead, ad
from test_impact_attribution import action

def trial(ident='trial-1', email='never-publish@example.test', date='2026-09-17 12:00:00', event='Free Trial', status='Pending'):
    return {**action(email, ident, date), 'Brand':'Shopify', 'Event Type':event, 'Status':status}

class LiveTrialsTests(unittest.TestCase):
    def test_duplicate_across_tabs_is_counted_once(self):
        rows, tabs, audit=normalize_actions({'Impact':[trial(),trial()], 'Recuperacao':[trial(),trial('paid',event='Paid Trial')]})
        self.assertEqual(len(rows),2)
        self.assertEqual(audit['duplicatesRemoved'],2)

    def test_colliding_sheet_ids_keep_distinct_people_and_events(self):
        rows, _, audit=normalize_actions({'Impact':[trial(),trial(email='other@example.test')], 'Recuperacao':[trial(event='Paid Trial')]})
        self.assertEqual(len(rows),3)
        self.assertEqual(audit['collidingIds'],1)
        self.assertEqual(len({r['Action Id'] for r in rows}),3)

    def test_two_actions_same_contact_are_not_deduplicated(self):
        rows, _, _=normalize_actions({'Impact':[trial()], 'Recuperacao':[trial('another-id')]})
        self.assertEqual(len(rows),2)

    def test_recovery_trial_and_impact_sale_join_same_email_cohort(self):
        sources={'Impact':[trial('paid',date='2026-09-20 12:00:00',event='Paid Trial',status='Approved')],
                 'Recuperacao':[trial(email=' NEVER-PUBLISH@example.test ')]}
        snapshot=prepare_live_snapshot(sources,[lead()],[ad()])
        result=merge_impact(build([ad()],[lead()]),snapshot)
        self.assertEqual(sum(r['freeTrials'] for r in result['records']),1)
        self.assertEqual(sum(r['sales'] for r in result['records']),1)
        # The sale after the common coverage is counted as an action, but it
        # does not advance the cohort before the other source catches up.
        self.assertEqual(sum(r['trialSalesContacts'] for r in result['records']),0)
        self.assertEqual(result['impact']['eventTotals']['paidTrials']['mediaCandidates'],1)
        self.assertEqual(result['audit']['totals']['leads'],1)
        self.assertEqual(result['impact']['completeEnd'],'2026-09-17')
        self.assertEqual(result['impact']['end'],'2026-09-20')
        self.assertNotIn('never-publish',json.dumps(result).lower())
        self.assertNotIn('Sub Id',json.dumps(result))
        self.assertNotIn('Action Id',json.dumps(result))

    def test_non_trial_events_and_rejected_actions_excluded(self):
        other=[trial('retained',event='Retained Full Price Shops: 3 Mo'),trial('full',event='Full Price Shop'),trial('declined',status='Declined')]
        rows, _, audit=normalize_actions({'Impact':[trial()]+other, 'Recuperacao':[trial('paid',event='Paid Trial')]})
        self.assertEqual(len(rows),2)
        self.assertEqual(audit['otherEventsExcluded'],2)
        self.assertEqual(audit['statusesExcluded'],1)

    def test_cross_source_cohort_progression_with_common_coverage(self):
        sources={'Impact':[trial('paid',date='2026-09-20 12:00:00',event='Paid Trial')],
                 'Recuperacao':[trial(),trial('coverage',email='other@example.test',date='2026-09-20 16:00:00')]}
        snapshot=prepare_live_snapshot(sources,[lead()],[ad()])
        self.assertEqual(sum(r['trialSalesContacts'] for r in snapshot['records']),1)
        self.assertEqual(sum(r['cohortContacts'] for r in snapshot['records']),1)

    def test_future_registration_is_not_counted_as_progression(self):
        sources={'Impact':[trial(date='2026-09-15 12:00:00')], 'Recuperacao':[trial('paid',event='Paid Trial')]}
        snapshot=prepare_live_snapshot(sources,[lead()],[ad()])
        self.assertEqual(sum(r['dateIssues'] for r in snapshot['records']),1)
        self.assertEqual(sum(r['trialContacts'] for r in snapshot['records']),0)

    def test_conflicting_status_fails_closed(self):
        for status in ('Approved','Reversed'):
            with self.assertRaisesRegex(ValueError,'Conflicting status'):
                normalize_actions({'Impact':[trial()], 'Recuperacao':[trial(status=status)]})

    def test_missing_and_ambiguous_emails_not_assigned(self):
        other=lead(c='44444444444444',s='55555555555555',a='66666666666666')
        snapshot=prepare_live_snapshot({'Impact':[trial()], 'Recuperacao':[trial('unmatched',email=''),trial('alias',email='never-publish+alias@example.test')]},
                                       [lead(),other],[ad(),ad(c='44444444444444',s='55555555555555',a='66666666666666')])
        self.assertEqual(snapshot['eventTotals']['freeTrials']['ambiguousOrigin'],1)
        self.assertEqual(snapshot['eventTotals']['freeTrials']['noEmailMatch'],2)
        self.assertEqual(snapshot['eventTotals']['freeTrials']['mediaCandidates'],0)

    def test_duplicate_registrations_do_not_inflate_cohort(self):
        snapshot=prepare_live_snapshot({'Impact':[trial()], 'Recuperacao':[trial('paid',event='Paid Trial')]},[lead(),lead()],[ad()])
        self.assertEqual(sum(r['cohortContacts'] for r in snapshot['records']),1)
        self.assertEqual(sum(r['trialContacts'] for r in snapshot['records']),1)

    def test_invalid_or_empty_sources_fail(self):
        for sources in ({'Impact':[trial()]},{'Impact':[trial()],'Recuperacao':[]}, {'Impact':[trial()],'Recuperacao':[trial(status='Mystery')]}, {'Impact':[trial()],'Recuperacao':[trial(ident='')]}):
            with self.assertRaises(ValueError):normalize_actions(sources)

    def test_fetch_retains_only_needed_action_columns(self):
        stream=io.StringIO();fields=list(FIELDS)+['PRIVATE extra']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerow({**trial(),'PRIVATE extra':'DO-NOT-PUBLISH'})
        with patch('live_trials.urllib.request.urlopen',return_value=io.BytesIO(stream.getvalue().encode())):
            rows=fetch_actions('Impact')
        self.assertNotIn('PRIVATE extra',rows[0])

    def test_email_enabled_read_uses_one_lead_snapshot(self):
        stream=io.StringIO();fields=REQUIRED['leads']+['Email','IP']
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerow({**lead(),'IP':'private-ip'})
        with patch('build_data.urllib.request.urlopen',return_value=io.BytesIO(stream.getvalue().encode())) as request:
            rows=fetch_source('leads',include_email=True)
        self.assertIn('E%3AAG',request.call_args.args[0].full_url)
        self.assertEqual(rows[0]['Email'],lead()['Email'])
        self.assertNotIn('IP',rows[0])
        self.assertNotIn('never-publish',json.dumps(build([ad()],rows)).lower())

if __name__=='__main__':unittest.main()
