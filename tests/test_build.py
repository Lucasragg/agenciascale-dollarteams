import sys
import unittest
import io
import csv
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from build_data import build, day, identifier, number, fetch_source, REQUIRED

def ad(c='11111111111111',s='22222222222222',a='33333333333333',name='Creative',date='2026-09-16'):
    return {'Day':date,'Campaign ID':c,'Ad Set ID':s,'Ad ID':a,'Campaign Name':'Campaign '+c,'Ad Set Name':'Set '+s,'Ad Name':name,'Amount Spent':'10,50','Impressions':'1000','Link Clicks':'20','Landing Page Views':'15'}

def lead(c='11111111111111',s='22222222222222',a='33333333333333'):
    return {'Registration date':'Wed, 16 Sep 2026, 05:13 PM','UTM source':'Facebook-Ads','UTM medium':'paid','UTM campaign':c,'UTM term':s,'UTM content':a,'Total Signups':'101','Email':'NEVER-PUBLISH@example.test'}

class BuildTests(unittest.TestCase):
    def test_mixed_utm_export_preserves_legacy_text_and_numeric_ids(self):
        old=lead(c='Campaign 11111111111111',s='Instagram_Feed',a='Creative')
        stream=io.StringIO()
        fields=REQUIRED['leads']+['GDPR IP','Email']
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore')
        writer.writeheader()
        writer.writerows([{**old,'GDPR IP':'PRIVATE-IP'},lead()])
        with patch('build_data.urllib.request.urlopen',return_value=io.BytesIO(stream.getvalue().encode())) as request:
            rows=fetch_source('leads')
        self.assertIn('/export?',request.call_args.args[0].full_url)
        self.assertEqual(rows[0]['UTM campaign'],old['UTM campaign'])
        self.assertEqual(rows[1]['UTM campaign'],'11111111111111')
        self.assertNotIn('Email',rows[0])
        self.assertNotIn('GDPR IP',rows[0])
        self.assertEqual(build([ad()],rows)['audit']['attribution'],{'ad':2})

    def test_url_encoded_legacy_utm_matches_within_campaign(self):
        media=ad()
        media['Campaign Name']='LEO | CONV | US'
        result=build([media],[lead(c='LEO %7C CONV %7C US',s='Instagram_Reels',a='Creative')])
        self.assertEqual(result['audit']['attribution'],{'ad':1})

    def test_parsing(self):
        self.assertEqual(number('1.234,56'),1234.56)
        self.assertEqual(number('1,234.56'),1234.56)
        self.assertEqual(identifier('12345678901234567890'), '12345678901234567890')
        self.assertEqual(day('Wed, 16 Sep 2026, 05:13 PM'),'2026-09-16')
        with self.assertRaises(ValueError): number('NaN')

    def test_exact_id_and_pii(self):
        result=build([ad()],[lead()])
        self.assertEqual(result['audit']['attribution'],{'ad':1})
        self.assertEqual(result['audit']['totals']['leads'],1)
        self.assertEqual(result['audit']['totals']['spend'],10.5)
        self.assertNotIn('NEVER-PUBLISH',str(result))
        self.assertNotIn('sales',result['audit']['totals'])

    def test_partial_and_unmatched_reconcile(self):
        rows=[lead(),lead(a='missing'),lead(s='missing',a='missing'),lead(c='unknown',s='unknown',a='unknown'),{'Registration date':'2026-09-16'}]
        result=build([ad()],rows)
        self.assertEqual(result['audit']['attribution'],{'ad':1,'adset':1,'campaign':1,'unmatched':1,'no_utm':1})
        self.assertEqual(sum(r['leads'] for r in result['records']),len(rows))
        self.assertEqual(sum(r['leads'] for r in result['records'] if r['campaign']),3)

    def test_conflicting_hierarchy_not_attributed(self):
        result=build([ad(),ad(c='44444444444444',s='55555555555555',a='66666666666666')],[lead(c='44444444444444')])
        self.assertEqual(result['audit']['attribution'],{'conflict':1})
        self.assertEqual(sum(r['leads'] for r in result['records'] if r['campaign']),0)

    def test_exact_unique_names_only(self):
        result=build([ad()],[lead(c='Campaign 11111111111111',s='Set 22222222222222',a='Creative')])
        self.assertEqual(result['audit']['attribution'],{'ad':1})
        result=build([ad(),ad(a='77777777777777')],[lead(a='Creative')])
        self.assertEqual(result['audit']['attribution'],{'adset':1})

    def test_duplicate_media_not_double_counted(self):
        result=build([ad(),ad()],[lead()])
        self.assertEqual(result['audit']['totals']['spend'],10.5)
        self.assertEqual(result['audit']['duplicateMediaRowsRemoved'],1)

    def test_no_lead_duplication_across_days(self):
        result=build([ad(date='2026-09-15'),ad()],[lead()])
        self.assertEqual(result['audit']['totals']['leads'],1)
        self.assertEqual(result['audit']['totals']['spend'],21)

    def test_invalid_rows_abort(self):
        with self.assertRaises(ValueError): build([ad()],[{'Registration date':'invalid'}])
        with self.assertRaises(ValueError): build([ad(a='')],[lead()])

if __name__=='__main__': unittest.main()
