// Pitch shifter — resample + overlap-add time-stretch
// Changes pitch without affecting playback duration or tempo.
class PitchShifter {

  // Returns a new AudioBuffer with the pitch shifted by `semitones`.
  // `ctx` must be a live AudioContext / OfflineAudioContext.
  static shift(ctx, original, semitones) {
    if (semitones === 0) return original;
    const ratio = Math.pow(2, semitones / 12);
    const nc = original.numberOfChannels;
    const sr = original.sampleRate;
    const inLen = original.length;

    // Step 1: resample (linear interpolation) → pitch-shifted but compressed/expanded
    const resLen = Math.max(1, Math.floor(inLen / ratio));
    const resCh = [];
    for (let ch = 0; ch < nc; ch++) {
      const src = original.getChannelData(ch);
      const dst = new Float32Array(resLen);
      for (let i = 0; i < resLen; i++) {
        const pos = i * ratio;
        const idx = Math.floor(pos);
        const frac = pos - idx;
        if (idx + 1 < inLen) dst[i] = src[idx] * (1 - frac) + src[idx + 1] * frac;
        else if (idx < inLen) dst[i] = src[idx];
      }
      resCh.push(dst);
    }

    // Step 2: OLA time-stretch back to original length
    if (!ctx) ctx = new OfflineAudioContext(1, 1, sr);
    const out = ctx.createBuffer(nc, inLen, sr);
    for (let ch = 0; ch < nc; ch++) {
      const chData = PitchShifter._olaStretch(resCh[ch], inLen);
      out.copyToChannel(chData, ch);
    }
    return out;
  }

  // Overlap-add time stretch/compress to target length
  static _olaStretch(src, targetLen) {
    const srcLen = src.length;
    const out = new Float32Array(targetLen);
    if (srcLen >= targetLen) {
      // Expanding (audio was compressed by resample — pitch raised)
      PitchShifter._olaExpand(src, out);
    } else {
      // Compressing (audio was expanded by resample — pitch lowered)
      // Linear resample for compression is clean enough
      const ratio = srcLen / targetLen;
      for (let i = 0; i < targetLen; i++) {
        const pos = i * ratio;
        const idx = Math.floor(pos);
        const frac = pos - idx;
        if (idx + 1 < srcLen) out[i] = src[idx] * (1 - frac) + src[idx + 1] * frac;
        else if (idx < srcLen) out[i] = src[idx];
      }
    }
    return out;
  }

  static _olaExpand(src, out) {
    const srcLen = src.length;
    const outLen = out.length;
    const winSize = 2048;
    const window = PitchShifter._hann(winSize);
    const hopIn = winSize / 4;
    const stretchRatio = outLen / srcLen;
    const hopOut = hopIn * stretchRatio;

    let outPos = 0;
    for (let inPos = 0; inPos + winSize <= srcLen; inPos += hopIn) {
      for (let i = 0; i < winSize; i++) {
        const oi = Math.floor(outPos) + i;
        if (oi >= outLen) break;
        out[oi] += src[Math.floor(inPos) + i] * window[i];
      }
      outPos += hopOut;
    }
  }

  static _hann(size) {
    const w = new Float32Array(size);
    for (let i = 0; i < size; i++) w[i] = 0.5 * (1 - Math.cos(2 * Math.PI * i / (size - 1)));
    return w;
  }
}
