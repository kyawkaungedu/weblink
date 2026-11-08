const $ = id => document.getElementById(id);
let state = {rows: []}, currentJob = '', busy = false, generation = 0;
const safeURL = u => { try { if(typeof u!=='string')return '';const p = new URL(u); return ['https:', 'http:'].includes(p.protocol)&&p.hostname&&!p.username&&!p.password ? p.href : ''; } catch { return ''; } };
async function command(action, value) {
  if(action === 'latest') {
    const job = sessionStorage.getItem('link-job');
    if(!job) return {};
    try {return await command('status',job);} catch {sessionStorage.removeItem('link-job');return {};}
  }
  const endpoint = action === 'status' ? '/api/jobs/' + encodeURIComponent(value) : '/api/' + action;
  const options = action === 'status' ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(action === 'start' ? {url:value} : {job:value})};
  const response = await fetch(endpoint, options);
  const data = await response.json();
  if(!response.ok) throw new Error(data.error || 'Server error');
  return data;
}
function setBusy(value){busy=value;$('extract').disabled=value;$('extract').classList.toggle('is-working',value);$('extract').setAttribute('aria-busy',String(value));$('extract').textContent=value?'Link ထုတ်နေပါတယ်…':'⚡ Link အကုန်ထုတ်မယ်';$('url').disabled=value;$('cancel').hidden=!value;$('progress').hidden=!value;}
function showError(error){console.error(error);$('error').textContent=error.message||String(error);$('error').hidden=false;}
function qualityOf(r){let text=[r.resolution,r.url].filter(Boolean).join(' ');try{text=decodeURIComponent(text);}catch{}const m=text.match(/(?:^|[^0-9])(\d{3,4})[\s._-]*p\b/i);return m?m[1]+'p':'unknown';}
function filtered(){const q=$('search').value.toLowerCase().trim(),server=$('server').value,quality=$('quality').value;return (state.rows||[]).filter(r=>(!server||r.server===server)&&(!quality||qualityOf(r)===quality)&&(!q||[r.episode,r.server,r.size,r.resolution,r.url,r.error].join(' ').toLowerCase().includes(q)));}
function element(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
function render(){
  $('results').hidden=!(state.total||state.rows?.length);
  $('title').textContent=state.title||'Link ရလဒ်များ';
  $('total').textContent=state.total||0;
  $('success').textContent=(state.rows||[]).filter(r=>safeURL(r.url)).length;
  $('failed').textContent=(state.rows||[]).filter(r=>r.status==='failed').length;
  $('finishedBadge').hidden=state.status!=='complete';
  const previous=$('server').value, servers=[...new Set((state.rows||[]).map(r=>r.server))].sort();
  $('server').replaceChildren(new Option('Server အားလုံး',''),...servers.map(s=>new Option(s,s)));$('server').value=servers.includes(previous)?previous:'';
  const rows=filtered();$('shown').textContent=`ပြထားသည် ${rows.length} / ${state.total||0}`;
  $('rows').replaceChildren();
  for(const r of rows){
    const tr=element('tr');tr.append(element('td',r.episode),element('td',r.server),element('td',[r.size,qualityOf(r)==='unknown'?'Quality မသိရသေး':qualityOf(r)].filter(Boolean).join(' · ')));
    const td=element('td'),actions=element('td');const url=safeURL(r.url);
    if(url){const a=element('a',new URL(url).hostname,'link link-primary');a.href=url;a.target='_blank';a.rel='noopener noreferrer';a.title=url;td.append(a);td.className='link-cell';const b=element('button','Copy','btn btn-ghost btn-xs');b.onclick=()=>copy(url);actions.append(b);}
    else {td.append(element('span','မရပါ','badge badge-error'));td.append(element('div',r.error||'စစ်ဆေးနေဆဲ','small muted'));const source=safeURL(r.source);if(source){const a=element('a','မူရင်းကိုဖွင့်','link small');a.href=source;a.target='_blank';a.rel='noopener noreferrer';actions.append(a);}}
    tr.append(td,actions);$('rows').append(tr);
  }
  const urls=[...new Set(rows.map(r=>safeURL(r.url)).filter(Boolean))];$('copyAll').disabled=!urls.length;$('copyAll').textContent=`Copy All URLs (${urls.length})`;$('download').disabled=!rows.length;
}
function apply(data){
  state=data;render();
  if(data.status==='running'||data.status==='queued'){
    setBusy(true);$('status').textContent=data.total?`${data.done} / ${data.total} link စစ်ပြီးပါပြီ…`:'ပို့စ်ထဲက link တွေကို စုနေပါတယ်…';
    if(data.total){$('progress').max=data.total;$('progress').value=data.done;}else{$('progress').removeAttribute('value');}
  }else{
    setBusy(false);$('status').textContent=data.status==='complete'?`ပြီးပါပြီ — ${data.resolved||0} / ${data.total} URL ရပါတယ်။`:data.status==='cancelled'?'ရပ်ထားပါပြီ။ ရပြီးသား URL တွေ သုံးနိုင်ပါတယ်။':'စတင်နိုင်ပါပြီ။';
    if(data.status==='error')showError(new Error(data.error||'မအောင်မြင်ပါ။'));
  }
}
async function poll(job,version){
  try {let failures=0;while(currentJob===job){
    try {const data=await command('status',job);if(version!==generation)return;failures=0;apply(data);if(!['running','queued'].includes(data.status))break;}
    catch(err){if(version!==generation)return;if(++failures>=3)throw err;$('status').textContent='ပြန်ချိတ်ဆက်နေပါတယ်…';}
    await new Promise(r=>setTimeout(r,3500));
  }}catch(err){if(version===generation){setBusy(false);showError(err);}}
}
$('form').onsubmit=async event=>{
  event.preventDefault();if(busy)return;
  const version=++generation;
  currentJob='';sessionStorage.removeItem('link-job');
  $('error').hidden=true;$('notice').textContent='';$('copyFallback').hidden=true;
  try {
    const url=$('url').value.trim(),p=new URL(url);
    if(p.protocol!=='https:'||!['homietv.com','www.homietv.com','ysflix.com','www.ysflix.com','adsfly.org','www.adsfly.org','rmcmm.org','www.rmcmm.org','xxxmmsub.com','www.xxxmmsub.com'].includes(p.hostname)||p.username||p.password||(p.port&&p.port!=='443'))throw new Error('Support လုပ်ထားသော website မှ HTTPS link အပြည့်အစုံ ထည့်ပေးပါ။');
    setBusy(true);$('status').textContent='စတင်နေပါတယ်…';state={rows:[]};render();
    const result=await command('start',url);
    if(version!==generation){if(sessionStorage.getItem('link-job')===result.job)sessionStorage.removeItem('link-job');command('cancel',result.job).catch(console.error);return;}
    currentJob=result.job;sessionStorage.setItem('link-job',result.job);await poll(currentJob,version);
  }catch(err){if(version===generation){setBusy(false);showError(err);}}
};
$('cancel').onclick=async()=>{if(!currentJob){++generation;setBusy(false);$('status').textContent='ရပ်ထားပါပြီ။';return;}const version=generation;try{$('cancel').disabled=true;await command('cancel',currentJob);if(version===generation)$('status').textContent='ရပ်တန့်နေပါတယ်…';}catch(err){if(version===generation)showError(err);}finally{if(version===generation)$('cancel').disabled=false;}};
$('clearAll').onclick=()=>{
  const oldJob=currentJob,wasBusy=busy;++generation;currentJob='';
  sessionStorage.removeItem('link-job');state={rows:[]};
  for(const id of ['url','search','server','quality','copyFallback'])$(id).value='';
  $('error').textContent='';$('error').hidden=true;$('notice').textContent='';$('copyFallback').hidden=true;
  $('cancel').disabled=false;$('progress').value=0;setBusy(false);render();
  $('status').textContent='အားလုံးရှင်းပြီးပါပြီ ✓ Link အသစ်ထည့်နိုင်ပါပြီ။';$('url').focus();
  if(wasBusy&&oldJob)command('cancel',oldJob).catch(console.error);
};
$('search').oninput=render;$('server').onchange=render;$('quality').onchange=render;
async function copy(text){const version=generation;try{await navigator.clipboard.writeText(text);if(version!==generation)return;$('notice').textContent='ကူးပြီးပါပြီ ✓';$('copyFallback').hidden=true;}catch{if(version!==generation)return;$('copyFallback').value=text;$('copyFallback').hidden=false;$('copyFallback').select();$('notice').textContent='ဒီစာသားကို ရွေးပြီး Copy လုပ်ပေးပါ။';}}
$('copyAll').onclick=()=>copy([...new Set(filtered().map(r=>safeURL(r.url)).filter(Boolean))].join('\n'));
$('download').onclick=()=>{const text=[state.title,state.source,'',...filtered().map(r=>`${r.episode} | ${r.server} | ${r.size} | ${r.resolution}\n${safeURL(r.url)||`UNRESOLVED: ${r.source}`}\n`)].join('\n');const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));const a=element('a');a.href=url;a.download='extracted-links.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);};
// Start with a blank form; results appear only after the user submits a link.
render();

// Delegation also covers dynamically-created row Copy buttons and keyboard clicks.
document.addEventListener('click',event=>{
  const button=event.target.closest('button');
  if(!button||button.disabled||matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  const bounds=button.getBoundingClientRect(),wave=document.createElement('span');
  const size=Math.max(bounds.width,bounds.height)*2;
  wave.className='button-ripple';wave.setAttribute('aria-hidden','true');
  const x=event.detail?event.clientX-bounds.left:bounds.width/2,y=event.detail?event.clientY-bounds.top:bounds.height/2;
  Object.assign(wave.style,{width:size+'px',height:size+'px',left:x+'px',top:y+'px'});
  button.append(wave);wave.addEventListener('animationend',()=>wave.remove(),{once:true});setTimeout(()=>wave.remove(),750);
  if(button.animate)button.animate([{scale:'1'},{scale:'.95',offset:.25},{scale:'1.03',offset:.65},{scale:'1'}],{duration:320,easing:'ease-out'});
},true);
