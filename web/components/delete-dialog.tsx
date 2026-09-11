"use client";

import { useEffect, useRef, useState } from "react";
import { Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { Dialog } from "@/components/dialog";
import "./management.css";

export type DeleteTarget = {
  kind: "workspace" | "project" | "video" | "export" | "collection";
  name: string;
  path: string;
};

export function DeleteDialog({
  target,
  onClose,
  onDeleted,
}: {
  target: DeleteTarget;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const requiresName = target.kind === "workspace" || target.kind === "project";
  const description = {
    workspace:
      "Permanently delete this workspace and all its projects, uploaded videos, analysis, collections and exports. Everyone in the workspace will lose access. Your account stays active.",
    project:
      "Permanently delete this project, its uploaded videos, analysis, collections and exports.",
    video:
      "Permanently delete this video from RUSHES, including its uploaded copy, previews, analysis and saved selections. Completed exports stay available until you delete them separately.",
    export:
      "Permanently delete this export and its downloadable files. Your footage and collections stay in RUSHES.",
    collection:
      "Delete this collection and its saved selections or search. Your videos stay in the library, and completed exports stay available.",
  }[target.kind];

  return (
    <Dialog
      open
      onOpenChange={(open) => !open && !pending.current && onClose()}
      title={`Delete ${target.kind}?`}
      description={description}
    >
      <form
        className="delete-form"
        onSubmit={async (event) => {
          event.preventDefault();
          if (
            pending.current ||
            (requiresName && confirmation.trim() !== target.name.trim())
          )
            return;
          pending.current = true;
          const location = window.location.href;
          setBusy(true);
          setError("");
          try {
            await api(target.path, {
              method: "DELETE",
            });
            if (mounted.current && window.location.href === location)
              onDeleted();
          } catch (failure) {
            if (mounted.current)
              setError(
                failure instanceof Error
                  ? failure.message
                  : "Could not delete this item. Try again.",
              );
          } finally {
            pending.current = false;
            if (mounted.current) setBusy(false);
          }
        }}
      >
        <p className="delete-item-name">{target.name}</p>
        {["workspace", "project", "video"].includes(target.kind) && (
          <p className="muted small">
            Files you indexed from an external source folder are never deleted.
            Copies uploaded to RUSHES are removed.
          </p>
        )}
        {requiresName && (
          <label className="field">
            <span>Type the {target.kind} name to confirm</span>
            <input
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              autoComplete="off"
              spellCheck={false}
              disabled={busy}
            />
          </label>
        )}
        {error && (
          <p className="notice danger" role="alert">
            {error}
          </p>
        )}
        <div className="button-row delete-actions">
          <button
            type="button"
            className="secondary"
            disabled={busy}
            onClick={onClose}
          >
            Keep {target.kind}
          </button>
          <button
            type="submit"
            className="delete-primary"
            disabled={
              busy ||
              (requiresName && confirmation.trim() !== target.name.trim())
            }
          >
            <Trash2 size={16} />
            {busy ? "Deleting…" : `Delete ${target.kind}`}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
