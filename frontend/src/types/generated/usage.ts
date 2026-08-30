/** Compile-only fixture so generated OpenAPI types stay referenced. */
import type { components, paths } from "./openapi";

export type MvpServerSettings =
  paths["/v1/settings/server"]["get"]["responses"][200]["content"]["application/json"];
export type MvpLlmSettings =
  paths["/v1/settings/llm"]["get"]["responses"][200]["content"]["application/json"];
export type MvpSearch =
  paths["/v1/search"]["get"]["responses"][200]["content"]["application/json"];
export type MvpUpload =
  paths["/v1/upload"]["post"]["responses"][201]["content"]["application/json"];
export type MvpStats =
  paths["/v1/stats/overview"]["get"]["responses"][200]["content"]["application/json"];
export type MvpRunningCount =
  paths["/v1/tasks/running-count"]["get"]["responses"][200]["content"]["application/json"];
export type MvpActiveTasks =
  paths["/v1/tasks/active"]["get"]["responses"][200]["content"]["application/json"];
export type MvpRecentTasks =
  paths["/v1/tasks/recent"]["get"]["responses"][200]["content"]["application/json"];
export type MvpThroughput =
  paths["/v1/tasks/throughput"]["get"]["responses"][200]["content"]["application/json"];
export type MvpChatStream =
  paths["/v1/chat/{session_id}"]["post"]["responses"][200]["content"]["text/event-stream"];
export type MvpChatResume =
  paths["/v1/conversations/{conversation_id}/events"]["get"]["responses"][200]["content"]["text/event-stream"];
export type ContractSessions =
  paths["/v1/sessions"]["get"]["responses"][200]["content"]["application/json"];
export type ContractFolders =
  paths["/v1/folders"]["get"]["responses"][200]["content"]["application/json"];
export type ContractWebDav =
  paths["/v1/sync/webdav/status"]["get"]["responses"][200]["content"]["application/json"];

type _Schemas = components["schemas"]["ServerSettingsResponse"]
  | components["schemas"]["LlmSettingsResponse"]
  | components["schemas"]["SearchResponse"]
  | components["schemas"]["UploadResponse"];
export type _KeepGeneratedSchemas = _Schemas;
