// pdf.js text items -> positioned words, in the same coordinate frame pdfplumber uses
// (x from the left, top measured down from the top of the page, in PDF points).
import type { Word } from "./layout";

export interface TextItemLike { str: string; transform: number[]; width: number; height: number }
export interface PageLike {
  getViewport(o: { scale: number }): { height: number; width: number };
  getTextContent(): Promise<{ items: unknown[] }>;
}

/** Split one text run into words, placing each by its share of the run's characters. */
export function itemToWords(it: TextItemLike, pageHeight: number, page: number): Word[] {
  const x = it.transform[4];
  const y = it.transform[5];
  const size = Math.hypot(it.transform[2], it.transform[3]) || it.height || 8;
  const top = pageHeight - y - size * 0.75; // baseline to cap top, close enough for line grouping
  const s = it.str;
  if (!s.trim()) return [];
  const per = it.width / Math.max(s.length, 1);
  const out: Word[] = [];
  const re = /\S+/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s))) {
    out.push({ text: m[0], x0: x + m.index * per, x1: x + (m.index + m[0].length) * per, top, page });
  }
  return out;
}

export async function wordsFromPages(pages: PageLike[]): Promise<Word[]> {
  const words: Word[] = [];
  for (let p = 0; p < pages.length; p++) {
    const vp = pages[p].getViewport({ scale: 1 });
    const tc = await pages[p].getTextContent();
    for (const raw of tc.items) {
      const it = raw as TextItemLike;
      if (typeof it.str !== "string") continue;
      words.push(...itemToWords(it, vp.height, p));
    }
  }
  return words;
}
