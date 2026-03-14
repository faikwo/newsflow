import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import {
  Rss, BookOpen, Compass, BarChart2, Settings,
  Mail, LogOut, Menu, X, Zap, Bookmark
} from "lucide-react";

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const navItems = [
    { to: "/", icon: <Rss size={17} />, label: "Feed", end: true },
    { to: "/topics", icon: <Compass size={17} />, label: "Topics" },
    { to: "/read-later", icon: <Bookmark size={17} />, label: "Read Later" },
    { to: "/digest", icon: <Mail size={17} />, label: "Email Digest" },
    { to: "/stats", icon: <BarChart2 size={17} />, label: "My Stats" },
  ];

  const adminItems = user?.is_admin ? [
    { to: "/settings", icon: <Settings size={17} />, label: "Settings" },
  ] : [];

  return (
    <div className="app-layout">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Sidebar */}
      <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="sidebar-logo">
          <h1>📰 NewsFlow</h1>
          <p>Your personal news AI</p>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-section">
            <div className="nav-section-title">Navigation</div>
            {navItems.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
                onClick={() => setSidebarOpen(false)}
              >
                <span className="nav-icon">{item.icon}</span>
                {item.label}
              </NavLink>
            ))}
          </div>

          {adminItems.length > 0 && (
            <div className="nav-section">
              <div className="nav-section-title">Admin</div>
              {adminItems.map(item => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
                  onClick={() => setSidebarOpen(false)}
                >
                  <span className="nav-icon">{item.icon}</span>
                  {item.label}
                </NavLink>
              ))}
            </div>
          )}

          <div className="nav-section">
            <div className="nav-section-title">Account</div>
            <button className="nav-link" onClick={handleLogout}>
              <span className="nav-icon"><LogOut size={17} /></span>
              Sign out
            </button>
          </div>
        </nav>

        <div className="sidebar-footer">
          <div className="user-pill">
            <div className="user-avatar">
              {user?.username?.[0]?.toUpperCase() || "U"}
            </div>
            <div className="user-info">
              <div className="user-name">{user?.username}</div>
              <div className="user-role">{user?.is_admin ? "Admin" : "Reader"}</div>
            </div>
            <Zap size={14} color="var(--accent)" />
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="main-content">
        {/* Mobile topbar */}
        <div className="topbar" style={{ display: 'flex' }}>
          <button className="hamburger" onClick={() => setSidebarOpen(!sidebarOpen)}>
            {sidebarOpen ? <X size={22} /> : <Menu size={22} />}
          </button>
          <span style={{ fontFamily: "'Playfair Display', serif", fontSize: '18px', fontWeight: 700 }}>
            📰 NewsFlow
          </span>
        </div>

        <Outlet />
      </main>
    </div>
  );
}
