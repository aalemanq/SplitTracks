const player = new Player();
let jobId = null, jobData = null, duration = 0, updateTimer = null, _elapsedStart = 0, _elapsedTimer = null;

const STEMS = [
  {key:'vocals',name:'Voces',color:'#d33682'},{key:'drums',name:'Batería',color:'#cb4b16'},
  {key:'bass',name:'Bajo',color:'#268bd2'},{key:'guitar',name:'Guitarra',color:'#6c71c4'},
  {key:'piano',name:'Piano',color:'#b58900'},{key:'other',name:'Other',color:'#859900'}
];
let selectedStems = new Set(STEMS.map(s=>s.key));

const $ = id => document.getElementById(id);

function fmtTime(sec){ const m=Math.floor(sec/60), s=Math.floor(sec%60); return `${m}:${String(s).padStart(2,'0')}`; }

// ── Stem chips ──
function buildChips(){
  const ctr = $('stemChips'); ctr.innerHTML='';
  STEMS.forEach(s=>{
    const chip = document.createElement('div');
    chip.className=`chip active ${s.key}`; chip.textContent=s.name;
    chip.onclick=()=>{
      if(selectedStems.has(s.key)){selectedStems.delete(s.key);chip.className=`chip inactive ${s.key}`;}
      else{selectedStems.add(s.key);chip.className=`chip active ${s.key}`;}
    };
    ctr.appendChild(chip);
  });
  $('processBtn').disabled=false;
}

// ── Import ──
$('addUrlBtn').onclick=()=>{ const url=$('youtubeUrl').value.trim(); if(url) startJob({url}); };
$('fileInput').onchange=()=>{ const f=$('fileInput').files[0]; if(f) startJob({file:f}); };

// ── Process ──
async function startJob({url,file}={}){
  const form = new FormData();
  if(file) form.append('file',file);
  if(url) form.append('url',url);
  form.append('stems',JSON.stringify([...selectedStems]));
  $('progressPanel').hidden=false; $('studioPanel').hidden=true; $('footer').hidden=true;
  $('progressTitle').textContent='Enviando...'; $('progressPct').textContent='0%'; $('progressPhase').textContent='';
  $('cancelBtn').hidden=false; $('processBtn').disabled=true;
  _elapsedStart=Date.now(); _startElapsed();
  try{
    const job = await API.createJob(form);
    jobId=job.id; $('progressTitle').textContent='Procesando audio'; pollJob(jobId);
  }catch(e){
    $('progressTitle').textContent='Error'; $('progressPhase').textContent=e.message||'Error'; $('cancelBtn').hidden=true; _stopElapsed();
  }
}
$('cancelBtn').onclick=()=>{ if(jobId){API.cancelJob(jobId);$('cancelBtn').hidden=true;$('progressPhase').textContent='Cancelando...';} };

// ── Poll ──
async function pollJob(id){
  if(id!==jobId) return;
  try{
    const job = await API.getJob(id); if(id!==jobId) return;
    const pct=Math.round(job.progress*100);
    $('progressFill').style.width=pct+'%'; $('progressPct').textContent=pct+'%'; $('progressPhase').textContent=job.phase||'';
    if(job.status==='done'&&job.stems&&job.stems.length>0){
      $('progressPanel').hidden=true; _stopElapsed(); jobData=job; buildStudio(job); return;
    }
    if(job.status==='error'){$('progressTitle').textContent='Error en el proceso';$('cancelBtn').hidden=true;_stopElapsed();return;}
    updateTimer=setTimeout(()=>pollJob(id),800);
  }catch(e){updateTimer=setTimeout(()=>pollJob(id),1500);}
}
function _startElapsed(){ _elapsedTimer=setInterval(()=>{ const s=((Date.now()-_elapsedStart)/1000).toFixed(1); $('progressElapsed').hidden=false; $('progressElapsed').textContent=`Tiempo: ${s}s`; },250); }
function _stopElapsed(){ clearInterval(_elapsedTimer); $('progressElapsed').hidden=true; }

