const player = new Player();
let jobId = null;
let duration = 0;
let updateTimer = null;

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

// ── Stem chips ──
function buildChips() {
  const ctr = $('stemChips');
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

// ── Import ──
$('addUrlBtn').onclick = () => {
  const url = $('youtubeUrl').value.trim();
  if (url) startJob({ url });
};

$('fileInput').onchange = () => {
  const file = $('fileInput').files[0];
  if (file) startJob({ file });
};

// ── Process ──
async function startJob({ url, file } = {}) {
  const form = new FormData();
  if (file) form.append('file', file);
  if (url) form.append('url', url);
  form.append('stems', JSON.stringify([...selectedStems]));

  $('statusPill').textContent = 'Enviando...';
  $('progressWrap').hidden = false;
  $('progressLabel').textContent = '';
  $('processBtn').disabled = true;

  try {
    const job = await API.createJob(form);
    jobId = job.id;
    $('statusPill').textContent = 'Procesando...';
    pollJob(jobId);
  } catch (e) {
    $('statusPill').textContent = 'Error: ' + e.message;
    $('progressWrap').hidden = true;
    $('processBtn').disabled = false;
  }
}

async function pollJob(id) {
  if (id !== jobId) return;
  try {
    const job = await API.getJob(id);
    if (id !== jobId) return;

    $('progressFill').style.width = (job.progress * 100) + '%';
    $('progressLabel').textContent = job.phase || '';

    if (job.status === 'done' && job.stems.length > 0) {
      $('statusPill').textContent = 'Listo';
      $('progressWrap').hidden = true;
      $('progressLabel').textContent = '';
      buildMixer(job);
      return;
    }
    updateTimer = setTimeout(() => pollJob(id), 800);
  } catch (e) {
    updateTimer = setTimeout(() => pollJob(id), 1500);
  }
}

// ── Mixer ──
async function buildMixer(job) {
  $('studio').hidden = false;
  $('footer').hidden = false;
  const mixer = $('mixer');
  mixer.innerHTML = '';

  const stemsData = job.stems;
  // Add URLs for each stem
  for (const s of stemsData) {
    s.path = API.stemUrl(job.id, s.file);
    s.volume = 1.0;
    s.mute = false;
    s.solo = false;
  }

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

  duration = await player.load(stemsData);
  $('timeline').max = duration;
  $('totalTime').textContent = fmtTime(duration);
  $('currentTime').textContent = '0:00';
  $('exportMixBtn').disabled = false;
  $('exportStemsBtn').disabled = false;
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
$('exportMixBtn').onclick = () => {
  if (jobId) API.mixDownload(jobId);
};

// ── Init ──
buildChips();
