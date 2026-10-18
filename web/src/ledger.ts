// Shared ledger rendering for the story and the tool.
import { rupeesPaise } from "./engine/money";
import type { Decoded } from "./engine/narration";

export const COLS = ["Date", "Particulars", "Dr.", "Cr.", "Balance", ""] as const;

export function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", text = ""): HTMLElementTagNameMap[K] {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text) n.textContent = text;
  return n;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function shortDate(iso: string | null): string {
  if (!iso) return "";
  const [, m, d] = iso.split("-");
  return `${parseInt(d, 10)} ${MONTHS[parseInt(m, 10) - 1]}`;
}

const title = (s: string) => s.toLowerCase().replace(/(^|[\s/])\S/g, (m) => m.toUpperCase());

/** Plain-language particulars, the way a person would write them in a ledger. */
export function particulars(narration: string, d: Decoded, isCredit: boolean): string {
  const who = d.counterparty;
  const dir = isCredit ? "from" : "to";
  switch (d.rail) {
    case "UPI": case "IMPS": case "NEFT": case "RTGS":
      return who ? `${d.rail} ${dir} ${who}` : `${d.rail} ${isCredit ? "credit" : "payment"}`;
    case "ATM": return "Cash withdrawal";
    case "CARD": return who ? `Card payment, ${who}` : "Card payment";
    case "CHEQUE": return `Cheque ${d.cheque}${who ? `, ${who}` : ""}`;
    case "INTEREST": return "Interest credited";
    case "CHARGES": return title(narration);
    case "ACH": return who ? `Auto-debit, ${who}` : "Auto-debit";
    case "CASH": return "Cash deposit";
    default: return narration ? title(narration) : "";
  }
}

const SVG_NS = "http://www.w3.org/2000/svg";
export function markSvg(): SVGSVGElement {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const paths: [string, string][] = [
    ["tick", "M5 12.5l4.2 4.3L19.5 6.5"],
    ["ring", "M12 3.5c4.8 0 8.4 3.6 8.4 8.3 0 4.6-3.8 8.5-8.5 8.5S3.5 16.6 3.6 12c.1-4.7 3.9-8.3 8.9-8.4"],
    ["redo", "M18.5 9.5A7 7 0 1 0 19 14.5M19 4.5v5h-5"],
  ];
  for (const [cls, d] of paths) {
    const p = document.createElementNS(SVG_NS, "path");
    p.setAttribute("class", cls);
    p.setAttribute("d", d);
    p.setAttribute("pathLength", "1");
    svg.appendChild(p);
  }
  return svg;
}

/** A money cell: rupees, a red rule, paise. Optionally a struck figure and its correction. */
export function moneyCell(was: number | null, now?: number | null): HTMLSpanElement {
  const cell = el("span", "money");
  const [rs, ps] = rupeesPaise(was);
  const w = el("span", "was");
  w.append(el("span", "rs", rs), el("span", "ps", ps));
  cell.append(w);
  if (now !== undefined) {
    const [nrs, nps] = rupeesPaise(now);
    const n = el("span", "now");
    n.append(el("span", "rs", nrs), el("span", "ps", nps));
    cell.append(el("span", "strike"), n);
  }
  return cell;
}

export function headRow(): HTMLDivElement {
  const h = el("div", "ledger-cols");
  COLS.forEach((c, i) => h.append(el("span", i >= 2 && i <= 4 ? "num" : "", c)));
  return h;
}

export function rulesLayer(): HTMLDivElement {
  const r = el("div", "ledger-rules");
  for (let i = 0; i < 6; i++) r.append(el("i", i >= 2 && i <= 4 ? "mr" : ""));
  return r;
}

export function readableAmount(paise: number | null): string {
  if (paise === null) return "nothing";
  const [rs, ps] = rupeesPaise(paise);
  return `${rs}.${ps}`;
}
