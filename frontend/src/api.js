import axios from "axios";

// Single axios instance used by every file in the app.
// Interceptor reads the token from localStorage before EVERY request —
// no timing issues, no React state race conditions.
const api = axios.create();

api.interceptors.request.use(config => {
  const token = localStorage.getItem("nf_token");
  if (token) {
    config.headers["Authorization"] = `Bearer ${token}`;
  }
  return config;
});

export default api;
