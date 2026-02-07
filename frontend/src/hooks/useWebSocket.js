import { useEffect, useRef, useState } from 'react';

function playAudioFromBase64(audioB64, mime = 'audio/wav') {
  try {
    const bytes = Uint8Array.from(atob(audioB64), (char) => char.charCodeAt(0));
    const blob = new Blob([bytes], { type: mime });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.play().finally(() => {
      setTimeout(() => URL.revokeObjectURL(url), 8000);
    });
  } catch (_err) {
    // Keep UI resilient if audio decode/playback fails.
  }
}

export function useWebSocket(url = 'ws://localhost:8000/ws') {
  const wsRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [riskLevel, setRiskLevel] = useState('SAFE');
  const [events, setEvents] = useState([]);

  useEffect(() => {
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setEvents((prev) => [...prev, data]);
      if (data.type === 'risk_update' && data.risk_level) {
        setRiskLevel(data.risk_level);
      }
      if (data.type === 'agent_response' && data.metadata?.audio_b64) {
        playAudioFromBase64(data.metadata.audio_b64, data.metadata.audio_mime || 'audio/wav');
      }
    };

    return () => ws.close();
  }, [url]);

  const sendTranscript = (transcript) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return;
    }
    wsRef.current.send(JSON.stringify({ type: 'user_speech', transcript }));
  };

  return { connected, riskLevel, events, sendTranscript };
}
