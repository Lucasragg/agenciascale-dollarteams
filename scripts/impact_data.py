"""Import private CSV/email data once; publish only aggregate Impact snapshots."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from audit_impact_attribution import audit, email_key, make_resolver, UTMS
from build_data import build, day

METRICS = ('freeTrials', 'sales', 'cohortContacts', 'trialContacts', 'trialSalesContacts', 'dateIssues')


def prepare_snapshot(actions, leads, ads):
    result = audit(actions, leads, ads)
    records = []
    for item in result['records']:
        if item['event'] not in ('Free Trial', 'Paid Trial'):
            raise ValueError('Unmapped Impact event type')
        row = {k: item[k] for k in ('date', 'campaign', 'adset', 'ad', 'attribution')}
        row.update({k: 0 for k in METRICS})
        row['freeTrials' if item['event'] == 'Free Trial' else 'sales'] = item['actions']
        row['dateIssues'] = item['actions'] if item['registration_date_relation'] == 'registration_later_date' else 0
        records.append(row)

    resolve = make_resolver(ads)
    registrations, conversions = defaultdict(list), defaultdict(list)
    for lead in leads:
        if lead.get('Email') and lead.get('Registration date'):
            registrations[email_key(lead['Email'])].append(lead)
    for action in actions:
        conversions[email_key(action['Sub Id 3'])].append(action)
    cohort_groups = Counter()
    cohort_start = min(day(l['Registration date']) for l in leads if l.get('Registration date'))
    snapshot_end = max(day(a['Action Date']) for a in actions)
    for email, entries in registrations.items():
        origins = {resolve(tuple(str(l.get(k) or '') for k in UTMS)) for l in entries}
        if len(origins) != 1:
            continue
        c, s, a, attribution = next(iter(origins))
        registration_date = min(day(l['Registration date']) for l in entries)
        if registration_date > snapshot_end:
            continue
        # Same-day times remain uncertain; exclude actions on earlier dates.
        trials = [day(x['Action Date']) for x in conversions[email] if x['Event Type'] == 'Free Trial' and day(x['Action Date']) >= registration_date]
        sales = [day(x['Action Date']) for x in conversions[email] if x['Event Type'] == 'Paid Trial' and day(x['Action Date']) >= registration_date]
        key = (registration_date, c, s, a, attribution)
        cohort_groups[key + ('cohortContacts',)] += 1
        if trials:
            cohort_groups[key + ('trialContacts',)] += 1
            if any(sale >= min(trials) for sale in sales):
                cohort_groups[key + ('trialSalesContacts',)] += 1
    grouped = {}
    for key, count in cohort_groups.items():
        group, metric = key[:-1], key[-1]
        if group not in grouped:
            grouped[group] = dict(zip(('date', 'campaign', 'adset', 'ad', 'attribution'), group), **{k: 0 for k in METRICS})
        grouped[group][metric] += count
    records.extend(grouped.values())
    dimensions = build(ads, [leads[0]])['dimensions']
    return {
        'version': 1,
        'importedAt': datetime.now(timezone.utc).isoformat(),
        'start': min(day(a['Action Date']) for a in actions),
        'end': snapshot_end,
        'cohortStart': cohort_start,
        'source': 'CSV Impact · Shopify',
        'salesDefinition': 'Paid Trial',
        'provisional': True,
        'eventSummary': result['events'],
        'dimensions': dimensions,
        'records': records,
    }


def merge_impact(dataset, snapshot):
    if snapshot.get('version') != 1 or not snapshot.get('records'):
        raise ValueError('Missing or invalid Impact snapshot')
    if snapshot['start'] > snapshot['end']:
        raise ValueError('Invalid Impact dates')
    # Only allowlisted aggregates reach the public website.
    for record in dataset['records']:
        record.update({k: 0 for k in METRICS})
    for item in snapshot['records']:
        row = {k: item[k] for k in ('date', 'campaign', 'adset', 'ad', 'attribution')}
        row.update({k: 0 for k in ('spend', 'impressions', 'clicks', 'views', 'leads')})
        for metric in METRICS:
            value = item[metric]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError('Invalid Impact count')
            row[metric] = value
        for level in ('campaign', 'adset', 'ad'):
            ident = row[level]
            if ident:
                original = snapshot['dimensions'][level][ident]
                if ident not in dataset['dimensions'][level]:
                    dataset['dimensions'][level][ident] = {k: original[k] for k in ('id', 'name', 'campaign', 'adset') if k in original}
                current = dataset['dimensions'][level][ident]
                if any(current.get(k) != original.get(k) for k in ('campaign', 'adset')):
                    raise ValueError('Impact media hierarchy changed')
        dataset['records'].append(row)
    dataset['impact'] = {k: snapshot[k] for k in ('importedAt', 'start', 'end', 'cohortStart', 'source', 'salesDefinition', 'provisional')}
    dataset['schema'] = 2
    dataset['coverage']['start'] = min(dataset['coverage']['start'], snapshot['start'])
    dataset['records'].sort(key=lambda r: (r['date'], r['campaign'], r['adset'], r['ad']))
    return dataset


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('impact_csv', type=Path)
    parser.add_argument('--leads', type=Path, required=True)
    parser.add_argument('--ads', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.impact_csv.open(encoding='utf-8-sig', newline='') as stream:
        actions = list(csv.DictReader(stream))
    leads = json.loads(args.leads.read_text(encoding='utf-8'))
    snapshot = prepare_snapshot(actions, leads, json.loads(args.ads.read_text(encoding='utf-8')))
    serialized = json.dumps(snapshot, ensure_ascii=False, separators=(',', ':'))
    if any(email_key(l['Email']) in serialized.lower() for l in leads if l.get('Email')):
        raise ValueError('Personal data detected in aggregate output')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized, encoding='utf-8')
    print(json.dumps({'records': len(snapshot['records']), 'start': snapshot['start'], 'end': snapshot['end']}))


if __name__ == '__main__':
    main()
