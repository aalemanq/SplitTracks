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
  const ctr=$('stemChips'); ctr.innerHTML='';
  STEMS.forEach(s=>{
    const chip=document.createElement('div'); chip.className=`chip active ${s.key}`; chip.textContent=s.name;
    chip.onclick=()=>{ if(selectedStems.has(s.key)){selectedStems.delete(s.key);chip.className=`chip inactive ${s.key}`;} else{selectedStems.add(s.key);chip.className=`chip active ${s.key}`;} };
    ctr.appendChild(chip);
  });
  $('processBtn').disabled=false;
}

// ── Import & Process ──
$('addUrlBtn').onclick=()=>{ const url=$('youtubeUrl').value.trim(); if(url) startJob({url}); };
$('fileInput').onchange=()=>{ const f=$('fileInput').files[0]; if(f) startJob({file:f}); };

async function startJob({url,file}={}){
  const form = new FormData(); if(file) form.append('file',file); if(url) form.append('url',url);
  form.append('stems',JSON.stringify([...selectedStems]));
  $('progressPanel').hidden=false; $('studioPanel').hidden=true; $('footer').hidden=true;
  $('progressTitle').textContent='Enviando...'; $('progressPct').textContent='0%'; $('progressPhase').textContent='';
  $('cancelBtn').hidden=false; $('processBtn').disabled=true;
  _elapsedStart=Date.now(); _startElapsed();
  try{
    const job = await API.createJob(form); jobId=job.id;
    $('progressTitle').textContent='Procesando audio';
    // Fix 8: fetch chords in parallel while Demucs runs
    if(url){ fetchChordsInBackground(); }
    pollJob(jobId);
  }catch(e){ $('progressTitle').textContent='Error'; $('progressPhase').textContent=e.message||'Error'; $('cancelBtn').hidden=true; _stopElapsed(); }
}
$('cancelBtn').onclick=()=>{ if(jobId){API.cancelJob(jobId);$('cancelBtn').hidden=true;$('progressPhase').textContent='Cancelando...';} };

// Fix 8: load chords in background during separation
async function fetchChordsInBackground(){
  const url=$('youtubeUrl').value.trim();
  if(!url) return;
  // Extract artist/title from URL or use manual search
  // We need artist+title for chords, so we poll for them
  let attempts=0;
  while(attempts<30&&jobId){
    await new Promise(r=>setTimeout(r,2000));
    try{
      const j=await API.getJob(jobId);
      if(j.artist&&j.title){
        $('harmonyArtist').value=j.artist; $('harmonyTitle').value=j.title;
        searchHarmony(); return;
      }
    }catch(e){}
    attempts++;
  }
}

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
  let meta=[];
  if(job.bpm) meta.push(`<span class="metric-pill bpm">${Math.round(job.bpm)} BPM</span>`);
  if(job.key_name||job.chart?.key) meta.push(`<span class="metric-pill key">Tono: ${job.chart?.key||job.key_name||'?'}</span>`);
  $('studioMeta').innerHTML=meta.join(' ');
  buildAnalysis(job);
  $('pitchPanel').hidden=false; updatePitchDisplay();
  $('tempoPanel').hidden=false; updateTempoDisplay();
  buildChordPanels(job);
  buildMixer(job);
  if(job.artist){$('harmonyArtist').value=job.artist;} if(job.title){$('harmonyTitle').value=job.title;}
  if(job.artist&&job.title){ searchHarmony(); }
  for(const s of job.stems){ s.path=API.stemUrl(job.id,s.file); s.volume=1;s.mute=false;s.solo=false; }
  duration=await player.load(job.stems);
  $('timeline').max=duration;$('totalTime').textContent=fmtTime(duration);$('currentTime').textContent='0:00';
}

// ── Analysis metrics ── Fix 6+7: only 6 metrics, unique chord count
function buildAnalysis(job){
  const allChords = job.chart?.sections?.flatMap(s=>s.lines.flatMap(l=>l.chords))||[];
  const uniqueCount = new Set(allChords.filter(c=>c&&c!=='—')).size;
  const keys=[['key_name','TONALIDAD'],['bpm','BPM'],['duration_label','DURACIÓN'],['scale','ESCALA'],['sample_rate_label','MUESTREO'],['chord_count','ACORDES']];
  const grid=$('metricsGrid'); grid.innerHTML='';
  keys.forEach(([k,title])=>{
    let val = k==='chord_count'?uniqueCount:(job[k]!==undefined&&job[k]!==null&&job[k]!==''?job[k]:'—');
    const cell=document.createElement('div'); cell.className='metric-cell';
    cell.innerHTML=`<span class="metric-label">${title}</span><span class="metric-value">${val}</span>`;
    grid.appendChild(cell);
  });
  $('analysisPanel').hidden=false;
}

