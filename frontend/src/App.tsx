import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Workbench from "./pages/Workbench";
import Translate from "./pages/Translate";
import { JobDetail, Jobs } from "./pages/Jobs";
import Chat from "./pages/Chat";
import { GlossaryDetailPage, GlossaryPage } from "./pages/Glossary";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Workbench />} />
        <Route path="/translate" element={<Translate />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/jobs/:id" element={<JobDetail />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/chat/:id" element={<Chat />} />
        <Route path="/glossary" element={<GlossaryPage />} />
        <Route path="/glossary/:id" element={<GlossaryDetailPage />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
