"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { WebSocketMessage } from "@/lib/types";

export function useScanSocket(
  url: string = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/api/v1/ws/updates",
  onMessage?: (message: WebSocketMessage) => void
) {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const connect = useCallback((): Promise<void> => {
    return new Promise((resolve, reject) => {
      if (socketRef.current && socketRef.current.readyState <= WebSocket.OPEN) {
        resolve();
        return;
      }

      try {
        const ws = new WebSocket(url);
        socketRef.current = ws;

        ws.onopen = () => {
          setTimeout(() => setIsConnected(true), 0);
          setTimeout(() => setError(null), 0);
          resolve();
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data) as WebSocketMessage;
            if (onMessageRef.current) onMessageRef.current(data);
          } catch {
            setTimeout(() => setError("Failed to parse server message."), 0);
          }
        };

        ws.onclose = () => {
          setTimeout(() => setIsConnected(false), 0);
        };

        ws.onerror = () => {
          const msg = "Cannot reach the scanning server. Is the backend running?";
          setTimeout(() => setError(msg), 0);
          reject(new Error(msg));
        };
      } catch {
        const msg = "Failed to create WebSocket connection.";
        setTimeout(() => setError(msg), 0);
        reject(new Error(msg));
      }
    });
  }, [url]);

  const disconnect = useCallback(() => {
    socketRef.current?.close();
    socketRef.current = null;
  }, []);

  useEffect(() => {
    return () => {
      socketRef.current?.close();
    };
  }, []);

  return { isConnected, error, connect, disconnect };
}