// ── Chord panels ── Fix 2: use _transposed when available
function buildChordPanels(job){
  const ctr=$('chordPanels'); ctr.innerHTML='';
  const sections = job._transposed || job.chart?.sections || [];
  if(!sections.length){ctr.innerHTML='<div class="chord-panel"><div class="chord-panel-title">Sin acordes</div></div>';return;}
  // Chords panel
  const chordsPanel=document.createElement('div'); chordsPanel.className='chord-panel';
  chordsPanel.innerHTML='<div class="chord-panel-title">Acordes de la fuente</div>';
  const chordsGrid=document.createElement('div'); chordsGrid.className='chord-grid';
  sections.forEach(sec=>{
    if(sec.title){ const t=document.createElement('div'); t.className='chord-section-title'; t.textContent=sec.title; chordsGrid.appendChild(t); }
    sec.lines.forEach(line=>{ line.chords.forEach(c=>{ const chip=document.createElement('div'); chip.className='chord-chip chords'; chip.textContent=c||'—'; chordsGrid.appendChild(chip); }); });
  });
  chordsPanel.appendChild(chordsGrid); ctr.appendChild(chordsPanel);
  // Degrees panel
  const degSections = job._degrees || [];
  if(degSections.length){
    const degPanel=document.createElement('div'); degPanel.className='chord-panel';
    degPanel.innerHTML='<div class="chord-panel-title">Grados de escala</div>';
    const degGrid=document.createElement('div'); degGrid.className='chord-grid';
    degSections.forEach(sec=>{
      if(sec.title){ const t=document.createElement('div'); t.className='chord-section-title'; t.textContent=sec.title; degGrid.appendChild(t); }
      sec.lines.forEach(line=>{ line.chords.forEach(d=>{ const chip=document.createElement('div'); chip.className='chord-chip degrees'; chip.textContent=d||'—'; degGrid.appendChild(chip); }); });
    });
    degPanel.appendChild(degGrid); ctr.appendChild(degPanel);
  }
}

