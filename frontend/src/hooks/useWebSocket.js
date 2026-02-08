import { useEffect, useRef, useState } from 'react';

function playAudioFromBase64(audioB64, mime = 'audio/wav', currentAudioRef) {
  return new Promise((resolve) => {
    try {
      const bytes = Uint8Array.from(atob(audioB64), (char) => char.charCodeAt(0));
      const blob = new Blob([bytes], { type: mime });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      currentAudioRef.current = audio;

      let done = false;

      const cleanup = () => {
        if (done) return;
        done = true;
        if (currentAudioRef.current === audio) {
          currentAudioRef.current = null;
        }
        URL.revokeObjectURL(url);
        resolve();
      };

      audio.onended = cleanup;
      audio.onpause = cleanup;
      audio.onerror = cleanup;
      audio.play().catch(cleanup);
    } catch (_err) {
      // Keep UI resilient if audio decode/playback fails.
      resolve();
    }
  });
}

export function useWebSocket(url = 'ws://localhost:8000/ws') {
  const wsRef = useRef(null);
  const audioQueueRef = useRef(Promise.resolve());
  const currentAudioRef = useRef(null);
  const playbackVersionRef = useRef(0);
  const [connected, setConnected] = useState(false);
  const [riskLevel, setRiskLevel] = useState('SAFE');
  const [voiceState, setVoiceState] = useState('LISTENING');
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
      if (data.type === 'voice_state' && data.voice_state) {
        setVoiceState(data.voice_state);
      }
      if (data.type === 'agent_response' && data.metadata?.audio_b64) {
        const version = playbackVersionRef.current;
        audioQueueRef.current = audioQueueRef.current.finally(async () => {
          if (version !== playbackVersionRef.current) return;
          await playAudioFromBase64(
            data.metadata.audio_b64,
            data.metadata.audio_mime || 'audio/wav',
            currentAudioRef,
          );
        });
      }
    };

    return () => {
      ws.close();
      if (currentAudioRef.current) {
        currentAudioRef.current.pause();
        currentAudioRef.current = null;
      }
    };
  }, [url]);

  const stopSpeechPlayback = () => {
    playbackVersionRef.current += 1;
    audioQueueRef.current = Promise.resolve();
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current.currentTime = 0;
      currentAudioRef.current = null;
    }
  };

  const sendInterrupt = () => {
    stopSpeechPlayback();
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return;
    }
    wsRef.current.send(JSON.stringify({ type: 'interrupt' }));
  };

  const sendTranscript = (transcript) => {
    stopSpeechPlayback();
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return;
    }
    wsRef.current.send(JSON.stringify({ type: 'user_speech', transcript }));
  };

  return { connected, riskLevel, voiceState, events, sendTranscript, sendInterrupt };
}
