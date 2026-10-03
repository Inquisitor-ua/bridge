// Turns any picked photo into a small square avatar before upload: centre
// crop, 256x256, WebP (JPEG where the browser can't encode WebP, i.e. Safari).
// A phone photo of several MB becomes a few dozen KB.
const SIZE = 256;
const BACKGROUND = "#161c1a"; // shows through transparent PNGs in the JPEG fallback

function toBlob(canvas, type, quality) {
  return new Promise((resolve) => canvas.toBlob(resolve, type, quality));
}

export async function prepareAvatar(file) {
  let bitmap;
  try {
    // honours EXIF rotation, so phone photos aren't sideways
    bitmap = await createImageBitmap(file);
  } catch {
    throw new Error("не удалось открыть картинку, попробуйте другой файл");
  }
  const side = Math.min(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = BACKGROUND;
  ctx.fillRect(0, 0, SIZE, SIZE);
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(bitmap, (bitmap.width - side) / 2, (bitmap.height - side) / 2, side, side, 0, 0, SIZE, SIZE);
  bitmap.close?.();

  const webp = await toBlob(canvas, "image/webp", 0.86);
  if (webp && webp.type === "image/webp") return webp;
  const jpeg = await toBlob(canvas, "image/jpeg", 0.88);
  if (!jpeg) throw new Error("не удалось обработать картинку");
  return jpeg;
}
