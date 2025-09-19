const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function health() {
  const res = await fetch(`${API_URL}/health`);
  if (!res.ok) throw new Error("API not reachable");
  return res.json();
}

export async function uploadCsv(file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API_URL}/upload-csv`, {
    method: "POST",
    body: fd,
  });
  if (!res.ok) throw new Error("Upload failed");
  return res.json(); // { path, size }
}

export async function runNow({ account, csv_path }) {
  const res = await fetch(`${API_URL}/run-now`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account, csv_path }),
  });
  if (!res.ok) throw new Error("Run-now failed");
  return res.json(); // { queued: true }
}

export async function scheduleOnce({ account, csv_path, when }) {
  const res = await fetch(`${API_URL}/schedule-once`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account, csv_path, when }),
  });
  if (!res.ok) throw new Error("Schedule failed");
  return res.json(); // { scheduled, job_id, run_at }
}
