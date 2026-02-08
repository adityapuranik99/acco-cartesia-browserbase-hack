import { useEffect, useRef, useState } from 'react';

export default function VoicePanel({ connected, onSend }) {
  const [input, setInput] = useState('Go to google.com');
  const [isListening, setIsListening] = useState(false);
  const [micSupported, setMicSupported] = useState(false);
  const [micStatus, setMicStatus] = useState('Mic idle');
  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  useEffect(() => {
    if (!navigator.mediaDevices || typeof MediaRecorder === 'undefined') {
      setMicSupported(false);
      setMicStatus('Mic STT not supported in this browser');
      return;
    }
    setMicSupported(true);

    return () => {
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
    };
  }, []);

  const submit = (e) => {
    e.preventDefault();
    if (!input.trim()) return;
    onSend(input.trim());
    setInput('');
  };

  const startMic = async () => {
    if (!connected || isListening) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];

      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        setIsListening(false);
        setMicStatus('Transcribing...');
        const audioBlob = new Blob(chunksRef.current, { type: 'audio/webm' });
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
        formData.append('audio', audioBlob, 'speech.webm');

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
          onSend(transcript);
          setMicStatus('Mic idle');
        } catch (err) {
          setMicStatus(`STT error: ${err.message}`);
        }
      };

      recorder.start();
      setIsListening(true);
      setMicStatus('Listening...');
    } catch (err) {
      setMicStatus(`Mic error: ${err.message || 'permission/device issue'}`);
    }
  };

  const stopMic = () => {
    if (!mediaRecorderRef.current) return;
    if (mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
  };

  return (
    <section className="panel voice-panel">
      <header className="card-title-row">
        <h2 className="card-title">
          <span className="material-icons-outlined">mic</span>
          Voice Control
        </h2>
        <span className="card-kicker">Active</span>
      </header>
      <p className="panel-meta">WebSocket: {connected ? 'Connected' : 'Disconnected'}</p>
      <p className="panel-meta">Mic: {micStatus}</p>
      <div className="waveform">
        <span className="waveform-bar" />
        <span className="waveform-bar" />
        <span className="waveform-bar" />
        <span className="waveform-bar" />
        <span className="waveform-bar" />
        <span className="waveform-bar" />
        <span className="waveform-bar" />
        <span className="waveform-bar" />
      </div>
      <div className="mic-controls">
        <button
          type="button"
          className={`ptt-button ${isListening ? 'active' : ''}`}
          disabled={!micSupported || !connected}
          onMouseDown={startMic}
          onMouseUp={stopMic}
          onMouseLeave={() => {
            if (isListening) stopMic();
          }}
          onTouchStart={startMic}
          onTouchEnd={stopMic}
        >
          {isListening ? 'Release to Send' : 'Hold to Talk'}
        </button>
      </div>
      <form onSubmit={submit} className="voice-form">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Speak into mic or type transcript..."
          rows={3}
        />
        <button type="submit" className="secondary-button">Send Transcript</button>
      </form>
    </section>
  );
}
