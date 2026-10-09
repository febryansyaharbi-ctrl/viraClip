"""Opt-in real provider smoke test, isolated from production state.
VIRACLIP_TEST_KEYS=/absolute/server/data/api-keys.json python tests/live_services.py
"""
import json,os,sys,time,pathlib,shutil,subprocess,urllib.request,urllib.error
from integration import Integration
import unittest

class LiveServices(Integration):
 @classmethod
 def setUpClass(cls):
  super().setUpClass()
  shutil.copyfile(os.environ['VIRACLIP_TEST_KEYS'],pathlib.Path(cls.temp.name)/'api-keys.json')
  os.chmod(pathlib.Path(cls.temp.name)/'api-keys.json',0o600)
 def wait_job(self,jid):
  for _ in range(480):
   r=self.call('/api/jobs/'+jid)
   if r['status'] in ('done','error'):return r
   time.sleep(.5)
  self.fail('Timed out: '+jid)
 def test_workflow(self):
  self.call('/api/login',{'password':'test-password-only'})
  with self.assertRaises(urllib.error.HTTPError) as e:self.call('/api/youtube',{'url':'http://127.0.0.1/'})
  self.assertEqual(e.exception.code,400)
  j=self.wait_job(self.call('/api/youtube',{'url':'https://www.youtube.com/watch?v=jNQXAC9IVRw','language':'en'})['job'])
  self.assertEqual(j['status'],'done',j);mid=j['result']['media'];boot=self.call('/api/bootstrap');trans=boot['state']['transcript:'+mid]
  self.assertEqual(trans['source'],'youtube');self.assertGreater(len(trans['segments']),0);print('LIVE_CAPTIONS_OK',len(trans['segments']),flush=True)
  with self.assertRaises(urllib.error.HTTPError):self.call('/api/transcribe',{'media':mid})
  with self.assertRaises(urllib.error.HTTPError):self.call('/api/render',{'media':mid,'start':0,'end':10})
  j=self.wait_job(self.call('/api/analyze',{'media':mid})['job']);self.assertEqual(j['status'],'done',j)
  t=self.call('/api/bootstrap')['state']['transcript:'+mid];self.assertEqual(t['analysis']['segments_reviewed'],len(trans['segments']));print('LIVE_ANALYSIS_OK',len(t['candidates']),'candidates',flush=True)
  self.call('/api/state',{'key':'profile','value':{'name':'Test kreator','minutes':60,'language':'id','skills':'Bisa demonstrasi CCTV dan akses produk distributor','budget':0}})
  j=self.wait_job(self.call('/api/coach',{'message':'Bantu bandingkan tiga niche yang sesuai profil saya dan berikan dua misi pertama. Jangan mengasumsikan saya sudah punya channel.'})['job']);self.assertEqual(j['status'],'done',j)
  state=self.call('/api/bootstrap')['state'];self.assertEqual(len(state['coachHistory']),2);self.assertGreater(len(state['coachNiches']),0);self.assertGreater(len(state['coachMissions']),0)
  print('LIVE_COACH_OK',state['coachLast']['meta'],'missions',len(state['coachMissions']),flush=True)
  task=state['coachMissions'][0]['id'];self.call('/api/state',{'key':'coachTasks','value':{task:True}});self.assertTrue(self.call('/api/bootstrap')['state']['coachTasks'][task])
  backup=self.call('/api/backup');self.assertNotIn('api-keys',json.dumps(backup));self.assertNotIn('sk-or-v1-',json.dumps(backup))
  duration=max(s['end'] for s in trans['segments'])+1;path=pathlib.Path(self.temp.name)/'same-timeline.mp4'
  subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=green:size=160x120:rate=10','-t',str(duration),'-c:v','libx264',str(path)],check=True)
  media=self.call('/api/upload',raw=path.read_bytes(),headers={'X-Filename':'test-timeline.mp4'})
  self.call('/api/attach-video',{'source':mid,'target':media['id']});self.assertEqual(self.call('/api/bootstrap')['state']['transcript:'+media['id']]['segments'],trans['segments'])
  j=self.wait_job(self.call('/api/render',{'media':media['id'],'start':0,'end':min(18,duration),'subtitles':True,'format':'vertical','position':50})['job']);self.assertEqual(j['status'],'done',j);print('YOUTUBE_CAPTION_TO_MP4_OK',flush=True)

if __name__=='__main__':
 if not os.environ.get('VIRACLIP_TEST_KEYS'):raise SystemExit('Set VIRACLIP_TEST_KEYS to opt in to real provider calls.')
 unittest.main(verbosity=2)
