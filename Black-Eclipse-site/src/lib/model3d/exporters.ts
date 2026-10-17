// ── Mesh exporters (OBJ + binary STL) ────────────────────────────────────────
//
// The compiler bakes geometry to world space, so exporting is a direct walk of
// the compiled parts. No dependencies; pure and total.

import type { CompiledPart } from './compile';

export function model3dToObj(parts: CompiledPart[]): string {
  const lines: string[] = ['# BlackEclipse model3d', 'o eclipse_model'];
  let offset = 1;
  for (const part of parts) {
    const positions = part.mesh.positions;
    const indices = part.mesh.indices;
    if (positions.length === 0 || indices.length === 0) continue;
    lines.push(`g ${part.group}`);
    for (let i = 0; i < positions.length; i += 3) {
      lines.push(`v ${positions[i]} ${positions[i + 1]} ${positions[i + 2]}`);
    }
    for (let i = 0; i < indices.length; i += 3) {
      lines.push(`f ${indices[i]! + offset} ${indices[i + 1]! + offset} ${indices[i + 2]! + offset}`);
    }
    offset += positions.length / 3;
  }
  return lines.join('\n');
}

export function model3dToStl(parts: CompiledPart[]): Uint8Array {
  let triangles = 0;
  for (const part of parts) triangles += part.mesh.indices.length / 3;

  const buffer = new ArrayBuffer(84 + triangles * 50);
  const view = new DataView(buffer);
  const header = 'BlackEclipse model3d';
  for (let i = 0; i < header.length && i < 80; i++) view.setUint8(i, header.charCodeAt(i));
  view.setUint32(80, triangles, true);

  let offset = 84;
  const float = (value: number) => {
    view.setFloat32(offset, value, true);
    offset += 4;
  };

  for (const part of parts) {
    const p = part.mesh.positions;
    const idx = part.mesh.indices;
    for (let i = 0; i < idx.length; i += 3) {
      const a = idx[i]! * 3, b = idx[i + 1]! * 3, c = idx[i + 2]! * 3;
      const ax = p[a]!, ay = p[a + 1]!, az = p[a + 2]!;
      const bx = p[b]!, by = p[b + 1]!, bz = p[b + 2]!;
      const cx = p[c]!, cy = p[c + 1]!, cz = p[c + 2]!;
      const ux = bx - ax, uy = by - ay, uz = bz - az;
      const vx = cx - ax, vy = cy - ay, vz = cz - az;
      let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
      const len = Math.hypot(nx, ny, nz) || 1;
      nx /= len; ny /= len; nz /= len;
      float(nx); float(ny); float(nz);
      float(ax); float(ay); float(az);
      float(bx); float(by); float(bz);
      float(cx); float(cy); float(cz);
      view.setUint16(offset, 0, true);
      offset += 2;
    }
  }

  return new Uint8Array(buffer);
}
