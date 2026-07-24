class WaveformDisplay {
  constructor(player) {
    this.player = player;
    this.spectrumCanvas = null;
    this._running = false;
  }

  init() {
    this.spectrumCanvas = document.getElementById('spectrumCanvas');
    if (this.spectrumCanvas) this.spectrumCanvas.hidden = false;
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
    if (!ctx) return;

    const colors = ['#d33682', '#cb4b16', '#268bd2', '#6c71c4', '#b58900', '#859900'];
    const canvases = document.querySelectorAll('.track-wave');
    for (let i = 0; i < canvases.length; i++) {
      const canvas = canvases[i];
      const analyser = this.player.analysers[i];
      if (!canvas || !analyser) continue;
      const w = canvas.width, h = canvas.height;
      const c = canvas.getContext('2d');
      c.clearRect(0, 0, w, h);

      c.strokeStyle = '#1a5662'; c.lineWidth = 0.5;
      c.beginPath(); c.moveTo(0, h / 2); c.lineTo(w, h / 2); c.stroke();

      const buf = new Uint8Array(analyser.fftSize);
      analyser.getByteTimeDomainData(buf);

      let hasSignal = false;
      for (let j = 0; j < buf.length; j++) {
        if (buf[j] !== 128) { hasSignal = true; break; }
      }
      if (!hasSignal) continue;

      c.strokeStyle = colors[i % colors.length]; c.lineWidth = 1.5;
      c.beginPath();
      for (let x = 0; x < buf.length; x++) {
        const v = buf[x] / 128.0 - 1.0;
        c.lineTo((x / buf.length) * w, (h / 2) + v * (h / 2) * 0.9);
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
        const barH = (freqData[i] / 255) * sh;
        sc.fillStyle = '#2aa198'; sc.fillRect(i * barW, sh - barH, barW - 1, barH);
      }
    }
  }
}

export { WaveformDisplay };
