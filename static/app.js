const $ = id => document.getElementById(id);
let token, files = [], selected = null, busy = false, ready = false, stages = [], viewed = null, polling = false;
let thumbnailURLs = [];
function notice(message) { $('notice').textContent = message || ''; $('notice').hidden = !message; }
async function api(path, data, extra = {}) {
  const options = data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-Head-Studio-Token':token}, body:JSON.stringify(data)};
  const response = await fetch(path, {...options,...extra});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || 'Request failed');
  return value;
}
function updateButton() { $('build').disabled = busy || !ready || files.length < 12 || files.length > 200; }
function choose(input) {
  if (busy) return;
  const accepted = /\.(jpe?g|png|hei[cf]|tiff?|webp)$/i;
  files = Array.from(input).filter(file => accepted.test(file.name)).sort((a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true}));
  thumbnailURLs.forEach(URL.revokeObjectURL); thumbnailURLs=[]; $('thumbs').replaceChildren();
  $('selection').textContent = `${files.length} photos selected · ${(files.reduce((s,f)=>s+f.size,0)/1024/1024).toFixed(0)} MB`;
  for (const file of files.filter(f=>/\.(jpe?g|png|webp)$/i.test(f.name)).slice(0,8)) {
    const img = document.createElement('img'); const url = URL.createObjectURL(file); thumbnailURLs.push(url); img.src=url;img.alt=file.name;$('thumbs').append(img);
  }
  notice(files.length && (files.length < 12 || files.length > 200) ? 'Choose 12–200 photos. Around 80–150 is a good starting point for a full head.' : '');
  updateButton();
}
$('photos').addEventListener('change',event=>choose(event.target.files));
for (const name of ['dragenter','dragover']) $('drop').addEventListener(name,event=>{event.preventDefault();$('drop').classList.add('over');});
for (const name of ['dragleave','drop']) $('drop').addEventListener(name,event=>{event.preventDefault();$('drop').classList.remove('over');});
$('drop').addEventListener('drop',event=>choose(event.dataTransfer.files));
$('build').addEventListener('click',async()=>{
  busy=true;updateButton();notice('');
  try {
    const project=await api('/api/projects',{name:$('name').value,preset:$('quality').value}); selected=project.id;
    $('progress-panel').hidden=false; $('progress-panel').scrollIntoView({behavior:'smooth',block:'nearest'});
    for(let i=0;i<files.length;i++){
      $('message').textContent=`Importing photo ${i+1} of ${files.length}…`;
      await api(`/api/projects/${selected}/photos`,null,{method:'POST',headers:{'X-Head-Studio-Token':token,'X-Filename':encodeURIComponent(files[i].name),'Content-Type':'application/octet-stream'},body:files[i]});
    }
    await api(`/api/projects/${selected}/start`,{});
  } catch(error){notice(error.message);}
  finally {busy=false;updateButton();await refresh();}
});
$('cancel').addEventListener('click',async()=>{try{await api(`/api/projects/${selected}/cancel`,{});$('message').textContent='Stopping processing…';}catch(error){notice(error.message);}});
async function display(state){
  $('progress-panel').hidden=false;$('project-title').textContent=state.name;$('message').textContent=state.message;
  $('progress').value=state.step;$('badge').textContent=state.state==='complete'?'Model ready':state.state;
  $('cancel').hidden=state.state!=='running';
  $('warnings').textContent=(state.warnings||[]).join(' ');
  $('output').textContent=state.output?`Saved to ${state.output}`:'';
  $('stages').replaceChildren(...stages.map((label,index)=>{const el=document.createElement('span');el.textContent=label;el.className=index<state.step?'done':index===state.step?'current':'';return el;}));
  $('download').hidden=state.state!=='complete';
  if(state.state==='complete'){
    $('download').href=`/api/projects/${state.id}/download`;
    if(viewed!==state.id){
      viewed=state.id;
      try{const viewer=await import('/viewer.js');await viewer.loadModel(`/api/projects/${state.id}/result/`);}
      catch(error){notice(`Your model is saved, but the preview could not load: ${error.message}. Download the ZIP to open it in Blender or MeshLab.`);}
    }
  }else if(viewed){
    const viewer=await import('/viewer.js');viewer.clearModel();viewed=null;
  }
  const log=await api(`/api/projects/${state.id}/log`);$('log').textContent=log.text;$('log').scrollTop=$('log').scrollHeight;
}
async function refresh(){
  if(polling||busy)return;polling=true;
  try{
    const projects=await api('/api/projects');
    const active=projects.find(p=>p.state==='running');
    $('build').disabled=!!active||!ready||files.length<12||files.length>200;
    if(!selected&&projects.length)selected=(active||projects[0]).id;
    const state=projects.find(p=>p.id===selected);if(state)await display(state);
    $('history').replaceChildren();
    if(!projects.length)$('history').textContent='Your projects will be saved here.';
    for(const project of projects){
      const row=document.createElement('div');row.className='history-row';
      const title=document.createElement('strong');title.textContent=project.name;
      const info=document.createElement('span');info.textContent=`${project.count} photos · ${project.state}`;
      const button=document.createElement('button');button.textContent='View';button.onclick=()=>{selected=project.id;refresh();};
      row.append(title,info,button);$('history').append(row);
    }
  }catch(error){notice(`Cannot connect to Head Studio: ${error.message}. Keep its Terminal window open.`);}
  finally{polling=false;}
}
async function init(){
  try{const info=await api('/api/info');token=info.token;stages=info.steps;ready=Object.values(info.tools).every(Boolean);
    $('tools').textContent=ready?`COLMAP + OpenMVS ready · ${info.free_gb} GB free`:'Some tools are missing. See README.md for setup.';
    updateButton();await refresh();setInterval(refresh,2000);
  }catch(error){notice(error.message);}
}
init();
