import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedAdminRoute } from "./auth/ProtectedAdminRoute";
import { AppLayout } from "./layouts/AppLayout";
import { AdminLoginPage } from "./pages/AdminLoginPage";
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
      <Route path="/login" element={<AdminLoginPage />} />
      <Route path="/" element={<AppLayout />}>
        <Route index element={<Navigate to="/chat" replace />} />
        <Route path="/chat" element={<ChatCenterPage />} />
        <Route path="/context" element={<ProtectedAdminRoute><ContextPage /></ProtectedAdminRoute>} />
        <Route path="/providers" element={<ProtectedAdminRoute><ProviderModelPage /></ProtectedAdminRoute>} />
        <Route path="/chains" element={<ProtectedAdminRoute><ChainPage /></ProtectedAdminRoute>} />
        <Route path="/personas" element={<ProtectedAdminRoute><PersonaPage /></ProtectedAdminRoute>} />
        <Route path="/voices" element={<ProtectedAdminRoute><VoicePage /></ProtectedAdminRoute>} />
        <Route path="/knowledge" element={<ProtectedAdminRoute><KnowledgePage /></ProtectedAdminRoute>} />
        <Route path="/settings" element={<ProtectedAdminRoute><SettingsPage /></ProtectedAdminRoute>} />
      </Route>
    </Routes>
  );
}
