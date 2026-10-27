"use client";

// Push to talk (Phase 5). Hold the button (or tap to start and tap again to send): the microphone is captured only
// while you talk, resampled to 24 kHz 16-bit PCM in an AudioWorklet, and streamed to Envoy's /api/voice, which relays it
// to Muse Voice Transcribe (the API key stays on your Mac). If that fails, the browser's own speech recognition is
// the fallback. Replies are spoken with the device's built-in speech.
import { useCallback, useRef, useState } from "react";
import { metric } from "@/lib/device";

export type VoiceState = "idle" | "starting" | "listening" | "finishing";
export type Turn = { text: string; source: "muse" | "browser"; audio_ms?: number; connect_ms?: number; finalize_ms?: number; release_to_text_ms: number; cost_usd?: number };

let unlocked = false;
// iOS speaks only after a first utterance started from a tap; an empty one unlocks it.
export function unlockSpeech(): void {
  if (unlocked || typeof speechSynthesis === "undefined") return;
  speechSynthesis.speak(new SpeechSynthesisUtterance(""));
  unlocked = true;
}

export function speak(text: string, onStart?: () => void): void {
  if (typeof speechSynthesis === "undefined" || !text) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text.length > 220 ? text.slice(0, 220) : text);
  u.rate = 1.05;
  if (onStart) u.onstart = onStart;
  speechSynthesis.speak(u);
}

export function usePushToTalk(onTurn: (t: Turn) => void, onError: (msg: string) => void) {
  const [state, setState] = useState<VoiceState>("idle");
  const [partial, setPartial] = useState("");
  const r = useRef<{ ws?: WebSocket; ctx?: AudioContext; node?: AudioWorkletNode; stream?: MediaStream; pending: ArrayBuffer[];
    released?: number; recog?: any; cancelled?: boolean }>({ pending: [] });

  const cleanup = () => {
    const s = r.current;
    s.stream?.getTracks().forEach((t) => t.stop());
    s.node?.disconnect();
    s.stream = undefined;
    s.node = undefined;
  };

  const browserFallback = useCallback(() => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) return false;
    const recog = new SR();
    recog.lang = "en-US";
    recog.interimResults = true;
    recog.onresult = (e: any) => {
      const res = e.results[e.results.length - 1];
      setPartial(res[0].transcript);
      if (res.isFinal) {
        onTurn({ text: res[0].transcript, source: "browser", release_to_text_ms: r.current.released ? Math.round(performance.now() - r.current.released) : 0 });
        setState("idle");
        setPartial("");
      }
    };
    recog.onerror = () => { setState("idle"); };
    recog.onend = () => setState((s) => (s === "finishing" ? "idle" : s));
    recog.start();
    r.current.recog = recog;
    setState("listening");
    return true;
  }, [onTurn]);

  const start = useCallback(async () => {
    if (state !== "idle") return;
    unlockSpeech();
    const s = r.current;
    s.pending = [];
    s.cancelled = false;
    s.released = undefined;
    s.recog = undefined;
    setPartial("");
    setState("starting");
    const pressed = performance.now();
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/api/voice`);
    ws.binaryType = "arraybuffer";
    s.ws = ws;
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "start" }));
      for (const b of s.pending) ws.send(b);
      s.pending = [];
    };
    ws.onmessage = (m) => {
      const msg = JSON.parse(m.data);
      if (msg.type === "partial") setPartial(msg.text);
      else if (msg.type === "final") {
        const turn: Turn = { text: msg.text, source: "muse", audio_ms: msg.audio_ms, connect_ms: msg.connect_ms, finalize_ms: msg.finalize_ms,
          cost_usd: msg.cost_usd, release_to_text_ms: s.released ? Math.round(performance.now() - s.released) : 0 };
        setState("idle");
        setPartial("");
        if (msg.text) onTurn(turn);
        else onError(msg.silence_ms >= msg.audio_ms - 300 ? "No sound reached Envoy from the microphone." : "I didn't catch that. Try again?");
      } else if (msg.type === "error") {
        cleanup();
        setState("idle");
        onError(msg.error || "voice failed");
      }
    };
    ws.onclose = () => setState((st) => (st === "finishing" || st === "starting" ? "idle" : st));
    try {
      if (!s.ctx) {
        s.ctx = new AudioContext();
        await s.ctx.audioWorklet.addModule("/voice-worklet.js");
      }
      await s.ctx.resume();
      s.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } });
      if (s.cancelled) { cleanup(); return; }
      const src = s.ctx.createMediaStreamSource(s.stream);
      const node = new AudioWorkletNode(s.ctx, "envoy-pcm", { processorOptions: { targetRate: 24000 } });
      const mute = s.ctx.createGain();
      mute.gain.value = 0;
      src.connect(node).connect(mute).connect(s.ctx.destination);
      node.port.onmessage = (e) => {
        const buf = e.data as ArrayBuffer;
        if (ws.readyState === WebSocket.OPEN) ws.send(buf);
        else s.pending.push(buf);
      };
      s.node = node;
      setState("listening");
      metric({ kind: "voice_mic", press_to_mic_ms: Math.round(performance.now() - pressed) });
    } catch (e: any) {
      cleanup();
      ws.close();
      if (!browserFallback()) {
        setState("idle");
        onError(e?.name === "NotAllowedError" ? "Microphone access is off for Envoy." : `Microphone: ${e?.message ?? e}`);
      }
    }
  }, [state, onTurn, onError, browserFallback]);

  const stop = useCallback(() => {
    const s = r.current;
    s.released = performance.now();
    if (s.recog) { setState("finishing"); s.recog.stop(); return; }
    if (!s.node) { s.cancelled = true; s.ws?.close(); setState("idle"); return; }
    setState("finishing");
    s.node.port.postMessage({ flush: true });
    setTimeout(() => {
      cleanup();
      if (s.ws?.readyState === WebSocket.OPEN) s.ws.send(JSON.stringify({ type: "stop" }));
      else { s.ws?.close(); setState("idle"); }
    }, 40);
  }, []);

  const cancel = useCallback(() => {
    const s = r.current;
    s.cancelled = true;
    cleanup();
    s.recog?.abort?.();
    if (s.ws?.readyState === WebSocket.OPEN) s.ws.send(JSON.stringify({ type: "cancel" }));
    s.ws?.close();
    setState("idle");
    setPartial("");
  }, []);

  return { state, partial, start, stop, cancel };
}
