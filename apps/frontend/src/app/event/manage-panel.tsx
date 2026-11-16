import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiError, createAdminEvent, deleteAdminLogo, getAdminAccess, getAdminBranding, listAdminEvents, setAdminEventStatus, updateAdminBranding, updateAdminEvent, uploadAdminLogo, type AdminBranding, type AdminEvent } from "@/lib/tenant-api";

const statusText: Record<AdminEvent["status"], string> = { draft: "Rascunho", published: "Publicado", closed: "Encerrado" };
const slugify = (value: string) => value.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 63);

function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Sua sessão expirou. Entre novamente.";
    if (error.status === 403) return "Não foi possível validar a sessão ou você não tem permissão.";
    if (error.status === 404) return "Item não encontrado.";
    if (error.status === 409) return "Este endereço (slug) já está em uso ou o estado do evento mudou.";
    if (error.status === 413) return "O arquivo é grande demais. Use uma imagem de até 1 MB.";
    if (error.status === 422) return "Dados inválidos. Revise os campos ou use uma imagem PNG, JPEG ou WebP válida.";
  }
  return "Não foi possível concluir a operação. Tente novamente.";
}

export function OrganizerPanel({ onExpired, onBrandingChange }: { onExpired: () => void; onBrandingChange: () => void }) {
  const [access, setAccess] = useState<"loading" | "allowed" | "denied" | "error">("loading");
  const [events, setEvents] = useState<AdminEvent[]>([]);
  const [branding, setBranding] = useState<AdminBranding | null>(null);
  const [palette, setPalette] = useState("");
  const [editing, setEditing] = useState<AdminEvent | null>(null);
  const [form, setForm] = useState({ name: "", slug: "", description: "" });
  const [slugTouched, setSlugTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const fail = useCallback((error: unknown) => { if (error instanceof ApiError && error.status === 401) onExpired(); setMessage(errorText(error)); }, [onExpired]);

  const load = useCallback(async () => {
    setAccess("loading");
    try {
      await getAdminAccess();
      const [list, theme] = await Promise.all([listAdminEvents(), getAdminBranding()]);
      setEvents(list.events); setBranding(theme); setPalette(theme.palette ?? ""); setAccess("allowed");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onExpired();
      setAccess(error instanceof ApiError && error.status === 403 ? "denied" : "error");
    }
  }, [onExpired]);
  useEffect(() => { void load(); }, [load]);

  const run = async (action: () => Promise<void>) => { setBusy(true); setMessage(""); try { await action(); } catch (error) { fail(error); } finally { setBusy(false); } };
  const replace = (event: AdminEvent) => setEvents(current => current.map(item => item.id === event.id ? event : item));
  const resetForm = () => { setEditing(null); setForm({ name: "", slug: "", description: "" }); setSlugTouched(false); };
  const startEdit = (event: AdminEvent) => { setEditing(event); setForm({ name: event.name, slug: event.slug, description: event.description ?? "" }); setSlugTouched(true); };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      const draft = { name: form.name.trim(), slug: form.slug, description: form.description.trim() || null };
      if (editing) { replace(await updateAdminEvent(editing.id, draft)); setMessage("Evento atualizado."); }
      else { const created = await createAdminEvent(draft); setEvents(current => [created, ...current]); setMessage("Evento criado como rascunho."); }
      resetForm();
    });
  };
  const changeStatus = (event: AdminEvent, action: "publish" | "unpublish" | "close") => void run(async () => { replace(await setAdminEventStatus(event.id, action)); });
  const applyBranding = (next: AdminBranding) => { setBranding(next); setPalette(next.palette ?? ""); onBrandingChange(); };
  const colors = branding?.palettes[palette] ?? branding?.colors ?? {};

  if (access === "loading") return <p>Verificando acesso de organização…</p>;
  if (access === "denied") return <><h2>Acesso restrito</h2><p>Esta área é exclusiva para organizadores deste espaço. Sua conta não tem permissão para administrá-lo.</p></>;
  if (access === "error") return <><p>Não foi possível carregar o painel.</p><button className="participant-link" onClick={() => void load()}>Tentar novamente</button></>;
  return <div className="manage-panel">
    {message && <p role="status" className="participant-message">{message}</p>}
    <h2>Eventos</h2>
    {events.length === 0 && <p>Nenhum evento ainda. Crie o primeiro abaixo.</p>}
    <ul className="manage-events">{events.map(event => <li key={event.id}>
      <div><strong>{event.name}</strong> <span className={`manage-badge manage-${event.status}`}>{statusText[event.status]}</span><br /><small>/events/{event.id} · {event.slug}</small></div>
      <div className="manage-actions">
        {event.status === "published" ? <button className="participant-link" disabled={busy} onClick={() => changeStatus(event, "unpublish")}>Despublicar</button> : <button className="participant-link" disabled={busy} onClick={() => changeStatus(event, "publish")}>Publicar</button>}
        {event.status !== "closed" && <button className="participant-link" disabled={busy} onClick={() => changeStatus(event, "close")}>Encerrar</button>}
        <button className="participant-link" disabled={busy} onClick={() => startEdit(event)}>Editar</button>
        <Link className="participant-link" to={`/events/${event.id}/manage`}>Fotos</Link>
      </div></li>)}</ul>
    <form onSubmit={submit} aria-label={editing ? "Editar evento" : "Novo evento"}>
      <h3>{editing ? `Editar ${editing.name}` : "Novo evento"}</h3>
      <label htmlFor="ev-name">Nome</label>
      <input id="ev-name" value={form.name} maxLength={120} required onChange={e => { const name = e.target.value; setForm(f => ({ ...f, name, slug: slugTouched ? f.slug : slugify(name) })); }} />
      <label htmlFor="ev-slug">Endereço (slug)</label>
      <input id="ev-slug" value={form.slug} maxLength={63} required pattern="[a-z0-9]+(-[a-z0-9]+)*" title="Letras minúsculas, números e hífens" onChange={e => { setSlugTouched(true); setForm(f => ({ ...f, slug: e.target.value })); }} />
      <label htmlFor="ev-desc">Descrição (opcional)</label>
      <textarea id="ev-desc" value={form.description} maxLength={2000} rows={3} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
      <div className="manage-actions"><button className="participant-action" disabled={busy}>{editing ? "Salvar alterações" : "Criar evento"}</button>{editing && <button type="button" className="participant-link" onClick={resetForm}>Cancelar</button>}</div>
    </form>
    <h2>Identidade visual</h2>
    {branding && <>
      <fieldset className="manage-palettes"><legend>Paleta de cores</legend>
        {Object.entries(branding.palettes).map(([key, value]) => <label key={key} className="manage-palette">
          <input type="radio" name="palette" value={key} checked={palette === key} onChange={() => setPalette(key)} />
          <span className="manage-swatches" aria-hidden="true">{[value.primary, value.secondary, value.accent, value.background].map(color => <i key={color} style={{ background: color }} />)}</span>{key}</label>)}
      </fieldset>
      <button className="participant-action" disabled={busy || !palette || palette === branding.palette} onClick={() => void run(async () => { applyBranding(await updateAdminBranding(palette)); setMessage("Paleta salva."); })}>Salvar paleta</button>
      <div className="manage-preview" aria-label="Prévia" style={{ background: colors.background, color: colors.text, borderColor: colors.accent }}>
        <div className="manage-preview-card" style={{ background: colors.surface }}>
          {branding.logo_url && <img src={branding.logo_url} alt="Logo atual" />}
          <strong>Prévia do seu espaço</strong>
          <span className="manage-preview-button" style={{ background: colors.primary }}>Encontrar minhas fotos</span>
        </div>
      </div>
      <h3>Logo</h3>
      <p><small>PNG, JPEG ou WebP até 1 MB. A imagem é reprocessada e reduzida para até 512 px.</small></p>
      <input type="file" aria-label="Arquivo do logo" accept="image/png,image/jpeg,image/webp" disabled={busy} onChange={e => { const file = e.target.files?.[0]; e.target.value = ""; if (file) void run(async () => { applyBranding(await uploadAdminLogo(file)); setMessage("Logo atualizado."); }); }} />
      {branding.logo_url && <button className="participant-link" disabled={busy} onClick={() => void run(async () => { applyBranding(await deleteAdminLogo()); setMessage("Logo removido."); })}>Remover logo</button>}
    </>}
  </div>;
}
