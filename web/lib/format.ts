export function storageSize(bytes: number) {
  if (!Number.isFinite(bytes) || bytes < 0) return "Unavailable";
  const unit = bytes === 0 ? 0 : Math.min(4, Math.floor(Math.log10(bytes) / 3));
  return `${(bytes / 1000 ** unit).toLocaleString(undefined, { maximumFractionDigits: unit === 0 ? 0 : 1 })} ${["B", "KB", "MB", "GB", "TB"][unit]}`;
}
