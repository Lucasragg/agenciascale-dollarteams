"""Read conversion sheets and join emails in memory; publish aggregates only."""
import csv
import io
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

from build_data import SOURCES, day, identifier
from audit_impact_attribution import email_key, make_resolver, UTMS
from impact_data import prepare_snapshot, METRICS

TABS = {'Impact': '215288026', 'Recuperacao': '579566718'}
FIELDS = ('Action Date', 'Action Id', 'Brand', 'Event Type', 'Status', 'Sub Id 3', 'Action Earnings')
EVENTS = ('Free Trial', 'Paid Trial')
ACCEPTED = {'Pending', 'Approved'}
EXCLUDED = {'Reversed', 'Declined', 'Rejected'}

def commission_cents(value):
    """User-confirmed source scale: 1,450,000 stored units = USD 145.00.

    Parse native CSV's pt-BR thousands groups explicitly, using Decimal, and
    reject missing or sub-cent values rather than guessing a different scale.
    """
    raw = str(value).strip().replace('\xa0','').replace(' ','')
    if re.fullmatch(r'\d{1,3}(?:\.\d{3})+(?:,\d+)?', raw):
        raw = raw.replace('.','').replace(',','.')
    elif re.fullmatch(r'\d+(?:,\d+)?',raw):
        raw = raw.replace(',','.')
    elif not re.fullmatch(r'\d+\.\d+',raw):
        raise ValueError('Invalid commission amount')
    try:
        cents = Decimal(raw)/Decimal(100)  # divide 10,000, then convert to cents
        if not cents.is_finite() or cents<0 or cents!=cents.to_integral_value():
            raise ValueError('Commission scale must produce whole cents')
        return int(cents)
    except InvalidOperation:
        raise ValueError('Invalid commission amount') from None

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

def normalize_actions(sources, all_events=False):
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
                if not all_events: continue
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
            cents = commission_cents(source['Action Earnings'])
            ids[ident].add(key)
            if key in seen:
                if seen[key]['Status'] != status:
                    raise ValueError('Conflicting status for the same conversion; reconcile the source')
                if seen[key]['commissionCents'] != cents:
                    raise ValueError('Conflicting earnings for the same action; reconcile the source')
                duplicates += 1
                continue
            seen[key] = {**source, 'Action Date':timestamp, 'Sub Id 3':key[-1], 'commissionCents':cents}
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

def revenue_snapshot(sources, leads, ads):
    actions, tabs, diagnostics = normalize_actions(sources, all_events=True)
    by_email = defaultdict(list)
    for lead in leads:
        if lead.get('Registration date') and email_key(lead.get('Email')):
            by_email[email_key(lead['Email'])].append(lead)
    resolve, origins, grouped = make_resolver(ads), {}, Counter()
    totals = {'totalCents':0,'attributedCents':0,'pendingCents':0,'approvedCents':0}
    for action in actions:
        cents=action['commissionCents']
        totals['totalCents']+=cents
        totals['pendingCents' if action['Status']=='Pending' else 'approvedCents']+=cents
        if not cents: continue
        email=email_key(action['Sub Id 3'])
        if email not in origins:
            candidates=by_email.get(email,[])
            matches={resolve(tuple(str(row.get(k) or '') for k in UTMS)) for row in candidates}
            origins[email]=next(iter(matches)) if len(matches)==1 else ('','','','ambiguous_origin' if matches else 'no_email_match')
        campaign, adset, ad, attribution = origins[email]
        if campaign: totals['attributedCents']+=cents
        grouped[(day(action['Action Date']),campaign,adset,ad,attribution)]+=cents
    records=[]
    for key,cents in grouped.items():
        record=dict(zip(('date','campaign','adset','ad','attribution'),key),**{k:0 for k in METRICS})
        record['revenueCents']=cents
        records.append(record)
    metadata={**totals,'currency':'USD','sourceScale':10000,
              'start':min(tab['start'] for tab in tabs.values()),'end':max(tab['end'] for tab in tabs.values()),
              'completeStart':max(tab['start'] for tab in tabs.values()),'completeEnd':min(tab['end'] for tab in tabs.values()),
              'duplicatesRemoved':diagnostics['duplicatesRemoved']}
    return records, metadata, {email_key(row['Sub Id 3']) for row in actions}

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
    revenue_records, snapshot['revenue'], revenue_emails = revenue_snapshot(sources, leads, ads)
    snapshot['records'].extend(revenue_records)
    serialized = json.dumps(snapshot,ensure_ascii=False).lower()
    emails = {email_key(row.get('Email')) for row in leads} | revenue_emails
    if any(email and email in serialized for email in emails):
        raise ValueError('Personal data detected in aggregate snapshot')
    return snapshot