// ── Build studio ──
async function buildStudio(job){
  $('studioPanel').hidden=false; $('footer').hidden=false; $('exportMixBtn').disabled=false; $('exportStemsBtn').disabled=false;
  // Meta
  let meta=[];
  if(job.bpm) meta.push(`<span class="metric-pill bpm">${Math.round(job.bpm)} BPM</span>`);
  if(job.key_name||job.chart?.key) meta.push(`<span class="metric-pill key">Tono: ${job.chart?.key||job.key_name||'?'}</span>`);
  $('studioMeta').innerHTML=meta.join(' ');
  // Analysis panel
  buildAnalysis(job);
  // Pitch
  $('pitchPanel').hidden=false; updatePitchDisplay();
  // Chords
  buildChordPanels(job);
  // Mixer
  buildMixer(job);
  // Harmony pre-fill
  if(job.artist){$('harmonyArtist').value=job.artist;}
  if(job.title){$('harmonyTitle').value=job.title;}
  if(job.artist&&job.title){searchHarmony();}
  // Player
  for(const s of job.stems){ s.path=API.stemUrl(job.id,s.file); s.volume=1;s.mute=false;s.solo=false; }
  duration=await player.load(job.stems);
  $('timeline').max=duration;$('totalTime').textContent=fmtTime(duration);$('currentTime').textContent='0:00';
}

// ── Analysis metrics ──
function buildAnalysis(job){
  const chordCount = job.chord_count || (job.chart?.sections?.reduce((n,s)=>n+s.lines.reduce((m,l)=>m+l.chords.length,0),0) || 0);
  const keys=[['key_name','TONALIDAD'],['bpm','BPM'],['duration_label','DURACIÓN'],['scale','ESCALA'],['lufs','LUFS'],['dynamic_range_db','DINÁMICA'],['format_name','FORMATO'],['sample_rate_label','MUESTREO'],['channels','CANALES'],['tempo_confidence','TEMPO ESTABLE'],['key_confidence','CONFIANZA TONAL'],['chord_count','ACORDES']];
  const grid=$('metricsGrid'); grid.innerHTML='';
  keys.forEach(([k,title])=>{
    let val = k==='chord_count'?chordCount:(job[k]!==undefined&&job[k]!==null&&job[k]!==''?job[k]:'—');
    const cell=document.createElement('div'); cell.className='metric-cell';
    cell.innerHTML=`<span class="metric-label">${title}</span><span class="metric-value">${val}</span>`;
    grid.appendChild(cell);
  });
  $('analysisPanel').hidden=false;
}

// ── Chord panels ──
function buildChordPanels(job){
  const ctr=$('chordPanels'); ctr.innerHTML='';
  const chart=job.chart;
  if(!chart||!chart.sections||chart.sections.length===0){ctr.innerHTML='<div class="chord-panel"><div class="chord-panel-title">Sin acordes</div></div>';return;}
  // Chords panel
  const chordsPanel=document.createElement('div'); chordsPanel.className='chord-panel';
  chordsPanel.innerHTML='<div class="chord-panel-title">Acordes de la fuente</div>';
  const chordsGrid=document.createElement('div'); chordsGrid.className='chord-grid';
  chart.sections.forEach(sec=>{
    if(sec.title){ const t=document.createElement('div'); t.className='chord-section-title'; t.textContent=sec.title; chordsGrid.appendChild(t); }
    sec.lines.forEach(line=>{ line.chords.forEach(c=>{ const chip=document.createElement('div'); chip.className='chord-chip chords'; chip.textContent=c||'—'; chordsGrid.appendChild(chip); }); });
  });
  chordsPanel.appendChild(chordsGrid); ctr.appendChild(chordsPanel);
  // Degrees panel (if available from pitch)
  if(job._degrees){
    const degPanel=document.createElement('div'); degPanel.className='chord-panel';
    degPanel.innerHTML='<div class="chord-panel-title">Grados de escala</div>';
    const degGrid=document.createElement('div'); degGrid.className='chord-grid';
    job._degrees.forEach(sec=>{
      if(sec.title){ const t=document.createElement('div'); t.className='chord-section-title'; t.textContent=sec.title; degGrid.appendChild(t); }
      sec.lines.forEach(line=>{ line.chords.forEach(d=>{ const chip=document.createElement('div'); chip.className='chord-chip degrees'; chip.textContent=d||'—'; degGrid.appendChild(chip); }); });
    });
    degPanel.appendChild(degGrid); ctr.appendChild(degPanel);
  }
}

