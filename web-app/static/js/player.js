class Player {
  constructor() {
    this.ctx = null; this.stems = []; this.buffers = {}; this.sources = []; this.gains = [];
    this.masterGain = null; this.playing = false; this.startTime = 0; this.pausedAt = 0;
    this.duration = 0; this.pitchSemitones = 0;
  }

  async load(stemsData) {
    this.stop(); this.stems = stemsData; this.pitchSemitones = 0;
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    this.masterGain = this.ctx.createGain(); this.masterGain.connect(this.ctx.destination); this.masterGain.gain.value = 1.0;
    this.buffers = {}; this.gains = []; this.duration = 0;
    for (const s of stemsData) {
      try {
        const res = await fetch(s.path); const arrayBuf = await res.arrayBuffer();
        const audioBuf = await this.ctx.decodeAudioData(arrayBuf);
        this.buffers[s.name] = audioBuf;
        if (audioBuf.duration > this.duration) this.duration = audioBuf.duration;
        const gain = this.ctx.createGain(); gain.connect(this.masterGain);
        gain.gain.value = s.mute ? 0 : (s.volume || 1.0);
        this.gains.push({ name: s.name, node: gain });
      } catch (e) { console.warn('Error loading stem:', s.name, e); }
    }
    this.pausedAt = 0; this._updateGains(); return this.duration;
  }

  _updateGains() {
    let hasSolo = this.stems.some(s => s.solo);
    for (const g of this.gains) {
      const stem = this.stems.find(s => s.name === g.name); if (!stem) continue;
      let audible = !stem.mute; if (hasSolo) audible = audible && stem.solo;
      g.node.gain.value = audible ? (stem.volume || 1.0) : 0;
    }
  }

  _createSources(offset = 0) {
    this._stopSources(); this.sources = [];
    const when = this.ctx.currentTime + 0.01;
    const rate = Math.pow(2, this.pitchSemitones / 12);
    for (const g of this.gains) {
      const buf = this.buffers[g.name]; if (!buf) continue;
      const src = this.ctx.createBufferSource(); src.buffer = buf; src.playbackRate.value = rate;
      src.connect(g.node); src.start(when, offset); this.sources.push(src);
    }
  }

  _stopSources() { for (const src of this.sources) { try { src.stop(); } catch (e) {} } this.sources = []; }

  play() { if (!this.ctx || this.playing) return; if (this.ctx.state === 'suspended') this.ctx.resume(); this._createSources(this.pausedAt); this.startTime = this.ctx.currentTime - this.pausedAt; this.playing = true; }
  pause() { if (!this.playing) return; this.pausedAt = this.position(); this._stopSources(); this.playing = false; }
  stop() { this._stopSources(); this.playing = false; this.pausedAt = 0; if (this.ctx) this.ctx.suspend(); }

  seek(seconds) {
    const wasPlaying = this.playing; if (this.playing) this._stopSources();
    this.pausedAt = Math.max(0, Math.min(seconds, this.duration));
    if (wasPlaying) { this._createSources(this.pausedAt); this.startTime = this.ctx.currentTime - this.pausedAt; }
  }

  position() { if (this.playing) return this.ctx.currentTime - this.startTime; return this.pausedAt; }
  setVolume(index, vol) { if (index < this.stems.length) { this.stems[index].volume = Math.max(0, Math.min(1.5, vol)); this._updateGains(); } }
  setMute(index, mute) { if (index < this.stems.length) { this.stems[index].mute = mute; this._updateGains(); } }
  setSolo(index, solo) { if (index < this.stems.length) { this.stems[index].solo = solo; this._updateGains(); } }
  setMasterVolume(vol) { if (this.masterGain) this.masterGain.gain.value = Math.max(0, Math.min(1.5, vol)); }

  setPitch(semitones) {
    semitones = Math.max(-12, Math.min(12, semitones));
    if (semitones === this.pitchSemitones) return;
    this.pitchSemitones = semitones;
    if (this.playing) { this.pausedAt = this.position(); this._stopSources(); this._createSources(this.pausedAt); this.startTime = this.ctx.currentTime - this.pausedAt; }
  }
}
