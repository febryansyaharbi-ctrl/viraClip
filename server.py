#!/usr/bin/env python3
"""ViraClip: private, single-owner creator workspace. Python 3.10+."""
import os,json,sqlite3,secrets,hashlib,hmac,time,re,subprocess,threading,queue,shutil,mimetypes,traceback
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlsplit,unquote,parse_qs
from http.cookies import SimpleCookie
import intelligence

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('VIRACLIP_DATA',str(ROOT/'data'))).resolve()
DATA.mkdir(parents=True,exist_ok=True)
for d in ['media','exports','jobs']: (DATA/d).mkdir(exist_ok=True)
DB=DATA/'app.sqlite3'
MAX_UPLOAD=500*1024*1024
QUE=queue.Queue(maxsize=12)
MODEL=None
LOGIN_TRIES={}
LOCK=threading.Lock()

def db():
 c=sqlite3.connect(DB,timeout=30); c.row_factory=sqlite3.Row;return c

def init():
 with db() as c:
  c.executescript('''PRAGMA journal_mode=WAL;
  CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY,value TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS media (id TEXT PRIMARY KEY,name TEXT,ext TEXT,duration REAL,width INTEGER,height INTEGER,audio INTEGER,created REAL);
  CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY,kind TEXT,status TEXT,progress INTEGER,message TEXT,result TEXT,created REAL);
  CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY,expires REAL);
  ''')
  c.execute("UPDATE jobs SET status='error',message='Proses terhenti saat layanan dimulai ulang. Jalankan kembali.' WHERE status IN ('queued','running')")
  c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
 if not (DATA/'credentials.json').exists():
  password=os.environ.get('VIRACLIP_PASSWORD') or secrets.token_urlsafe(15)
  salt=secrets.token_hex(16)
  (DATA/'credentials.json').write_text(json.dumps({'salt':salt,'hash':hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),250000).hex()}))
  os.chmod(DATA/'credentials.json',0o600)
  if not os.environ.get('VIRACLIP_PASSWORD'):
   (DATA/'initial-password.txt').write_text(password+'\n');os.chmod(DATA/'initial-password.txt',0o600)

def jget(key,default=None):
 with db() as c:r=c.execute('SELECT value FROM kv WHERE key=?',(key,)).fetchone()
 return json.loads(r[0]) if r else default

def jset(key,value):
 with db() as c:c.execute('INSERT OR REPLACE INTO kv VALUES (?,?)',(key,json.dumps(value,ensure_ascii=False)))

def safe_number(v,low,high):
 try: n=float(v)
 except (TypeError,ValueError):raise ValueError('Angka tidak valid.')
 if not low<=n<=high:raise ValueError(f'Angka harus antara {low}–{high}.')
 return n

def media_row(mid):
 if not re.fullmatch(r'[a-f0-9]{24}',mid):raise ValueError('ID media tidak valid.')
 with db() as c:r=c.execute('SELECT * FROM media WHERE id=?',(mid,)).fetchone()
 if not r:raise ValueError('Media tidak ditemukan.')
 return dict(r)

def media_path(r):return DATA/'media'/(r['id']+r['ext'])
def run(args,timeout=900):
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
 if p.returncode:raise ValueError('Pemrosesan media gagal. Pastikan berkas dapat diputar dan durasi benar. '+p.stderr.decode(errors='replace')[-350:])
 return p.stdout

def probe(path):
 data=json.loads(run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)],30))
 streams=data.get('streams',[]); video=next((s for s in streams if s['codec_type']=='video'),{})
 return {'duration':float(data.get('format',{}).get('duration',0)),'width':video.get('width',0),'height':video.get('height',0),'audio':int(any(s['codec_type']=='audio' for s in streams))}

def update_job(jid,status='running',progress=0,message='',result=None):
 with db() as c:c.execute('UPDATE jobs SET status=?,progress=?,message=?,result=? WHERE id=?',(status,progress,message,json.dumps(result or {},ensure_ascii=False),jid))

def enqueue(kind,payload):
 if QUE.full():raise ValueError('Antrean penuh. Tunggu proses sebelumnya selesai.')
 jid=secrets.token_hex(12)
 with db() as c:c.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',(jid,kind,'queued',0,'Menunggu giliran','{}',time.time()))
 QUE.put((jid,kind,payload));return jid

