import { useState } from "react";
import { runNow } from "../lib/api";

export default function RunNow({ defaultAccount = "Account_001", csvPath }) {
  const [account, setAccount] = useState(defaultAccount);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function handleRun() {
    if (!csvPath) return setMsg("No CSV selected/uploaded yet.");
    setBusy(true);
    setMsg("");
    try {
      await runNow({ account, csv_path: csvPath });
      setMsg("Queued ✓  Check logs in your Account logs folder.");
    } catch (e) {
      setMsg(e.message || "Run-now failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-2xl shadow p-4 border bg-white">
      <h2 className="text-lg font-semibold mb-3">2) Run Now</h2>
      <label className="block text-sm mb-1">Account</label>
      <input
        value={account}
        onChange={(e) => setAccount(e.target.value)}
        className="w-full border rounded-xl px-3 py-2 mb-3"
      />
      <div className="text-xs mb-3">
        <span className="font-medium">CSV Path:</span>{" "}
        {csvPath ? <code className="break-all">{csvPath}</code> : <em>none</em>}
      </div>
      <button
        onClick={handleRun}
        disabled={busy || !csvPath}
        className="px-4 py-2 rounded-xl bg-black text-white disabled:opacity-50"
      >
        {busy ? "Starting..." : "Run once"}
      </button>
      {msg && <p className="text-sm mt-2">{msg}</p>}
    </div>
  );
}
