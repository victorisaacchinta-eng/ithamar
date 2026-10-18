// The live tool: a PDF in this tab, parsed by pdf.js, proven by the TypeScript engine.
import { auditWords, type Audit } from "./engine/audit";
import { fmtInr } from "./engine/money";
import { wordsFromPages, type PageLike } from "./engine/pdf";
import { el, headRow, markSvg, moneyCell, particulars, rulesLayer, shortDate } from "./ledger";

type PdfJs = typeof import("pdfjs-dist");
let pdfjsPromise: Promise<PdfJs> | null = null;
function loadPdfJs(): Promise<PdfJs> {
  pdfjsPromise ??= (async () => {
    const [lib, worker] = await Promise.all([import("pdfjs-dist"), import("pdfjs-dist/build/pdf.worker.min.mjs?url")]);
    lib.GlobalWorkerOptions.workerSrc = worker.default;
    return lib;
  })();
  return pdfjsPromise;
}

const KIND_TEXT: Record<string, string> = {
  direction_swapped: "Amount in the wrong column",
  amount_misread: "Amount misread",
  balance_misread: "Balance misread",
  missing_row: "Row missing",
};
const REASON_TEXT: Record<string, string> = {
  missing_row_suspected: "A row seems to be missing above this one. Ithamar does not invent transactions; check the paper statement.",
  ambiguous: "More than one correction would balance this row, so none was applied.",
  unconfirmable: "A correction would balance this row, but nothing below it can confirm it.",
  no_explanation: "No single correction explains this row.",
};

export function mountTool() {
  const zone = document.getElementById("dropzone")!;
  const input = document.getElementById("file") as HTMLInputElement;
  const status = document.getElementById("tool-status")!;
  const result = document.getElementById("result")!;
  const pwForm = document.getElementById("password-form") as HTMLFormElement;
  const pwInput = document.getElementById("password") as HTMLInputElement;
  const label = zone.querySelector<HTMLElement>(".dropzone-label")!;
  let pending: { data: Uint8Array; name: string } | null = null;

  const say = (msg: string, tone: "info" | "error" = "info") => {
    status.textContent = msg;
    status.dataset.tone = tone;
  };

  async function run(data: Uint8Array, name: string, password?: string) {
    say(`Reading ${name}`);
    const pdfjs = await loadPdfJs();
    let doc;
    try {
      doc = await pdfjs.getDocument({ data: data.slice(), password, isEvalSupported: false }).promise;
    } catch (err) {
      const e = err as { name?: string; code?: number };
      if (e.name === "PasswordException") {
        pending = { data, name };
        label.hidden = true;
        pwForm.hidden = false;
        pwInput.value = "";
        pwInput.focus();
        say(e.code === 2 ? "That password did not open the file. Try again." : `${name} is password protected.`, e.code === 2 ? "error" : "info");
        return;
      }
      say(`${name} could not be read as a PDF. Check that it is the statement file itself, not a screenshot or a link.`, "error");
      return;
    }
    pwForm.hidden = true;
    label.hidden = false;
    pending = null;
    const pages: PageLike[] = [];
    for (let i = 1; i <= doc.numPages; i++) pages.push(await doc.getPage(i));
    const words = await wordsFromPages(pages);
    if (words.length < 20) {
      say(`${name} has almost no text in it. It is probably a scanned image, which needs OCR; Ithamar cannot read those yet.`, "error");
      result.hidden = true;
      return;
    }
    const audit = auditWords(words, name);
    if (!audit.rows.length) {
      say(`No transaction table found in ${name}. Ithamar looks for a header row with a date, an amount and a balance column.`, "error");
      result.hidden = true;
      return;
    }
    say("");
    renderResult(result, audit);
    result.hidden = false;
    result.querySelector<HTMLElement>("h3")?.focus({ preventScroll: true });
    result.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  }

  async function fromFile(f: File) {
    if (!/\.pdf$/i.test(f.name) && f.type !== "application/pdf") {
      say(`${f.name} is not a PDF. Download the statement from net banking as a PDF and drop that here.`, "error");
      return;
    }
    await run(new Uint8Array(await f.arrayBuffer()), f.name);
  }

  input.addEventListener("change", () => input.files?.[0] && fromFile(input.files[0]));
  ["dragenter", "dragover"].forEach((t) => zone.addEventListener(t, (e) => { e.preventDefault(); zone.dataset.over = "true"; }));
  ["dragleave", "drop"].forEach((t) => zone.addEventListener(t, (e) => { e.preventDefault(); zone.dataset.over = "false"; }));
  zone.addEventListener("drop", (e) => {
    const f = (e as DragEvent).dataTransfer?.files?.[0];
    if (f) fromFile(f);
  });
  pwForm.addEventListener("submit", (e) => {
    e.preventDefault();
    if (pending) run(pending.data, pending.name, pwInput.value);
  });
  document.querySelectorAll<HTMLButtonElement>("[data-sample]").forEach((b) =>
    b.addEventListener("click", async () => {
      const name = b.dataset.sample!;
      say(`Fetching the sample statement`);
      const res = await fetch(`/samples/${name}.pdf`);
      await run(new Uint8Array(await res.arrayBuffer()), `${name}.pdf`);
    }),
  );
  // Let a pinned link like /#audit?sample=story open a sample directly.
  const m = /sample=([\w-]+)/.exec(location.hash);
  if (m) document.querySelector<HTMLButtonElement>(`[data-sample="${m[1]}"]`)?.click();
}

