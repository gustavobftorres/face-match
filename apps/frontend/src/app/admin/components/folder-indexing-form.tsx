import { useState } from "react";
import { FolderPlus, LogIn, ShieldCheck, LogOut } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/hooks/use-auth";
import { indexFolderAdmin } from "@/lib/api";

interface FolderIndexingFormProps {
  onFolderIndexed: () => void;
}

export function FolderIndexingForm({ onFolderIndexed }: FolderIndexingFormProps) {
  const { authState, login, logout } = useAuth();
  const [driveLink, setDriveLink] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!authState.accessToken) {
      toast.error("Conecte sua conta Google primeiro");
      return;
    }
    if (!driveLink.trim()) {
      toast.error("Informe o link ou ID da pasta");
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await indexFolderAdmin(driveLink.trim(), authState.accessToken);
      toast.success(response.message || "Pasta adicionada à fila");
      setDriveLink("");
      onFolderIndexed();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Erro ao indexar pasta";
      toast.error(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-2xl border border-[#211E1D]/10 bg-[#FCF9F2]">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[#211E1D]/12 ${
              authState.isAuthenticated ? "bg-[#E2F3EE] text-[#175F50]" : "bg-white text-[#211E1D]"
            }`}
          >
            <ShieldCheck className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-medium text-[#211E1D]">
                {authState.isAuthenticated
                  ? "Google Drive conectado"
                  : "Conta Google necessária"}
              </p>
              <Badge variant={authState.isAuthenticated ? "success" : "neutral"}>
                {authState.isAuthenticated ? "Conectado" : "Desconectado"}
              </Badge>
            </div>
            {authState.isAuthenticated && authState.userEmail && (
              <p className="text-xs text-[#6E675F] mt-0.5 truncate">
                {authState.userEmail}
              </p>
            )}
          </div>
        </div>

        {authState.isAuthenticated ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={logout}
            className="w-full sm:w-auto"
          >
            <LogOut className="h-3.5 w-3.5" />
            <span>Sair</span>
          </Button>
        ) : (
          <Button
            type="button"
            variant="primary"
            size="md"
            onClick={login}
            className="w-full sm:w-auto shrink-0"
          >
            <LogIn className="h-4 w-4" />
            <span>Conectar Google Drive</span>
          </Button>
        )}
      </div>

      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-[#6E675F] mb-2">
            Link ou ID da pasta do Google Drive
          </label>
          <div className="flex flex-col sm:flex-row gap-2.5">
            <Input
              type="text"
              placeholder="https://drive.google.com/drive/folders/..."
              value={driveLink}
              onChange={(e) => setDriveLink(e.target.value)}
              disabled={!authState.isAuthenticated || isSubmitting}
              className="flex-1"
            />
            <Button
              type="submit"
              variant="orange"
              disabled={!authState.isAuthenticated || !driveLink.trim() || isSubmitting}
              className="w-full sm:w-auto shrink-0 min-h-[44px]"
            >
              {isSubmitting ? (
                <>
                  <span className="h-4 w-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
                  <span>Enviando...</span>
                </>
              ) : (
                <>
                  <FolderPlus className="h-4 w-4" />
                  <span>Indexar álbum</span>
                </>
              )}
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}
