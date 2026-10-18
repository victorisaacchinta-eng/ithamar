// Indian money parsing. Every amount becomes integer paise; floats never touch money.
// Port of ithamar/money.py. Keep the two in step: tests/parity.ts checks them.

const AMOUNT = /^\(?(?:INR|Rs\.?|₹)?\s*(-)?(\d{1,3}(?:,\d{2,3})*|\d+)\.(\d{2})\)?\s*(Cr|Dr|CR|DR|cr|dr)?\.?$/;

export type Marker = "Dr" | "Cr" | null;

export function looksLikeAmount(text: string): boolean {
  return AMOUNT.test(text.trim());
}

export function parseAmount(text: string): [number, Marker] | null {
  const raw = text.trim();
  const m = AMOUNT.exec(raw);
  if (!m) return null;
  const [, minus, whole, frac, marker] = m;
  let paise = parseInt(whole.replace(/,/g, ""), 10) * 100 + parseInt(frac, 10);
  if (minus || raw.startsWith("(")) paise = -paise;
  const mk = marker ? ((marker[0].toUpperCase() + marker[1].toLowerCase()) as Marker) : null;
  return [paise, mk];
}

export function fmtInr(paise: number | null | undefined): string {
  if (paise === null || paise === undefined) return "";
  const sign = paise < 0 ? "-" : "";
  const abs = Math.abs(paise);
  const whole = Math.floor(abs / 100);
  const frac = abs % 100;
  let s = String(whole);
  if (s.length > 3) {
    let head = s.slice(0, -3);
    const tail = s.slice(-3);
    const groups: string[] = [];
    while (head.length > 2) {
      groups.unshift(head.slice(-2));
      head = head.slice(0, -2);
    }
    if (head) groups.unshift(head);
    s = [...groups, tail].join(",");
  }
  return `${sign}${s}.${String(frac).padStart(2, "0")}`;
}

/** Split for ledger display: ["12,34,567", "89"]. */
export function rupeesPaise(paise: number | null | undefined): [string, string] {
  if (paise === null || paise === undefined) return ["", ""];
  const f = fmtInr(paise);
  const k = f.lastIndexOf(".");
  return [f.slice(0, k), f.slice(k + 1)];
}
