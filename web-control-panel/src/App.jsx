import { useEffect, useState } from "react";
import UploadCsv from "./components/UploadCsv";
import RunNow from "./components/RunNow";
import ScheduleOnce from "./components/ScheduleOnce";
import { health } from "./lib/api";
import "./App.css";

export default function App() {
  const [apiOk, setApiOk] = useState(false);
  const [csvPath, setCsvPath] = useState("");

  useEffect(() => {
    health().then(() => setApiOk(true)).catch(() => setApiOk(false));
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white">
        <div className="max-w-6xl mx-auto p-4 flex items-center justify-between">
          <h1 className="text-xl font-bold">Crazy Poster — Control Panel</h1>
          <span
            className={`text-xs px-2 py-1 rounded ${
              apiOk ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
            }`}
          >
            API {apiOk ? "Online" : "Offline"}
          </span>
        </div>
      </header>

      <main className="max-w-6xl mx-auto p-4 grid md:grid-cols-3 gap-4">
        <UploadCsv onUploaded={(p) => setCsvPath(p)} />
        <RunNow csvPath={csvPath} />
        <ScheduleOnce csvPath={csvPath} />
      </main>

      <footer className="max-w-6xl mx-auto p-4 text-xs text-gray-500">
        CSVs are stored in <code>shared-resources/uploads</code>. Logs in your account’s <code>logs</code> folder.
      </footer>
    </div>
  );
}
