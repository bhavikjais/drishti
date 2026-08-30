import { Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/layout/AppLayout";
import { Analysis } from "./pages/Analysis";
import { AnprSearch } from "./pages/AnprSearch";
import { Dashboard } from "./pages/Dashboard";
import { Events } from "./pages/Events";
import { Jobs } from "./pages/Jobs";
import { Processing } from "./pages/Processing";
import { Results } from "./pages/Results";
import { Settings } from "./pages/Settings";
import { SystemStatusPage } from "./pages/SystemStatusPage";

export default function App() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/analysis" element={<Analysis />} />
        <Route path="/processing/:jobId" element={<Processing />} />
        <Route path="/results/:jobId" element={<Results />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/events" element={<Events />} />
        <Route path="/anpr-search" element={<AnprSearch />} />
        <Route path="/system" element={<SystemStatusPage />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </AppLayout>
  );
}
