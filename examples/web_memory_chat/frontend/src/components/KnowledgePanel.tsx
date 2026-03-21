import { useState, useEffect, useRef, useCallback } from "react";
import {
  getDocuments,
  uploadDocument,
  deleteDocument,
  clearDocuments,
} from "../api";
import type { DocumentItem } from "../types";

interface Props {
  userId: string;
  refreshKey: number;
}

const ACCEPTED = ".txt,.md,.pdf,.png,.jpg,.jpeg,.gif,.webp";

const TYPE_ICONS: Record<string, string> = {
  text: "\u{1F4C4}",
  pdf: "\u{1F4D1}",
  image: "\u{1F5BC}",
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function KnowledgePanel({ userId, refreshKey }: Props) {
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadDocs = useCallback(async () => {
    try {
      const list = await getDocuments(userId);
      setDocs(list);
    } catch {
      /* ignore */
    }
  }, [userId]);

  useEffect(() => {
    loadDocs();
  }, [userId, refreshKey, loadDocs]);

  const handleFiles = async (files: FileList | File[]) => {
    setError(null);
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        await uploadDocument(userId, file);
      }
      await loadDocs();
    } catch (e: any) {
      setError(e.message || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
  };

  const handleDelete = async (docId: string) => {
    try {
      await deleteDocument(userId, docId);
      await loadDocs();
    } catch (e: any) {
      setError(e.message || "Delete failed");
    }
  };

  const handleClearAll = async () => {
    if (!confirm("Delete ALL documents for this user?")) return;
    try {
      await clearDocuments(userId);
      await loadDocs();
    } catch (e: any) {
      setError(e.message || "Clear failed");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Upload zone */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onClick={() => fileInputRef.current?.click()}
        style={{
          border: `2px dashed ${dragOver ? "#60a5fa" : "#555"}`,
          borderRadius: 8,
          padding: "16px 12px",
          textAlign: "center",
          cursor: "pointer",
          background: dragOver ? "rgba(96,165,250,0.08)" : "transparent",
          margin: "0 0 12px 0",
          transition: "all 0.15s",
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED}
          multiple
          style={{ display: "none" }}
          onChange={(e) => {
            if (e.target.files?.length) handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
        {uploading ? (
          <span style={{ color: "#60a5fa" }}>Processing...</span>
        ) : (
          <>
            <div style={{ fontSize: 13, color: "#ccc", marginBottom: 4 }}>
              Drop files here or click to upload
            </div>
            <div style={{ fontSize: 11, color: "#888" }}>
              TXT, MD, PDF, PNG, JPG
            </div>
          </>
        )}
      </div>

      {error && (
        <div style={{
          color: "#f87171", fontSize: 12, marginBottom: 8, padding: "0 4px",
        }}>
          {error}
        </div>
      )}

      {/* Document list */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {docs.length === 0 ? (
          <div style={{ color: "#888", fontSize: 13, textAlign: "center",
                        padding: 20 }}>
            No documents uploaded
          </div>
        ) : (
          docs.map((doc) => (
            <div
              key={doc.doc_id}
              style={{
                background: "#2a2a2a",
                borderRadius: 6,
                padding: "8px 10px",
                marginBottom: 6,
                fontSize: 12,
              }}
            >
              <div style={{
                display: "flex", justifyContent: "space-between",
                alignItems: "center", marginBottom: 4,
              }}>
                <span style={{ fontWeight: 600, color: "#e0e0e0" }}>
                  {TYPE_ICONS[doc.file_type] || ""} {doc.filename}
                </span>
                <button
                  onClick={() => handleDelete(doc.doc_id)}
                  style={{
                    background: "none", border: "none", color: "#888",
                    cursor: "pointer", fontSize: 14, padding: "0 2px",
                  }}
                  title="Delete"
                >
                  x
                </button>
              </div>
              <div style={{ color: "#999", fontSize: 11 }}>
                {doc.chunks} chunk{doc.chunks !== 1 ? "s" : ""}
                {" · "}
                {formatSize(doc.file_size)}
                {" · "}
                {new Date(doc.uploaded_at).toLocaleDateString()}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Footer actions */}
      {docs.length > 0 && (
        <div style={{ padding: "8px 0 0", borderTop: "1px solid #333" }}>
          <button
            onClick={handleClearAll}
            style={{
              background: "#7f1d1d", color: "#fca5a5", border: "none",
              borderRadius: 4, padding: "4px 10px", fontSize: 11,
              cursor: "pointer", width: "100%",
            }}
          >
            Clear All Documents
          </button>
        </div>
      )}
    </div>
  );
}
