import { join } from "node:path";
import { format } from "prettier";

const PRETTIER_OPTIONS = { parser: "json", printWidth: 120 } as const;

async function collectJsonFiles(dir: string): Promise<string[]> {
  const paths: string[] = [];
  const glob = new Bun.Glob("**/*.json");
  for await (const file of glob.scan({ cwd: dir, absolute: true })) {
    paths.push(file);
  }
  return paths;
}

function mergeInto(target: Record<string, unknown>, source: Record<string, unknown>): void {
  for (const [key, value] of Object.entries(source)) {
    if (Array.isArray(value) && Array.isArray(target[key])) {
      (target[key] as unknown[]).push(...value);
    } else if (
      value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      target[key] !== undefined &&
      typeof target[key] === "object" &&
      !Array.isArray(target[key])
    ) {
      mergeInto(target[key] as Record<string, unknown>, value as Record<string, unknown>);
    } else {
      target[key] = value;
    }
  }
}

type AnyEntry = Record<string, unknown>;

const APPENDIX_MAP: Record<string, { key: string; tag: (e: AnyEntry) => string }> = {
  Ancestries: { key: "race", tag: (e) => `{@race ${e.name}|${e.source}}` },
  Feats: { key: "feat", tag: (e) => `{@feat ${e.name}|${e.source}}` },
  "Item Masteries": { key: "itemMastery", tag: (e) => `{@itemMastery ${e.name}|${e.source}}` },
  Classes: { key: "class", tag: (e) => `{@class ${e.name}|${e.source}}` },
  Subclasses: {
    key: "subclass",
    tag: (e) => `{@subclass ${e.shortName ?? e.name}|${e.className}|${e.classSource}|${e.source}}`,
  },
  Spells: { key: "spell", tag: (e) => `{@spell ${e.name}|${e.source}}` },
  Items: { key: "item", tag: (e) => `{@item ${e.name}|${e.source}}` },
  "Shapeshifter Forms": { key: "monster", tag: (e) => `{@monster ${e.name}|${e.source}}` },
};

function generateAppendix(merged: Record<string, unknown>): void {
  const bookDataArr = merged["bookData"] as AnyEntry[] | undefined;
  const bookArr = merged["book"] as AnyEntry[] | undefined;
  if (!bookDataArr || !bookArr) return;

  for (const bookData of bookDataArr) {
    const data = bookData["data"] as AnyEntry[] | undefined;
    if (!data) continue;

    const appendixSection = data.find((s) => s["name"] === "Appendix") as AnyEntry | undefined;
    if (!appendixSection) continue;

    const entries = appendixSection["entries"] as AnyEntry[] | undefined;
    if (!entries) continue;

    const populatedHeaders: string[] = [];

    for (const entry of entries) {
      const sectionName = entry["name"] as string;
      const mapping = APPENDIX_MAP[sectionName];
      if (!mapping) continue;

      const dataArr = (merged[mapping.key] as AnyEntry[] | undefined) ?? [];
      const items = dataArr.map(mapping.tag).sort();

      const listEntries = entry["entries"] as AnyEntry[] | undefined;
      const listEntry = listEntries?.find((e) => e["type"] === "list");
      if (listEntry) listEntry["items"] = items;

      if (items.length > 0) populatedHeaders.push(sectionName);
    }

    // Sync the book contents appendix headers to match what was populated.
    const book = bookArr.find((b) => b["id"] === bookData["id"]) as AnyEntry | undefined;
    const appendixContent = (book?.["contents"] as AnyEntry[] | undefined)?.find((c) => c["name"] === "Appendix");
    if (appendixContent) appendixContent["headers"] = populatedHeaders;
  }
}

async function buildBundle(partialDir: string, outputFile: string): Promise<void> {
  const files = await collectJsonFiles(partialDir);
  // Process _meta.json first so it anchors the output structure
  files.sort((a, b) => {
    const aIsMeta = a.endsWith("_meta.json") ? -1 : 0;
    const bIsMeta = b.endsWith("_meta.json") ? -1 : 0;
    return aIsMeta - bIsMeta;
  });

  const merged: Record<string, unknown> = {};
  for (const file of files) {
    const data = await Bun.file(file).json();
    mergeInto(merged, data);
  }

  generateAppendix(merged);

  // Stamp the current unix timestamp.
  const meta = merged["_meta"] as Record<string, unknown>;
  meta["dateLastModified"] = Math.floor(Date.now() / 1000);

  const formatted = await format(JSON.stringify(merged), PRETTIER_OPTIONS);
  await Bun.write(outputFile, formatted);
  console.log(`Written to ${outputFile}`);
}

await buildBundle(join(import.meta.dir, "public/partial"), join(import.meta.dir, "public/5bb-public.json"));

await buildBundle(join(import.meta.dir, "private/partial"), join(import.meta.dir, "private/5bb-private.json"));
