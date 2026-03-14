import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import ResetPasswordPage from "./pages/ResetPasswordPage";
import FeedPage from "./pages/FeedPage";
import TopicsPage from "./pages/TopicsPage";
import ArticlePage from "./pages/ArticlePage";
import SettingsPage from "./pages/SettingsPage";
import DigestPage from "./pages/DigestPage";
import StatsPage from "./pages/StatsPage";
import ReadLaterPage from "./pages/ReadLaterPage";

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return (
    <div className="loading-screen">
      <div className="loader-ring"></div>
    </div>
  );
  return user ? children : <Navigate to="/login" replace />;
}

function AppRoutes() {
  const { user } = useAuth();
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route index element={<FeedPage />} />
        <Route path="topics" element={<TopicsPage />} />
        <Route path="article/:id" element={<ArticlePage />} />
        <Route path="digest" element={<DigestPage />} />
        <Route path="stats" element={<StatsPage />} />
        <Route path="read-later" element={<ReadLaterPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
        <Toaster position="bottom-right" toastOptions={{
          style: { background: '#1a1a2e', color: '#fff', borderRadius: '10px' }
        }} />
      </AuthProvider>
    </BrowserRouter>
  );
}
