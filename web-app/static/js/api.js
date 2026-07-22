const API = {
  async createJob(formData) {
    const res = await fetch('/api/jobs', { method: 'POST', body: formData });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async getJob(id) {
    const res = await fetch(`/api/jobs/${id}`);
    return res.json();
  },
  cancelJob(id) {
    return fetch(`/api/jobs/${id}/cancel`, { method: 'POST' });
  },
  stemUrl(jobId, file) {
    return `/api/jobs/${jobId}/stems/${file}`;
  },
  stemMp3Url(jobId, file) {
    return `/api/jobs/${jobId}/stems-mp3/${file}`;
  },
  mixUrl(jobId) {
    return `/api/jobs/${jobId}/export/mix`;
  },
  async searchChords(artist, title) {
    const res = await fetch(`/api/chords/search?artist=${encodeURIComponent(artist)}&title=${encodeURIComponent(title)}`);
    return res.json();
  },
  async fetchChords(url) {
    const res = await fetch(`/api/chords/fetch?url=${encodeURIComponent(url)}`);
    return res.json();
  },
  async transposeChords(url, semitones) {
    const res = await fetch('/api/chords/transpose', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, semitones }),
    });
    return res.json();
  },
};
