import { useState } from "react";
import { uploadCsv } from "../lib/api";

export default function UploadCsv({ onUploaded }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function handleUpload() {
    if (!file) return setMsg("Select a CSV file first.");
    setBusy(true);
    setMsg("");
    try {
      const res = await uploadCsv(file);
      setMsg(`Uploaded ✓  (${(res.size/1024).toFixed(1)} KB)`);
      onUploaded?.(res.path);
    } catch (e) {
      setMsg(e.message || "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-2xl shadow p-4 border bg-white">
      <h2 className="text-lg font-semibold mb-3">1) Upload CSV</h2>
      <input
        type="file"
        accept=".csv"
        onChange={(e) => setFile(e.target.files?.[0] || null)}
        className="block w-full text-sm mb-3"
      />
      <button
        onClick={handleUpload}
        disabled={busy || !file}
        className="px-4 py-2 rounded-xl bg-black text-white disabled:opacity-50"
      >
        {busy ? "Uploading..." : "Upload"}
      </button>
      {msg && <p className="text-sm mt-2">{msg}</p>}
    </div>
  );
}
