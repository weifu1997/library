/** Decoder for `user_artifact` SSE payloads and replayed transcript artifacts.

The runtime emits `{tool, payload}` where `payload` is the tool's
`__user_only__` blob. Session replay projects the same blob onto
`ReplayedTurn.artifacts`. One parser owns both so ChatPage and TurnView
do not each invent the contract.
*/
import type { UserArtifact } from "@/types/api";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseUserArtifact(payload: unknown): UserArtifact | null {
  if (!isRecord(payload)) return null;
  const kind = payload.kind;
  if (kind === "vega_lite") {
    const chartId = payload.chart_id;
    const spec = payload.spec;
    if (typeof chartId !== "string" || !chartId.trim()) return null;
    if (!isRecord(spec)) return null;
    return {
      kind: "vega_lite",
      chart_id: chartId,
      spec,
      ...(typeof payload.title === "string" && payload.title
        ? { title: payload.title }
        : {}),
      ...(typeof payload.caption === "string" && payload.caption
        ? { caption: payload.caption }
        : {}),
    };
  }
  if (kind === "data_export") {
    const filename = payload.filename;
    const format = payload.format;
    const rowCount = payload.row_count;
    if (format !== "csv") return null;
    if (typeof filename !== "string" || !filename) return null;
    if (typeof rowCount !== "number" || !Number.isFinite(rowCount)) return null;
    return {
      kind: "data_export",
      format: "csv",
      filename,
      row_count: rowCount,
      ...(typeof payload.truncated === "boolean"
        ? { truncated: payload.truncated }
        : {}),
      ...(Array.isArray(payload.columns)
        && payload.columns.every((c): c is string => typeof c === "string")
        ? { columns: payload.columns }
        : {}),
    };
  }
  return null;
}

export function parseUserArtifactEvent(data: unknown): UserArtifact | null {
  if (!isRecord(data)) return null;
  return parseUserArtifact(data.payload);
}
