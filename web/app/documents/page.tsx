"use client";

import { ChangeEvent, DragEvent, FormEvent, useEffect, useRef, useState } from "react";
import Topbar from "@/components/Topbar";
import { api, dateText } from "@/lib/api";

type BulkResult = {
  summary: {
    submitted_items: number;
    received_bytes: number;
    documents_queued: number;
    duplicates: number;
    skipped: number;
    errors: number;
    archives: number;
  };
  archives: Array<{
    name: string;
    accepted: number;
    duplicates: number;
    skipped: number;
    errors: number;
  }>;
  duplicates: Array<{ name: string; existing_document_id: string }>;
  skipped: Array<{ name: string; reason: string }>;
  errors: Array<{ name: string; error: string }>;
};

export default function DocumentsPage() {
  const [items, setItems] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<BulkResult | null>(null);
  const [dragging, setDragging] = useState(false);

  const fileInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    folderInput.current?.setAttribute("webkitdirectory", "");
    folderInput.current?.setAttribute("directory", "");
  }, []);

  function load() {
    api<any[]>("/api/v1/documents").then(setItems).catch((e) => setError(e.message));
  }

  useEffect(load, []);

  function appendFiles(incoming: File[]) {
    setResult(null);
    setSelected((current) => {
      const byKey = new Map<string, File>();
      for (const file of [...current, ...incoming]) {
        const relative = file.webkitRelativePath || file.name;
        byKey.set(`${relative}:${file.size}:${file.lastModified}`, file);
      }
      return [...byKey.values()];
    });
  }

  function chooseFiles(e: ChangeEvent<HTMLInputElement>) {
    appendFiles(Array.from(e.target.files || []));
    e.target.value = "";
  }

  async function walkEntry(entry: any, prefix = ""): Promise<File[]> {
    if (entry.isFile) {
      return await new Promise((resolve) => {
        entry.file((file: File) => {
          const name = prefix ? `${prefix}/${file.name}` : file.name;
          const wrapped = new File([file], name, {
            type: file.type,
            lastModified: file.lastModified,
          });
          Object.defineProperty(wrapped, "webkitRelativePath", {
            value: name,
            configurable: true,
          });
          resolve([wrapped]);
        });
      });
    }

    if (entry.isDirectory) {
      const reader = entry.createReader();
      const children: any[] = [];
      while (true) {
        const batch: any[] = await new Promise((resolve, reject) =>
          reader.readEntries(resolve, reject)
        );
        if (!batch.length) break;
        children.push(...batch);
      }

      const nextPrefix = prefix ? `${prefix}/${entry.name}` : entry.name;
      const nested = await Promise.all(
        children.map((child) => walkEntry(child, nextPrefix))
      );
      return nested.flat();
    }

    return [];
  }

  async function drop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);

    const itemEntries = Array.from(e.dataTransfer.items || [])
      .map((item: any) => item.webkitGetAsEntry?.())
      .filter(Boolean);

    if (itemEntries.length) {
      const resolved = await Promise.all(
        itemEntries.map((entry: any) => walkEntry(entry))
      );
      appendFiles(resolved.flat());
    } else {
      appendFiles(Array.from(e.dataTransfer.files || []));
    }
  }

  async function uploadBulk() {
    if (!selected.length) return;

    setBusy(true);
    setError("");
    setResult(null);

    const fd = new FormData();
    for (const file of selected) {
      const relative = file.webkitRelativePath || file.name;
      fd.append("files", file, relative);
    }

    try {
      const response = await api<BulkResult>("/api/v1/documents/bulk", {
        method: "POST",
        body: fd,
      });
      setResult(response);
      setSelected([]);
      load();
      setTimeout(load, 2200);
      setTimeout(load, 6500);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function uploadSingle(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    try {
      await api("/api/v1/documents", { method: "POST", body: fd });
      form.reset();
      load();
      setTimeout(load, 2500);
    } catch (e: any) {
      setError(e.message);
    }
  }

  const selectedBytes = selected.reduce((total, file) => total + file.size, 0);

  return (
    <>
      <Topbar eyebrow="Source material" title="Documents" />

      {error && <div className="errorBox">{error}</div>}

      <section className="panel" style={{ marginTop: 0 }}>
        <div className="panelHead">
          <div>
            <h2>Bulk ingest</h2>
            <div className="meta">
              Whole folders, ZIP archives, or hundreds of documents in one batch
            </div>
          </div>
          <span className="badge">recursive</span>
        </div>

        <div
          className={`bulkDrop ${dragging ? "dragging" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={drop}
        >
          <div className="bulkGlyph">⇣</div>
          <strong>Drop files, folders or ZIP archives here</strong>
          <div className="meta" style={{ marginTop: 7 }}>
            Folders are uploaded recursively. ZIPs are safely unpacked server-side.
          </div>

          <div className="row" style={{ justifyContent: "center", marginTop: 18, flexWrap: "wrap" }}>
            <button className="button" type="button" onClick={() => fileInput.current?.click()}>
              Choose files / ZIPs
            </button>
            <button className="button" type="button" onClick={() => folderInput.current?.click()}>
              Choose folder
            </button>
          </div>

          <input
            ref={fileInput}
            type="file"
            multiple
            hidden
            onChange={chooseFiles}
            accept=".pdf,.docx,.txt,.md,.csv,.json,.log,.yaml,.yml,.zip"
          />
          <input
            ref={folderInput}
            type="file"
            multiple
            hidden
            onChange={chooseFiles}
          />
        </div>

        {selected.length > 0 && (
          <div className="bulkQueue">
            <div className="panelHead" style={{ marginBottom: 10 }}>
              <div>
                <h2>{selected.length} item{selected.length === 1 ? "" : "s"} queued</h2>
                <div className="meta">
                  {(selectedBytes / 1024 / 1024).toFixed(2)} MB before ZIP expansion
                </div>
              </div>
              <div className="row">
                <button className="ghostButton" type="button" onClick={() => setSelected([])}>
                  Clear
                </button>
                <button className="button primary" type="button" onClick={uploadBulk} disabled={busy}>
                  {busy ? "Ingesting…" : "Start bulk ingest"}
                </button>
              </div>
            </div>

            <div className="bulkFileList">
              {selected.slice(0, 18).map((file, index) => (
                <div className="bulkFile" key={`${file.name}-${file.size}-${index}`}>
                  <span>{file.webkitRelativePath || file.name}</span>
                  <span className="meta">{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                </div>
              ))}
              {selected.length > 18 && (
                <div className="meta" style={{ paddingTop: 8 }}>
                  + {selected.length - 18} more files
                </div>
              )}
            </div>
          </div>
        )}

        {result && (
          <div className="bulkResult">
            <div className="grid4">
              <div className="miniStat">
                <span>Queued</span>
                <strong>{result.summary.documents_queued}</strong>
              </div>
              <div className="miniStat">
                <span>Duplicates</span>
                <strong>{result.summary.duplicates}</strong>
              </div>
              <div className="miniStat">
                <span>Skipped</span>
                <strong>{result.summary.skipped}</strong>
              </div>
              <div className="miniStat">
                <span>Errors</span>
                <strong>{result.summary.errors}</strong>
              </div>
            </div>

            {result.archives.length > 0 && (
              <div style={{ marginTop: 14 }}>
                <div className="meta">Archives unpacked</div>
                {result.archives.map((archive) => (
                  <div className="bulkFile" key={archive.name}>
                    <span>{archive.name}</span>
                    <span className="meta">
                      {archive.accepted} queued · {archive.duplicates} duplicate · {archive.skipped} skipped · {archive.errors} error
                    </span>
                  </div>
                ))}
              </div>
            )}

            {(result.errors.length > 0 || result.skipped.length > 0) && (
              <details style={{ marginTop: 14 }}>
                <summary className="meta" style={{ cursor: "pointer" }}>
                  Show skipped files and errors
                </summary>
                <div style={{ marginTop: 10 }}>
                  {result.errors.slice(0, 100).map((item, index) => (
                    <div className="errorBox" key={`e-${index}`}>
                      <strong>{item.name}</strong><br />{item.error}
                    </div>
                  ))}
                  {result.skipped.slice(0, 100).map((item, index) => (
                    <div className="bulkFile" key={`s-${index}`}>
                      <span>{item.name}</span>
                      <span className="meta">{item.reason}</span>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panelHead">
          <div>
            <h2>Single document</h2>
            <div className="meta">PDF, DOCX, TXT, Markdown, CSV, JSON, YAML and logs</div>
          </div>
          <form className="row" onSubmit={uploadSingle}>
            <input
              className="input"
              type="file"
              name="file"
              required
              accept=".pdf,.docx,.txt,.md,.csv,.json,.log,.yaml,.yml"
            />
            <button className="button primary">Upload</button>
          </form>
        </div>
      </section>

      <section className="panel">
        <div className="panelHead">
          <h2>Document library</h2>
          <span className="meta">{items.length} source documents</span>
        </div>

        <div className="tableWrap">
          <table>
            <thead>
              <tr><th>File</th><th>Status</th><th>Size</th><th>Uploaded</th><th></th></tr>
            </thead>
            <tbody>
              {items.map((d) => (
                <tr key={d.id}>
                  <td>
                    <strong>{d.filename}</strong>
                    <div className="meta">{d.content_type || "unknown type"}</div>
                  </td>
                  <td>
                    <span className={`badge ${d.status}`}>{d.status}</span>
                    {d.extraction_error && <div className="meta">{d.extraction_error}</div>}
                  </td>
                  <td>{(d.byte_size / 1024 / 1024).toFixed(2)} MB</td>
                  <td className="meta">{dateText(d.created_at)}</td>
                  <td>
                    <a className="ghostButton" href={`/api/v1/documents/${d.id}/download`}>
                      Download
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!items.length && <div className="empty">No source documents uploaded yet.</div>}
      </section>
    </>
  );
}
