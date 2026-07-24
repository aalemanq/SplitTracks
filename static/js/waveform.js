class WaveformDisplay {
  constructor(player) {
    this.player = player;
    this.spectrumCanvas = null;
    this._running = false;
    this._vuCanvases = [];
    this._vuAnalysers = [];
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
    const canvases = document.querySelectorAll('.track-peaks');
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
      if (!buf) continue;

      const w = canvas.width = canvas.clientWidth || 300;
      const h = canvas.height = 30;
      const ctx = canvas.getContext('2d');
      const data = buf.getChannelData(0);
      const step = Math.max(1, Math.floor(data.length / w));
      const mid = h / 2;

      ctx.clearRect(0, 0, w, h);
      ctx.strokeStyle = '#1a5662'; ctx.lineWidth = 0.5;
      ctx.beginPath(); ctx.moveTo(0, mid); ctx.lineTo(w, mid); ctx.stroke();

      ctx.fillStyle = this.colors[t % this.colors.length];
      for (let x = 0; x < w; x++) {
        let min = 0, max = 0;
        const start = x * step;
        const end = Math.min(start + step, data.length);
        for (let i = start; i < end; i++) {
          const v = data[i];
          if (v < min) min = v;
          if (v > max) max = v;
        }
        min /= globalMax; max /= globalMax;
        const y1 = mid - max * mid * 0.92;
        const y2 = mid - min * mid * 0.92;
        ctx.fillRect(x, y1, 1, Math.max(1, y2 - y1));
      }
    }
  }

  _findVuCanvases() {
    this._vuCanvases = [];
    this._vuAnalysers = [];
    const els = document.querySelectorAll('.vu-bar');
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
      this._drawVus();
      this._drawTrackSpectrums();
      this._drawMasterSpectrum();
      requestAnimationFrame(draw);
    };
    draw();
  }

  stop() { this._running = false; }

  _drawVus() {
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
    }
  }

  _drawTrackSpectrums() {
    const canvases = document.querySelectorAll('.track-wave');
    for (let i = 0; i < canvases.length; i++) {
      const canvas = canvases[i];
      const analyser = this.player.analysers[i];
      if (!canvas || !analyser) continue;
      const w = canvas.width, h = canvas.height;
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, w, h);
      const freq = new Uint8Array(analyser.fftSize / 2);
      analyser.getByteFrequencyData(freq);
      const barW = Math.max(1, w / freq.length);
      ctx.fillStyle = this.colors[i % this.colors.length];
      for (let j = 0; j < freq.length; j++) {
        const barH = (freq[j] / 255) * h;
        ctx.fillRect(j * barW, h - barH, barW - 1, barH);
      }
    }
  }

  _drawMasterSpectrum() {
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
