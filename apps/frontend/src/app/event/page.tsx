import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError, createChallenge, getEvent, getSession, getTenant, loginWithGoogle, logout, type EventInfo, type Tenant } from "@/lib/tenant-api";
import "./participant.css";
import { OrganizerGallery, ParticipantGallery } from "./gallery";
import { OrganizerPanel } from "./manage-panel";

type GoogleIdentity = {
  initialize: (config: { client_id: string; nonce: string; ux_mode: "popup"; callback: (response: { credential: string }) => void }) => void;
  renderButton: (container: HTMLElement, options: { theme: string; size: string; text: string }) => void;
  disableAutoSelect: () => void;
};
declare global { interface Window { google?: { accounts: { id: GoogleIdentity } } } }

let googleScript: Promise<void> | undefined;
function loadGoogle(): Promise<void> {
  if (window.google?.accounts.id) return Promise.resolve();
  if (!googleScript) {
    googleScript = new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => { script.remove(); googleScript = undefined; reject(new Error("Google indisponível")); };
      document.head.appendChild(script);
    });
  }
  return googleScript;
}

export default function ParticipantEventPage({ manage = false, panel = false }: { manage?: boolean; panel?: boolean }) {
  const { eventId = "" } = useParams();
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [phase, setPhase] = useState<"loading" | "login" | "ready" | "notfound" | "error">("loading");
  const [signedIn, setSignedIn] = useState(false);
  const [event, setEvent] = useState<EventInfo | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const buttonRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    setPhase("loading"); setMessage(""); setEvent(null);
    try {
      const branding = await getTenant(); setTenant(branding);
      try { await getSession(); } catch (error) {
        if (error instanceof ApiError && error.status === 401) { setSignedIn(false); setPhase("login"); return; }
        throw error;
      }
      setSignedIn(true);
      if (panel) { setPhase("ready"); return; }
      try { setEvent(await getEvent(eventId)); setPhase("ready"); } catch (error) {
        if (error instanceof ApiError && error.status === 401) { setSignedIn(false); setPhase("login"); return; }
        if (error instanceof ApiError && (error.status === 404 || error.status === 422)) { setPhase("notfound"); return; }
        throw error;
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) setPhase("notfound");
      else setPhase("error");
    }
  }, [eventId, panel]);
  useEffect(() => { void refresh(); }, [refresh]);

  const prepareLogin = async () => {
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
    if (!clientId) { setMessage("O login Google ainda não foi configurado."); return; }
    if (window.location.protocol !== "https:") { setMessage("O login requer uma conexão HTTPS."); return; }
    setBusy(true); setMessage("");
    try {
      const [{ nonce }] = await Promise.all([createChallenge(), loadGoogle()]);
      if (!window.google || !buttonRef.current) throw new Error("Google indisponível");
      buttonRef.current.replaceChildren();
      window.google.accounts.id.initialize({ client_id: clientId, nonce, ux_mode: "popup", callback: ({ credential }) => {
        setBusy(true);
        void loginWithGoogle(credential).then(refresh).catch(() => setMessage("Não foi possível entrar. Prepare o login e tente novamente.")).finally(() => setBusy(false));
      } });
      window.google.accounts.id.renderButton(buttonRef.current, { theme: "outline", size: "large", text: "signin_with" });
      setMessage("Selecione sua conta no botão Google abaixo. Se demorar mais de cinco minutos, prepare o login novamente.");
    } catch { setMessage("Não foi possível preparar o login Google. Tente novamente."); }
    finally { setBusy(false); }
  };
  const signOut = async () => {
    setBusy(true); setMessage("");
    try { await logout(); window.google?.accounts.id.disableAutoSelect(); setEvent(null); setSignedIn(false); setPhase("login"); }
    catch (error) { if (error instanceof ApiError && error.status === 401) { setEvent(null); setSignedIn(false); setPhase("login"); } else setMessage("Não foi possível sair. Tente novamente."); }
    finally { setBusy(false); }
  };
  const onExpired = useCallback(() => { setSignedIn(false); setEvent(null); setPhase("login"); setMessage("Sua sessão expirou. Entre novamente."); }, []);
  const primary = tenant?.branding.colors.primary;
  const accent = primary && /^#[0-9a-fA-F]{6}$/.test(primary) ? primary : "#5934c9";
  return <main className="participant-page" style={{ "--tenant-accent": accent } as React.CSSProperties}>
    <header className="participant-header">
      <div className="participant-brand">{tenant?.branding.logo_url && <img src={tenant.branding.logo_url} alt="" />}<span>{tenant?.name || "Face Match"}</span></div>
      {signedIn && <button className="participant-link" disabled={busy} onClick={() => void signOut()}>Sair</button>}
    </header>
    <section className={`participant-card${panel ? " participant-wide" : ""}`} aria-live="polite">
      <p className="participant-eyebrow">{panel ? "ORGANIZAÇÃO" : "SEU EVENTO · SUAS MEMÓRIAS"}</p>
      {phase === "loading" && <><h1>{panel ? "Preparando o painel" : "Preparando seu evento"}</h1><p>Aguarde um instante.</p></>}
      {phase === "login" && <><h1>{panel ? "Painel do organizador" : "Boas-vindas ao seu evento"}</h1><p>{panel ? "Entre com a conta Google de organizador para gerenciar eventos e a identidade visual." : "Entre com sua conta Google para acessar os detalhes do evento."}</p><button className="participant-action" disabled={busy} onClick={() => void prepareLogin()}>{busy ? "Preparando…" : "Preparar login com Google"}</button><div className="google-button" ref={buttonRef} /></>}
      {phase === "ready" && panel && <><h1>Painel do organizador</h1><OrganizerPanel onExpired={onExpired} onBrandingChange={() => void getTenant().then(setTenant).catch(() => undefined)} /></>}
      {phase === "ready" && !panel && event && <><h1>{event.name}</h1>{manage ? <OrganizerGallery key={eventId} eventId={eventId} onExpired={onExpired} /> : <ParticipantGallery key={eventId} eventId={eventId} onExpired={onExpired} />}</>}
      {phase === "notfound" && <><h1>Evento indisponível</h1><p>Não encontramos este evento ou sua conta não tem acesso a ele.</p><button className="participant-link" onClick={() => void refresh()}>Tentar novamente</button></>}
      {phase === "error" && <><h1>Não foi possível carregar</h1><p>Verifique sua conexão e tente novamente.</p><button className="participant-action" onClick={() => void refresh()}>Tentar novamente</button></>}
      {message && <p className="participant-message" role="status">{message}</p>}
    </section>
    <footer className="participant-footer">Um espaço para reencontrar seus melhores momentos.</footer>
  </main>;
}
