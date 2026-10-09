"""Real HTTP and ffmpeg integration tests; runs in an isolated temporary workspace."""
import unittest,subprocess,tempfile,os,time,json,urllib.request,urllib.error,http.cookiejar,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Integration(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.base='http://127.0.0.1:18022';cls.cookie=http.cookiejar.CookieJar();cls.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cls.cookie))
  cls.proc=subprocess.Popen([sys.executable,str(ROOT/'server.py')],env={**os.environ,'PORT':'18022','VIRACLIP_DATA':cls.temp.name,'VIRACLIP_PASSWORD':'test-password-only'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  for _ in range(50):
   try:urllib.request.urlopen(cls.base+'/api/health');break
   except Exception:time.sleep(.1)
 @classmethod
 def tearDownClass(cls):cls.proc.terminate();cls.proc.wait();cls.temp.cleanup()
 def call(self,path,body=None,raw=None,headers=None,opener=None):
  h={'X-ViraClip':'1',**(headers or {})};data=raw if raw is not None else json.dumps(body).encode() if body is not None else None
  req=urllib.request.Request(self.base+path,data=data,headers=h)
  with (opener or self.opener).open(req,timeout=20) as r:return json.loads(r.read())
 def test_workflow(self):
  with self.assertRaises(urllib.error.HTTPError) as ctx:urllib.request.urlopen(self.base+'/api/bootstrap')
  self.assertEqual(ctx.exception.code,401)
  self.assertTrue(self.call('/api/login',{'password':'test-password-only'})['ok'])
  self.call('/api/state',{'key':'profile','value':{'name':'Test','minutes':30,'language':'id'}})
  self.assertIn('3 Shorts',self.call('/api/bootstrap')['mentor']['cadence'])
  self.call('/api/state',{'key':'sources','value':[{'id':'1','rights':'own','creator':'test'}]})
  self.assertEqual(self.call('/api/backup')['state']['sources'][0]['rights'],'own')
  path=pathlib.Path(self.temp.name)/'source.mp4'
  subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=320x240:rate=15','-f','lavfi','-i','sine=frequency=440','-t','3','-c:v','libx264','-c:a','aac',str(path)],check=True)
  media=self.call('/api/upload',raw=path.read_bytes(),headers={'X-Filename':'sample.mp4'})
  self.assertEqual(media['width'],320)
  mid=media['id']
  self.call('/api/subtitles',{'media':mid,'srt':'1\n00:00:00,000 --> 00:00:02,500\nContoh subtitle orisinal.\n'})
  job=self.call('/api/render',{'media':mid,'start':0,'end':2,'format':'vertical','position':50,'subtitles':True,'name':'Test render'})['job']
  for _ in range(90):
   result=self.call('/api/jobs/'+job)
   if result['status'] in ['done','error']:break
   time.sleep(.3)
  self.assertEqual(result['status'],'done',result)
  with self.opener.open(self.base+result['result']['video']) as r:self.assertEqual(r.read()[4:8],b'ftyp')
  export=pathlib.Path(self.temp.name)/'exports'/(job+'.mp4')
  info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(export)]))
  video=next(s for s in info['streams'] if s['codec_type']=='video');self.assertEqual((video['width'],video['height']),(720,1280))
  with self.assertRaises(urllib.error.HTTPError) as ctx:self.call('/api/render',{'media':mid,'start':2,'end':1})
  self.assertEqual(ctx.exception.code,400)
  with self.assertRaises(urllib.error.HTTPError) as ctx:self.call('/api/state',{'key':'profile','value':{}},headers={'Origin':'https://evil.example'})
  self.assertEqual(ctx.exception.code,403)
  with self.assertRaises(urllib.error.HTTPError):self.call('/api/state',{'key':'credentials','value':{}})
  if os.environ.get('VIRACLIP_TEST_TRANSCRIPTION')=='1':
   audio=pathlib.Path(self.temp.name)/'speech.wav'
   subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',"flite=text='This is a test of the video studio. We create useful lessons and explain every step.':voice=slt",str(audio)],check=True)
   voice=self.call('/api/upload',raw=audio.read_bytes(),headers={'X-Filename':'speech.wav'})
   jid=self.call('/api/transcribe',{'media':voice['id'],'language':'en'})['job']
   for _ in range(180):
    transcript=self.call('/api/jobs/'+jid)
    if transcript['status'] in ['done','error']:break
    time.sleep(.5)
   self.assertEqual(transcript['status'],'done',transcript)
   recognized=' '.join(s['text'] for s in transcript['result']['segments']).lower()
   self.assertIn('test',recognized)
   print('Speech recognized:',recognized)
   self.call('/api/delete-media',{'id':voice['id']})
  self.call('/api/password',{'current':'test-password-only','password':'changed-password-test'})
  self.assertFalse(self.call('/api/session')['authenticated'])
  self.call('/api/login',{'password':'changed-password-test'})
  self.call('/api/delete-media',{'id':mid})
  self.assertEqual(self.call('/api/bootstrap')['media'],[])
if __name__=='__main__':unittest.main(verbosity=2)
