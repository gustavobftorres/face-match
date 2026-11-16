import { useEffect, useState, type FormEvent } from "react";
import { ApiError, galleryPhotoUrl, latestGalleryJob, searchGallery, startGalleryIndex, type GalleryJob, type GallerySearch } from "@/lib/tenant-api";

function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Sua sessão expirou. Entre novamente.";
    if (error.status === 403) return "Não foi possível validar a sessão. Atualize a página e tente novamente.";
    if (error.status === 404) return "O evento não está disponível para esta conta.";
    if (error.status === 413) return "A imagem é grande demais. Escolha uma foto menor que 5 MB.";
    if (error.status === 422) return "Use uma imagem válida com exatamente um rosto.";
    if (error.status === 409) return "Já existe uma indexação em andamento.";
  }
  return "Não foi possível concluir a operação. Tente novamente.";
}

export function ParticipantGallery({ eventId, onExpired }: { eventId: string; onExpired: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<GallerySearch | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) { setMessage("Escolha uma selfie para continuar."); return; }
    setBusy(true); setMessage(""); setResult(null);
    try { setResult(await searchGallery(eventId, file)); }
    catch (error) { if (error instanceof ApiError && error.status === 401) onExpired(); setMessage(errorText(error)); }
    finally { setBusy(false); }
  };
  return <div className="gallery-panel"><p>Envie uma selfie para encontrar suas fotos neste evento.</p>
    <form onSubmit={event => void submit(event)}>
      <label htmlFor="event-selfie">Sua selfie</label>
      <input id="event-selfie" type="file" accept="image/*" onChange={event => { setFile(event.target.files?.[0] ?? null); setResult(null); }} />
      <button className="participant-action" type="submit" disabled={busy}>{busy ? "Buscando…" : "Encontrar minhas fotos"}</button>
    </form>
    {message && <p role="alert">{message}</p>}
    {result && result.photos.length === 0 && <p>Nenhuma foto correspondente foi encontrada.</p>}
    {result && result.photos.length > 0 && <><h2>Suas fotos</h2><div className="event-gallery">{result.photos.map((photo, index) => {
      const url = galleryPhotoUrl(eventId, result.id, photo);
      return <figure key={photo}><img src={url} alt={`Foto ${index + 1} do evento`} loading="lazy" onError={() => setMessage("Não foi possível carregar uma foto. Sua sessão ou acesso pode ter expirado.")} /><a href={url} download={`foto-${index + 1}.jpg`}>Baixar foto</a></figure>;
    })}</div></>}
  </div>;
}

const statusText: Record<GalleryJob["status"], string> = { queued: "Na fila", processing: "Processando", ready: "Pronto", failed: "Falhou" };
export function OrganizerGallery({ eventId, onExpired }: { eventId: string; onExpired: () => void }) {
  const [job, setJob] = useState<GalleryJob | null>(null);
  const [access, setAccess] = useState<"loading" | "allowed" | "denied" | "error">("loading");
  const [folder, setFolder] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const response = await latestGalleryJob(eventId);
        if (!active) return;
        setJob(response.job); setAccess("allowed");
        if (response.job && ["queued", "processing"].includes(response.job.status)) timer = setTimeout(() => void poll(), 3000);
      } catch (error) {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) onExpired();
        setAccess(error instanceof ApiError && error.status === 404 ? "denied" : "error");
      }
    };
    void poll();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [eventId, onExpired, reload]);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setMessage("");
    try { setJob(await startGalleryIndex(eventId, folder)); setFolder(""); setReload(n => n + 1); }
    catch (error) { if (error instanceof ApiError && error.status === 401) onExpired(); setMessage(errorText(error)); if (error instanceof ApiError && error.status === 409) setReload(n => n + 1); }
    finally { setBusy(false); }
  };
  if (access === "loading") return <p>Verificando acesso de organização…</p>;
  if (access === "denied") return <p>Esta área não está disponível para sua conta.</p>;
  if (access === "error") return <><p>Não foi possível verificar a indexação.</p><button className="participant-link" onClick={() => setReload(n => n + 1)}>Tentar novamente</button></>;
  return <div className="gallery-panel"><p>Indexe uma pasta pública do Google Drive para este evento. Os arquivos continuam públicos na origem.</p>
    <p>Status: <strong>{job ? statusText[job.status] : "Nenhuma indexação"}</strong></p>
    {job?.status === "failed" && <p>Não foi possível indexar a pasta. Verifique o link e tente novamente.</p>}
    <form onSubmit={event => void submit(event)}><label htmlFor="folder-url">Link ou ID da pasta pública</label><input id="folder-url" value={folder} onChange={event => setFolder(event.target.value)} required /><button className="participant-action" disabled={busy || job?.status === "queued" || job?.status === "processing"}>{busy ? "Enviando…" : "Indexar pasta"}</button></form>
    {message && <p role="alert">{message}</p>}
  </div>;
}
