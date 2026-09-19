import type { SubmitAnswerRequest, SubmitAnswerResponse } from "./client";

// Hand-rolled: the generated client has no SSE support (OpenAPI doesn't
// model text/event-stream), and this endpoint's framing is simple enough
// (two named events, single-line JSON data) not to warrant a library.
export type StreamCallbacks = {
  onRationaleDelta: (text: string) => void;
  onGraded: (result: SubmitAnswerResponse) => void;
  onError: (message: string) => void;
};

// SSE frames are separated by a blank line; within a frame, "event: x" and
// "data: y" are each one line (this endpoint never sends multi-line data).
function parseSseFrame(frame: string): { event: string; data: string } | null {
  let event = "";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice("event:".length).trim();
    else if (line.startsWith("data:")) data = line.slice("data:".length).trim();
  }
  return event ? { event, data } : null;
}

export async function submitAnswerStream(
  sessionId: string,
  request: SubmitAnswerRequest,
  { onRationaleDelta, onGraded, onError }: StreamCallbacks,
): Promise<void> {
  const response = await fetch(
    `/sessions/${encodeURIComponent(sessionId)}/answers/submit/stream`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );

  if (!response.ok || !response.body) {
    onError("Grading failed.");
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    // sse-starlette emits \r\n line endings; normalize before framing so
    // "\n\n" reliably matches the blank-line frame separator regardless of
    // which the server sends.
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

    let separatorIndex: number;
    while ((separatorIndex = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      const parsed = parseSseFrame(frame);
      if (!parsed) continue;

      if (parsed.event === "rationale_delta") {
        onRationaleDelta((JSON.parse(parsed.data) as { text: string }).text);
      } else if (parsed.event === "graded") {
        onGraded(JSON.parse(parsed.data) as SubmitAnswerResponse);
      } else if (parsed.event === "error") {
        onError(parsed.data);
      }
    }
  }
}
