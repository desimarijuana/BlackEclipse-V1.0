#!/usr/bin/env node
// Rebrand the runtime executables a packaged install ships.
//
// Why: Windows draws each process in Task Manager / Explorer from the ICON and
// VERSIONINFO resources of the executable that process runs. A packaged install
// spawns two executables that are not ours — `runtime/node.exe` (the Node
// bootstrap + Next server) and `app/scripts/vendor/python/python.exe` (the
// agent runtime) — so without this step they appear as "Node.js JavaScript
// Runtime" and "Python" with the upstream logos. Rewriting those two resources
// makes them read as Black Eclipse. Nothing about their behaviour changes: only
// the icon and the descriptive strings are replaced.
//
// This is a PACKAGING step. A repository checkout (`npm run desktop:dev`) uses
// the machine's own Node and the vendored Python as-is; those are not touched.
//
// Caveat: upstream node.exe / python.exe are Authenticode-signed. Editing the
// resources invalidates that signature. The install is unsigned anyway, but it
// is the reason this runs at package time on a copy, never in place.
//
// Usage (CLI):
//   node scripts/brand-runtime.js --out dist/BlackEclipse
//   node scripts/brand-runtime.js <exe> [icon.ico] "<FileDescription>"
//
// API:
//   const { brandExecutable, brandPackagedRuntime } = require("./brand-runtime");

const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const DEFAULT_ICON = path.join(ROOT, "public", "branding", "black-eclipse.ico");

// en-US. Every resource this touches already carries it; using the same value
// replaces rather than appends, so repeated packaging runs cannot grow the file.
const LANG = 1033;
const CODEPAGE = 1200;

function loadResedit() {
  try {
    return require("resedit");
  } catch {
    throw new Error(
      "resedit is not installed. Run `npm install` in Black-Eclipse-site (it is a devDependency)."
    );
  }
}

/**
 * Point the Resource / BaseRelocation data-directory entries at where the
 * sections actually landed.
 *
 * `NtExecutable.generate()` compacts virtual addresses. Node's `.reloc` stays
 * put, but Python's embedded launcher has a large hole after `.rsrc`, so its
 * `.reloc` moves — while the BaseRelocation directory keeps the old RVA. That
 * leaves a directory pointing at unmapped memory (and makes the file fail to
 * re-parse). Patching the entry costs nothing and keeps the binary coherent.
 */
function repairDataDirectories(buf) {
  if (buf.readUInt16LE(0) !== 0x5a4d) return; // "MZ"
  const pe = buf.readUInt32LE(0x3c);
  if (buf.readUInt32LE(pe) !== 0x00004550) return; // "PE\0\0"
  const magic = buf.readUInt16LE(pe + 24);
  const is64 = magic === 0x20b;
  if (!is64 && magic !== 0x10b) return;

  const optionalOffset = pe + 24;
  const dataDirOffset = optionalOffset + (is64 ? 112 : 96);
  const dirCount = buf.readUInt32LE(optionalOffset + (is64 ? 108 : 92));
  const sectionCount = buf.readUInt16LE(pe + 6);
  const sectionTable = optionalOffset + buf.readUInt16LE(pe + 20);

  const sections = [];
  for (let i = 0; i < sectionCount; i += 1) {
    const o = sectionTable + i * 40;
    sections.push({
      name: buf.toString("ascii", o, o + 8).replace(/\0+$/, ""),
      va: buf.readUInt32LE(o + 12),
      span: Math.max(buf.readUInt32LE(o + 8), buf.readUInt32LE(o + 16)),
    });
  }

  const pointAt = (dirIndex, sectionName) => {
    if (dirIndex >= dirCount) return;
    const section = sections.find((s) => s.name === sectionName);
    if (!section) return;
    const offset = dataDirOffset + dirIndex * 8;
    const rva = buf.readUInt32LE(offset);
    const inside = sections.some((s) => rva >= s.va && rva < s.va + s.span);
    if (!inside) buf.writeUInt32LE(section.va, offset);
  };

  pointAt(2, ".rsrc"); // IMAGE_DIRECTORY_ENTRY_RESOURCE
  pointAt(5, ".reloc"); // IMAGE_DIRECTORY_ENTRY_BASERELOC
}

/**
 * Rewrite the icon and the descriptive version strings of one PE executable.
 * Returns the number of icon groups replaced.
 */
