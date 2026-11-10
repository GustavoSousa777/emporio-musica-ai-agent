import type { UIMessage } from "ai";

export type ToolInfo = { name: string; ok: boolean };

export type ChatMeta = {
  tools: ToolInfo[];
  escalated: boolean;
  degraded: boolean;
};

export type ChatMessage = UIMessage<never, { meta: ChatMeta }>;

export type BackendReply = {
  reply: string;
  session_id: string;
  tools: ToolInfo[];
  escalated: boolean;
  degraded: boolean;
  model: string | null;
  input_truncated: boolean;
};
