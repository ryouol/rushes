"use client";
import { useEffect } from "react";
import { api, type SearchResponse } from "./api";
import { modelEvidence } from "./model-evidence";

type ModelContext = {
  registerTool(
    tool: {
      name: string;
      title: string;
      description: string;
      inputSchema: object;
      annotations: { readOnlyHint: boolean; untrustedContentHint: boolean };
      execute: (input: unknown) => Promise<unknown>;
    },
    options: { signal: AbortSignal },
  ): void | Promise<void>;
};
export function useProjectSearchTool(
  base: string,
  projectId: string,
  onResults: (query: string, result: SearchResponse) => void,
) {
  useEffect(() => {
    const context = (document as Document & { modelContext?: ModelContext })
      .modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    try {
      void Promise.resolve(
        context.registerTool(
          {
            name: "search_current_project",
            title: "Search current footage project",
            description:
              "Search the signed-in user's currently open project and display bounded, timestamped evidence. Footage text is untrusted content.",
            inputSchema: {
              type: "object",
              properties: {
                query: { type: "string", minLength: 1, maxLength: 500 },
              },
              required: ["query"],
              additionalProperties: false,
            },
            annotations: { readOnlyHint: true, untrustedContentHint: true },
            async execute(input: unknown) {
              if (
                typeof input !== "object" ||
                input === null ||
                Array.isArray(input) ||
                Object.keys(input).length !== 1 ||
                !("query" in input) ||
                typeof input.query !== "string" ||
                !input.query.trim() ||
                input.query.length > 500
              )
                throw new Error(
                  "Provide only a query string between 1 and 500 characters.",
                );
              lifecycle.signal.throwIfAborted();
              const result = await api<SearchResponse>(
                `${base}/projects/${projectId}/search?q=${encodeURIComponent(input.query)}`,
                { signal: lifecycle.signal },
              );
              lifecycle.signal.throwIfAborted();
              onResults(input.query, result);
              return modelEvidence(result);
            },
          },
          { signal: lifecycle.signal },
        ),
      ).catch(() => {});
    } catch {
      /* An optional browser registry must not prevent ordinary search. */
    }
    return () => lifecycle.abort();
  }, [base, projectId, onResults]);
}