// ── Mixer ──
function buildMixer(job){
  const mixer=$('mixer'); mixer.innerHTML='';
  job.stems.forEach((s,i)=>{
    const row=document.createElement('div'); row.className='track-row';
    const color=document.createElement('div'); color.className='track-color'; color.style.background=s.color; row.appendChild(color);
    const name=document.createElement('div'); name.className='track-name'; name.textContent=s.name; row.appendChild(name);
    const btns=document.createElement('div'); btns.className='track-btns';
    const muteBtn=document.createElement('button'); muteBtn.textContent='M'; muteBtn.className='muted';
    muteBtn.onclick=()=>{ s.mute=!s.mute; muteBtn.classList.toggle('active',s.mute); player.setMute(i,s.mute); saveState(); };
    btns.appendChild(muteBtn);
    const soloBtn=document.createElement('button'); soloBtn.textContent='S'; soloBtn.className='soloed';
    soloBtn.onclick=()=>{ s.solo=!s.solo; soloBtn.classList.toggle('active',s.solo); player.setSolo(i,s.solo); saveState(); };
    btns.appendChild(soloBtn); row.appendChild(btns);
    const volWrap=document.createElement('div'); volWrap.className='track-volume';
    const volSlider=document.createElement('input'); volSlider.type='range'; volSlider.min='0'; volSlider.max='125'; volSlider.value='100';
    const volVal=document.createElement('span'); volVal.className='track-vol-val'; volVal.textContent='100%';
    volSlider.oninput=()=>{ const v=parseInt(volSlider.value)/100; player.setVolume(i,v); volVal.textContent=Math.round(v*100)+'%'; saveState(); };
    volWrap.appendChild(volSlider); row.appendChild(volWrap); row.appendChild(volVal);
    const expBtn=document.createElement('button'); expBtn.className='track-export'; expBtn.textContent='MP3';
    expBtn.onclick=()=>{ window.open(API.stemMp3Url(job.id,s.file),'_blank'); };
    row.appendChild(expBtn); mixer.appendChild(row);
  });
}

// ── Harmony search ──
$('harmonySearchBtn').onclick=searchHarmony;
async function searchHarmony(){
  const artist=$('harmonyArtist').value.trim(), title=$('harmonyTitle').value.trim();
  if(!artist||!title){$('harmonyStatus').textContent='Escribe artista y canción.';return;}
  $('harmonyStatus').textContent='Buscando versiones en Cifra Club…';
  try{
    const res=await API.searchChords(artist,title);
    const versions=$('harmonyVersions'); versions.innerHTML='';
    if(!res.candidates||res.candidates.length===0){$('harmonyStatus').textContent='No hay versiones disponibles.';return;}
    $('harmonyStatus').textContent=`${res.candidates.length} versiones encontradas`;
    res.candidates.forEach((c,i)=>{
      const row=document.createElement('div'); row.className='version-row'; if(i===0) row.classList.add('selected');
      const info=document.createElement('div'); info.className='version-info';
      let detail=[]; if(c.key) detail.push(c.key+(c.scale?' '+c.scale:'')); if(c.capo&&c.capo>0) detail.push('capo '+c.capo); if(c.instrument) detail.push(c.instrument); if(c.reviewed) detail.push('revisada');
      info.innerHTML=`<div class="version-name">${c.source} · ${c.version}</div><div class="version-detail">${detail.join(' · ')||'tonalidad y formato se leerán al abrirla'}</div>`;
      row.appendChild(info);
      const btnOpen=document.createElement('button'); btnOpen.className='btn btn-sm btn-outline'; btnOpen.textContent='Fuente'; btnOpen.onclick=e=>{e.stopPropagation();window.open(c.url,'_blank');};
      const btnUse=document.createElement('button'); btnUse.className='btn btn-sm btn-cyan'; btnUse.textContent='Usar'; btnUse.onclick=e=>{e.stopPropagation();selectVersion(c,row);};
      row.appendChild(btnOpen); row.appendChild(btnUse);
      row.onclick=()=>selectVersion(c,row);
      versions.appendChild(row);
    });
    // Auto-select first
    selectVersion(res.candidates[0], versions.firstChild);
  }catch(e){$('harmonyStatus').textContent='Error al buscar: '+e.message;}
}

