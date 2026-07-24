class WaveformDisplay {
  constructor(player) {
    this.player = player;
    this.canvases = [];
    this.spectrumCanvas = null;
    this._running = false;
  }

  init() {
    const container = document.getElementById('waveformContainer');
    if (!container) return;
    container.innerHTML = '';
    this.canvases = [];

    for (let i = 0; i < 6; i++) {
      const canvas = document.createElement('canvas');
      canvas.className = 'waveform-canvas';
      canvas.width = container.clientWidth || 600;
      canvas.height = 40;
      container.appendChild(canvas);
      this.canvases.push(canvas);
    }
    this.spectrumCanvas = document.getElementById('spectrumCanvas');
    this.start();
  }

  start() {
    if (this._running) return;
    this._running = true;
    const draw = () => {
      if (!this._running) return;
      this._draw();
      requestAnimationFrame(draw);
    };
    draw();
  }

  stop() { this._running = false; }

  _draw() {
    const ctx = this.player.ctx;
    if (!ctx || !this.player.analysers.length) return;

    const colors = ['#d33682', '#cb4b16', '#268bd2', '#6c71c4', '#b58900', '#859900'];
    for (let i = 0; i < this.canvases.length; i++) {
      const canvas = this.canvases[i];
      const analyser = this.player.analysers[i] || this.player.masterAnalyser;
      if (!canvas || !analyser) continue;
      const w = canvas.width, h = canvas.height;
      const c = canvas.getContext('2d');
      c.clearRect(0, 0, w, h);

      const buf = new Uint8Array(analyser.fftSize);
      analyser.getByteTimeDomainData(buf);

      c.strokeStyle = '#1a5662'; c.lineWidth = 1;
      c.beginPath(); c.moveTo(0, h / 2); c.lineTo(w, h / 2); c.stroke();

      c.strokeStyle = colors[i % colors.length]; c.lineWidth = 1.5;
      c.beginPath();
      for (let x = 0; x < buf.length; x++) {
        const v = buf[x] / 128.0 - 1.0;
        const y = (h / 2) + v * (h / 2) * 0.85;
        c.lineTo((x / buf.length) * w, y);
      }
      c.stroke();
    }

    if (this.spectrumCanvas && this.player.masterAnalyser) {
      const sw = this.spectrumCanvas.width, sh = this.spectrumCanvas.height;
      const sc = this.spectrumCanvas.getContext('2d');
      sc.clearRect(0, 0, sw, sh);
      const freqData = new Uint8Array(this.player.masterAnalyser.fftSize / 2);
      this.player.masterAnalyser.getByteFrequencyData(freqData);
      const barW = sw / freqData.length;
      for (let i = 0; i < freqData.length; i++) {
        const h = (freqData[i] / 255) * sh;
        sc.fillStyle = '#2aa198'; sc.fillRect(i * barW, sh - h, barW - 1, h);
      }
    }
  }
}

export { WaveformDisplay };
