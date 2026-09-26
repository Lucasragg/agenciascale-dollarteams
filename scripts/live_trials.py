"""Read conversion sheets and join emails in memory; publish aggregates only."""
import csv
import io
import json
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime

from build_data import SOURCES, day, identifier
from audit_impact_attribution import email_key
from impact_data import prepare_snapshot

TABS = {'Impact': '215288026', 'Recuperacao': '579566718'}
FIELDS = ('Action Date', 'Action Id', 'Brand', 'Event Type', 'Status', 'Sub Id 3')
EVENTS = ('Free Trial', 'Paid Trial')
ACCEPTED = {'Pending', 'Approved'}
EXCLUDED = {'Reversed', 'Declined', 'Rejected'}

def fetch_actions(tab):
    sid = SOURCES['leads'][0]
    for attempt in range(4):
        try:
            params = urllib.parse.urlencode({'format':'csv','gid':TABS[tab],'range':'A:K','_cb':time.time_ns()})
            req = urllib.request.Request(f'https://docs.google.com/spreadsheets/d/{sid}/export?'+params,
                                         headers={'Cache-Control':'no-cache','User-Agent':'ScaleDollarTeams/1.0'})
            with urllib.request.urlopen(req, timeout=90) as response:
                reader = csv.DictReader(io.StringIO(response.read().decode('utf-8-sig')))
                if not set(FIELDS).issubset(reader.fieldnames or []):
                    raise ValueError('Missing conversion headers')
                rows = [{k:str(row.get(k) or '').strip() for k in FIELDS} for row in reader]
            rows = [row for row in rows if any(row.values())]
            if not rows: raise ValueError('Empty conversion source')
            return rows
        except Exception:
            if attempt == 3:
                raise RuntimeError(f'Failed reading {tab}; preserving previous deployment') from None
            time.sleep(2**attempt)

def normalize_actions(sources):
    """Action IDs in Sheets collide. Preserve distinct dates/emails/events.

    Deduplicate the same ID + timestamp + brand + event + normalized email
    within and between tabs. Conflicting statuses are not silently resolved.
    Distinct action IDs never collapse merely because the email is the same.
    """
    if set(sources) != set(TABS): raise ValueError('Both conversion tabs are required')
    seen, ids, tab_stats, event_statuses = {}, defaultdict(set), {}, {}
    ignored = Counter()
    duplicates = 0
    for tab in TABS:
        rows = sources[tab]
        if not rows: raise ValueError('Empty conversion tab')
        accepted_dates, event_counts, status_counts = [], Counter(), Counter()
        for source in rows:
            if not set(FIELDS).issubset(source): raise ValueError('Missing action fields')
            if not source['Action Id'] or not source['Action Date']: raise ValueError('Action missing ID or date')
            try:
                # Keep the displayed source day; no speculative timezone shift.
                timestamp = datetime.fromisoformat(source['Action Date']).isoformat(sep=' ')
                if datetime.fromisoformat(timestamp).tzinfo is not None: raise ValueError()
            except ValueError:
                raise ValueError('Unsupported conversion timestamp') from None
            event, status = source['Event Type'], source['Status']
            if source['Brand'] != 'Shopify': raise ValueError('Unexpected conversion brand')
            if not event: raise ValueError('Missing conversion event')
            event_counts[event] += 1
            status_counts[status] += 1
            if event not in EVENTS:
                ignored['otherEvents'] += 1
                continue
            if status not in ACCEPTED | EXCLUDED: raise ValueError('Unknown conversion status')
            ident = identifier(source['Action Id'])
            key = (ident, timestamp, source['Brand'], event, email_key(source['Sub Id 3']))
            if key in event_statuses and event_statuses[key] != status:
                raise ValueError('Conflicting status for the same conversion; reconcile the source')
            event_statuses[key] = status
            if status in EXCLUDED:
                ignored['excludedStatuses'] += 1
                continue
            accepted_dates.append(day(timestamp))
            ids[ident].add(key)
            if key in seen:
                if seen[key]['Status'] != status:
                    raise ValueError('Conflicting status for the same conversion; reconcile the source')
                duplicates += 1
                continue
            seen[key] = {**source, 'Action Date':timestamp, 'Sub Id 3':key[-1]}
        if not accepted_dates: raise ValueError('No valid trial events in a conversion tab')
        tab_stats[tab] = {'rows':len(rows),'start':min(accepted_dates),'end':max(accepted_dates),
                          'freeTrials':event_counts['Free Trial'],'paidTrials':event_counts['Paid Trial']}
    actions=[]
    for index, action in enumerate(seen.values()):
        # Only an ephemeral unique key is passed to the existing audit, which
        # requires unique IDs. No IDs or email-derived hashes are published.
        actions.append({**action, 'Action Id':f'joined-{index}'})
    diagnostics = {'sourceRows':sum(len(rows) for rows in sources.values()),
                   'uniqueActions':len(actions),'duplicatesRemoved':duplicates,
                   'collidingIds':sum(len(keys)>1 for keys in ids.values()),
                   'otherEventsExcluded':ignored['otherEvents'],
                   'statusesExcluded':ignored['excludedStatuses']}
    return actions, tab_stats, diagnostics

def prepare_live_snapshot(sources, leads, ads):
    actions, tab_stats, diagnostics = normalize_actions(sources)
    if any('Email' not in row for row in leads): raise ValueError('Lead email column is required for conversion matching')
    common_end = min(tab['end'] for tab in tab_stats.values())
    snapshot = prepare_snapshot(actions, leads, ads, observation_end=common_end)
    snapshot['source'] = 'Google Sheets · Impact + Recuperacao'
    snapshot['mode'] = 'sheets'
    snapshot['tabs'] = tab_stats
    # Cost/rate coverage requires both conversion exports, not just the source
    # that happens to have the newest event. Raw event counts remain visible.
    snapshot['completeStart'] = max(tab['start'] for tab in tab_stats.values())
    snapshot['completeEnd'] = min(tab['end'] for tab in tab_stats.values())
    snapshot['diagnostics'] = diagnostics
    snapshot['eventTotals'] = {}
    for event, metric in [('Free Trial','freeTrials'),('Paid Trial','paidTrials')]:
        audit = snapshot['eventSummary'].get(event,{})
        snapshot['eventTotals'][metric] = {key:int(audit.get(key,0)) for key in
                                          ('actions','emailMatched','noEmailMatch','ambiguousOrigin','mediaCandidates')}
    statuses = Counter(a['Status'] for a in actions)
    snapshot['statuses'] = {key:statuses[key] for key in sorted(ACCEPTED)}
    serialized = json.dumps(snapshot,ensure_ascii=False).lower()
    emails = {email_key(row.get('Email')) for row in leads} | {email_key(row['Sub Id 3']) for row in actions}
    if any(email and email in serialized for email in emails):
        raise ValueError('Personal data detected in aggregate snapshot')
    return snapshot
