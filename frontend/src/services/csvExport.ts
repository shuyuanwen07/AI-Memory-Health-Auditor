/** A quoted leading tab protects formula-like text in spreadsheet CSV imports.
 * JSON and saved evidence retain exact source text; the marker is CSV-only.
 * https://community.owasp.org/attacks/CSV_Injection
 */
export function spreadsheetCsvCell(value: unknown) {
  const text=String(value??'');
  const probe=text.normalize('NFKC').trimStart();
  const guarded=typeof value==='string'&&(/^[=+\-@]/u.test(probe)||/^[\t\r\n\0]/u.test(text))?`\t${text}`:text;
  return `"${guarded.replaceAll('"','""')}"`;
}
