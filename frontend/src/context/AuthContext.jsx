import { createContext, useContext, useState, useEffect } from "react";
import api from "../api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("nf_token");
    if (token) {
      api.get("/api/auth/me")
        .then(r => setUser(r.data))
        .catch(() => localStorage.removeItem("nf_token"))
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (username, password) => {
    const form = new FormData();
    form.append("username", username);
    form.append("password", password);
    const { data } = await api.post("/api/auth/login", form);
    localStorage.setItem("nf_token", data.access_token);
    setUser({ username: data.username, is_admin: data.is_admin });
    return data;
  };

  const register = async (username, email, password) => {
    const { data } = await api.post("/api/auth/register", { username, email, password });
    localStorage.setItem("nf_token", data.access_token);
    setUser({ username: data.username, is_admin: data.is_admin });
    return data;
  };

  const logout = () => {
    localStorage.removeItem("nf_token");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, login, register, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
