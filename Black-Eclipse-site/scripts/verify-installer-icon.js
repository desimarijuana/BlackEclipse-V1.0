#!/usr/bin/env node
// Prove that a built setup .exe really carries the Black Eclipse icon.
//
// Why this exists: the 0.4.2 release shipped NSIS's stock globe/disk icon even
// though `desktop/installer/BlackEclipse.nsi` already set `MUI_ICON`. The tag
// (`v0.4.2`) pointed at a commit that forked before the branding change, so the
// release workflow built exactly the source it was given — the wizard assets
// simply were not in that commit. A green build therefore said nothing about
// what Explorer would draw for the downloaded file.
//
// This check reads the finished setup's RT_GROUP_ICON (the same resource
// Explorer uses) and compares it with `public/branding/black-eclipse.ico`. It
// fails when the frames are the stock NSIS set (16/32/48px, 4/8bpp) instead of
// the brand set (16/24/32/48/64/128/256px, all 32bpp).
//
// Usage:
//   node scripts/verify-installer-icon.js [setup.exe] [brand.ico]
//   npm run installer:verify
//
// `desktop-installer.js` calls this automatically after makensis, so a CI
// release cannot publish an unbranded setup again.

const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const DEFAULT_EXE = path.join(ROOT, "dist", "BlackEclipse-Setup.exe");
const DEFAULT_ICO = path.join(ROOT, "public", "branding", "black-eclipse.ico");

const RT_ICON = 3;
const RT_GROUP_ICON = 14;

/** Section table of a PE image, read from an in-memory copy of the file. */
function readSections(buf) {
  if (buf.length < 0x40 || buf.toString("ascii", 0, 2) !== "MZ") {
    throw new Error("not a Windows executable (missing MZ header)");
  }
  const lfanew = buf.readUInt32LE(0x3c);
  if (buf.toString("ascii", lfanew, lfanew + 4) !== "PE\0\0") {
    throw new Error("not a PE image (missing PE signature)");
  }
  const count = buf.readUInt16LE(lfanew + 6);
  const optionalSize = buf.readUInt16LE(lfanew + 20);
  const table = lfanew + 24 + optionalSize;
  const sections = [];
  for (let i = 0; i < count; i += 1) {
    const at = table + i * 40;
    sections.push({
      name: buf.toString("ascii", at, at + 8).replace(/\0+$/, ""),
      virtualSize: buf.readUInt32LE(at + 8),
      virtualAddress: buf.readUInt32LE(at + 12),
      rawSize: buf.readUInt32LE(at + 16),
      rawPointer: buf.readUInt32LE(at + 20),
    });
  }
  return sections;
}

function makeReader(buf) {
  const sections = readSections(buf);
  const rsrc = sections.find((section) => section.name === ".rsrc");
  if (!rsrc) throw new Error("no .rsrc section — the exe has no resources");

  const fileOffset = (rva) => {
    const hit = sections.find(
      (section) =>
        rva >= section.virtualAddress &&
        rva < section.virtualAddress + Math.max(section.virtualSize, section.rawSize)
    );
    if (!hit) throw new Error(`RVA 0x${rva.toString(16)} is not inside any section`);
    return rva - hit.virtualAddress + hit.rawPointer;
  };

  // A resource directory holds NAMED + ID entries, each 8 bytes.
  const directory = (absolute) => {
    const named = buf.readUInt16LE(absolute + 12);
    const ids = buf.readUInt16LE(absolute + 14);
    const entries = [];
    for (let i = 0; i < named + ids; i += 1) {
      const at = absolute + 16 + i * 8;
      entries.push({
        name: buf.readUInt32LE(at),
        data: buf.readUInt32LE(at + 4),
      });
    }
    return entries;
  };

  const typeDirectory = directory(rsrc.rawPointer);
  const type = (id) => {
    const entry = typeDirectory.find((candidate) => candidate.name === id);
    if (!entry) return [];
    return directory(rsrc.rawPointer + (entry.data & 0x7fffffff));
  };

  // Type -> name/id -> language -> IMAGE_RESOURCE_DATA_ENTRY.
  const dataEntry = (entry) => {
    const at = rsrc.rawPointer + (entry.data & 0x7fffffff);
    return { rva: buf.readUInt32LE(at), size: buf.readUInt32LE(at + 4) };
  };
  const firstLeaf = (entry) =>
    directory(rsrc.rawPointer + (entry.data & 0x7fffffff))[0];

  return { buf, fileOffset, type, dataEntry, firstLeaf };
}

