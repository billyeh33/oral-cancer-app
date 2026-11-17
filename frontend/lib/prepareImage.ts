// 上傳前先在瀏覽器把照片縮小成 JPEG。
// 手機原圖動輒 1200 萬畫素，模型只用 224×224，原圖送上去會讓免費方案的伺服器記憶體不足而重開。
// iPhone 的 HEIC 大部分瀏覽器讀不了，用 heic-to（較新的 libheif）解碼。

const MAX_SIDE = 1600;
const JPEG_QUALITY = 0.92;

export function isHeic(file: File) {
  const lowerName = file.name.toLowerCase();
  return (
    file.type === "image/heic" ||
    file.type === "image/heif" ||
    lowerName.endsWith(".heic") ||
    lowerName.endsWith(".heif")
  );
}

async function decode(file: File, heic: boolean): Promise<ImageBitmap> {
  try {
    // Safari 可以直接解 HEIC，其他格式所有瀏覽器都可以。
    return await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch (error) {
    if (!heic) {
      throw error;
    }
    const { heicTo } = await import("heic-to/next");
    return heicTo({ blob: file, type: "bitmap" });
  }
}

/** 縮小後的 JPEG；瀏覽器處理不了時回傳 null，由呼叫端改傳原檔。 */
export async function prepareImage(file: File): Promise<File | null> {
  const heic = isHeic(file);
  try {
    const bitmap = await decode(file, heic);
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    if (scale === 1 && !heic) {
      bitmap.close();
      return file;
    }
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const context = canvas.getContext("2d");
    if (!context) {
      bitmap.close();
      return null;
    }
    context.imageSmoothingQuality = "high";
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY),
    );
    if (!blob) {
      return null;
    }
    const name = file.name.replace(/\.[^.]+$/, "") + ".jpg";
    return new File([blob], name, { type: "image/jpeg" });
  } catch {
    return null;
  }
}
