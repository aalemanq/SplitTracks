const player = new Player();
let jobId = null;
let duration = 0;
let updateTimer = null;
let stemsData = [];

const STEMS = [
  { key: 'vocals', name: 'Voces', color: '#d33682' },
  { key: 'drums', name: 'Batería', color: '#cb4b16' },
  { key: 'bass', name: 'Bajo', color: '#268bd2' },
  { key: 'guitar', name: 'Guitarra', color: '#6c71c4' },
  { key: 'piano', name: 'Piano', color: '#b58900' },
  { key: 'other', name: 'Other', color: '#859900' },
];
let selectedStems = new Set(STEMS.map(s => s.key));

const $ = id => document.getElementById(id);

function fmtTime(sec) {
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

// ── Tabs ──
document.querySelectorAll('.import-tab').forEach(tab => {
  tab.onclick = () => {
    document.querySelectorAll('.import-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const target = tab.dataset.tab;
    $('importUrl').classList.toggle('hidden', target !== 'url');
    $('importFile').classList.toggle('hidden', target !== 'file');
  };
});

// ── Stem chips ──
function buildChips() {
  const ctr = $('stemChips');
  ctr.innerHTML = '';
  STEMS.forEach(s => {
    const chip = document.createElement('div');
    chip.className = `chip active ${s.key}`;
    chip.textContent = s.name;
    chip.onclick = () => {
      if (selectedStems.has(s.key)) {
        selectedStems.delete(s.key);
        chip.className = `chip inactive ${s.key}`;
      } else {
        selectedStems.add(s.key);
        chip.className = `chip active ${s.key}`;
      }
    };
    ctr.appendChild(chip);
  });
  $('processBtn').disabled = false;
}

// ── Process button ──
$('processBtn').onclick = () => {
  const url = $('youtubeUrl').value.trim();
  const fileInput = $('fileInput');
  const file = fileInput.files[0];

  if (url) {
    startJob({ url });
  } else if (file) {
    startJob({ file });
  } else {
    startJob({ url: $('youtubeUrl').value.trim() });
  }
};

// ── Start job ──
async function startJob({ url, file } = {}) {
  if (!url && !file) return;

  const form = new FormData();
  if (file) form.append('file', file);
  if (url) form.append('url', url);
  form.append('stems', JSON.stringify([...selectedStems]));

  $('importPanel').hidden = true;
  $('progressPanel').hidden = false;
  $('studioPanel').hidden = true;
  $('footer').hidden = true;
  $('cancelBtn').hidden = false;
  $('progressTitle').textContent = 'Enviando...';
  $('progressPercent').textContent = '0%';
  $('progressPhase').textContent = '';

  try {
    const job = await API.createJob(form);
    jobId = job.id;
    $('progressTitle').textContent = 'Procesando audio';
    $('cancelBtn').hidden = false;
    pollJob(jobId);
  } catch (e) {
    $('progressTitle').textContent = 'Error';
    $('progressPhase').textContent = e.message || 'Error desconocido';
    $('cancelBtn').hidden = true;
  }
}

$('cancelBtn').onclick = () => {
  if (jobId) {
    API.cancelJob(jobId);
    $('cancelBtn').hidden = true;
    $('progressPhase').textContent = 'Cancelando...';
  }
};

// ── Poll job ──
async function pollJob(id) {
  if (id !== jobId) return;
  try {
    const job = await API.getJob(id);
    if (id !== jobId) return;

    const pct = Math.round(job.progress * 100);
    $('progressFill').style.width = pct + '%';
    $('progressPercent').textContent = pct + '%';
    $('progressPhase').textContent = job.phase || '';

    if (job.status === 'done' && job.stems && job.stems.length > 0) {
      $('progressPanel').hidden = true;
      buildStudio(job);
      return;
    }

    if (job.status === 'error') {
      $('progressTitle').textContent = 'Error en el proceso';
      $('cancelBtn').hidden = true;
      return;
    }

    updateTimer = setTimeout(() => pollJob(id), 800);
  } catch (e) {
    updateTimer = setTimeout(() => pollJob(id), 1500);
  }
}

// ── Build studio ──
async function buildStudio(job) {
  $('studioPanel').hidden = false;
  $('footer').hidden = false;

  stemsData = job.stems;
  for (const s of stemsData) {
    s.path = API.stemUrl(job.id, s.file);
    s.volume = 1.0;
    s.mute = false;
    s.solo = false;
  }

  // Meta info
  let meta = [];
  if (job.bpm) meta.push(job.bpm + ' BPM');
  if (job.key) meta.push('Tono: ' + job.key);
  $('studioMeta').textContent = meta.join(' · ');

  // Waveform placeholder
  drawWaveformPlaceholder();

  // Mixer
  const mixer = $('mixer');
  mixer.innerHTML = '';

  for (let i = 0; i < stemsData.length; i++) {
    const s = stemsData[i];
    const row = document.createElement('div');
    row.className = 'track-row';

    const color = document.createElement('div');
    color.className = 'track-color';
    color.style.background = s.color;
    row.appendChild(color);

    const name = document.createElement('div');
    name.className = 'track-name';
    name.textContent = s.name;
    row.appendChild(name);

    const btns = document.createElement('div');
    btns.className = 'track-btns';

    const muteBtn = document.createElement('button');
    muteBtn.textContent = 'M';
    muteBtn.className = 'muted';
    muteBtn.onclick = () => {
      s.mute = !s.mute;
      muteBtn.classList.toggle('active', s.mute);
      player.setMute(i, s.mute);
    };
    btns.appendChild(muteBtn);

    const soloBtn = document.createElement('button');
    soloBtn.textContent = 'S';
    soloBtn.className = 'soloed';
    soloBtn.onclick = () => {
      s.solo = !s.solo;
      soloBtn.classList.toggle('active', s.solo);
      player.setSolo(i, s.solo);
    };
    btns.appendChild(soloBtn);
    row.appendChild(btns);

    const volWrap = document.createElement('div');
    volWrap.className = 'track-volume';
    const volSlider = document.createElement('input');
    volSlider.type = 'range';
    volSlider.min = '0';
    volSlider.max = '125';
    volSlider.value = '100';
    const volVal = document.createElement('span');
    volVal.className = 'track-vol-val';
    volVal.textContent = '100%';
    volSlider.oninput = () => {
      const v = parseInt(volSlider.value) / 100;
      player.setVolume(i, v);
      volVal.textContent = Math.round(v * 100) + '%';
    };
    volWrap.appendChild(volSlider);
    row.appendChild(volWrap);
    row.appendChild(volVal);

    const expBtn = document.createElement('button');
    expBtn.className = 'track-export';
    expBtn.textContent = 'MP3';
    row.appendChild(expBtn);

    mixer.appendChild(row);
  }

  // Chord panel
  if (job.chord_sections && job.chord_sections.length > 0) {
    const chordPanel = document.createElement('div');
    chordPanel.className = 'chord-panel';
    chordPanel.innerHTML = '<div class="chord-panel-title">Acordes</div><div class="chord-key">Tono: ' + (job.key || '?') + '</div>';
    for (const sec of job.chord_sections) {
      const line = document.createElement('div');
      line.className = 'chord-line';
      for (const chordLine of sec.lines) {
        for (const chord of chordLine.chords) {
          const chip = document.createElement('span');
          chip.className = 'chord-chip-ui';
          chip.textContent = chord || '—';
          line.appendChild(chip);
        }
      }
      chordPanel.appendChild(line);
    }
    $('studioPanel').appendChild(chordPanel);
  }

  // Load audio
  duration = await player.load(stemsData);
  $('timeline').max = duration;
  $('totalTime').textContent = fmtTime(duration);
  $('currentTime').textContent = '0:00';
  $('exportMixBtn').disabled = false;
}

// ── Waveform placeholder ──
function drawWaveformPlaceholder() {
  const canvas = $('waveform');
  canvas.width = canvas.parentElement.clientWidth;
  canvas.height = canvas.parentElement.clientHeight || 200;
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;

  ctx.fillStyle = '#0a3b47';
  ctx.fillRect(0, 0, w, h);

  ctx.strokeStyle = '#1a5662';
  ctx.lineWidth = 1;
  for (let x = 0; x < w; x += 4) {
    const amp = Math.random() * h * 0.6 + h * 0.1;
    ctx.beginPath();
    ctx.moveTo(x, h / 2 - amp / 2);
    ctx.lineTo(x, h / 2 + amp / 2);
    ctx.stroke();
  }
}

// ── Transport ──
$('playBtn').onclick = () => {
  if (player.playing) {
    player.pause();
    $('playBtn').textContent = '▶';
  } else {
    player.play();
    $('playBtn').textContent = '⏸';
  }
};

$('stopBtn').onclick = () => {
  player.stop();
  $('playBtn').textContent = '▶';
  $('timeline').value = 0;
  $('currentTime').textContent = '0:00';
};

$('timeline').oninput = () => {
  player.seek(parseFloat($('timeline').value));
};

$('masterVolume').oninput = () => {
  player.setMasterVolume(parseInt($('masterVolume').value) / 100);
};

// Key shortcuts
document.onkeydown = e => {
  if (e.code === 'Space') { e.preventDefault(); $('playBtn').click(); }
  if (e.code === 'BracketLeft') player.seek(Math.max(0, player.position() - 5));
  if (e.code === 'BracketRight') player.seek(Math.min(duration, player.position() + 5));
};

// Update loop
setInterval(() => {
  if (player.playing) {
    const pos = player.position();
    $('timeline').value = pos;
    $('currentTime').textContent = fmtTime(pos);
    if (pos >= duration - 0.2) {
      player.playing = false;
      $('playBtn').textContent = '▶';
    }
  }
}, 150);

// ── Export ──
$('exportMixBtn').onclick = async () => {
  if (!jobId) return;
  try {
    await API.mixDownload(jobId);
  } catch (e) {
    alert('Error al exportar: ' + e.message);
  }
};

// ── File drop ──
const fileDrop = document.querySelector('.file-drop');
if (fileDrop) {
  fileDrop.onclick = () => $('fileInput').click();
  fileDrop.ondragover = e => { e.preventDefault(); fileDrop.style.borderColor = 'var(--cyan)'; };
  fileDrop.ondragleave = () => { fileDrop.style.borderColor = ''; };
  fileDrop.ondrop = e => {
    e.preventDefault();
    fileDrop.style.borderColor = '';
    const file = e.dataTransfer.files[0];
    if (file) {
      $('fileInput').files = e.dataTransfer.files;
      startJob({ file });
    }
  };
}

$('fileInput').onchange = () => {
  const file = $('fileInput').files[0];
  if (file) startJob({ file });
};

// ── Init ──
buildChips();