/** Frames of the icon group Explorer draws for the exe. */
function readExeIcon(exePath) {
  const buf = fs.readFileSync(exePath);
  const reader = makeReader(buf);
  const groups = reader.type(RT_GROUP_ICON);
  if (!groups.length) throw new Error("the exe has no RT_GROUP_ICON resource");

  const group = reader.dataEntry(reader.firstLeaf(groups[0]));
  const at = reader.fileOffset(group.rva);
  const count = buf.readUInt16LE(at + 4);
  const frames = [];
  for (let i = 0; i < count; i += 1) {
    const entry = at + 6 + i * 14;
    frames.push({
      width: buf[entry] || 256,
      height: buf[entry + 1] || 256,
      colors: buf[entry + 2],
      planes: buf.readUInt16LE(entry + 4),
      bitsPerPixel: buf.readUInt16LE(entry + 6),
      bytes: buf.readUInt32LE(entry + 8),
      id: buf.readUInt16LE(entry + 12),
    });
  }
  return frames;
}

/** Frames of a .ico file on disk. */
function readIcoIcon(icoPath) {
  const buf = fs.readFileSync(icoPath);
  if (buf.readUInt16LE(0) !== 0 || buf.readUInt16LE(2) !== 1) {
    throw new Error(`${path.basename(icoPath)} is not an .ico file`);
  }
  const count = buf.readUInt16LE(4);
  const frames = [];
  for (let i = 0; i < count; i += 1) {
    const at = 6 + i * 16;
    frames.push({
      width: buf[at] || 256,
      height: buf[at + 1] || 256,
      colors: buf[at + 2],
      planes: buf.readUInt16LE(at + 4),
      bitsPerPixel: buf.readUInt16LE(at + 6),
      bytes: buf.readUInt32LE(at + 8),
      offset: buf.readUInt32LE(at + 12),
    });
  }
  return frames;
}

const signature = (frames) =>
  frames.map((frame) => `${frame.width}x${frame.height}@${frame.bitsPerPixel}`).join(",");

/**
 * @returns {{ ok: boolean, actual: string, expected: string }}
 */
function verifyInstallerIcon(exePath = DEFAULT_EXE, icoPath = DEFAULT_ICO) {
  if (!fs.existsSync(exePath)) throw new Error(`setup not found: ${exePath}`);
  if (!fs.existsSync(icoPath)) throw new Error(`brand icon not found: ${icoPath}`);
  const actual = signature(readExeIcon(exePath));
  const expected = signature(readIcoIcon(icoPath));
  return { ok: actual === expected, actual, expected };
}

function main() {
  const exePath = path.resolve(process.argv[2] || DEFAULT_EXE);
  const icoPath = path.resolve(process.argv[3] || DEFAULT_ICO);
  try {
    const result = verifyInstallerIcon(exePath, icoPath);
    if (!result.ok) {
      console.error(`Installer icon mismatch: ${path.basename(exePath)}`);
      console.error(`  embedded: ${result.actual}`);
      console.error(`  expected: ${result.expected}`);
      console.error(
        "\nThis is NSIS's stock icon (or a stale build). Check that the tagged\n" +
          "commit contains desktop/installer/BlackEclipse.nsi with MUI_ICON, then\n" +
          "rebuild with `npm run desktop:installer`."
      );
      process.exit(1);
    }
    console.log(`Installer icon OK: ${path.basename(exePath)}`);
    console.log(`  ${result.actual}`);
  } catch (error) {
    console.error(`verify-installer-icon: ${error.message}`);
    process.exit(2);
  }
}

module.exports = { verifyInstallerIcon, readExeIcon, readIcoIcon, signature };

if (require.main === module) main();