function brandExecutable(exePath, { icon = DEFAULT_ICON, description, product = "Black Eclipse", company = "Black Eclipse" }) {
  if (process.platform !== "win32") {
    console.log(`  brand: skipped ${path.basename(exePath)} (Windows PE resources only)`);
    return 0;
  }
  if (!fs.existsSync(exePath)) throw new Error(`brand: executable not found: ${exePath}`);
  if (!fs.existsSync(icon)) throw new Error(`brand: icon not found: ${icon}`);
  if (!description) throw new Error("brand: a FileDescription is required");

  const ResEdit = loadResedit();
  const original = fs.readFileSync(exePath);

  // `ignoreCert` lets a signed upstream binary parse. The signature is dropped
  // by generate(), which is expected — this is a modified copy.
  const exe = ResEdit.NtExecutable.from(original, { ignoreCert: true });
  const res = ResEdit.NtExecutableResource.from(exe);

  // --- icon ---------------------------------------------------------------
  const iconFile = ResEdit.Data.IconFile.from(fs.readFileSync(icon));
  const icons = iconFile.icons.map((entry) => entry.data);
  const groups = ResEdit.Resource.IconGroupEntry.fromEntries(res.entries);
  if (groups.length === 0) {
    ResEdit.Resource.IconGroupEntry.replaceIconsForResource(res.entries, 1, LANG, icons);
  } else {
    for (const group of groups) {
      ResEdit.Resource.IconGroupEntry.replaceIconsForResource(res.entries, group.id, group.lang, icons);
    }
  }

  // --- version strings ----------------------------------------------------
  // Keep the upstream numeric file version (it is the runtime's real version and
  // is useful in a bug report); replace only the human-facing identity.
  let versionInfos = ResEdit.Resource.VersionInfo.fromEntries(res.entries);
  if (versionInfos.length === 0) {
    versionInfos = [
      ResEdit.Resource.VersionInfo.create(LANG, {}, [
        { lang: LANG, codepage: CODEPAGE, values: {} },
      ]),
    ];
  }
  for (const vi of versionInfos) {
    const languages = vi.getAllLanguagesForStringValues();
    const targets = languages.length > 0 ? languages : [{ lang: LANG, codepage: CODEPAGE }];
    for (const language of targets) {
      vi.setStringValues(language, {
        FileDescription: description,
        ProductName: product,
        CompanyName: company,
      });
    }
    vi.outputToResourceEntries(res.entries);
  }

  res.outputResource(exe);

  const output = Buffer.from(exe.generate());
  repairDataDirectories(output);
  fs.writeFileSync(exePath, output);

  console.log(`  brand: ${path.basename(exePath)} -> "${description}"`);
  return groups.length || 1;
}

/**
 * Brand the runtime executables inside an assembled install directory
 * (`dist/BlackEclipse`), if they are present. Safe to call on non-Windows.
 */
function brandPackagedRuntime(outDir, { icon = DEFAULT_ICON } = {}) {
  if (process.platform !== "win32") {
    console.log("  brand: skipped (Windows packaging only)");
    return;
  }
  const nodeName = "node.exe";
  const pyName = "python.exe";
  const targets = [
    {
      file: path.join(outDir, "runtime", nodeName),
      description: "Black Eclipse Server (Node.js)",
    },
    {
      file: path.join(outDir, "app", "scripts", "vendor", "python", pyName),
      description: "Black Eclipse Agent Runtime (Python)",
    },
    {
      // pythonw.exe runs windowless; the embedded distribution ships it and a
      // future caller may use it. Brand it when present so both look the same.
      file: path.join(outDir, "app", "scripts", "vendor", "python", "pythonw.exe"),
      description: "Black Eclipse Agent Runtime (Python)",
    },
  ];

  for (const target of targets) {
    if (!fs.existsSync(target.file)) {
      console.log(`  brand: skip ${path.relative(outDir, target.file)} (not present)`);
      continue;
    }
    brandExecutable(target.file, { icon, description: target.description });
  }
}

module.exports = { brandExecutable, brandPackagedRuntime, DEFAULT_ICON };

if (require.main === module) {
  const args = process.argv.slice(2);
  if (args[0] === "--out") {
    const outDir = path.resolve(args[1] || path.join(ROOT, "dist", "BlackEclipse"));
    brandPackagedRuntime(outDir);
  } else {
    const [exe, icon, description] = args;
    if (!exe || !description) {
      console.error('usage: node scripts/brand-runtime.js --out <install-dir> | <exe> [icon.ico] "<FileDescription>"');
      process.exit(2);
    }
    brandExecutable(exe, { icon: icon || DEFAULT_ICON, description });
  }
}