// ── Mixer ── Fix 4: chip-style names + small volume
function buildMixer(job){
  const mixer=$('mixer'); mixer.innerHTML='';
  job.stems.forEach((s,i)=>{
    const displayName = s.name==='Batería completa'?'Batería':s.name==='Piano y teclados'?'Piano':s.name;
    const stemInfo = STEMS.find(st=>st.name===displayName) || {key:'other'};
    const row=document.createElement('div'); row.className='track-row';

    const chip=document.createElement('div');
    chip.className=`chip active ${stemInfo.key}`; chip.textContent=displayName;
    row.appendChild(chip);

    const btns=document.createElement('div'); btns.className='track-btns';
    const muteBtn=document.createElement('button'); muteBtn.textContent='M'; muteBtn.className='muted';
    muteBtn.onclick=()=>{ s.mute=!s.mute; muteBtn.classList.toggle('active',s.mute); player.setMute(i,s.mute); saveState(); };
    btns.appendChild(muteBtn);
    const soloBtn=document.createElement('button'); soloBtn.textContent='S'; soloBtn.className='soloed';
    soloBtn.onclick=()=>{ s.solo=!s.solo; soloBtn.classList.toggle('active',s.solo); player.setSolo(i,s.solo); saveState(); };
    btns.appendChild(soloBtn); row.appendChild(btns);

    const spacer=document.createElement('div'); spacer.className='track-spacer'; row.appendChild(spacer);

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
    selectVersion(res.candidates[0], versions.firstChild);
  }catch(e){$('harmonyStatus').textContent='Error al buscar: '+e.message;}
}

// Fix 3: fetch degrees on first load too
async function selectVersion(candidate,row){
  document.querySelectorAll('.version-row').forEach(r=>r.classList.remove('selected'));
  if(row) row.classList.add('selected');
  $('harmonyStatus').textContent=`Cargando ${candidate.source} · ${candidate.version}…`;
  try{
    const res=await API.fetchChords(candidate.url);
    if(res.chart){
      jobData.chart=res.chart;
      $('harmonyStatus').textContent=`${res.chart.source} · ${res.chart.version} · ${res.chart.display_key||'tonalidad no indicada'}${res.chart.capo?' · capo '+res.chart.capo:''}`;
      // Fix 3: also fetch degrees at pitch 0
      try{ const tp=await API.transposeChords(candidate.url,0); jobData._transposed=tp.sections; jobData._degrees=tp.degrees; }catch(e){}
      buildChordPanels(jobData); buildAnalysis(jobData);
      $('pitchUp').disabled=false; $('pitchDown').disabled=false; $('pitchReset').disabled=false;
    }
  }catch(e){$('harmonyStatus').textContent='Error: '+e.message;}
}

// ── Pitch ── Fix 1: also update audio pitch
$('pitchDown').onclick=()=>changePitch(-1); $('pitchUp').onclick=()=>changePitch(1); $('pitchReset').onclick=()=>changePitch(0,true);
async function changePitch(delta,reset=false){
  if(!jobData||player._rendering) return;
  const current=reset?0:(jobData.pitch||0)+delta;
  const semitones=Math.max(-12,Math.min(12,current));
  jobData.pitch=semitones; updatePitchDisplay();
  $('pitchDown').disabled=true; $('pitchUp').disabled=true; $('pitchReset').disabled=true;
  $('pitchValue').textContent+=' · procesando…';
  await player.setPitch(semitones);
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
  $('pitchDown').disabled=!jobData||s<=-12; $('pitchUp').disabled=!jobData||s>=12; $('pitchReset').disabled=!jobData||s===0||!jobData.chart;
}

// ── Tempo ──
$('tempoDown').onclick=()=>changeTempo(-0.05); $('tempoUp').onclick=()=>changeTempo(0.05); $('tempoReset').onclick=()=>changeTempo(1.0,true);
function changeTempo(delta,reset=false){
  if(!jobData) return;
  const current=reset?1.0:(jobData.tempo||1.0)+delta;
  const tempo=Math.round(Math.max(0.5,Math.min(2.0,current))*100)/100;
  jobData.tempo=tempo; updateTempoDisplay();
  player.setTempo(tempo);
}
function updateTempoDisplay(){
  const t=jobData?.tempo||1.0;
  const pct=Math.round((t-1.0)*100);
  if(t===1.0){$('tempoValue').textContent='×1.00 · original';}
  else{const sign=pct>=0?'+':'';$('tempoValue').textContent=`×${t.toFixed(2)} · ${sign}${pct}%`;}
  $('tempoDown').disabled=!jobData||t<=0.5; $('tempoUp').disabled=!jobData||t>=2.0; $('tempoReset').disabled=!jobData||t===1.0;
}

// ── Transport ──
$('playBtn').onclick=()=>{ if(player.playing){player.pause();$('playBtn').textContent='▶';}else{player.play();$('playBtn').textContent='⏸';} };
$('stopBtn').onclick=()=>{player.stop();$('playBtn').textContent='▶';$('timeline').value=0;$('currentTime').textContent='0:00';};
$('timeline').oninput=()=>{ player.seek(parseFloat($('timeline').value)); };
$('masterVolume').oninput=()=>{ player.setMasterVolume(parseInt($('masterVolume').value)/100); };
document.onkeydown=e=>{ if(e.code==='Space'){e.preventDefault();$('playBtn').click();} };

setInterval(()=>{ if(player.playing){ const pos=player.position(); $('timeline').value=pos; $('currentTime').textContent=fmtTime(pos); if(pos>=duration-0.2){player.playing=false;$('playBtn').textContent='▶';} } },150);

// ── Export ──
$('exportMixBtn').onclick=async()=>{ if(!jobId) return;
  try{const res=await fetch(API.mixUrl(jobId),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stems:jobData.stems})}); const blob=await res.blob(); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='mezcla.mp3'; a.click();}catch(e){alert('Error exportando mezcla');}
};
$('exportStemsBtn').onclick=async()=>{ if(!jobId) return;
  try{const res=await fetch(`/api/jobs/${jobId}/export/stems`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stems:jobData.stems})}); const data=await res.json(); data.files.forEach(f=>{window.open(f.url,'_blank');});}catch(e){alert('Error exportando pistas');}
};

// ── State ──
function saveState(){ try{localStorage.setItem('splittracks_mixer',JSON.stringify(jobData?.stems?.map(s=>({name:s.name,volume:s.volume,mute:s.mute,solo:s.solo}))))}catch(e){} }
function loadState(){ try{const d=JSON.parse(localStorage.getItem('splittracks_mixer'));if(d&&jobData) d.forEach(s=>{const stem=jobData.stems.find(ss=>ss.name===s.name);if(stem){stem.volume=s.volume??1;stem.mute=s.mute??false;stem.solo=s.solo??false;}});}catch(e){} }

buildChips();
