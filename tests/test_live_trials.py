import csv
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from live_trials import normalize_actions, prepare_live_snapshot, fetch_actions, FIELDS, commission_cents
from build_data import build, fetch_source, REQUIRED
from impact_data import merge_impact
from test_build import lead, ad
from test_impact_attribution import action

def trial(ident='trial-1', email='never-publish@example.test', date='2026-09-17 12:00:00', event='Free Trial', status='Pending'):
    return {**action(email, ident, date), 'Brand':'Shopify', 'Event Type':event, 'Status':status,'Action Earnings':'0'}

class LiveTrialsTests(unittest.TestCase):
    def test_acquisition_moves_cross_month_trials_and_revenue_but_preserves_events(self):
        registration={**lead(),'Registration date':'Mon, 31 Aug 2026, 10:00 AM'}
        free=trial(date='2026-09-02 12:00:00')
        paid={**trial('paid',event='Paid Trial',date='2026-09-20 12:00:00'),'Action Earnings':'1450000'}
        snapshot=prepare_live_snapshot({'Impact':[paid],'Recuperacao':[free]},[registration],[ad()])
        data=merge_impact(build([ad()],[registration]),snapshot)
        acquired=[r for r in data['acquisitionRecords'] if r['date']=='2026-08-31']
        self.assertEqual(sum(r['sales'] for r in acquired),1)
        self.assertEqual(sum(r['freeTrials'] for r in acquired),1)
        self.assertEqual(sum(r['revenueCents'] for r in acquired),14500)
        self.assertEqual(sum(r['trialSalesContacts'] for r in acquired),1)
        self.assertEqual(sum(r['sales'] for r in data['records'] if r['date']=='2026-09-20'),1)
        self.assertEqual(sum(r['sales'] for r in data['acquisitionRecords'] if r['date']=='2026-09-20'),0)
        self.assertEqual(sum(r['spend'] for r in data['acquisitionRecords']),sum(r['spend'] for r in data['records']))
        self.assertEqual(sum(r['leads'] for r in data['acquisitionRecords']),1)
        self.assertNotIn('never-publish',json.dumps(data))

    def test_acquisition_excludes_unknown_and_prior_events_without_inventing_dates(self):
        prior={**trial('prior',date='2026-09-15 12:00:00',event='Paid Trial'),'Action Earnings':'1450000'}
        unknown={**trial('unknown',email='missing@example.test',event='Paid Trial'),'Action Earnings':'950000'}
        snapshot=prepare_live_snapshot({'Impact':[prior],'Recuperacao':[unknown,trial()]},[lead()],[ad()])
        a=snapshot['acquisition']
        self.assertEqual(a['totals']['sales'],0)
        self.assertEqual(a['excluded']['beforeRegistration'],{'freeTrials':0,'sales':1,'revenueCents':14500})
        self.assertEqual(a['excluded']['noEmailMatch'],{'freeTrials':0,'sales':1,'revenueCents':9500})
        self.assertEqual(sum(r['sales'] for r in snapshot['records']),2)

    def test_acquisition_uses_first_registration_and_deduplicates_contacts_not_actions(self):
        first={**lead(),'Registration date':'Tue, 15 Sep 2026, 10:00 AM'}
        paid={**trial('paid',event='Paid Trial'),'Action Earnings':'1450000'}
        snapshot=prepare_live_snapshot({'Impact':[trial(),paid],'Recuperacao':[paid,trial('free-2')]},[lead(),first],[ad()])
        a=snapshot['acquisition']['totals']
        self.assertEqual((a['cohortContacts'],a['trialContacts'],a['trialSalesContacts']),(1,1,1))
        self.assertEqual((a['freeTrials'],a['sales'],a['revenueCents']),(2,1,14500))
        self.assertTrue(all(r['date']=='2026-09-15' for r in snapshot['acquisitionRecords']))

    def test_acquisition_separates_ambiguous_origin_and_known_signup_without_utm(self):
        other=lead(c='44444444444444',s='55555555555555',a='66666666666666')
        no_utm={**lead(),'Email':'no-utm@example.test',**{k:'' for k in ('UTM source','UTM medium','UTM campaign','UTM term','UTM content')}}
        paid={**trial('paid',event='Paid Trial',email=no_utm['Email']),'Action Earnings':'1450000'}
        sources={'Impact':[trial()],'Recuperacao':[paid]}
        snapshot=prepare_live_snapshot(sources,[lead(),other,no_utm],[ad(),ad(c='44444444444444',s='55555555555555',a='66666666666666')])
        self.assertEqual(snapshot['acquisition']['excluded']['ambiguousOrigin']['freeTrials'],1)
        self.assertEqual(snapshot['acquisition']['totals']['revenueCents'],14500)
        self.assertEqual(sum(r['revenueCents'] for r in snapshot['acquisitionRecords'] if r['campaign']),0)

    def test_new_paid_event_updates_old_acquisition_day_without_duplicate_leads(self):
        sources={'Impact':[trial()],'Recuperacao':[trial()]}
        before=prepare_live_snapshot(sources,[lead()],[ad()])
        sources['Impact'].append(trial('late-paid',event='Paid Trial',date='2026-09-25 12:00:00'))
        after=prepare_live_snapshot(sources,[lead()],[ad()])
        self.assertEqual(before['acquisition']['totals']['sales'],0)
        self.assertEqual(after['acquisition']['totals']['sales'],1)
        self.assertEqual(after['acquisition']['totals']['cohortContacts'],1)
        self.assertEqual(next(r['date'] for r in after['acquisitionRecords'] if r['sales']),'2026-09-16')

    def test_confirmed_commission_scale(self):
        for value in ('1450000','1.450.000','1450000.0000','1.450.000,00'):
            self.assertEqual(commission_cents(value),14500)
        self.assertEqual(commission_cents('950000'),9500)
        self.assertEqual(commission_cents('1.000'),10)
        self.assertEqual(commission_cents('100'),1)
        for value in ('','NaN','-100','145.0000','1.450.00'):
            with self.assertRaises(ValueError):commission_cents(value)

    def test_revenue_includes_all_commissions_but_preserves_trial_counts(self):
        paid={**trial('paid',event='Paid Trial'),'Action Earnings':'1.450.000'}
        full={**trial('full',event='Full Price Shop',status='Approved',email='outside@example.test'),'Action Earnings':'3.250.000'}
        retained={**trial('retained',event='Retained Full Price Shops: 3 Mo',status='Approved'),'Action Earnings':'950000'}
        declined={**trial('declined',event='Full Price Shop',status='Declined'),'Action Earnings':'4.000.000'}
        sources={'Impact':[trial(),paid], 'Recuperacao':[paid,full,retained,declined]}
        snapshot=prepare_live_snapshot(sources,[lead(),lead()],[ad()])
        result=merge_impact(build([ad()],[lead()]),snapshot)
        revenue=result['impact']['revenue']
        self.assertEqual(revenue['totalCents'],56500)
        self.assertEqual(revenue['attributedCents'],24000)
        self.assertEqual(revenue['pendingCents'],14500)
        self.assertEqual(revenue['approvedCents'],42000)
        self.assertEqual(revenue['duplicatesRemoved'],1)
        self.assertEqual(sum(r['revenueCents'] for r in result['records']),56500)
        self.assertEqual(sum(r['revenueCents'] for r in result['records'] if r['campaign']),24000)
        self.assertEqual(sum(r['freeTrials'] for r in result['records']),1)
        self.assertEqual(sum(r['sales'] for r in result['records']),1)
        self.assertNotIn('outside@example',json.dumps(result))

    def test_conflicting_duplicate_earnings_fail(self):
        a={**trial(),'Action Earnings':'1450000'}
        b={**trial(),'Action Earnings':'950000'}
        with self.assertRaisesRegex(ValueError,'Conflicting earnings'):
            normalize_actions({'Impact':[a],'Recuperacao':[b]})

    def test_revenue_uses_action_date_and_keeps_colliding_ids(self):
        a={**trial('paid',event='Paid Trial'),'Action Earnings':'1450000'}
        b={**trial('paid',event='Paid Trial',date='2026-09-18 15:00:00'),'Action Earnings':'950000'}
        result=prepare_live_snapshot({'Impact':[a],'Recuperacao':[b]},[lead()],[ad()])
        self.assertEqual(sum(r['revenueCents'] for r in result['records'] if r['date']=='2026-09-17'),14500)
        self.assertEqual(sum(r['revenueCents'] for r in result['records'] if r['date']=='2026-09-18'),9500)

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
