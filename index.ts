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

  // Stamp the current unix timestamp.
  const meta = merged["_meta"] as Record<string, unknown>;
  meta["dateLastModified"] = Math.floor(Date.now() / 1000);

  const formatted = await format(JSON.stringify(merged), PRETTIER_OPTIONS);
  await Bun.write(outputFile, formatted);
  console.log(`Written to ${outputFile}`);
}

await buildBundle(join(import.meta.dir, "public/partial"), join(import.meta.dir, "public/5bb-public.json"));

await buildBundle(join(import.meta.dir, "private/partial"), join(import.meta.dir, "private/5bb-private.json"));
