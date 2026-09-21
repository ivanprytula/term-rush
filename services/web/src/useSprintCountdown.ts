import { useEffect, useRef, useState } from "react";

/**
 * Ticks a Sprint round's remaining time on requestAnimationFrame, not
 * setInterval — a timer needs to reflect wall-clock time precisely and
 * stop the instant it hits zero, not drift with tab-throttled interval
 * ticks. serverRemainingSeconds re-syncs the local countdown whenever the
 * server sends a fresh value (e.g. right after POST /game-rounds); passing
 * null stops the loop entirely (Classic mode, or before a round exists).
 */
export function useSprintCountdown(
  serverRemainingSeconds: number | null,
): number | null {
  const [remaining, setRemaining] = useState<number | null>(
    serverRemainingSeconds,
  );
  const deadlineRef = useRef<number | null>(null);

  useEffect(() => {
    if (serverRemainingSeconds === null) {
      deadlineRef.current = null;
      setRemaining(null);
      return;
    }
    deadlineRef.current = performance.now() + serverRemainingSeconds * 1000;
    setRemaining(serverRemainingSeconds);

    let frame: number;
    const tick = () => {
      const deadline = deadlineRef.current;
      if (deadline === null) return;
      const next = Math.max(0, (deadline - performance.now()) / 1000);
      setRemaining(next);
      if (next > 0) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);

    return () => cancelAnimationFrame(frame);
    // serverRemainingSeconds re-arms the countdown on every value it emits,
    // not just the first — a new round always carries a fresh one.
  }, [serverRemainingSeconds]);

  return remaining;
}
