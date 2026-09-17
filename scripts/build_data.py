"""Build a read-only, aggregate-only Meta Ads dashboard (Python standard library)."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import shutil
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'ads': ('1YlmghmRdvXgjPaEppRH5fnyBxqADz70HalLv1jfAhMU', '2142085051', 'select A,B,C,D,E,F,G,H,I,J,K'),
    'leads': ('1XcaQNhwyzwpn8sW5gp9OgCRp0pVXyFceoXqVrmAP_3Q', '1507896329', 'select J,AC,AD,AE,AF,AG'),
}
REQUIRED = {
    'ads': ['Day', 'Campaign Name', 'Ad Set Name', 'Ad Name', 'Campaign ID', 'Ad Set ID', 'Ad ID', 'Amount Spent', 'Impressions', 'Link Clicks', 'Landing Page Views'],
    'leads': ['Registration date', 'UTM source', 'UTM medium', 'UTM campaign', 'UTM term', 'UTM content'],
}
METRICS = ('spend', 'impressions', 'clicks', 'views', 'leads')

def norm(value):
    value = unicodedata.normalize('NFKD', urllib.parse.unquote(str(value or '')))
    return ' '.join(''.join(c for c in value if not unicodedata.combining(c)).lower().split())

def number(value):
    raw = str(value or '').strip().replace('\xa0', '').replace(' ', '')
    if not raw:
        return 0
    raw = re.sub(r'^(R\$|US\$|\$)', '', raw)
    if ',' in raw and '.' in raw:
        raw = raw.replace('.', '').replace(',', '.') if raw.rfind(',') > raw.rfind('.') else raw.replace(',', '')
    elif ',' in raw:
        raw = raw.replace(',', '.')
    result = float(raw)
    if not math.isfinite(result) or result < 0:
        raise ValueError('Invalid negative/nonfinite metric')
    return result

def identifier(value):
    value = urllib.parse.unquote(str(value or '')).strip()
    # Never round Meta IDs through floating point.
    if re.fullmatch(r'\d+\.0+', value):
        value = value.split('.')[0]
    return value

def day(value):
    raw = str(value or '').strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}', raw):
        return datetime.strptime(raw[:10], '%Y-%m-%d').date().isoformat()
    # Parse English webinar export without dependence on the runner locale.
    match = re.search(r'(\d{1,2}) ([A-Za-z]{3}) (\d{4})', raw)
    if match:
        month = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'].index(match[2].lower()) + 1
        return datetime(int(match[3]), month, int(match[1])).date().isoformat()
    for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError('Unsupported source date format')

def fetch_source(kind):
    sid, gid, query = SOURCES[kind]
    error = None
    for attempt in range(4):
        try:
            if kind == 'leads':
                # GViz infers a numeric type for mixed UTM columns and silently
                # blanks legacy campaign/creative names. Native CSV keeps both.
                # A single rectangular snapshot keeps dates and UTMs aligned;
                # discard all intermediate columns immediately below.
                params = {'format':'csv', 'gid':gid, 'range':'J:AG', '_cb':time.time_ns()}
                url = f'https://docs.google.com/spreadsheets/d/{sid}/export?' + urllib.parse.urlencode(params)
            else:
                params = {'tqx':'out:csv', 'gid':gid, 'headers':1, 'tq':query, '_cb':time.time_ns()}
                url = f'https://docs.google.com/spreadsheets/d/{sid}/gviz/tq?' + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers={'User-Agent':'ScaleDollarTeams/1.0', 'Cache-Control':'no-cache'})
            with urllib.request.urlopen(req, timeout=90) as response:
                content = response.read().decode('utf-8-sig')
            if '<html' in content[:300].lower():
                raise ValueError('Source returned HTML instead of CSV')
            reader = csv.DictReader(io.StringIO(content))
            if not set(REQUIRED[kind]).issubset(reader.fieldnames or []):
                raise ValueError(f'{kind}: required headers are missing')
            rows = [{k: str(row.get(k) or '').strip() for k in REQUIRED[kind]} for row in reader]
            rows = [row for row in rows if any(row.values())]
            if not rows:
                raise ValueError(f'{kind}: source is empty; preserving previous deployment')
            return rows
        except Exception as exc:
            error = exc
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise RuntimeError(f'Failed reading {kind}; no new data will be published') from error

def blank(date, campaign='', adset='', ad='', attribution='ad'):
    return dict(date=date, campaign=campaign, adset=adset, ad=ad, attribution=attribution, **{m:0 for m in METRICS})

def build(ads, leads):
    dimensions = {'campaign':{}, 'adset':{}, 'ad':{}}
    groups = {}
    duplicate_ads = 0
    seen = set()
    ads_dates, lead_dates = [], []

    def bucket(date, campaign='', adset='', ad='', attribution='ad'):
        key = (date, campaign, adset, ad, attribution)
        if key not in groups:
            groups[key] = blank(*key)
        return groups[key]

    for row in ads:
        if not row.get('Day'):
            if any(row.values()):
                raise ValueError('Media row without date')
            continue
        date = day(row['Day'])
        ids = tuple(identifier(row.get(key)) for key in ('Campaign ID','Ad Set ID','Ad ID'))
        if not all(ids):
            raise ValueError('Media row missing campaign/adset/ad ID')
        campaign, adset, ad = ids
        for level, ident, name in zip(('campaign','adset','ad'), ids, ('Campaign Name','Ad Set Name','Ad Name')):
            item = {'id':ident, 'name':row.get(name) or ident, 'campaign':campaign}
            if level != 'campaign': item['adset'] = adset
            previous = dimensions[level].get(ident)
            if previous and any(previous[k] != item[k] for k in ('campaign','adset') if k in item):
                raise ValueError('Conflicting hierarchy for media ID')
            dimensions[level][ident] = item
        values = [number(row.get(key)) for key in ('Amount Spent','Impressions','Link Clicks','Landing Page Views')]
        fingerprint = (date, *ids, *values)
        if fingerprint in seen:
            duplicate_ads += 1
            continue
        seen.add(fingerprint)
        target = bucket(date, *ids)
        for metric, value in zip(METRICS[:4], values): target[metric] += value
        ads_dates.append(date)

    name_index = {level:defaultdict(set) for level in dimensions}
    for level, entries in dimensions.items():
        for ident, item in entries.items(): name_index[level][norm(item['name'])].add(ident)

    def lookup(level, raw, parent=''):
        raw = identifier(raw)
        if raw in dimensions[level]: return raw
        candidates = name_index[level].get(norm(raw), set())
        if parent: candidates = {i for i in candidates if dimensions[level][i]['campaign'] == parent}
        return next(iter(candidates)) if len(candidates) == 1 else ''

    attribution_counts = Counter()
    for row in leads:
        if not row.get('Registration date'):
            if any(row.values()): raise ValueError('Registration without date')
            continue
        date = day(row['Registration date'])
        lead_dates.append(date)
        campaign = lookup('campaign', row.get('UTM campaign'))
        adset = lookup('adset', row.get('UTM term'), campaign)
        ad = lookup('ad', row.get('UTM content'), campaign)
        conflict = False
        if ad:
            parent = dimensions['ad'][ad]
            conflict = bool((campaign and campaign != parent['campaign']) or (adset and adset != parent['adset']))
            campaign, adset = parent['campaign'], parent['adset']
            attribution = 'ad'
        elif adset:
            parent = dimensions['adset'][adset]
            conflict = bool(campaign and campaign != parent['campaign'])
            campaign = parent['campaign']
            attribution = 'adset'
        elif campaign:
            attribution = 'campaign'
        elif not any(row.get(k) for k in ('UTM source','UTM medium','UTM campaign','UTM term','UTM content')):
            attribution = 'no_utm'
        else:
            attribution = 'unmatched'
        if conflict:
            # Conflicting IDs must never silently assign a conversion.
            campaign = adset = ad = ''
            attribution = 'conflict'
        target = bucket(date, campaign, adset, ad, attribution)
        target['leads'] += 1
        attribution_counts[attribution] += 1

    if not ads_dates or not lead_dates: raise ValueError('Missing dated source data')
    records = sorted(groups.values(), key=lambda x:(x['date'],x['campaign'],x['adset'],x['ad'],x['attribution']))
    for record in records: record['spend'] = round(record['spend'], 2)
    totals = {key:round(sum(row[key] for row in records), 2) for key in METRICS}
    return {
        'schema':1, 'generatedAt':datetime.now(timezone.utc).isoformat(), 'currency':'USD',
        'sources':{'ads':{'start':min(ads_dates),'end':max(ads_dates),'rows':len(ads)}, 'leads':{'start':min(lead_dates),'end':max(lead_dates),'rows':len(leads)}},
        'coverage':{'start':min(ads_dates+lead_dates),'end':max(ads_dates+lead_dates),'commonStart':max(min(ads_dates),min(lead_dates))},
        'audit':{'attribution':dict(attribution_counts), 'duplicateMediaRowsRemoved':duplicate_ads, 'totals':totals},
        'dimensions':dimensions, 'records':records,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--local', action='store_true', help='Use previously audited local fixtures')
    args = parser.parse_args()
    if args.local:
        inputs = [json.loads((ROOT/'.local'/f'{kind}.json').read_text(encoding='utf-8')) for kind in SOURCES]
    else:
        with ThreadPoolExecutor(max_workers=2) as pool: inputs = list(pool.map(fetch_source, SOURCES))
    dataset = build(*inputs)
    from impact_data import merge_impact
    snapshot = json.loads((ROOT/'data'/'impact.json').read_text(encoding='utf-8'))
    dataset = merge_impact(dataset, snapshot)
    output = ROOT/'dist'
    output.mkdir(exist_ok=True)
    for name in ('index.html','app.js','styles.css','.nojekyll'):
        shutil.copyfile(ROOT/'public'/name, output/name)
    index = (output/'index.html').read_text(encoding='utf-8')
    for name in ('app.js','styles.css'):
        digest = hashlib.sha256((output/name).read_bytes()).hexdigest()[:12]
        index = index.replace(f'{name}?v=BUILD', f'{name}?v={digest}')
    (output/'index.html').write_text(index, encoding='utf-8')
    (output/'data.json').write_text(json.dumps(dataset, ensure_ascii=False, separators=(',',':'), allow_nan=False), encoding='utf-8')
    print(json.dumps({'generatedAt':dataset['generatedAt'], 'sources':dataset['sources'], 'audit':dataset['audit']}, ensure_ascii=False))

if __name__ == '__main__': main()
