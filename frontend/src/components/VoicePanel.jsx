import { useCallback, useEffect, useRef, useState } from 'react';
import { useLineVoice } from '../hooks/useLineVoice.js';

const VOICE_STATE_LABELS = {
  LISTENING: 'Listening for request',
  ACK: 'Acknowledged',
  WORKING: 'Working',
  SAFETY_CHECK: 'Safety check',
  RESULT: 'Result ready',
};

const BAR_COUNT = 32;

export default function VoicePanel({ connected, voiceState, voiceMode = 'ptt', onSend, onInterrupt }) {
  const isLineMode = voiceMode === 'line';
  const [input, setInput] = useState('Go to google.com');
  const [isListening, setIsListening] = useState(false);
  const [micSupported, setMicSupported] = useState(false);
  const [micStatus, setMicStatus] = useState('Mic idle');
  const [devices, setDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const analyserRef = useRef(null);
  const animFrameRef = useRef(null);
  const barsRef = useRef(null);
  const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
  const lineAgentId = import.meta.env.VITE_CARTESIA_LINE_AGENT_ID || '';
  const lineVoice = useLineVoice({ apiBase, agentId: lineAgentId });

  const pickRecorderMimeType = () => {
    if (typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') {
      return '';
    }
    const candidates = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/mp4',
      'audio/ogg;codecs=opus',
    ];
    for (const candidate of candidates) {
      if (MediaRecorder.isTypeSupported(candidate)) return candidate;
    }
    return '';
  };

  // Enumerate audio input devices
  const loadDevices = useCallback(async () => {
    try {
      const all = await navigator.mediaDevices.enumerateDevices();
      const mics = all.filter((d) => d.kind === 'audioinput');
      setDevices(mics);
      if (mics.length === 0) {
        setMicStatus('No microphone detected');
      }
      if (!selectedDeviceId && mics.length > 0) {
        setSelectedDeviceId(mics[0].deviceId);
      }
    } catch (_) {
      // ignore
    }
  }, [selectedDeviceId]);

  useEffect(() => {
    if (isLineMode) {
      setMicSupported(false);
      setMicStatus('Line mode active');
      return () => {};
    }

    if (!navigator.mediaDevices || typeof MediaRecorder === 'undefined') {
      setMicSupported(false);
      setMicStatus('Mic STT not supported in this browser');
      return;
    }
    setMicSupported(true);
    loadDevices();
    navigator.mediaDevices.addEventListener('devicechange', loadDevices);

    return () => {
      navigator.mediaDevices.removeEventListener('devicechange', loadDevices);
      try {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
          mediaRecorderRef.current.stop();
        }
      } catch (_err) {
        // no-op
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, [isLineMode, loadDevices]);

  // Real-time visualizer driven by AnalyserNode
  const startVisualizer = useCallback((stream) => {
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = audioCtx.createMediaStreamSource(stream);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 128;
    analyser.smoothingTimeConstant = 0.75;
    source.connect(analyser);
    analyserRef.current = { analyser, audioCtx };

    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    const draw = () => {
      analyser.getByteFrequencyData(dataArray);
      const bars = barsRef.current;
      if (bars) {
        const children = bars.children;
        const step = Math.floor(dataArray.length / BAR_COUNT);
        for (let i = 0; i < children.length; i++) {
          const val = dataArray[i * step] || 0;
          const pct = val / 255;
          const h = Math.max(3, pct * 100);
          children[i].style.height = `${h}%`;
          children[i].style.opacity = Math.max(0.25, pct);
        }
      }
      animFrameRef.current = requestAnimationFrame(draw);
    };
    draw();
  }, []);

  const stopVisualizer = useCallback(() => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (analyserRef.current) {
      analyserRef.current.audioCtx.close().catch(() => {});
      analyserRef.current = null;
    }
    // Reset bars to idle
    if (barsRef.current) {
      for (const child of barsRef.current.children) {
        child.style.height = '3%';
        child.style.opacity = '0.25';
      }
    }
  }, []);

  const submit = (e) => {
    e.preventDefault();
    if (isLineMode) return;
    if (!input.trim()) return;
    onInterrupt?.();
    onSend(input.trim());
    setInput('');
  };

  const startMic = async () => {
    if (isLineMode || !connected || isListening) return;
    onInterrupt?.();
    try {
      if (devices.length === 0) {
        setMicStatus('No microphone detected');
        return;
      }
      const constraints = { audio: selectedDeviceId ? { deviceId: { exact: selectedDeviceId } } : true };
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = stream;
      chunksRef.current = [];

      // Re-enumerate after permission grant (labels may now be available)
      loadDevices();

      startVisualizer(stream);

      const mimeType = pickRecorderMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        setIsListening(false);
        setMicStatus('Transcribing...');
        stopVisualizer();

        const blobType = recorder.mimeType || 'audio/webm';
        const audioBlob = new Blob(chunksRef.current, { type: blobType });
        chunksRef.current = [];

        if (streamRef.current) {
          streamRef.current.getTracks().forEach((track) => track.stop());
          streamRef.current = null;
        }

        if (audioBlob.size === 0) {
          setMicStatus('No audio captured');
          return;
        }

        const formData = new FormData();
        const extension = blobType.includes('ogg') ? 'ogg' : blobType.includes('mp4') ? 'm4a' : 'webm';
        formData.append('audio', audioBlob, `speech.${extension}`);

        try {
          const response = await fetch(`${apiBase}/stt`, {
            method: 'POST',
            body: formData,
          });
          if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'STT request failed');
          }

          const data = await response.json();
          const transcript = (data.transcript || '').trim();
          if (!transcript) {
            setMicStatus('No transcript returned');
            return;
          }

          setInput(transcript);
          onSend?.(transcript);
          setMicStatus('Mic idle');
        } catch (err) {
          setMicStatus(`STT error: ${err.message}`);
        }
      };

      recorder.start();
      setIsListening(true);
      setMicStatus('Listening...');
    } catch (err) {
      const msg = err?.name === 'NotAllowedError'
        ? 'Microphone permission denied'
        : err?.name === 'NotFoundError'
          ? 'No microphone found'
          : err?.name === 'NotReadableError'
            ? 'Microphone is busy in another app'
            : err.message || 'permission/device issue';
      setMicStatus(`Mic error: ${msg}`);
    }
  };

  const stopMic = () => {
    if (!mediaRecorderRef.current) return;
    if (mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
  };

  const toggleMic = () => {
    if (isListening) {
      stopMic();
      return;
    }
    startMic();
  };

  return (
    <section className="panel voice-panel">
      <header className="card-title-row">
        <h2 className="card-title">
          <span className="material-icons-outlined">mic</span>
          Voice Control
        </h2>
        <span className="card-kicker">{VOICE_STATE_LABELS[voiceState] || voiceState || 'Idle'}</span>
      </header>

      {isLineMode && (
        <>
          <p className="mic-status-text">
            Cartesia Line mode is active. Connect below to stream microphone audio directly to your Line agent.
          </p>
          <div className="line-controls">
            <button
              type="button"
              className="secondary-button"
              onClick={lineVoice.connect}
              disabled={lineVoice.isConnected || !connected}
            >
              Connect Line Audio
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={lineVoice.disconnect}
              disabled={!lineVoice.isConnected}
            >
              Disconnect
            </button>
          </div>
          <p className="mic-status-text">
            {lineVoice.status}
            {lineVoice.isListening ? ' • listening' : ''}
            {lineVoice.isSpeaking ? ' • speaking' : ''}
          </p>
          {lineVoice.error && <p className="mic-status-text">Line error: {lineVoice.error}</p>}
        </>
      )}

      {/* Real-time audio visualizer */}
      <div className={`audio-visualizer ${!isLineMode && isListening ? 'active' : ''}`} ref={barsRef}>
        {Array.from({ length: BAR_COUNT }, (_, i) => (
          <span key={i} className="viz-bar" />
        ))}
      </div>

      {/* Mic selector */}
      {!isLineMode && devices.length > 0 && (
        <div className="mic-selector">
          <span className="material-icons-outlined mic-selector-icon">settings_voice</span>
          <select
            value={selectedDeviceId}
            onChange={(e) => setSelectedDeviceId(e.target.value)}
            disabled={isListening}
          >
            {devices.map((d) => (
              <option key={d.deviceId} value={d.deviceId}>
                {d.label || `Microphone ${d.deviceId.slice(0, 6)}`}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Mic icon button with radiating waves */}
      <div className="mic-button-wrap">
        <button
          type="button"
          className={`mic-icon-button ${isListening ? 'active' : ''}`}
          disabled={isLineMode || !micSupported || !connected}
          onClick={toggleMic}
          aria-label={isListening ? 'Stop listening' : 'Start listening'}
        >
          <span className="material-icons-outlined mic-btn-icon">
            {isListening ? 'mic' : 'mic_none'}
          </span>
          {isListening && (
            <>
              <span className="ripple r1" />
              <span className="ripple r2" />
              <span className="ripple r3" />
            </>
          )}
        </button>
        <span className="mic-label">
          {isLineMode ? 'Line handles microphone input' : isListening ? 'Tap to stop' : 'Tap to speak'}
        </span>
      </div>

      <p className="mic-status-text">{micStatus}</p>

      {!isLineMode && (
        <form onSubmit={submit} className="voice-form">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Speak into mic or type transcript..."
            rows={3}
          />
          <button type="submit" className="secondary-button">Send Transcript</button>
        </form>
      )}
    </section>
  );
}