async function selectVersion(candidate,row){
  document.querySelectorAll('.version-row').forEach(r=>r.classList.remove('selected'));
  if(row) row.classList.add('selected');
  $('harmonyStatus').textContent=`Cargando ${candidate.source} · ${candidate.version}…`;
  try{
    const res=await API.fetchChords(candidate.url);
    if(res.chart){
      jobData.chart=res.chart;
      jobData.chord_count=res.chart.sections?res.chart.sections.reduce((n,s)=>n+s.lines.reduce((m,l)=>m+l.chords.length,0),0):0;
      $('harmonyStatus').textContent=`${res.chart.source} · ${res.chart.version} · ${res.chart.display_key||'tonalidad no indicada'}${res.chart.capo?' · capo '+res.chart.capo:''}`;
      buildChordPanels(jobData);
      buildAnalysis(jobData);
      jobData._degrees = null; // reset
      $('pitchUp').disabled=false; $('pitchDown').disabled=false; $('pitchReset').disabled=false;
    }
  }catch(e){$('harmonyStatus').textContent='Error: '+e.message;}
}

// ── Pitch ──
$('pitchDown').onclick=()=>changePitch(-1);
$('pitchUp').onclick=()=>changePitch(1);
$('pitchReset').onclick=()=>changePitch(0,true);
async function changePitch(delta,reset=false){
  if(!jobData) return;
  const current=reset?0:(jobData.pitch||0)+delta;
  const semitones=Math.max(-12,Math.min(12,current));
  jobData.pitch=semitones;
  updatePitchDisplay();
  if(jobData.chart?.url){
    try{
      const res=await API.transposeChords(jobData.chart.url,semitones);
      if(res.sections){jobData._transposed=res.sections; jobData._degrees=res.degrees; buildChordPanels(jobData);}
      if(res.key){ let meta=[]; if(jobData.bpm) meta.push(`<span class="metric-pill bpm">${Math.round(jobData.bpm)} BPM</span>`); meta.push(`<span class="metric-pill key">Tono: ${res.key}</span>`); $('studioMeta').innerHTML=meta.join(' '); }
    }catch(e){}
  }
}
function updatePitchDisplay(){
  const s=jobData?.pitch||0;
  if(s===0){$('pitchValue').textContent='Original · 0 semitonos';}
  else{const sign=s>0?'+':'−';$('pitchValue').textContent=`${sign}${Math.abs(s)} ${Math.abs(s)===1?'semitono':'semitonos'}`;}
  $('pitchDown').disabled=!jobData||s<=-12;
  $('pitchUp').disabled=!jobData||s>=12;
  $('pitchReset').disabled=!jobData||s===0||!jobData.chart;
}

// ── Transport ──
$('playBtn').onclick=()=>{ if(player.playing){player.pause();$('playBtn').textContent='▶';}else{player.play();$('playBtn').textContent='⏸';} };
$('stopBtn').onclick=()=>{player.stop();$('playBtn').textContent='▶';$('timeline').value=0;$('currentTime').textContent='0:00';};
$('timeline').oninput=()=>{ player.seek(parseFloat($('timeline').value)); };
$('masterVolume').oninput=()=>{ player.setMasterVolume(parseInt($('masterVolume').value)/100); };
document.onkeydown=e=>{ if(e.code==='Space'){e.preventDefault();$('playBtn').click();} };

setInterval(()=>{
  if(player.playing){
    const pos=player.position(); $('timeline').value=pos; $('currentTime').textContent=fmtTime(pos);
    if(pos>=duration-0.2){player.playing=false;$('playBtn').textContent='▶';}
  }
},150);

// ── Export ──
$('exportMixBtn').onclick=async()=>{ if(!jobId) return;
  try{const res=await fetch(API.mixUrl(jobId),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stems:jobData.stems})});
    const blob=await res.blob(); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='mezcla.mp3'; a.click();}catch(e){alert('Error exportando mezcla');}
};
$('exportStemsBtn').onclick=async()=>{ if(!jobId) return;
  try{const res=await fetch(`/api/jobs/${jobId}/export/stems`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stems:jobData.stems})});
    const data=await res.json(); data.files.forEach(f=>{window.open(f.url,'_blank');});}catch(e){alert('Error exportando pistas');}
};

// ── State ──
function saveState(){ try{localStorage.setItem('splittracks_mixer',JSON.stringify(jobData?.stems?.map(s=>({name:s.name,volume:s.volume,mute:s.mute,solo:s.solo}))))}catch(e){} }
function loadState(){ try{const d=JSON.parse(localStorage.getItem('splittracks_mixer'));if(d&&jobData) d.forEach(s=>{const stem=jobData.stems.find(ss=>ss.name===s.name);if(stem){stem.volume=s.volume||1;stem.mute=s.mute||false;stem.solo=s.solo||false;}});}catch(e){} }

// ── Init ──
buildChips();
