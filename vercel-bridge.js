// This adapter is appended only by the Vercel /client.js route.
// Existing filters, rendering, Clear All, themes and animation stay unchanged.
(() => {
  let active = null, collecting = null;
  const snapshot = job => ({job:job.id, source:job.source, title:job.title,
    status:job.cancelled?'cancelled':job.next>=job.pending.length?'complete':'running',
    total:job.total, done:job.results.filter(Boolean).length,
    resolved:job.results.filter(r=>r&&r.url).length, rows:job.results.filter(Boolean)});
  async function post(path, body, signal) {
    const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body), signal});
    let data;
    try { data = await response.json(); }
    catch { throw new Error('Server timeout သို့မဟုတ် response မမှန်ပါ။ ပြန်စမ်းပေးပါ။'); }
    if (!response.ok) throw new Error(data.error || 'Server request failed');
    return data;
  }
  command = async function(action, value) {
    if(action==='latest')return {};
    if(action==='start') {
      const version=generation, controller=new AbortController();
      active=null;
      collecting=controller;
      let data;
      try { data=await post('/api/collect', {url:value},controller.signal); }
      finally { if(collecting===controller)collecting=null; }
      const job = {id:crypto.randomUUID().replaceAll('-',''),source:data.source,title:data.title,
        total:data.total,results:new Array(data.rows.length).fill(null),pending:[],next:0,cancelled:false,controller:null};
      // A response after Clear All must not replace a newer extraction.
      if(version!==generation)return {job:job.id};
      data.rows.forEach((row,index)=>{
        const host=new URL(row.source).hostname;
        if(['adsfly.org','www.adsfly.org'].includes(host))job.pending.push({row,index});
        else job.results[index]={...row,url:row.source,status:'direct'};
      });
      active=job;
      return {job:job.id};
    }
    const job=active;
    if(!job||job.id!==value)throw new Error('Job မတွေ့ပါ။ Link ပြန်ထည့်ပေးပါ။');
    if(action==='cancel') {
      job.cancelled=true;
      if(job.controller)job.controller.abort();
      return {cancelled:true};
    }
    if(action!=='status')throw new Error('Unknown action');
    if(job.cancelled||job.next>=job.pending.length)return snapshot(job);
    const batch=job.pending.slice(job.next,job.next+4);
    job.controller=new AbortController();
    try {
      const result=await post('/api/resolve',{rows:batch.map(item=>item.row)},job.controller.signal);
      if(!Array.isArray(result.rows)||result.rows.length!==batch.length)throw new Error('Invalid batch response');
      if(!job.cancelled){result.rows.forEach((row,i)=>{job.results[batch[i].index]=row;});job.next+=batch.length;}
    }catch(error){
      if(!job.cancelled){
        // Preserve completed batches and make failed links visible/exportable.
        batch.forEach(item=>{job.results[item.index]={...item.row,url:'',status:'failed',error:error.message};});
        job.next+=batch.length;
      }
    }finally{job.controller=null;}
    return snapshot(job);
  };
  $('cancel').onclick=()=>{
    ++generation;
    currentJob='';
    if(collecting){collecting.abort();collecting=null;}
    if(active){
      active.cancelled=true;
      if(active.controller)active.controller.abort();
      apply(snapshot(active));
    }else{
      setBusy(false);
      $('status').textContent='ရပ်ထားပါပြီ။';
    }
    $('cancel').disabled=false;
  };
})();
