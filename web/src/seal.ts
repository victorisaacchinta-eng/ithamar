// The seal: a guilloche rosette, the kind printed on cheques and banknotes,
// drawn from one statement's own balances. Each row owns a slice of the circle.
// A row that is proven draws clean. A repaired row draws in stamp-pad violet.
// A row that does not balance breaks the line, in magenta, where it happened.

export type SealStatus = "verified" | "repaired" | "broken" | "unchecked";
export interface SealRow { balance: number | null; status: SealStatus }

interface Palette { ink: string; tint: string; repair: string; broken: string }

function css(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/** A small deterministic generator so the same statement always draws the same seal. */
function rng(seed: number) {
  let s = seed >>> 0 || 1;
  return () => {
    s ^= s << 13; s ^= s >>> 17; s ^= s << 5;
    return ((s >>> 0) % 100000) / 100000;
  };
}

function seedOf(rows: SealRow[]): number {
  let h = 2166136261;
  for (const r of rows) {
    const b = Math.abs(r.balance ?? 0);
    h = Math.imul(h ^ (b % 1000003), 16777619);
    h = Math.imul(h ^ Math.floor(b / 1000003), 16777619);
  }
  return h >>> 0;
}

interface Ring { k: number; r0: number; a: number; n: number; b: number; m: number; twist: number; weight: number; tone: "ink" | "tint" }

function design(rows: SealRow[]): Ring[] {
  const rand = rng(seedOf(rows));
  const pick = (xs: number[]) => xs[Math.floor(rand() * xs.length)];
  const n1 = pick([7, 8, 9, 11, 12]);
  const n2 = pick([5, 6, 7, 9]);
  const n3 = pick([10, 12, 14, 16]);
  return [
    // Outer band: a wide wave crossing itself, the moire most people know from banknotes.
    { k: 64, r0: 0.82, a: 0.1, n: n1, b: 0.03, m: n1 * 2, twist: 1, weight: 0.42, tone: "ink" },
    // Middle band, in the cheque tint's darker ink.
    { k: 48, r0: 0.55, a: 0.1, n: n2 * 2, b: 0.04, m: n2, twist: 1, weight: 0.45, tone: "tint" },
    // The inner rosette.
    { k: 36, r0: 0.26, a: 0.1, n: n3, b: 0.05, m: n3 / 2, twist: 0.5, weight: 0.45, tone: "ink" },
  ];
}

const TAU = Math.PI * 2;

export interface SealHandle { draw(progress?: number): void; resize(): void }

/**
 * Draw a statement's seal into a canvas. `progress` 0..1 reveals the line as if engraved.
 * The canvas sizes itself to its CSS box.
 */
export function mountSeal(canvas: HTMLCanvasElement, rows: SealRow[]): SealHandle {
  const ctx = canvas.getContext("2d")!;
  const rings = design(rows);
  const N = Math.max(rows.length, 1);
  let w = 0, h = 0, dpr = 1;
  let pal: Palette;

  function resize() {
    const box = canvas.getBoundingClientRect();
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = Math.max(1, box.width); h = Math.max(1, box.height);
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    pal = {
      ink: css("--ink", "#0F1720"),
      tint: css("--tint-ink", "#3E7C8C"),
      repair: css("--repair", "#4B39A3"),
      broken: css("--broken", "#A3154A"),
    };
  }

  const statusAt = (theta: number): SealStatus => rows[Math.min(N - 1, Math.floor((theta / TAU) * N))]?.status ?? "verified";

  function draw(progress = 1) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const R = Math.min(w, h) / 2 - 4;
    const cx = w / 2, cy = h / 2;
    const steps = 540;
    ctx.lineJoin = "round";

    rings.forEach((ring, ri) => {
      // Rings are engraved one after another, overlapping.
      const local = Math.min(1, Math.max(0, progress * 1.5 - ri * 0.22));
      if (local <= 0) return;
      const end = Math.ceil(steps * local);
      for (let j = 0; j < ring.k; j++) {
        const phi = (j / ring.k) * TAU * ring.twist;
        let prevStatus: SealStatus | null = null;
        let started = false;
        for (let s = 0; s <= end; s++) {
          const t = (s / steps) * TAU;
          const st = statusAt(t);
          // A broken row prints out of register: the band slips outward where the chain fails.
          const slip = st === "broken" ? 0.05 * Math.sin(((t * N) / TAU % 1) * Math.PI) : 0;
          const r = R * (ring.r0 + slip + ring.a * Math.sin(ring.n * t + phi) + ring.b * Math.sin(ring.m * t - 2 * phi));
          const x = cx + r * Math.cos(t - Math.PI / 2);
          const y = cy + r * Math.sin(t - Math.PI / 2);
          if (st !== prevStatus) {
            if (started) { ctx.lineTo(x, y); ctx.stroke(); }
            ctx.beginPath();
            ctx.moveTo(x, y);
            const tone = st === "broken" ? pal.broken : st === "repaired" ? pal.repair : ring.tone === "tint" ? pal.tint : pal.ink;
            ctx.strokeStyle = tone;
            ctx.globalAlpha = st === "verified" || st === "unchecked" ? (ring.tone === "tint" ? 0.8 : 0.6) : 0.95;
            ctx.lineWidth = ring.weight;
            ctx.setLineDash(st === "unchecked" ? [1, 3] : []);
            prevStatus = st;
            started = true;
          } else {
            ctx.lineTo(x, y);
          }
        }
        if (started) ctx.stroke();
      }
    });
    ctx.globalAlpha = 1;
    ctx.setLineDash([]);
    if (progress >= 1 && R > 120) microRing(cx, cy, R * 0.985);
  }

  // Microprint, as on a banknote: the one line of arithmetic, repeated around the rim.
  function microRing(cx: number, cy: number, r: number) {
    const size = Math.max(6, Math.min(7.5, r / 48));
    ctx.font = `500 ${size}px "Martian Mono Variable", ui-monospace, monospace`;
    ctx.fillStyle = pal.ink;
    ctx.globalAlpha = 0.7;
    const phrase = "BALANCE ABOVE + CREDIT \u2212 DEBIT = BALANCE   ";
    const unit = ctx.measureText(phrase).width;
    const reps = Math.max(1, Math.floor((TAU * r) / unit));
    const text = phrase.repeat(reps);
    const step = TAU / text.length;
    for (let i = 0; i < text.length; i++) {
      const a = i * step - Math.PI / 2;
      ctx.save();
      ctx.translate(cx + r * Math.cos(a), cy + r * Math.sin(a));
      ctx.rotate(a + Math.PI / 2);
      ctx.fillText(text[i], -size * 0.3, 0);
      ctx.restore();
    }
    ctx.globalAlpha = 1;
  }

  resize();
  return { draw, resize };
}

/** Engrave the seal once, then hold. Respects reduced motion. */
export function engrave(handle: SealHandle, ms = 1600): Promise<void> {
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced) { handle.draw(1); return Promise.resolve(); }
  return new Promise((done) => {
    const t0 = performance.now();
    const ease = (x: number) => 1 - Math.pow(1 - x, 4);
    const frame = (now: number) => {
      const p = Math.min(1, (now - t0) / ms);
      handle.draw(ease(p));
      if (p < 1) requestAnimationFrame(frame); else done();
    };
    requestAnimationFrame(frame);
  });
}
