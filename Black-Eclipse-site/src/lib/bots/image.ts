// ── Bot/group avatar image helper ────────────────────────────────────────────
// Turns a picked image file into a small, square data URL we can persist on the
// client. Uploaded avatars are downscaled + center-cropped here so a large photo
// never blows the localStorage quota or the payload a bubble re-reads.

export const AVATAR_IMAGE_MAX = 128;

/**
 * Read a file, center-crop it to a square, downscale to `max` px and return a
 * JPEG data URL. Rejects when the file is not an image or the canvas is
 * unavailable (e.g. SSR — this only runs in the browser).
 */
export async function fileToAvatarDataUrl(file: File, max = AVATAR_IMAGE_MAX): Promise<string> {
  if (!file.type.startsWith('image/')) {
    throw new Error('Please choose an image file.');
  }
  const bitmap = await loadImage(file);
  const side = Math.min(bitmap.width, bitmap.height);
  const sx = (bitmap.width - side) / 2;
  const sy = (bitmap.height - side) / 2;
  const canvas = document.createElement('canvas');
  canvas.width = max;
  canvas.height = max;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Could not process the image.');
  ctx.drawImage(bitmap, sx, sy, side, side, 0, 0, max, max);
  if ('close' in bitmap && typeof (bitmap as ImageBitmap).close === 'function') {
    (bitmap as ImageBitmap).close();
  }
  return canvas.toDataURL('image/jpeg', 0.85);
}

async function loadImage(file: File): Promise<ImageBitmap | HTMLImageElement> {
  if (typeof createImageBitmap === 'function') {
    return createImageBitmap(file);
  }
  const url = URL.createObjectURL(file);
  try {
    return await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error('Could not read the image.'));
      img.src = url;
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}
