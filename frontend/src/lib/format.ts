export function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return value.toFixed(value >= 10 || unit === 0 ? 0 : 1) + " " + units[unit];
}

export function formatTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export const STATUS_LABEL: Record<string, string> = {
  queued: "排队中",
  parsing: "解析中",
  translating: "翻译中",
  rebuilding: "重建中",
  validating: "校验中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};
