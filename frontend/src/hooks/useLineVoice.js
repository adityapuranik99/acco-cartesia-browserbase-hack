import { useCallback, useEffect, useRef, useState } from 'react';

const CARTESIA_VERSION = '2025-04-16';
const INPUT_FORMAT = 'pcm_44100';

function base64FromBytes(bytes) {
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    const sub = bytes.subarray(i, i + chunk);
    binary += String.fromCharCode(...sub);
  }
  return btoa(binary);
}

function bytesFromBase64(payload) {
  const binary = atob(payload);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

function float32ToPcm16(float32Array) {
  const out = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i += 1) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return new Uint8Array(out.buffer);
}

async function fetchAccessToken(apiBase) {
  const response = await fetch(`${apiBase}/cartesia/access-token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ expires_in: 600, grant_agent: true }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || 'Failed to create Cartesia access token');
  }
  const payload = await response.json();
  return payload.token || '';
}

export function useLineVoice({ apiBase, agentId }) {
  const [isConnected, setIsConnected] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [status, setStatus] = useState('Line idle');
  const [error, setError] = useState('');

  const wsRef = useRef(null);
  const streamIdRef = useRef('');
  const mediaStreamRef = useRef(null);
  const micCtxRef = useRef(null);
  const micSourceRef = useRef(null);
  const processorRef = useRef(null);
  const playbackCtxRef = useRef(null);
  const speakingTimerRef = useRef(null);
  const keepAliveRef = useRef(null);

  const closeInternal = useCallback(() => {
    if (keepAliveRef.current) {
      clearInterval(keepAliveRef.current);
      keepAliveRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current.onaudioprocess = null;
      processorRef.current = null;
    }
    if (micSourceRef.current) {
      micSourceRef.current.disconnect();
      micSourceRef.current = null;
    }
    if (micCtxRef.current) {
      micCtxRef.current.close().catch(() => {});
      micCtxRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    if (playbackCtxRef.current) {
      playbackCtxRef.current.close().catch(() => {});
      playbackCtxRef.current = null;
    }
    if (speakingTimerRef.current) {
      clearTimeout(speakingTimerRef.current);
      speakingTimerRef.current = null;
    }
    streamIdRef.current = '';
    setIsConnected(false);
    setIsListening(false);
    setIsSpeaking(false);
  }, []);

  const disconnect = useCallback(() => {
    closeInternal();
    setStatus('Disconnected');
  }, [closeInternal]);

  const playPcmChunk = useCallback((base64Payload, sampleRate = 24000) => {
    const bytes = bytesFromBase64(base64Payload);
    const int16 = new Int16Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 2));
    const floatData = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i += 1) {
      floatData[i] = int16[i] / 0x8000;
    }

    if (!playbackCtxRef.current) {
      playbackCtxRef.current = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate,
      });
    }

    const ctx = playbackCtxRef.current;
    const buffer = ctx.createBuffer(1, floatData.length, sampleRate);
    buffer.copyToChannel(floatData, 0);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    source.start();

    setIsSpeaking(true);
    if (speakingTimerRef.current) clearTimeout(speakingTimerRef.current);
    speakingTimerRef.current = setTimeout(() => setIsSpeaking(false), 500);
  }, []);

  const connect = useCallback(async () => {
    if (isConnected) return;
    if (!agentId) {
      setError('Missing VITE_CARTESIA_LINE_AGENT_ID');
      return;
    }

    setError('');
    setStatus('Requesting token...');

    try {
      const token = await fetchAccessToken(apiBase);
      if (!token) {
        throw new Error('No token returned by backend');
      }

      const streamId = `web-${Date.now()}`;
      streamIdRef.current = streamId;

      const wsUrl = `wss://api.cartesia.ai/agents/stream/${encodeURIComponent(agentId)}?access_token=${encodeURIComponent(token)}&cartesia_version=${encodeURIComponent(CARTESIA_VERSION)}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        setStatus('Connected to Line');
        ws.send(
          JSON.stringify({
            event: 'start',
            stream_id: streamId,
            config: { input_format: INPUT_FORMAT },
          }),
        );

        keepAliveRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ event: 'custom', stream_id: streamId, metadata: { keepalive: true } }));
          }
        }, 20000);
      };

      ws.onmessage = (message) => {
        try {
          const data = JSON.parse(message.data);
          const event = data.event || data.type;
          if (event === 'ack') {
            const ackStream = data.stream_id || streamId;
            streamIdRef.current = ackStream;
            setStatus(`Line ready (${ackStream})`);
            return;
          }
          if (event === 'media_output') {
            const payload = data.media?.payload;
            if (payload) {
              const sampleRate = data.media?.sample_rate || data.media?.sampleRate || 24000;
              playPcmChunk(payload, sampleRate);
            }
            return;
          }
          if (event === 'clear') {
            setIsSpeaking(false);
            return;
          }
          if (event === 'error') {
            setError(data.error?.message || data.message || 'Line websocket error');
          }
        } catch (_err) {
          // Ignore malformed messages to keep stream resilient.
        }
      };

      ws.onerror = () => {
        setError('Line websocket connection error');
      };

      ws.onclose = (evt) => {
        closeInternal();
        setStatus(`Closed (${evt.code}${evt.reason ? `: ${evt.reason}` : ''})`);
      };

      setStatus('Opening microphone...');
      const mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = mediaStream;
      const micCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 44100 });
      micCtxRef.current = micCtx;

      const source = micCtx.createMediaStreamSource(mediaStream);
      micSourceRef.current = source;
      const processor = micCtx.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (event) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        const pcm = float32ToPcm16(event.inputBuffer.getChannelData(0));
        wsRef.current.send(
          JSON.stringify({
            event: 'media_input',
            stream_id: streamIdRef.current,
            media: { payload: base64FromBytes(pcm) },
          }),
        );
      };

      source.connect(processor);
      processor.connect(micCtx.destination);
      setIsListening(true);
      setStatus('Streaming mic audio');
    } catch (err) {
      closeInternal();
      setError(err?.message || 'Failed to connect to Line');
      setStatus('Line connection failed');
    }
  }, [agentId, apiBase, closeInternal, isConnected, playPcmChunk]);

  useEffect(() => () => closeInternal(), [closeInternal]);

  return {
    isConnected,
    isListening,
    isSpeaking,
    status,
    error,
    connect,
    disconnect,
  };
}
