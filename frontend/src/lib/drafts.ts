/** Local metadata only, never the uploaded files. */
export function readDraft(key: string, size?: number): string[] | null {
  try {
    const data: unknown = JSON.parse(localStorage.getItem(`wbalc:draft:${key}`) ?? 'null');
    return Array.isArray(data) && data.length > 0 && (size === undefined || data.length === size) &&
      data.every(value => typeof value === 'string') ? data : null;
  } catch { return null; }
}
export function writeDraft(key: string, values: string[] | null) {
  try {
    if (values) localStorage.setItem(`wbalc:draft:${key}`, JSON.stringify(values));
    else localStorage.removeItem(`wbalc:draft:${key}`);
  } catch { /* storage is optional */ }
}
export function mappingKey(project: string, kind: string, files: File[]) {
  return JSON.stringify([project, kind, files.map(f => [f.webkitRelativePath || f.name, f.size, f.lastModified])]);
}
