import { PitchShifter } from './lib/soundtouch.js';

class Player {
  constructor() {
    this.ctx = null; this.stems = []; this.shifters = []; this.gains = [];
    this.masterGain = null; this.playing = false;
    this.duration = 0; this._position = 0; this._lastTime = 0;
    this.pitchSemitones = 0; this.tempoRate = 1.0;
    this.analysers = []; this.masterAnalyser = null;
  }

  async load(stemsData) {
    this.stop(); this.stems = stemsData; this.pitchSemitones = 0; this.tempoRate = 1.0;
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    this.masterGain = this.ctx.createGain(); this.masterGain.connect(this.ctx.destination); this.masterGain.gain.value = 1.0;
    this.shifters = []; this.gains = []; this.duration = 0; this._position = 0; this._lastTime = 0;
    this.analysers = [];

    for (const s of stemsData) {
      try {
        const res = await fetch(s.path); const arrayBuf = await res.arrayBuffer();
        const audioBuf = await this.ctx.decodeAudioData(arrayBuf);
        if (audioBuf.duration > this.duration) this.duration = audioBuf.duration;

        const shifter = new PitchShifter(this.ctx, audioBuf, 16384);
        shifter.rate = 1.0;
        shifter.pitchSemitones = 0;
        shifter.off();

        const gain = this.ctx.createGain(); gain.gain.value = s.mute ? 0 : (s.volume ?? 1.0);
        const analyser = this.ctx.createAnalyser(); analyser.fftSize = 256;
        gain.connect(analyser); analyser.connect(this.masterGain);
        this.shifters.push(shifter);
        this.gains.push({ name: s.name, node: gain, shifter: shifter });
        this.analysers.push(analyser);
      } catch (e) { console.warn('Error loading stem:', s.name, e); }
    }
    this.masterAnalyser = this.ctx.createAnalyser(); this.masterAnalyser.fftSize = 512;
    this.masterGain.connect(this.masterAnalyser); this.masterAnalyser.connect(this.ctx.destination);
    this._updateGains(); return this.duration;
  }

  _updateGains() {
    let hasSolo = this.stems.some(s => s.solo);
    for (const g of this.gains) {
      const stem = this.stems.find(s => s.name === g.name); if (!stem) continue;
      let audible = !stem.mute; if (hasSolo) audible = audible && stem.solo;
      g.node.gain.value = audible ? (stem.volume ?? 1.0) : 0;
    }
  }

  play() {
    if (!this.ctx || this.playing) return;
    if (this.ctx.state === 'suspended') this.ctx.resume();
    for (const g of this.gains) {
      g.shifter.percentagePlayed = this._position / this.duration;
      g.shifter.connect(g.node);
    }
    this._lastTime = this.ctx.currentTime;
    this.playing = true;
  }

  pause() {
    if (!this.playing) return;
    this._position = this.position();
    for (const g of this.gains) g.shifter.disconnect();
    this.playing = false;
  }

  stop() {
    for (const g of this.gains) {
      try { g.shifter.disconnect(); } catch (e) {}
      g.shifter.percentagePlayed = 0;
    }
    this.playing = false; this._position = 0;
    if (this.ctx) this.ctx.suspend();
  }

  seek(seconds) {
    seconds = Math.max(0, Math.min(seconds, this.duration));
    this._position = seconds;
    if (this.playing) {
      for (const g of this.gains) {
        g.shifter.disconnect();
        g.shifter.percentagePlayed = seconds / this.duration;
        g.shifter.connect(g.node);
      }
      this._lastTime = this.ctx.currentTime;
    }
  }

  position() {
    if (this.playing) return this._position + (this.ctx.currentTime - this._lastTime);
    return this._position;
  }

  setVolume(index, vol) { if (index < this.stems.length) { this.stems[index].volume = Math.max(0, Math.min(1.5, vol)); this._updateGains(); } }
  setMute(index, mute) { if (index < this.stems.length) { this.stems[index].mute = mute; this._updateGains(); } }
  setSolo(index, solo) { if (index < this.stems.length) { this.stems[index].solo = solo; this._updateGains(); } }
  setMasterVolume(vol) { if (this.masterGain) this.masterGain.gain.value = Math.max(0, Math.min(1.5, vol)); }

  setPitch(semitones) {
    semitones = Math.max(-12, Math.min(12, semitones));
    if (semitones === this.pitchSemitones) return;
    this.pitchSemitones = semitones;
    for (const g of this.gains) {
      g.shifter.pitchSemitones = semitones;
      g.shifter.rate = this.tempoRate;
    }
  }

  setTempo(multiplier) {
    multiplier = Math.max(0.5, Math.min(2.0, multiplier));
    if (multiplier === this.tempoRate) return;
    this.tempoRate = multiplier;
    for (const g of this.gains) {
      g.shifter.rate = multiplier;
      g.shifter.pitchSemitones = this.pitchSemitones;
    }
  }
}

export { Player };
