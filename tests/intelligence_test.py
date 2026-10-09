import unittest,sys,tempfile,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import intelligence as ai

class IntelligenceTests(unittest.TestCase):
 def test_url_rejects_external_and_extracts_supported_links(self):
  for url in ['https://youtu.be/jNQXAC9IVRw?t=2','https://www.youtube.com/watch?v=jNQXAC9IVRw','https://youtube.com/shorts/jNQXAC9IVRw']:
   self.assertEqual(ai.youtube_id(url),'jNQXAC9IVRw')
  for url in ['http://127.0.0.1/test','https://youtube.com.evil.org/watch?v=jNQXAC9IVRw','https://evil@youtube.com/watch?v=jNQXAC9IVRw','https://youtube.com:8080/watch?v=jNQXAC9IVRw']:
   with self.assertRaises(ValueError):ai.youtube_id(url)
 def test_model_cannot_invent_timestamp_or_out_of_bounds_indices(self):
  rows=[{'start':i*10,'end':i*10+10,'text':'Pelajaran '+str(i)} for i in range(10)]
  reply=json.dumps({'clips':[{'first':0,'last':3,'title':'Valid','reason':'Pelajaran','start':-9},{'first':8,'last':100,'title':'Invalid'}]})
  with patch.object(ai,'ai_chat',return_value=(reply,{'provider':'test'})):
   r=ai.analyze('.',{'segments':rows})
  self.assertEqual(len(r['candidates']),1);self.assertEqual(r['candidates'][0]['start'],0);self.assertEqual(r['candidates'][0]['end'],40)
  self.assertEqual(r['analysis']['segments_reviewed'],10)
 def test_full_transcript_is_chunked_not_silently_truncated(self):
  rows=[{'start':i*5,'end':i*5+5,'text':'x'*200} for i in range(300)]
  with patch.object(ai,'ai_chat',return_value=('{"clips":[]}',{'provider':'test'})) as chat:
   r=ai.analyze('.',{'segments':rows})
  self.assertGreater(chat.call_count,1);self.assertEqual(r['analysis']['segments_reviewed'],300)
  seen=[]
  for call in chat.call_args_list:seen.extend(json.loads(call.args[1][1]['content']))
  self.assertEqual([r['i'] for r in seen],list(range(300)))
 def test_no_key_is_actionable(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaisesRegex(ValueError,'Kunci API'):ai.ai_chat(d,[])
 def test_coach_history_and_context(self):
  with patch.object(ai,'ai_chat',return_value=('{"reply":"Mulai dari kemampuan Anda","niches":[],"missions":[]}',{'provider':'test'})) as chat:
   r,m=ai.coach('.',{'profile':{'minutes':30}},'Bantu pilih niche',[{'role':'user','text':'Saya suka berkebun'}],{})
  self.assertIn('30',chat.call_args.args[1][1]['content']);self.assertIn('berkebun',chat.call_args.args[1][2]['content']);self.assertTrue(r['reply'])

if __name__=='__main__':unittest.main(verbosity=2)
