import SubmissionPortal from "./pages/SubmissionPortal";
import AdminDashboard from "./pages/AdminDashboard";

export default function App() {
  // Tiny router — no react-router needed for two routes.
  const path = window.location.pathname;
  return path.startsWith("/admin") ? <AdminDashboard /> : <SubmissionPortal />;
}