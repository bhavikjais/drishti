// Copy of frontend/src/lib/siren.ts - synthesized two-tone alarm (Web Audio
// oscillator sweep), no audio asset needed. Fired here whenever a poll turns
// up a notification this app hasn't seen before (see App.tsx).
let ctx: AudioContext | null = null;

function getCtx(): AudioContext {
  if (!ctx) ctx = new AudioContext();
  return ctx;
}

export function playSiren(durationSec = 1.2): void {
  try {
    const audioCtx = getCtx();
    if (audioCtx.state === "suspended") void audioCtx.resume();

    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = "sawtooth";
    osc.connect(gain);
    gain.connect(audioCtx.destination);

    const now = audioCtx.currentTime;
    const sweepLen = 0.4;
    const sweeps = Math.max(1, Math.round(durationSec / sweepLen));
    osc.frequency.setValueAtTime(600, now);
    for (let i = 0; i < sweeps; i++) {
      const t0 = now + i * sweepLen;
      osc.frequency.linearRampToValueAtTime(1100, t0 + sweepLen / 2);
      osc.frequency.linearRampToValueAtTime(600, t0 + sweepLen);
    }

    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(0.25, now + 0.05);
    gain.gain.setValueAtTime(0.25, now + durationSec - 0.1);
    gain.gain.linearRampToValueAtTime(0, now + durationSec);

    osc.start(now);
    osc.stop(now + durationSec + 0.05);
  } catch {
    // Web Audio unavailable or blocked by autoplay policy - fail silently.
  }
}
