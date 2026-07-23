// Pitch shifter — resample + overlap-add time-stretch
// Changes pitch without affecting playback duration or tempo.
class PitchShifter {

  static shift(ctx, original, semitones) {
    if (semitones === 0) return original;
    const ratio = Math.pow(2, semitones / 12);
    const nc = original.numberOfChannels;
    const sr = original.sampleRate;
    const inLen = original.length;

    // Step 1: resample → pitch changes, duration changes
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

    // Step 2: time-stretch back to original length
    if (!ctx) ctx = new OfflineAudioContext(1, 1, sr);
    const out = ctx.createBuffer(nc, inLen, sr);
    for (let ch = 0; ch < nc; ch++) {
      out.copyToChannel(PitchShifter._stretch(resCh[ch], inLen), ch);
    }
    return out;
  }

  // Time-stretch / compress to exactly targetLen samples
  static _stretch(src, targetLen) {
    const srcLen = src.length;
    const out = new Float32Array(targetLen);
    if (srcLen >= targetLen) {
      // Need to expand (pitch was raised, audio compressed by resample)
      PitchShifter._expand(src, out);
    } else {
      // Need to compress (pitch lowered, audio expanded by resample)
      PitchShifter._compress(src, out);
    }
    return out;
  }

  // OLA expand: fixed output hop for uniform overlap = no amplitude ripple
  static _expand(src, out) {
    const srcLen = src.length;
    const outLen = out.length;
    const winSize = 4096;
    const window = PitchShifter._hann(winSize);
    const hopOut = winSize / 4;            // fixed → constant 4× overlap
    const stretch = outLen / srcLen;
    const hopIn = hopOut / stretch;        // variable input step
    const norm = new Float32Array(outLen);

    let inPos = 0;
    for (let outPos = 0; outPos + winSize <= outLen; outPos += hopOut) {
      const baseIn = Math.round(inPos);
      for (let i = 0; i < winSize; i++) {
        const si = baseIn + i;
        const oi = outPos + i;
        if (si >= srcLen || oi >= outLen) break;
        out[oi] += src[si] * window[i];
        norm[oi] += window[i];
      }
      inPos += hopIn;
    }
    // Normalize
    for (let i = 0; i < outLen; i++) {
      if (norm[i] > 0.001) out[i] /= norm[i];
    }
  }

  // Compress: linear resample (cleaner than OLA for compression)
  static _compress(src, out) {
    const srcLen = src.length;
    const outLen = out.length;
    const ratio = srcLen / outLen;
    for (let i = 0; i < outLen; i++) {
      const pos = i * ratio;
      const idx = Math.floor(pos);
      const frac = pos - idx;
      if (idx + 1 < srcLen) out[i] = src[idx] * (1 - frac) + src[idx + 1] * frac;
      else if (idx < srcLen) out[i] = src[idx];
    }
  }

  static _hann(size) {
    const w = new Float32Array(size);
    for (let i = 0; i < size; i++) w[i] = 0.5 * (1 - Math.cos(2 * Math.PI * i / (size - 1)));
    return w;
  }
}