def suggestions(segments,duration):
 out=[];keywords=['cara','kenapa','mengapa','kesalahan','contoh','tips','karena','how','why','mistake','because']
 for i,s in enumerate(segments):
  start=float(s['start']);end=min(start+45,duration)
  if end-start<12:continue
  text=' '.join(x['text'] for x in segments[i:] if x['start']<end)
  score=sum(k in text.lower() for k in keywords)+min(len(text.split())/45,2)
  out.append({'start':round(start,2),'end':round(end,2),'text':text[:280],'score':round(score,1),'reason':'Kandidat berdasarkan kata penjelas dan kepadatan transkrip; periksa konteks dan akhir kalimat.'})
 chosen=[]
 for x in sorted(out,key=lambda x:x['score'],reverse=True):
  if all(abs(x['start']-y['start'])>30 for y in chosen):chosen.append(x)
  if len(chosen)==5:break
 return chosen

def transcribe(jid,p):
 global MODEL
 r=media_row(p['media']);
 if r['ext']=='.youtube':raise ValueError('Proyek tautan hanya menggunakan caption YouTube.')
 if not r['audio']:raise ValueError('Video ini tidak memiliki audio.')
 try:from faster_whisper import WhisperModel
 except ImportError:raise ValueError('Mesin transkripsi belum terpasang. Anda tetap dapat mengimpor subtitle SRT.')
 update_job(jid,progress=8,message='Menyiapkan pengenal suara lokal…')
 if MODEL is None:MODEL=WhisperModel(os.environ.get('WHISPER_MODEL','base'),device='cpu',compute_type='int8',cpu_threads=2,num_workers=1)
 segments,info=MODEL.transcribe(str(media_path(r)),beam_size=3,vad_filter=True,language=p.get('language') or None)
 rows=[]
 for s in segments:
  rows.append({'start':round(s.start,3),'end':round(s.end,3),'text':s.text.strip()})
  update_job(jid,progress=min(95,int(s.end/max(r['duration'],1)*90)+5),message='Menyusun subtitle dan kandidat klip…')
 result={'segments':rows,'language':info.language,'candidates':suggestions(rows,r['duration'])}
 jset('transcript:'+r['id'],result)
 update_job(jid,'done',100,'Transkripsi selesai. Periksa ejaan sebelum ekspor.',result)

def timestamp(seconds):
 ms=max(0,round(seconds*1000));h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
 return f'{h:02}:{m:02}:{s:02},{ms:03}'

def parse_srt(text):
 result=[]
 for block in re.split(r'\n\s*\n',text.strip().replace('\r','')):
  match=re.search(r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})',block)
  if not match:continue
  n=list(map(int,match.groups()));a=n[0]*3600+n[1]*60+n[2]+n[3]/1000;b=n[4]*3600+n[5]*60+n[6]+n[7]/1000
  t=re.sub('<[^>]*>','',block[match.end():].strip()).strip()
  if b>a and t:result.append({'start':a,'end':b,'text':t[:1500]})
 if not result:raise ValueError('Subtitle SRT tidak terbaca. Gunakan waktu HH:MM:SS,mmm --> HH:MM:SS,mmm.')
 return result[:10000]

