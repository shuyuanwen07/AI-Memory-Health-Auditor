import {spreadsheetCsvCell} from './csvExport';

test.each(['=1+1','+SUM(1,2)','-1+2','@SUM(1,2)','  =1+1','\ufeff =1+1','＝1+1','＋1','－1','＠SUM(1,2)','\tvalue','\rvalue','\nvalue','\0value'])('protects formula-like untrusted text %j without changing its original characters',text=>{
 expect(spreadsheetCsvCell(text)).toBe(`"\t${text}"`);
});

test('keeps numeric deltas numeric and quotes embedded separators and line breaks',()=>{
 expect(spreadsheetCsvCell(-75)).toBe('"-75"');
 expect(spreadsheetCsvCell(-0.5)).toBe('"-0.5"');
 expect(spreadsheetCsvCell(null)).toBe('""');
 expect(spreadsheetCsvCell('Béthune')).toBe('"Béthune"');
 expect(spreadsheetCsvCell('normal",=1+1')).toBe('"normal"",=1+1"');
 expect(spreadsheetCsvCell('line one\n=1+1')).toBe('"line one\n=1+1"');
});
