// Render every working surface with empty and populated data, without a browser.
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict'),path=require('node:path');
const root=path.resolve(__dirname,'..'),els=new Map();
const get=s=>{if(!els.has(s))els.set(s,{innerHTML:'',textContent:'',style:{},showModal(){},close(){}});return els.get(s)};
const ctx=vm.createContext({console,URL,Intl,Date,crypto:require('node:crypto').webcrypto,setTimeout,clearTimeout,location:{hash:''},window:{addEventListener(){},scrollTo(){}},document:{querySelector:get,querySelectorAll:()=>[],addEventListener(){}},confirm:()=>true});
const js=fs.readFileSync(path.join(root,'public/app.js'),'utf8').split('\n(async()=>')[0];
vm.runInContext(js,ctx);vm.runInContext('research='+fs.readFileSync(path.join(root,'public/research.json'),'utf8'),ctx);
for(const populated of [false,true]){
 if(populated)vm.runInContext(`data={state:{profile:{name:'<script>bad</script>',minutes:60,niche:'software'},metrics:[{id:'m',title:'Test',views:100,format:'short',revenue:5,cost:2,retention:80,age:48}],sources:[{id:'s',creator:'Test',rights:'own',url:'javascript:alert(1)',contribution:'Demo'}],calendar:[{id:'c',title:'Video',date:'2026-10-08',time:'19:00',status:'idea',zone:'WIB'}]},media:[{id:'a'.repeat(24),name:'video.mp4',ext:'.mp4',width:320,height:240,duration:12,audio:1}],jobs:[],mentor:{cadence:'3 Shorts',strategy:'original',market:'ID',next:'review'},capabilities:{ffmpeg:true,transcription:false}};selected='a'.repeat(24);`,ctx);
 for(const route of ['dashboard','studio','mentor','niches','sources','calendar','analytics','monetization','research','settings']){
  const html=vm.runInContext(`views['${route}']()`,ctx);assert.ok(html.includes('<h1>'),route);assert.ok(!html.includes('href="javascript:'),route);assert.ok(!html.includes('<script>bad</script>'),route);
 }
}
assert.equal(vm.runInContext("safeLink('javascript:alert(1)','bad')",ctx),'');
assert.equal(vm.runInContext("median([1,9,3,4])",ctx),3.5);
console.log('PASS: 20 page renders, hostile text and URL escaping, median calculation. Browser layout still requires visual verification.');
vm.runInContext(`data.state['youtube:'+selected]={video_id:'jNQXAC9IVRw',url:'https://www.youtube.com/watch?v=jNQXAC9IVRw'};data.media[0].ext='.youtube';data.state['transcript:'+selected]={source:'youtube',language:'en',segments:[{start:10,end:13,text:'test'}],candidates:[{start:10,end:30,title:'<img onerror=bad>',reason:'good',method:'ai'}]};`,ctx);
for(const tab of ['edit','subtitles','candidates']){vm.runInContext(`subtab='${tab}'`,ctx);const html=vm.runInContext('studio()',ctx);assert.ok(html.includes('youtube-nocookie.com/embed/'));assert.ok(!html.includes('<img onerror=bad>'));}
assert.equal(vm.runInContext(`subtitleFile([{start:10,end:13,text:'hello'}],11,12)`,ctx),'1\n00:00:00,000 --> 00:00:01,000\nhello\n');
vm.runInContext(`data.state.coachHistory=[{role:'assistant',text:'<script>bad</script>',meta:{provider:'Test'}}];data.state.coachMissions=[{id:'m1',title:'Test',detail:'Do this',minutes:20}];`,ctx);assert.ok(!vm.runInContext('mentor()',ctx).includes('<script>bad</script>'));
console.log('PASS: YouTube tabs, SRT clipping offsets, AI reply escaping.');
