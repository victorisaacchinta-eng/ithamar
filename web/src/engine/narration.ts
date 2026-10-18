// Decode Indian bank narrations. Port of ithamar/narration/decode.py.
// Best effort and never proven by the chain: decoration on proven numbers.

const VPA = /\b([a-z0-9][a-z0-9.\-_]{1,63}@[a-z][a-z0-9]{1,30})\b/i;
const RRN = /(?<!\d)(\d{12})(?!\d)/;
const IFSC = /\b([A-Z]{4}0[A-Z0-9]{6})\b/;
const UTR = /\b([A-Z]{4}[RHN0-9]\d{2}[0-9A-Z]{8,15})\b/g;
const CHQ = /\b(?:CHQ|CHEQUE|CLG)\D{0,6}(\d{6})\b/i;
const RAILS: [string, RegExp][] = [
  ["UPI", /\bUPI\b/i],
  ["IMPS", /\bIMPS\b|\bMMT\b/i],
  ["NEFT", /\bNEFT\b/i],
  ["RTGS", /\bRTGS\b/i],
  ["ACH", /\bACH\b|\bNACH\b|\bECS\b/i],
  ["ATM", /\bATM\b|\bATW\b|\bNWD\b|CASH WDL/i],
  ["CARD", /\bPOS\b|\bECOM\b|\bVPS\b|\bIPS\b/i],
  ["CHEQUE", /\bCHQ\b|\bCHEQUE\b|\bCLG\b/i],
  ["INTEREST", /\bINT(?:EREST)?\.?\s*(?:CR|PD|PAID|CREDIT)\b|\bSB INT\b|\bINTEREST\b/i],
  ["CHARGES", /\bCHGS?\b|\bCHARGES?\b|\bGST\b|\bFEE\b|\bAMC\b/i],
  ["CASH", /\bCASH\s*(?:DEP|DEPOSIT)\b|\bBY CASH\b/i],
];
const NOISE = new Set(["UPI", "IMPS", "NEFT", "RTGS", "P2A", "P2M", "P2P", "CR", "DR", "PAYMENT", "TRANSFER",
  "TO", "FROM", "BY", "REF", "NA", "MMT", "ACH", "NACH", "D", "C", "INB"]);

export interface Decoded { rail: string; vpa: string; rrn: string; utr: string; ifsc: string; cheque: string; counterparty: string }

const title = (s: string) => s.toLowerCase().replace(/(^|\s)\S/g, (m) => m.toUpperCase());

function counterparty(narration: string, d: Decoded): string {
  let t = narration;
  for (const id of [d.vpa, d.rrn, d.utr, d.ifsc, d.cheque]) if (id) t = t.split(id).join(" ");
  let best = "";
  let parts = t.split(/[/|-]/).map((x) => x.replace(/^[ .:]+|[ .:]+$/g, ""));
  // UPI narrations end with the payee's name; a purpose like "RENT" sits earlier.
  if (d.rail === "UPI") parts = parts.reverse();
  for (const p of parts) {
    const cand = p.split(/\s+/).filter((w) => w && !NOISE.has(w.toUpperCase())).join(" ");
    if (!cand || /\d/.test(cand) || cand.includes("@")) continue;
    const letters = (cand.match(/[A-Za-z]/g) ?? []).length;
    if (letters >= 3 && cand.length > best.length) {
      best = cand;
      if (d.rail === "UPI") break;
    }
  }
  return best === best.toUpperCase() ? title(best) : best;
}

export function decode(narration: string): Decoded {
  const n = narration || "";
  const d: Decoded = { rail: "", vpa: "", rrn: "", utr: "", ifsc: "", cheque: "", counterparty: "" };
  for (const [name, pat] of RAILS) if (pat.test(n)) { d.rail = name; break; }
  let m = VPA.exec(n); if (m) d.vpa = m[1].toLowerCase();
  m = RRN.exec(n); if (m) d.rrn = m[1];
  m = IFSC.exec(n); if (m) d.ifsc = m[1];
  if (["NEFT", "RTGS", "IMPS"].includes(d.rail)) {
    for (const u of n.matchAll(UTR)) if (u[1] !== d.ifsc) { d.utr = u[1]; break; }
  }
  m = CHQ.exec(n); if (m) d.cheque = m[1];
  if (!["INTEREST", "CHARGES", "ATM"].includes(d.rail)) d.counterparty = counterparty(n, d);
  return d;
}
