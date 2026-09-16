"""Match Impact actions to webinar leads; export aggregate candidates only.

Email matching establishes a link, not causality. Source timestamps have no
confirmed timezone, so every media association remains provisional.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from build_data import build, day

ROOT = Path(__file__).resolve().parents[1]
UTMS = ('UTM source', 'UTM medium', 'UTM campaign', 'UTM term', 'UTM content')
PAID_LEVELS = {'ad', 'adset', 'campaign'}


def email_key(value):
    # Do not strip dots or +suffixes: that could merge different accounts.
    return str(value or '').strip().lower()


def registration_datetime(value):
    match = re.search(r'(\d{1,2}) ([A-Za-z]{3}) (\d{4}), (\d{1,2}):(\d{2}) (AM|PM)', value)
    if not match:
        raise ValueError('Unsupported registration timestamp')
    month = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'].index(match[2].lower()) + 1
    hour = int(match[4]) % 12 + (12 if match[6] == 'PM' else 0)
    return datetime(int(match[3]), month, int(match[1]), hour, int(match[5]))


def make_resolver(ads):
    @lru_cache(None)
    def resolve(signature):
        # Reuse the dashboard's existing ID/name/hierarchy rules unchanged.
        # These intermediate media totals are not included in audit output.
        lead = dict(zip(UTMS, signature))
        lead['Registration date'] = '2000-01-01'
        result = build(ads, [lead])
        row = next(row for row in result['records'] if row['leads'])
        return tuple(row[k] for k in ('campaign', 'adset', 'ad', 'attribution'))
    return resolve


def audit(actions, leads, ads):
    by_email = defaultdict(list)
    for lead in leads:
        if lead.get('Registration date') and email_key(lead.get('Email')):
            by_email[email_key(lead['Email'])].append(lead)
    resolve = make_resolver(ads)

    totals = defaultdict(Counter)
    groups = Counter()
    seen = set()
    for action in actions:
        action_id = action.get('Action Id', '').strip()
        if not action_id or action_id in seen:
            raise ValueError('Missing or duplicate Action Id; reconcile the export before matching')
        seen.add(action_id)
        event = action['Event Type']
        event_date = day(action['Action Date'])
        tally = totals[event]
        tally['actions'] += 1
        candidates = by_email.get(email_key(action.get('Sub Id 3')), [])
        campaign = adset = ad = ''
        attribution = 'no_email_match'
        relation = 'unavailable'
        if not candidates:
            tally['noEmailMatch'] += 1
        else:
            tally['emailMatched'] += 1
            if len(candidates) > 1:
                tally['multipleRegistrations'] += 1
            origins = {resolve(tuple(str(row.get(k) or '') for k in UTMS)) for row in candidates}
            if len(origins) > 1:
                tally['ambiguousOrigin'] += 1
                attribution = 'ambiguous_origin'
            else:
                campaign, adset, ad, attribution = next(iter(origins))
                tally['origin_' + attribution] += 1
                if attribution in PAID_LEVELS:
                    tally['mediaCandidates'] += 1
                first = min(registration_datetime(row['Registration date']) for row in candidates)
                event_time = datetime.fromisoformat(action['Action Date'])
                if first.date() < event_time.date():
                    relation = 'registration_earlier_date'
                elif first.date() == event_time.date():
                    relation = 'same_date'
                else:
                    relation = 'registration_later_date'
                tally[relation] += 1
                if attribution in PAID_LEVELS:
                    tally['media_' + relation] += 1
                # Naive comparison is diagnostic only, never a causality rule.
                delta = (event_time - first).total_seconds() / 3600
                if delta < -24:
                    tally['eventOver24HoursBeforeRegistrationNaive'] += 1
                elif delta < 0:
                    tally['eventUpTo24HoursBeforeRegistrationNaive'] += 1
                else:
                    tally['eventAtOrAfterRegistrationNaive'] += 1
        key = (event_date, event, action.get('Status', ''), campaign, adset, ad, attribution, relation)
        groups[key] += 1

    keys = ('date', 'event', 'status', 'campaign', 'adset', 'ad', 'attribution', 'registration_date_relation')
    records = [dict(zip(keys, key), actions=count, provisional=True) for key, count in sorted(groups.items())]
    if sum(row['actions'] for row in records) != len(actions):
        raise AssertionError('Aggregated actions do not reconcile')
    return {
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'provisional': True,
        'rules': {
            'emailNormalization': 'trim + lowercase; exact match only',
            'multipleOrigins': 'unassigned; no arbitrary first/last touch',
            'counting': 'distinct Action Id; an action is not a unique person or store',
            'timezone': 'unconfirmed for both exported timestamps; date relations are diagnostic',
            'attribution': 'existing dashboard resolver, inherited from the matching lead',
        },
        'leadRows': len(leads),
        'uniqueLeadEmails': len(by_email),
        'duplicateLeadEmails': sum(len(rows) > 1 for rows in by_email.values()),
        'events': dict(totals),
        'records': records,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('impact_csv', type=Path)
    parser.add_argument('--leads-json', type=Path, default=ROOT / '.local/impact-lead-match-source.json')
    parser.add_argument('--ads-json', type=Path, default=ROOT / '.local/ads.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.impact_csv.open(encoding='utf-8-sig', newline='') as source:
        actions = list(csv.DictReader(source))
    result = audit(actions, json.loads(args.leads_json.read_text(encoding='utf-8')), json.loads(args.ads_json.read_text(encoding='utf-8')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    csv_path = args.output.with_suffix('.csv')
    if result['records']:
        with csv_path.open('w', encoding='utf-8-sig', newline='') as destination:
            writer = csv.DictWriter(destination, fieldnames=list(result['records'][0]))
            writer.writeheader()
            writer.writerows(result['records'])
    print(json.dumps({key: value for key, value in result.items() if key != 'records'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
