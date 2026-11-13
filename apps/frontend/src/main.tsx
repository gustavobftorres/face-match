import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import "./app/globals.css";
import HomePage from "./app/page";
import AdminPage from "./app/admin/page";
import AuthCallbackPage from "./app/auth/callback/page";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
      </Routes>
      <Toaster position="top-center" theme="light" richColors />
    </BrowserRouter>
  </StrictMode>
);
