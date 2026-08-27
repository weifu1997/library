import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

import type { ChatImage } from "@/types/api";

/** shadcn/ui-style class merge. Tailwind + conditional classes without
 *  worrying about ordering: `cn("p-2", condition && "p-4")` keeps p-4. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Keys that look human-friendly when rendered as a label, in order
 *  of preference. Mirrors the CLI's payload_label heuristic. */
const LABEL_KEYS = ["entry_id", "file_id", "session_id", "conversation_id", "path"];

export function payloadLabel(p: unknown): string {
  if (!p || typeof p !== "object") return "";
  const obj = p as Record<string, unknown>;
  for (const k of LABEL_KEYS) {
    const v = obj[k];
    if (v) {
      const s = String(v);
      return `${k}=${s.length > 24 ? s.slice(0, 24) + "…" : s}`;
    }
  }
  return "";
}

export function shortDuration(seconds: number): string {
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds - m * 60);
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

/** Format bytes as a human-readable size. KB/MB/GB are 1024-based to
 *  match what users see in OS file managers on Windows/macOS. */
export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

// --- Chat image attachments -------------------------------------------------
// Client-side mirror of the server caps enforced in POST /v1/chat/{id}
// (chat_image_max_count / chat_image_max_bytes). Keep these in sync with the
// backend so users get a friendly inline message instead of an HTTP 413.
export const CHAT_IMAGE_MAX_COUNT = 4;
export const CHAT_IMAGE_MAX_BYTES = 10 * 1024 * 1024;

export type ChatImageMediaType = ChatImage["media_type"];

const SUPPORTED_CHAT_IMAGE_TYPES: readonly ChatImageMediaType[] = [
  "image/png",
  "image/jpeg",
  "image/gif",
  "image/webp",
];

/** True if `type` is one of the media types the model's vision path accepts.
 *  Narrows to the ChatImage media_type union so the value can be sent as-is. */
export function isSupportedChatImageType(type: string): type is ChatImageMediaType {
  return (SUPPORTED_CHAT_IMAGE_TYPES as readonly string[]).includes(type);
}

/** A pending composer attachment: the wire fields (media_type + data_b64)
 *  plus a stable id and a ready-to-render preview data URL. */
export interface PendingChatImage extends ChatImage {
  id: string;
  previewUrl: string;
  name?: string;
}

/** Read a File into a PendingChatImage. Uses FileReader.readAsDataURL and
 *  splits the `data:<mime>;base64,<payload>` string into the media_type and
 *  RAW base64 payload the backend expects (no `data:` prefix in data_b64).
 *  The full data URL is retained as `previewUrl` for the thumbnail. */
export async function fileToChatImage(file: File): Promise<PendingChatImage> {
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("failed to read image"));
    reader.readAsDataURL(file);
  });
  const comma = dataUrl.indexOf(",");
  const header = comma === -1 ? dataUrl : dataUrl.slice(0, comma);
  const dataB64 = comma === -1 ? "" : dataUrl.slice(comma + 1);
  const mimeMatch = /^data:([^;]+)/.exec(header);
  const mediaType = (mimeMatch?.[1] ?? file.type) as ChatImageMediaType;
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    media_type: mediaType,
    data_b64: dataB64,
    previewUrl: dataUrl,
    name: file.name || undefined,
  };
}