function verdict(a: Audit): { text: string; blue: boolean; heading: string } {
  const s = a.summary;
  if (s.clean && !s.repaired) return { text: "Proven", blue: true, heading: `Every row of ${a.source} is proven.` };
  if (s.clean) return { text: "Proven after repair", blue: true, heading: `${a.source} is proven, after ${s.repaired} logged ${s.repaired === 1 ? "correction" : "corrections"}.` };
  return { text: s.broken === 1 ? "One row needs you" : `${s.broken} rows need you`, blue: false, heading: `${a.source} needs a look at ${s.broken} ${s.broken === 1 ? "row" : "rows"}.` };
}

function renderResult(root: HTMLElement, a: Audit) {
  root.replaceChildren();
  const s = a.summary;
  const v = verdict(a);
  const head = el("div", "result-head");
  const left = el("div");
  const h = el("h3", "", v.heading);
  h.tabIndex = -1;
  const closing = s.closing_ok === null ? "The statement prints no closing balance to check against." :
    s.closing_ok ? `The closing balance of ${fmtInr(a.closing_balance)} matches.` : `The closing balance does not match: the rows reach a different figure from the ${fmtInr(a.closing_balance)} printed.`;
  const counts = `${s.verified} of ${s.rows} rows proven as printed, ${s.repaired} repaired, ${s.broken} broken${s.unchecked ? `, ${s.unchecked} with no balance to check` : ""}.`;
  left.append(h, el("p", "", `${counts} ${closing}`));
  if (a.warnings.length) left.append(el("p", "", cap(a.warnings[0]) + "."));
  const actions = el("div", "result-actions");
  const csv = el("button", "btn btn-ink", "Download CSV");
  csv.type = "button";
  csv.addEventListener("click", () => download(toCsv(a), a.source.replace(/\.pdf$/i, "") + "-ithamar.csv", "text/csv"));
  const json = el("button", "btn-quiet", "Download the audit as JSON");
  json.type = "button";
  json.addEventListener("click", () => download(JSON.stringify(a, null, 1), a.source.replace(/\.pdf$/i, "") + "-ithamar.json", "application/json"));
  actions.append(csv, json);
  left.append(actions);
  const stamp = el("div", `stamp${v.blue ? " is-blue" : ""}`, v.text);
  head.append(left, stamp);

  const ledger = el("div", "ledger");
  const lh = el("header", "ledger-head");
  lh.append(el("h3", "", a.bank ? titleCase(a.bank) : a.source), el("p", "folio", `${s.rows} rows`),
    el("p", "", `Anchored on ${a.summary.anchor === "opening" ? "the printed opening balance" : "the first row, because no opening balance is printed"}.`));
  const win = el("div", "ledger-window");
  const body = el("div", "ledger-body");
  body.append(rulesLayer());
  if (a.opening_balance !== null) {
    const bf = el("div", "ledger-row l-bf");
    bf.append(el("span", "l-date"), el("span", "l-part", "Brought forward"), el("span"), el("span"), moneyCell(a.opening_balance), el("span", "mark"));
    body.append(bf);
  }
  const reps = new Map(a.repairs.map((r) => [r.row, r]));
  const lefts = new Map(a.unresolved.filter((u) => u.reason === "missing_row_suspected").map((u) => [u.row, u]));
  a.rows.forEach((r, i) => {
    const u = lefts.get(i);
    if (u) {
      const net = (u.candidates[0]?.fix.net as number) ?? 0;
      const gap = el("div", "ledger-row gap-row is-open");
      gap.append(el("span", "l-date"), el("span", "l-part", "A row may be missing here"),
        net < 0 ? moneyCell(-net) : el("span"), net > 0 ? moneyCell(net) : el("span"), el("span"), el("span", "mark"));
      body.append(gap);
    }
    const row = el("div", "ledger-row");
    row.title = r.narration;
    const rep = reps.get(i);
    row.append(el("span", "l-date", shortDate(r.date)), el("span", "l-part", particulars(r.narration, r.decoded, (r.credit ?? 0) > 0)));
    for (const f of ["debit", "credit", "balance"] as const) {
      if (rep && f in rep.before) {
        const c = moneyCell(rep.before[f] ?? null, rep.after[f] ?? null);
        if (rep.before[f] != null) c.classList.add("is-wrong");
        if (rep.after[f] != null) c.classList.add("is-target");
        row.append(c);
      } else row.append(moneyCell(r[f]));
    }
    const mark = el("span", "mark");
    mark.append(markSvg());
    row.append(mark);
    row.classList.add(r.status === "verified" ? "is-proven" : r.status === "repaired" ? "is-fixed" : r.status === "broken" ? "is-broken" : "is-unchecked");
    body.append(row);
  });
  win.append(body);
  ledger.append(lh, headRow(), win);

  const notes = el("ol", "notes");
  notes.setAttribute("aria-label", "What Ithamar changed and what it left for you");
  for (const r of a.repairs) {
    const li = el("li");
    const txt = el("span", "n-fix", `${KIND_TEXT[r.kind]}. ${cap(r.detail)}.`);
    for (const alt of r.rejected) txt.append(el("span", "n-alt", `Also considered and set aside: ${alt.detail}.`));
    li.append(el("span", "n-row", `Row ${r.row + 1}`), txt);
    notes.append(li);
  }
  for (const u of a.unresolved) {
    const li = el("li");
    const txt = el("span", "n-left", REASON_TEXT[u.reason] ?? u.reason);
    for (const c of u.candidates.slice(0, 2)) txt.append(el("span", "n-alt", cap(c.detail) + "."));
    li.append(el("span", "n-row", `Row ${u.row + 1}`), txt);
    notes.append(li);
  }
  root.append(head, ledger);
  if (notes.children.length) root.append(notes);
}

function toCsv(a: Audit): string {
  const cols = ["row", "date", "narration", "debit", "credit", "balance", "status", "rail", "counterparty", "vpa", "rrn", "utr"];
  const q = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const rupees = (p: number | null) => (p === null ? "" : (p / 100).toFixed(2));
  const lines = [cols.join(",")];
  for (const r of a.rows) {
    lines.push([r.index + 1, r.date, r.narration, rupees(r.debit), rupees(r.credit), rupees(r.balance), r.status,
      r.decoded.rail, r.decoded.counterparty, r.decoded.vpa, r.decoded.rrn, r.decoded.utr].map(q).join(","));
  }
  return lines.join("\n") + "\n";
}

function download(text: string, name: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = el("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const titleCase = (s: string) => s.toLowerCase().replace(/(^|\s)\S/g, (m) => m.toUpperCase());
const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);