def render(jid,p):
 r=media_row(p['media']);start=safe_number(p.get('start'),0,r['duration']);end=safe_number(p.get('end'),0,r['duration'])
 if not 1<=end-start<=180:raise ValueError('Pilih potongan sepanjang 1–180 detik.')
 duration=end-start;fmt=p.get('format','vertical');pos=safe_number(p.get('position',50),0,100)/100
 sizes={'vertical':(720,1280),'square':(720,720),'landscape':(1280,720)}
 w,h=sizes.get(fmt,sizes['vertical'])
 folder=DATA/'jobs'/jid;folder.mkdir(exist_ok=True)
 subs=[]
 transcript=jget('transcript:'+r['id'],{'segments':[]})
 for s in transcript['segments']:
  if s['end']>start and s['start']<end:
   text=re.sub(r'[{}\\]','',s['text']).replace('\n',' ')
   subs.append(f"{len(subs)+1}\n{timestamp(max(0,s['start']-start))} --> {timestamp(min(duration,s['end']-start))}\n{text}\n")
 srt=folder/'captions.srt';srt.write_text('\n'.join(subs),encoding='utf-8')
 vf=f'scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}:(iw-ow)*{pos}:(ih-oh)/2,setsar=1'
 if p.get('subtitles') and subs:
  vf+=f",subtitles='{str(srt)}':force_style='FontName=DejaVu Sans,FontSize=19,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,Outline=2,MarginV=30,Alignment=2'"
 args=['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(start),'-t',str(duration),'-i',str(media_path(r))]
 narration=p.get('narration')
 if narration:
  voice=media_row(narration)
  if not voice['audio']:raise ValueError('Narasi tidak memiliki audio.')
  args+=['-i',str(media_path(voice))]
  if r['audio']:args+=['-filter_complex','[0:a]volume=0.15[a];[1:a]apad[v];[a][v]amix=inputs=2:duration=first:normalize=0[out]','-map','0:v:0','-map','[out]']
  else:args+=['-filter_complex','[1:a]apad[out]','-map','0:v:0','-map','[out]']
 output=DATA/'exports'/(jid+'.mp4')
 args+=['-vf',vf,'-t',str(duration),'-c:v','libx264','-preset','veryfast','-crf','23','-threads','2','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(output)]
 update_job(jid,progress=20,message='Merender video, subtitle, dan audio…')
 run(args,1200)
 shutil.copy(srt,DATA/'exports'/(jid+'.srt'))
 result={'video':'/media/exports/'+jid+'.mp4','subtitle':'/media/exports/'+jid+'.srt','name':p.get('name','Klip baru'),'duration':duration,'created':time.time()}
 jset('export:'+jid,result);update_job(jid,'done',100,'Video siap diunduh.',result)

def youtube_import(jid,p):
 vid=intelligence.youtube_id(p['url']);mid=hashlib.sha256(('youtube:'+vid).encode()).hexdigest()[:24]
 update_job(jid,progress=10,message='Mengambil caption yang sudah tersedia di YouTube…')
 result=intelligence.fetch_captions(vid,p.get('language','id'));duration=max(x['end'] for x in result['segments'])
 with db() as c:
  c.execute('INSERT OR IGNORE INTO media VALUES (?,?,?,?,?,?,?,?)',(mid,'YouTube · '+vid,'.youtube',duration,1280,720,1,time.time()))
 jset('youtube:'+mid,{'video_id':vid,'url':'https://www.youtube.com/watch?v='+vid})
 jset('transcript:'+mid,result)
 update_job(jid,'done',100,'Caption YouTube siap. Jalankan analisis AI untuk menemukan poin bernilai.',{'media':mid})

def analyze_transcript(jid,p):
 r=media_row(p['media']);transcript=jget('transcript:'+r['id'],{'segments':[]})
 result=intelligence.analyze(DATA,transcript,lambda n:update_job(jid,progress=n,message='AI membaca transkrip dan memeriksa rentang klip…'))
 transcript.update(result);jset('transcript:'+r['id'],transcript)
 update_job(jid,'done',100,'Analisis selesai. '+str(len(result['candidates']))+' kandidat ditemukan.',{'media':r['id']})

def coach_reply(jid,p):
 update_job(jid,progress=15,message='Coach membaca profil, misi, dan hasil channel Anda…')
 context={key:jget(key,{} if key in ['profile','tasks','monetization','coachTasks'] else []) for key in ['profile','tasks','monetization','metrics','calendar','coachMissions','coachTasks']}
 history=jget('coachHistory',[]);research=json.loads((ROOT/'public/research.json').read_text())
 result,meta=intelligence.coach(DATA,context,p['message'],history,research)
 now=time.time();history.extend([{'role':'user','text':p['message'],'created':now},{'role':'assistant','text':result['reply'],'created':now,'meta':meta}]);jset('coachHistory',history[-80:])
 if result['niches']:jset('coachNiches',result['niches'])
 missions=jget('coachMissions',[]);titles={m['title'].lower() for m in missions}
 for m in result['missions']:
  if m['title'].lower() not in titles:
   m.update(id=secrets.token_hex(8),created=now);missions.append(m);titles.add(m['title'].lower())
 jset('coachMissions',missions[-80:]);jset('coachLast',{'meta':meta,'created':now})
 update_job(jid,'done',100,'Coach sudah menjawab. Buka Mentor channel.',{'reply':result['reply']})

def youtube_download(jid,p):
 r=media_row(p['media']);source=jget('youtube:'+r['id'])
 if not source:raise ValueError('Proyek ini bukan tautan YouTube.')
 import sys
 update_job(jid,progress=10,message='Mengambil berkas video untuk ekspor; caption tetap berasal dari YouTube…')
 dest=DATA/'jobs'/jid;dest.mkdir(exist_ok=True)
 args=[sys.executable,'-m','yt_dlp','--no-playlist','--no-progress','--no-warnings','--socket-timeout','20','--retries','1','--max-filesize','500M','--match-filter','duration <= 7200','-f','best[height<=720][ext=mp4]/best[height<=720]','--merge-output-format','mp4','-o',str(dest/'source.%(ext)s'),source['url']]
 try:
  run(args,300);files=[f for f in dest.glob('source.*') if f.suffix in ('.mp4','.webm','.mkv','.mov')]
  if not files:raise ValueError('empty')
  f=files[0];info=probe(f)
  if not info['width'] or info['duration']>7200 or f.stat().st_size>MAX_UPLOAD:raise ValueError('size')
  target=DATA/'media'/(r['id']+f.suffix);shutil.move(str(f),target)
  with db() as c:c.execute('UPDATE media SET ext=?,duration=?,width=?,height=?,audio=? WHERE id=?',(f.suffix,info['duration'],info['width'],info['height'],info['audio'],r['id']))
  update_job(jid,'done',100,'Video siap dipotong dan diekspor dengan caption YouTube.',{'media':r['id']})
 except Exception:
  raise ValueError('Berkas video tidak dapat diambil dari YouTube (akses dibatasi atau batas ukuran/durasi). Caption tetap tersimpan. Unggah berkas asli lalu hubungkan ke proyek ini.') from None
 finally:shutil.rmtree(dest,ignore_errors=True)

def enqueue_unique(kind,payload):
 with LOCK:
  with db() as c:
   if c.execute("SELECT 1 FROM jobs WHERE kind=? AND status IN ('queued','running')",(kind,)).fetchone():raise ValueError('Proses sejenis masih berjalan. Tunggu sampai selesai.')
   if kind in ('coach','analyze') and c.execute("SELECT COUNT(*) FROM jobs WHERE kind IN ('coach','analyze') AND created>?",(time.time()-86400,)).fetchone()[0]>=60:raise ValueError('Batas 60 pekerjaan AI per 24 jam tercapai. Lanjutkan misi atau coba besok.')
  return enqueue(kind,payload)

def worker():
 while True:
  jid,kind,p=QUE.get()
  try:
   if kind=='transcribe':transcribe(jid,p)
   elif kind=='render':render(jid,p)
   elif kind=='youtube':youtube_import(jid,p)
   elif kind=='analyze':analyze_transcript(jid,p)
   elif kind=='coach':coach_reply(jid,p)
   elif kind=='youtube-video':youtube_download(jid,p)
  except Exception as e:
   traceback.print_exc();update_job(jid,'error',0,str(e)[:700])
  finally:QUE.task_done()

def assessment(profile,metrics):
 minutes=float(profile.get('minutes',60));eng=profile.get('language','id')=='en'
 cadence='3 Shorts per minggu' if minutes<45 else ('1 Short per hari, 5 hari per minggu' if minutes<120 else '1 Short per hari + 1 video penjelasan per minggu')
 return {'cadence':cadence,'label':'Rencana uji 14 hari, bukan aturan algoritma','market':'Penonton berbahasa Inggris; uji satu segmen dahulu' if eng else 'Penonton Indonesia, dengan contoh yang dekat dengan keseharian','time':'19.00 waktu pasar target; bandingkan dengan 12.00 pada konten sejenis','strategy':'Utamakan tutorial rekaman sendiri. Jika memakai klip pihak lain, simpan izin dan tambahkan analisis/narasi yang benar-benar membantu penonton.','next':'Catat performa pada umur video yang sama (48 jam dan 7 hari). Bandingkan median kelompok, bukan satu video viral.','sample':len(metrics),'recommendation':'Belum cukup sampel untuk menyimpulkan waktu atau niche terbaik.' if len(metrics)<10 else 'Bandingkan minimal 5 video sejenis per variasi; periksa retensi dan subscriber per 1.000 tayangan.'}

class Handler(BaseHTTPRequestHandler):
 server_version='ViraClip'
 def log_message(self,fmt,*args):print('%s %s'%(self.address_string(),fmt%args),flush=True)
 def end_headers(self):
  self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','same-origin')
  self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-src https://www.youtube-nocookie.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
  super().end_headers()
 def send(self,data,status=200):
  raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def body(self):
  n=int(self.headers.get('Content-Length','0'))
  if n<0 or n>2*1024*1024:raise ValueError('Permintaan terlalu besar.')
  return json.loads(self.rfile.read(n) or b'{}')
 def authenticated(self):
  try:cookie=SimpleCookie(self.headers.get('Cookie',''));token=cookie['vc_session'].value
  except Exception:return False
  with db() as c:r=c.execute('SELECT expires FROM sessions WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
  return bool(r and r[0]>time.time())
 def mutation_allowed(self):
  if self.headers.get('X-ViraClip')!='1':return False
  origin=self.headers.get('Origin')
  return not origin or urlsplit(origin).netloc==self.headers.get('Host')
 def do_GET(self):
  try:self.get()
  except (ValueError,KeyError) as e:self.send({'error':str(e)},400)
  except (BrokenPipeError,ConnectionResetError):pass
  except Exception:traceback.print_exc();self.send({'error':'Terjadi kesalahan server.'},500)
 def get(self):
  path=urlsplit(self.path).path
  if path=='/api/health':return self.send({'ok':True,'app':'ViraClip'})
  if path=='/api/session':return self.send({'authenticated':self.authenticated()})
  if path.startswith(('/api/','/media/')) and not self.authenticated():return self.send({'error':'Silakan masuk.'},401)
  if path=='/api/bootstrap':
   with db() as c:
    media=[dict(x) for x in c.execute('SELECT * FROM media ORDER BY created DESC')]
    kv={r['key']:json.loads(r['value']) for r in c.execute('SELECT * FROM kv')}
    jobs=[dict(x) for x in c.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 30')]
   import importlib.util
   return self.send({'state':kv,'media':media,'jobs':jobs,'capabilities':{'ffmpeg':bool(shutil.which('ffmpeg')),'transcription':bool(importlib.util.find_spec('faster_whisper')),'model':os.environ.get('WHISPER_MODEL','base'),'mentor':'Coach AI + misi + sumber resmi',**intelligence.capabilities(DATA)},'mentor':assessment(kv.get('profile',{}),kv.get('metrics',[]))})
  if path.startswith('/api/jobs/'):
   with db() as c:r=c.execute('SELECT * FROM jobs WHERE id=?',(path.rsplit('/',1)[1],)).fetchone()
   if not r:return self.send({'error':'Proses tidak ditemukan'},404)
   data=dict(r);data['result']=json.loads(data['result']);return self.send(data)
  if path=='/api/backup':
   with db() as c:state={r['key']:json.loads(r['value']) for r in c.execute('SELECT * FROM kv')}
   return self.send({'version':1,'exported':time.time(),'state':state})
  if path.startswith('/media/'):
   parts=path.split('/')
   if len(parts)!=4 or parts[2] not in ['media','exports']:raise ValueError('Lokasi berkas tidak valid.')
   if not re.fullmatch(r'[a-f0-9]{24}\.[a-z0-9]{2,5}',parts[3]):raise ValueError('Berkas tidak valid.')
   return self.file(DATA/parts[2]/parts[3])
  if path.startswith('/api/'):return self.send({'error':'Tidak ditemukan'},404)
  if path=='/':path='/index.html'
  if path not in ['/index.html','/app.js','/style.css','/favicon.svg','/research.json']:return self.send({'error':'Tidak ditemukan'},404)
  self.file(ROOT/'public'/path.lstrip('/'))
 def file(self,path):
  if not path.is_file():return self.send({'error':'Berkas belum tersedia.'},404)
  size=path.stat().st_size;start=0;end=size-1;status=200
  rang=self.headers.get('Range','')
  if rang:
   m=re.fullmatch(r'bytes=(\d+)-(\d*)',rang)
   if not m:self.send_response(416);self.end_headers();return
   start=int(m[1]);end=min(int(m[2]) if m[2] else end,end);status=206
   if start>end:self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return
  self.send_response(status);self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream');self.send_header('Content-Length',str(max(0,end-start+1)));self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','private, no-cache')
  if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
  self.end_headers()
  with path.open('rb') as f:
   f.seek(start);remaining=end-start+1
   while remaining>0:
    chunk=f.read(min(1024*1024,remaining))
    if not chunk:break
    self.wfile.write(chunk);remaining-=len(chunk)
 def do_POST(self):
  try:
   if not self.mutation_allowed():return self.send({'error':'Permintaan tidak diizinkan.'},403)
   self.post()
  except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e:self.send({'error':str(e)},400)
  except (BrokenPipeError,ConnectionResetError):pass
  except Exception:traceback.print_exc();self.send({'error':'Terjadi kesalahan server.'},500)
 def post(self):
  path=urlsplit(self.path).path
  if path=='/api/login':
   b=self.body();ip=self.client_address[0];now=time.time()
   with LOCK:
    tries=[t for t in LOGIN_TRIES.get(ip,[]) if now-t<300];LOGIN_TRIES[ip]=tries
    if len(tries)>=10:return self.send({'error':'Terlalu banyak percobaan. Tunggu 5 menit.'},429)
   cred=json.loads((DATA/'credentials.json').read_text());pw=str(b.get('password',''))[:512]
   test=hashlib.pbkdf2_hmac('sha256',pw.encode(),cred['salt'].encode(),250000).hex()
   if not hmac.compare_digest(test,cred['hash']):
    with LOCK:LOGIN_TRIES[ip].append(now)
    return self.send({'error':'Kata sandi tidak sesuai.'},401)
   token=secrets.token_urlsafe(36)
   with db() as c:c.execute('INSERT INTO sessions VALUES (?,?)',(hashlib.sha256(token.encode()).hexdigest(),now+7*86400))
   self.send_response(200);self.send_header('Content-Type','application/json');secure='; Secure' if self.headers.get('X-Forwarded-Proto')=='https' else '';self.send_header('Set-Cookie',f'vc_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=604800{secure}');self.end_headers();self.wfile.write(b'{"ok":true}');return
  if not self.authenticated():return self.send({'error':'Silakan masuk.'},401)
  if path=='/api/logout':
   try:
    token=SimpleCookie(self.headers.get('Cookie',''))['vc_session'].value
    with db() as c:c.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),))
   except Exception:pass
   self.send_response(200);self.send_header('Set-Cookie','vc_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0');self.end_headers();return
  if path=='/api/upload':return self.upload()
  b=self.body()
  if path=='/api/youtube':
   intelligence.youtube_id(b.get('url',''))
   if b.get('language','id') not in ('id','en'):raise ValueError('Bahasa tidak didukung.')
   return self.send({'job':enqueue_unique('youtube',b)})
  if path=='/api/analyze':
   media_row(b['media']);return self.send({'job':enqueue_unique('analyze',b)})
  if path=='/api/coach':
   message=str(b.get('message','')).strip()
   if not 2<=len(message)<=4000:raise ValueError('Pesan harus 2–4.000 karakter.')
   return self.send({'job':enqueue_unique('coach',{'message':message})})
  if path=='/api/youtube-video':
   media_row(b['media'])
   if not b.get('rights'):raise ValueError('Konfirmasikan hak penggunaan video terlebih dahulu.')
   return self.send({'job':enqueue_unique('youtube-video',b)})
  if path=='/api/attach-video':
   source=media_row(b['source']);target=media_row(b['target'])
   if source['id']==target['id'] or not target['width'] or target['ext']=='.youtube':raise ValueError('Pilih berkas video unggahan yang berbeda.')
   trans=jget('transcript:'+source['id'])
   if not trans:raise ValueError('Transkrip sumber belum tersedia.')
   if max((x['end'] for x in trans['segments']),default=0)>target['duration']+5:raise ValueError('Video unggahan lebih pendek daripada transkrip. Gunakan berkas video penuh yang sama.')
   jset('transcript:'+target['id'],trans);return self.send({'media':target['id']})
  if path=='/api/state':
   key=b['key']
   if key not in ['profile','tasks','sources','calendar','metrics','monetization','researchNotes','checklist','drafts','coachTasks']:raise ValueError('Jenis data tidak didukung.')
   if key in ['profile','monetization','checklist','tasks','coachTasks'] and not isinstance(b['value'],dict):raise ValueError('Format data tidak valid.')
   if key in ['sources','calendar','metrics','drafts','researchNotes'] and not isinstance(b['value'],list):raise ValueError('Format daftar tidak valid.')
   jset(key,b['value']);return self.send({'ok':True})
  if path=='/api/transcribe':
   r=media_row(b['media'])
   if r['ext']=='.youtube':raise ValueError('Gunakan Ambil caption YouTube. Transkripsi audio tidak dijalankan untuk tautan.')
   if b.get('language') not in ['id','en',None,'']:raise ValueError('Bahasa tidak didukung.')
   return self.send({'job':enqueue('transcribe',b)})
  if path=='/api/render':
   r=media_row(b['media']);a=safe_number(b.get('start'),0,r['duration']);z=safe_number(b.get('end'),0,r['duration'])
   if not 1<=z-a<=180:raise ValueError('Panjang klip harus 1–180 detik.')
   if not r['width'] or r['ext']=='.youtube':raise ValueError('Ambil berkas video atau unggah berkas asli sebelum ekspor MP4.')
   return self.send({'job':enqueue('render',b)})
  if path=='/api/subtitles':
   r=media_row(b['media']);segments=b.get('segments')
   if segments is None:segments=parse_srt(b.get('srt',''))
   if not isinstance(segments,list) or len(segments)>10000:raise ValueError('Subtitle tidak valid.')
   clean=[]
   for s in segments:
    a=safe_number(s['start'],0,max(r['duration'],1));z=safe_number(s['end'],0,max(r['duration'],1)+5)
    if z>a:clean.append({'start':a,'end':z,'text':str(s['text'])[:1500]})
   result={**jget('transcript:'+r['id'],{}),'segments':clean,'candidates':suggestions(clean,r['duration']),'analysis':None};jset('transcript:'+r['id'],result);return self.send(result)
  if path=='/api/password':
   cred=json.loads((DATA/'credentials.json').read_text());test=hashlib.pbkdf2_hmac('sha256',str(b.get('current','')).encode(),cred['salt'].encode(),250000).hex()
   if not hmac.compare_digest(test,cred['hash']):raise ValueError('Kata sandi saat ini salah.')
   pw=str(b.get('password',''))
   if len(pw)<12:raise ValueError('Gunakan minimal 12 karakter.')
   salt=secrets.token_hex(16);(DATA/'credentials.json').write_text(json.dumps({'salt':salt,'hash':hashlib.pbkdf2_hmac('sha256',pw.encode(),salt.encode(),250000).hex()}))
   with db() as c:c.execute('DELETE FROM sessions')
   (DATA/'initial-password.txt').unlink(missing_ok=True)
   return self.send({'ok':True})
  if path=='/api/delete-media':
   r=media_row(b['id'])
   with db() as c:
    if c.execute("SELECT 1 FROM jobs WHERE status IN ('running','queued')").fetchone():raise ValueError('Tunggu semua proses selesai sebelum menghapus media.')
    c.execute('DELETE FROM media WHERE id=?',(r['id'],));c.execute('DELETE FROM kv WHERE key IN (?,?)',('transcript:'+r['id'],'youtube:'+r['id']))
   media_path(r).unlink(missing_ok=True);return self.send({'ok':True})
  return self.send({'error':'Tidak ditemukan.'},404)
 def upload(self):
  n=int(self.headers.get('Content-Length','0'));name=unquote(self.headers.get('X-Filename','video.mp4'));ext=Path(name).suffix.lower()
  if not 0<n<=MAX_UPLOAD:raise ValueError('Batas ukuran berkas 500 MB.')
  if ext not in ['.mp4','.mov','.mkv','.webm','.m4v','.mp3','.wav','.m4a','.ogg']:raise ValueError('Format media tidak didukung.')
  if shutil.disk_usage(DATA).free<n+1024**3:raise ValueError('Ruang penyimpanan tidak cukup. Hapus media lama.')
  mid=secrets.token_hex(12);path=DATA/'media'/(mid+ext)
  try:
   with path.open('wb') as f:
    remaining=n
    while remaining:
     chunk=self.rfile.read(min(1024*1024,remaining))
     if not chunk:raise ValueError('Unggahan terputus.')
     f.write(chunk);remaining-=len(chunk)
   info=probe(path)
   if not 0<info['duration']<=7200:raise ValueError('Durasi media harus lebih dari 0 dan maksimal 120 menit.')
   with db() as c:c.execute('INSERT INTO media VALUES (?,?,?,?,?,?,?,?)',(mid,Path(name).name[:180],ext,info['duration'],info['width'],info['height'],info['audio'],time.time()))
   self.send({'id':mid,**info})
  except Exception:path.unlink(missing_ok=True);raise

if __name__=='__main__':
 init();threading.Thread(target=worker,daemon=True).start()
 server=ThreadingHTTPServer((os.environ.get('HOST','127.0.0.1'),int(os.environ.get('PORT','8022'))),Handler)
 print('ViraClip ready',flush=True);server.serve_forever()
