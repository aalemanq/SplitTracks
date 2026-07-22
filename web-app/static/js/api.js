const API = {
  async createJob(formData) {
    const res = await fetch('/api/jobs', { method: 'POST', body: formData });
    if (!res.ok) throw new Error((await res.text()) || 'Error');
    return res.json();
  },

  getJob(id) {
    return fetch(`/api/jobs/${id}`).then(r => r.json());
  },

  cancelJob(id) {
    return fetch(`/api/jobs/${id}/cancel`, { method: 'POST' });
  },

  stemUrl(jobId, file) {
    return `/api/jobs/${jobId}/stems/${file}`;
  },

  async mixDownload(jobId) {
    const res = await fetch(`/api/jobs/${jobId}/mix`, { method: 'POST' });
    if (!res.ok) throw new Error('Export failed');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'mezcla.mp3';
    a.click();
    URL.revokeObjectURL(url);
  },
};
