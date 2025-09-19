import { useState } from "react";
import { scheduleOnce } from "../lib/api";

export default function ScheduleOnce({ defaultAccount = "Account_001", csvPath }) {
  const [account, setAccount] = useState(defaultAccount);
  const [when, setWhen] = useState(""); // HTML datetime-local
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function handleSchedule() {
    if (!csvPath) return setMsg("No CSV selected/uploaded yet.");
    if (!when) return setMsg("Pick a date/time.");
    setBusy(true);
    setMsg("");
    try {
      // datetime-local has no seconds -> add :00
      const iso = when.length === 16 ? `${when}:00` : when;
      const res = await scheduleOnce({ account, csv_path: csvPath, when: iso });
      setMsg(`Scheduled ✓  Job: ${res.job_id} at ${res.run_at}`);
    } catch (e) {
      setMsg(e.message || "Schedule failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-2xl shadow p-4 border bg-white">
      <h2 className="text-lg font-semibold mb-3">3) Schedule (one-time)</h2>
      <label className="block text-sm mb-1">Account</label>
      <input
        value={account}
        onChange={(e) => setAccount(e.target.value)}
        className="w-full border rounded-xl px-3 py-2 mb-3"
      />
      <label className="block text-sm mb-1">Run at</label>
      <input
        type="datetime-local"
        value={when}
        onChange={(e) => setWhen(e.target.value)}
        className="w-full border rounded-xl px-3 py-2 mb-3"
      />
      <div className="text-xs mb-3">
        <span className="font-medium">CSV Path:</span>{" "}
        {csvPath ? <code className="break-all">{csvPath}</code> : <em>none</em>}
      </div>
      <button
        onClick={handleSchedule}
        disabled={busy || !csvPath || !when}
        className="px-4 py-2 rounded-xl bg-black text-white disabled:opacity-50"
      >
        {busy ? "Scheduling..." : "Schedule"}
      </button>
      {msg && <p className="text-sm mt-2">{msg}</p>}
    </div>
  );
}
