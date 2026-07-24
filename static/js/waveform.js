class WaveformDisplay {
  constructor(player) {
    this.player = player;
    this.spectrumCanvas = null;
    this._running = false;
    this._peaks = [];        // pre-rendered min/max per track
    this._vuCanvases = [];   // VU meter mini canvases
    this._vuAnalysers = [];  // AnalyserNode references for RMS
    this.colors = ['#d33682', '#cb4b16', '#268bd2', '#6c71c4', '#b58900', '#859900'];
  }

  init() {
    this.spectrumCanvas = document.getElementById('spectrumCanvas');
    if (this.spectrumCanvas) this.spectrumCanvas.hidden = false;
    this._renderPeaks();
    this._findVuCanvases();
    this.start();
  }

  _renderPeaks() {
    this._peaks = [];
    const canvases = document.querySelectorAll('.track-wave');
    if (!canvases.length || !this.player.buffers.length) return;

    let globalMax = 0;
    for (const buf of this.player.buffers) {
      const data = buf.getChannelData(0);
      for (let i = 0; i < data.length; i++) {
        const abs = Math.abs(data[i]);
        if (abs > globalMax) globalMax = abs;
      }
    }
    if (globalMax === 0) globalMax = 1;

    for (let t = 0; t < canvases.length; t++) {
      const canvas = canvases[t];
      const buf = this.player.buffers[t];
      if (!buf) { this._peaks.push(null); continue; }

      const w = canvas.width = canvas.clientWidth || 600;
      const h = canvas.height = 30;
      const ctx = canvas.getContext('2d');
      const data = buf.getChannelData(0);
      const samplesPerPixel = Math.max(1, Math.floor(data.length / w));
      const peaks = [];
      for (let x = 0; x < w; x++) {
        let min = 0, max = 0;
        const start = x * samplesPerPixel;
        const end = Math.min(start + samplesPerPixel, data.length);
        for (let i = start; i < end; i++) {
          const v = data[i];
          if (v < min) min = v;
          if (v > max) max = v;
        }
        min /= globalMax; max /= globalMax;
        peaks.push({ min, max });
      }
      this._peaks.push(peaks);

      const mid = h / 2;
      ctx.clearRect(0, 0, w, h);
      ctx.strokeStyle = '#1a5662'; ctx.lineWidth = 0.5;
      ctx.beginPath(); ctx.moveTo(0, mid); ctx.lineTo(w, mid); ctx.stroke();

      ctx.fillStyle = this.colors[t % this.colors.length];
      for (let x = 0; x < peaks.length; x++) {
        const y1 = mid - peaks[x].max * mid * 0.92;
        const y2 = mid - peaks[x].min * mid * 0.92;
        ctx.fillRect(x, y1, 1, Math.max(1, y2 - y1));
      }
    }
  }

  _findVuCanvases() {
    this._vuCanvases = [];
    this._vuAnalysers = [];
    const els = document.querySelectorAll('.vu-meter canvas');
    for (let i = 0; i < els.length; i++) {
      this._vuCanvases.push(els[i]);
      this._vuAnalysers.push(this.player.analysers[i] || null);
    }
  }

  start() {
    if (this._running) return;
    this._running = true;
    const draw = () => {
      if (!this._running) return;
      this._drawPlayhead();
      this._drawVu();
      this._drawSpectrum();
      requestAnimationFrame(draw);
    };
    draw();
  }

  stop() { this._running = false; }

  _drawPlayhead() {
    const canvases = document.querySelectorAll('.track-wave');
    if (!this.player.duration) return;
    const pos = this.player.position();
    const ratio = Math.min(1, pos / this.player.duration);

    for (const canvas of canvases) {
      const w = canvas.width, h = canvas.height;
      const ctx = canvas.getContext('2d');
      const totalDraws = this._totalDraws || 0;
      if (totalDraws % 4 === 0) {
        const peaks = this._peaks[0]; // all same length
        if (peaks) {
          ctx.clearRect(0, 0, w, h);
          const mid = h / 2;
          ctx.strokeStyle = '#1a5662'; ctx.lineWidth = 0.5;
          ctx.beginPath(); ctx.moveTo(0, mid); ctx.lineTo(w, mid); ctx.stroke();
          // re-draw all peaks every 4th frame (lighter)
        }
      }
      const x = Math.floor(ratio * w);
      ctx.strokeStyle = '#f5f0df'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
    }
    this._totalDraws = (this._totalDraws || 0) + 1;
  }

  _drawVu() {
    for (let i = 0; i < this._vuCanvases.length; i++) {
      const canvas = this._vuCanvases[i];
      const analyser = this._vuAnalysers[i];
      if (!canvas || !analyser) continue;
      const w = canvas.width, h = canvas.height;
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, w, h);

      const buf = new Uint8Array(analyser.fftSize);
      analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (let j = 0; j < buf.length; j++) {
        const v = (buf[j] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / buf.length);
      const db = rms > 0.001 ? 20 * Math.log10(rms) : -60;
      const ratio = Math.max(0, Math.min(1, (db + 48) / 48));

      const barW = Math.floor(ratio * w);
      if (barW > 0) {
        const grad = ctx.createLinearGradient(0, 0, w, 0);
        grad.addColorStop(0, '#859900'); grad.addColorStop(0.7, '#b58900'); grad.addColorStop(1, '#cb4b16');
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, barW, h);
      }
      ctx.strokeStyle = '#1a5662'; ctx.lineWidth = 0.5;
      ctx.strokeRect(0, 0, w, h);
    }
  }

  _drawSpectrum() {
    if (!this.spectrumCanvas || !this.player.masterAnalyser) return;
    const sw = this.spectrumCanvas.width, sh = this.spectrumCanvas.height;
    const sc = this.spectrumCanvas.getContext('2d');
    sc.clearRect(0, 0, sw, sh);
    const freq = new Uint8Array(this.player.masterAnalyser.fftSize / 2);
    this.player.masterAnalyser.getByteFrequencyData(freq);
    const barW = sw / freq.length;
    for (let i = 0; i < freq.length; i++) {
      const barH = (freq[i] / 255) * sh;
      sc.fillStyle = '#2aa198'; sc.fillRect(i * barW, sh - barH, barW - 1, barH);
    }
  }
}

export { WaveformDisplay };
