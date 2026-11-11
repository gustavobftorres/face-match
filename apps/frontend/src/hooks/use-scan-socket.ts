import { useEffect, useRef, useState, useCallback } from "react";
import { WebSocketMessage } from "@/lib/types";

export function useScanSocket(
  baseUrl: string = import.meta.env.VITE_WS_URL || "ws://localhost:8000/api/v1/ws/updates",
  onMessage?: (message: WebSocketMessage) => void
) {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const scanIdRef = useRef<string | null>(null);
  const onMessageRef = useRef(onMessage);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const connect = useCallback((scanId: string, afterSequence = 0): Promise<void> => {
    return new Promise((resolve, reject) => {
      if (
        socketRef.current?.readyState === WebSocket.OPEN &&
        scanIdRef.current === scanId
      ) {
        resolve();
        return;
      }

      let settled = false;
      let connectionTimeout: ReturnType<typeof setTimeout> | undefined;
      const settle = (error?: Error) => {
        if (settled) return;
        settled = true;
        if (connectionTimeout) clearTimeout(connectionTimeout);
        if (error) reject(error);
        else resolve();
      };

      try {
        const previousSocket = socketRef.current;
        socketRef.current = null;
        previousSocket?.close();
        setIsConnected(false);
        setError(null);
        const cursor = Number.isInteger(afterSequence) && afterSequence > 0 ? afterSequence : 0;
        const url = `${baseUrl.replace(/\/$/, "")}/${encodeURIComponent(scanId)}?after_sequence=${cursor}`;
        const ws = new WebSocket(url);
        socketRef.current = ws;
        scanIdRef.current = scanId;

        ws.onopen = () => {
          if (socketRef.current !== ws) {
            settle(new Error("WebSocket connection was superseded."));
            ws.close();
            return;
          }
          setIsConnected(true);
          setError(null);
          settle();
        };

        ws.onmessage = (event) => {
          try {
            const parsed: unknown = JSON.parse(event.data);
            if (
              !parsed ||
              typeof parsed !== "object" ||
              !("scan_id" in parsed) ||
              !("sequence" in parsed) ||
              typeof parsed.sequence !== "number" ||
              !Number.isInteger(parsed.sequence)
            ) return;
            const data = parsed as WebSocketMessage;
            if (data.scan_id !== scanId || scanIdRef.current !== scanId) return;
            if (onMessageRef.current) onMessageRef.current(data);
          } catch {
            setError("Failed to parse server message.");
          }
        };

        ws.onclose = () => {
          // Closing a superseded/disconnected socket must still settle its own
          // pending connect() call, even though socketRef now points elsewhere.
          settle(new Error("WebSocket connection closed before opening."));
          if (socketRef.current !== ws) return;
          socketRef.current = null;
          setIsConnected(false);
        };

        ws.onerror = () => {
          const msg = "Cannot reach the scanning server. Is the backend running?";
          if (socketRef.current === ws) setError(msg);
          settle(new Error(msg));
        };

        connectionTimeout = setTimeout(() => {
          const message = "Timed out while connecting to the scanning server.";
          if (socketRef.current === ws) setError(message);
          settle(new Error(message));
          ws.close();
        }, 10000);
      } catch {
        const msg = "Failed to create WebSocket connection.";
        setError(msg);
        settle(new Error(msg));
      }
    });
  }, [baseUrl]);

  const disconnect = useCallback(() => {
    const socket = socketRef.current;
    socketRef.current = null;
    scanIdRef.current = null;
    socket?.close();
    setIsConnected(false);
    setError(null);
  }, []);

  useEffect(() => {
    return () => {
      const socket = socketRef.current;
      socketRef.current = null;
      scanIdRef.current = null;
      socket?.close();
    };
  }, []);

  return { isConnected, error, connect, disconnect };
}
