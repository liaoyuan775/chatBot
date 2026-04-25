import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./layouts/AppLayout";
import { ChainPage } from "./pages/ChainPage";
import { ChatCenterPage } from "./pages/ChatCenterPage";
import { ContextPage } from "./pages/ContextPage";
import { KnowledgePage } from "./pages/KnowledgePage";
import { PersonaPage } from "./pages/PersonaPage";
import { ProviderModelPage } from "./pages/ProviderModelPage";
import { SettingsPage } from "./pages/SettingsPage";
import { VoicePage } from "./pages/VoicePage";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<AppLayout />}>
        <Route index element={<Navigate to="/chat" replace />} />
        <Route path="/chat" element={<ChatCenterPage />} />
        <Route path="/context" element={<ContextPage />} />
        <Route path="/providers" element={<ProviderModelPage />} />
        <Route path="/chains" element={<ChainPage />} />
        <Route path="/personas" element={<PersonaPage />} />
        <Route path="/voices" element={<VoicePage />} />
        <Route path="/knowledge" element={<KnowledgePage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}
