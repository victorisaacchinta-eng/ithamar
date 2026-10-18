// The scroll story: a pinned ledger page, audited by the pen as you scroll.
// Data is the Python engine's own audit of samples/story.pdf.
import { fmtInr } from "./engine/money";
import { headRow, markSvg, moneyCell, particulars, rulesLayer, shortDate, el } from "./ledger";

interface PyRow {
  index: number; date: string | null; narration: string; debit: number | null; credit: number | null;
  balance: number | null; status: string; decoded: { rail: string; counterparty: string; cheque: string } & Record<string, string>;
}
interface PyRepair { row: number; kind: string; before: Record<string, number | null>; after: Record<string, number | null>; detail: string }
interface PyAudit {
  bank: string; opening_balance: number; closing_balance: number; rows: PyRow[]; repairs: PyRepair[];
  unresolved: { row: number; reason: string; candidates: { fix: Record<string, number>; detail: string }[] }[];
  summary: { verified: number; repaired: number; broken: number; rows: number };
}

type Field = "debit" | "credit" | "balance";
interface Timeline { kind: "plain" | "repaired" | "echo" | "left"; brokenAt: number; fixAt: number; provenAt: number }

const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));

export async function mountStory(root: HTMLElement): Promise<() => void> {
  const audit: PyAudit = await (await fetch("samples/story.audit.json")).json();
  const final = audit.rows;
  // What the PDF actually printed: undo each logged repair.
  const printed = final.map((r) => ({ ...r }));
  for (const rep of audit.repairs) Object.assign(printed[rep.row], rep.before);
  const repairs = new Map(audit.repairs.map((r) => [r.row, r]));
  const left = new Map(audit.unresolved.map((u) => [u.row, u]));
  const N = final.length;

  // A misread balance breaks its own row and the row below; the fix lands once both are seen.
  const tl: Timeline[] = final.map((_, r) => ({ kind: "plain", brokenAt: Infinity, fixAt: Infinity, provenAt: r + 0.6 }));
  for (const rep of audit.repairs) {
    const t = tl[rep.row];
    t.kind = "repaired";
    t.brokenAt = rep.row + 0.35;
    t.fixAt = rep.row + 0.85;
    if (rep.kind === "balance_misread" && rep.row + 1 < N && !repairs.has(rep.row + 1) && !left.has(rep.row + 1)) {
      const e = tl[rep.row + 1];
      e.kind = "echo";
      e.brokenAt = rep.row + 1.35;
      t.fixAt = e.fixAt = rep.row + 1.85;
      e.provenAt = e.fixAt;
    }
  }
  for (const r of left.keys()) Object.assign(tl[r], { kind: "left", brokenAt: r + 0.35, provenAt: Infinity });

  // ---------------------------------------------------------------- build the page
  root.replaceChildren();
  const head = el("header", "ledger-head");
  head.append(el("h3", "", "N. Joseph, savings account"), el("p", "folio", "Folio 4"),
    el("p", "", `${titleCase(audit.bank)}, a fictional bank. April 2026.`));
  const win = el("div", "ledger-window");
  const body = el("div", "ledger-body");
  const ruler = el("div", "ruler");
  body.append(rulesLayer());

  const bf = el("div", "ledger-row l-bf");
  bf.append(el("span", "l-date", "1 Apr"), el("span", "l-part", "Brought forward"), el("span"), el("span"),
    moneyCell(audit.opening_balance), el("span", "mark"));
  body.append(bf);

  const rowEls: HTMLDivElement[] = [];
  const cellsOf: Record<number, Partial<Record<Field, HTMLSpanElement>>> = {};
  let gapEl: HTMLDivElement | null = null;

  final.forEach((r, i) => {
    const u = left.get(i);
    if (u) {
      const gap = el("div", "ledger-row gap-row");
      const net = u.candidates[0]?.fix.net ?? 0;
      gap.append(el("span", "l-date"), el("span", "l-part", "A row is missing here"),
        net < 0 ? moneyCell(-net) : el("span"), net > 0 ? moneyCell(net) : el("span"), el("span"), el("span", "mark"));
      gap.setAttribute("aria-hidden", "true");
      body.append(gap);
      gapEl = gap;
    }
    const row = el("div", "ledger-row");
    row.title = r.narration;
    const rep = repairs.get(i);
    const cells: Partial<Record<Field, HTMLSpanElement>> = {};
    const isCredit = (r.credit ?? 0) > 0;
    const part = el("span", "l-part", particulars(r.narration, r.decoded as never, isCredit));
    row.append(el("span", "l-date", shortDate(r.date)), part);
    for (const f of ["debit", "credit", "balance"] as Field[]) {
      let cell: HTMLSpanElement;
      if (rep && f in rep.before) {
        cell = moneyCell(rep.before[f] ?? null, rep.after[f] ?? null);
        if (rep.before[f] !== null && rep.before[f] !== undefined) cell.classList.add("is-wrong");
        if (rep.after[f] !== null && rep.after[f] !== undefined) cell.classList.add("is-target");
      } else {
        cell = moneyCell(printed[i][f]);
      }
      cells[f] = cell;
      row.append(cell);
    }
    const mark = el("span", "mark");
    mark.append(markSvg());
    row.append(mark);
    body.append(row);
    rowEls.push(row);
    cellsOf[i] = cells;
  });

  const cf = el("div", "ledger-row l-cf");
  cf.append(el("span", "l-date", shortDate(final[N - 1].date)), el("span", "l-part", "Carried forward"), el("span"), el("span"),
    moneyCell(audit.closing_balance), el("span", "mark"));
  body.append(cf, ruler);
  win.append(body);

  const eq = el("footer", "ledger-eq");
  eq.setAttribute("aria-live", "polite");
  const stamp = el("div", "stamp", "One row needs you");
  root.append(head, headRow(), win, eq, stamp);

  // ---------------------------------------------------------------- render from the pen
  const steps = [...document.querySelectorAll<HTMLElement>(".story .step")];
  const tally = document.getElementById("tally");
  let lastKey = "";

  function rowState(i: number, p: number) {
    const t = tl[i];
    const fixed = t.kind === "repaired" && p >= t.fixAt;
    // A break shows from the moment the pen reaches it until its fix lands.
    // Echo rows are never repaired themselves; they close once the row above is fixed.
    const broken = p >= t.brokenAt && p < t.fixAt;
    const proven = p >= t.provenAt && (t.kind === "plain" || t.kind === "echo");
    return { fixed, broken, proven };
  }

  function equation(i: number, p: number) {
    if (i >= N) {
      return { state: "fixed", label: "Carried forward", parts: [`Closing balance ${fmtInr(audit.closing_balance)}`], res: "matches the statement" };
    }
    const s = rowState(i, p);
    const useFinal = s.fixed || (tl[i].kind === "echo" && p >= tl[i].fixAt);
    const src = useFinal ? final : printed;
    const prevBal = i === 0 ? audit.opening_balance : (useFinal ? final : printed)[i - 1].balance ?? 0;
    const cr = src[i].credit ?? 0, dr = src[i].debit ?? 0;
    const got = prevBal + cr - dr;
    const label = `Row ${i + 1}, ${shortDate(final[i].date)}`;
    const parts = [fmtInr(prevBal), "+", fmtInr(cr), "−", fmtInr(dr), "="];
    if (s.broken) {
      const extra = tl[i].kind === "left" ? ` A credit of ${fmtInr((src[i].balance ?? 0) - got)} is unaccounted for.` : "";
      return { state: "broken", label: `${label}: does not balance`, parts, res: `${fmtInr(got)}, but the statement says ${fmtInr(printed[i].balance)}.${extra}` };
    }
    if (s.fixed) return { state: "fixed", label: `${label}: repaired. ${cap(repairs.get(i)?.detail ?? "")}.`, parts, res: fmtInr(got) };
    if (p >= tl[i].provenAt) return { state: "proven", label: `${label}: proven`, parts, res: fmtInr(got) };
    return { state: "checking", label: `${label}: checking`, parts, res: fmtInr(got) };
  }

  function render(p: number) {
    const key = p.toFixed(2);
    if (key === lastKey) return;
    lastKey = key;
    rowEls.forEach((row, i) => {
      const s = rowState(i, p);
      row.classList.toggle("is-proven", s.proven);
      row.classList.toggle("is-broken", s.broken);
      row.classList.toggle("is-fixed", s.fixed);
      row.classList.toggle("is-left", tl[i].kind === "left" && s.broken);
    });
    const gapOpen = [...left.keys()].some((r) => p >= tl[r].brokenAt);
    gapEl?.classList.toggle("is-open", gapOpen);
    stamp.classList.toggle("is-on", p >= N + 0.4);

    const cur = Math.min(Math.floor(clamp(p, 0, N)), N);
    const target = cur >= N ? cf : rowEls[cur];
    ruler.style.transform = `translateY(${target.offsetTop}px)`;
    const view = win.clientHeight;
    const max = Math.max(0, body.scrollHeight - view);
    const shift = clamp(target.offsetTop - view * 0.42, 0, max);
    body.style.transform = `translateY(${-shift}px)`;

    const e = equation(cur, p);
    eq.dataset.state = e.state;
    eq.replaceChildren(el("span", "eq-label", e.label));
    for (const part of e.parts) eq.append(el("span", /[+−=]/.test(part) && part.length === 1 ? "eq-op" : "", part));
    eq.append(el("span", "eq-res", e.res));

    steps.forEach((s) => (s.dataset.active = String(p >= +s.dataset.from! && p < +s.dataset.to!)));

    const counts = { proven: 0, repaired: 0, left: 0, seen: 0 };
    rowEls.forEach((_, i) => {
      const st = rowState(i, p);
      if (st.proven) counts.proven++;
      if (st.fixed) counts.repaired++;
      if (tl[i].kind === "left" && st.broken) counts.left++;
      if (p >= i + 0.6) counts.seen++;
    });
    tally?.querySelectorAll<HTMLElement>("[data-k]").forEach((n) => {
      const v = String(counts[n.dataset.k as keyof typeof counts]);
      if (n.textContent !== v) n.textContent = v;
    });
  }

  function penFromScroll(): number {
    const line = window.innerHeight * (window.innerWidth <= 900 ? 0.8 : 0.5);
    let p = 0;
    for (const s of steps) {
      const r = s.getBoundingClientRect();
      const from = +s.dataset.from!, to = +s.dataset.to!;
      if (r.top > line) break;
      p = from + (to - from) * clamp((line - r.top) / r.height, 0, 1);
    }
    return p;
  }

  const update = () => render(penFromScroll());
  update();
  return update;
}

function titleCase(s: string) {
  return s.toLowerCase().replace(/(^|\s)\S/g, (m) => m.toUpperCase());
}
function cap(s: string) {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}
