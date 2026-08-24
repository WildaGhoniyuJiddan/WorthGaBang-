import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const backendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const inputDir = path.join(backendRoot, "data", "used_hardware");
const outputDir = inputDir;
const previewDir = path.join(inputDir, "previews");

const sheetFiles = [
  ["Summary", "summary.csv", "SummaryTable"],
  ["Laptops", "laptop.csv", "LaptopsTable"],
  ["PC Components", "komponen_pc.csv", "PCComponentsTable"],
  ["PC Fullsets", "pc_fullset.csv", "PCFullsetsTable"],
  ["Review Queue", "perlu_review.csv", "ReviewQueueTable"],
  ["Feed Summary", "feed_summary.csv", "FeedSummaryTable"],
  ["Data Dictionary", "data_dictionary.csv", "DataDictionaryTable"],
];

const outputPath = path.join(outputDir, "dataset_hardware_bekas.xlsx");

function columnLetter(index) {
  let value = index;
  let result = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    value = Math.floor((value - 1) / 26);
  }
  return result;
}

function setColumnWidth(sheet, colNumber, width, rowCount) {
  const letter = columnLetter(colNumber);
  sheet.getRange(`${letter}1:${letter}${Math.max(rowCount, 2)}`).format.columnWidth = width;
}

function coerceNumbers(sheet, address) {
  const range = sheet.getRange(address);
  const values = range.values;
  range.values = values.map((row) => row.map((value) => {
    if (value === "" || value === null || value === undefined) return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : value;
  }));
}

function styleSheet(sheet, sheetName, tableName, rowCount, columnCount) {
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  const lastCol = columnLetter(columnCount);
  const usedRange = sheet.getRange(`A1:${lastCol}${Math.max(rowCount, 1)}`);
  const header = sheet.getRange(`A1:${lastCol}1`);
  header.format = {
    fill: "#0F766E",
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
    verticalAlignment: "center",
  };
  header.format.rowHeight = 30;
  usedRange.format.font = { name: "Aptos", size: 10 };
  usedRange.format.verticalAlignment = "top";
  usedRange.format.wrapText = false;
  if (rowCount > 1) {
    try {
      sheet.tables.add(`A1:${lastCol}${rowCount}`, true, tableName);
    } catch (error) {
      console.log(`table_add_skipped=${sheetName}:${error.message}`);
    }
  }

  if (sheetName === "Summary") {
    setColumnWidth(sheet, 1, 30, rowCount);
    setColumnWidth(sheet, 2, 16, rowCount);
    setColumnWidth(sheet, 3, 62, rowCount);
    if (rowCount > 1) coerceNumbers(sheet, `B2:B${rowCount}`);
    sheet.getRange(`A2:A${rowCount}`).format.font = { bold: true, color: "#0F766E" };
    sheet.getRange(`B2:B${rowCount}`).format.numberFormat = "#,##0";
  } else if (sheetName === "Data Dictionary") {
    setColumnWidth(sheet, 1, 30, rowCount);
    setColumnWidth(sheet, 2, 64, rowCount);
    setColumnWidth(sheet, 3, 28, rowCount);
  } else if (sheetName === "Feed Summary") {
    for (const [col, width] of [[1, 22], [2, 18], [3, 58], [4, 28], [5, 18], [6, 18], [7, 18], [8, 16], [9, 16], [10, 22], [11, 28], [12, 28], [13, 22]]) {
      setColumnWidth(sheet, col, width, rowCount);
    }
  } else {
    const widths = [16, 12, 26, 22, 18, 38, 38, 48, 16, 18, 18, 34, 28, 14, 18, 18, 12, 14, 12, 14, 16, 18, 14, 16, 24, 34, 42, 24];
    widths.forEach((width, index) => setColumnWidth(sheet, index + 1, width, rowCount));
    if (rowCount > 1) coerceNumbers(sheet, `Q2:U${rowCount}`);
    sheet.getRange(`Q2:S${rowCount}`).format.numberFormat = "#,##0";
    sheet.getRange(`T2:T${rowCount}`).format.numberFormat = "0.0";
    sheet.getRange(`U2:U${rowCount}`).format.numberFormat = "#,##0";
    sheet.getRange(`A2:A${rowCount}`).format.font = { color: "#475569" };
    sheet.getRange(`B2:B${rowCount}`).conditionalFormats.add("containsText", { text: "accepted", format: { fill: "#DCFCE7", font: { color: "#166534" } } });
    sheet.getRange(`B2:B${rowCount}`).conditionalFormats.add("containsText", { text: "review", format: { fill: "#FEF3C7", font: { color: "#92400E" } } });
    sheet.getRange(`B2:B${rowCount}`).conditionalFormats.add("containsText", { text: "excluded", format: { fill: "#FEE2E2", font: { color: "#991B1B" } } });
  }
}

await fs.mkdir(previewDir, { recursive: true });
const workbook = Workbook.create();
const sheetInfo = [];

for (const [sheetName, fileName, tableName] of sheetFiles) {
  const csvText = (await fs.readFile(path.join(inputDir, fileName), "utf8")).replace(/^\uFEFF/, "");
  await workbook.fromCSV(csvText, { sheetName });
  const sheet = workbook.worksheets.getItem(sheetName);
  const firstLine = csvText.split(/\r?\n/, 1)[0];
  const columnCount = firstLine ? firstLine.split(",").length : 1;
  const rowCount = csvText.split(/\r?\n/).filter(Boolean).length;
  styleSheet(sheet, sheetName, tableName, rowCount, columnCount);
  sheetInfo.push({ sheetName, rowCount, columnCount });
}

for (const { sheetName } of sheetInfo) {
  const range = sheetName === "Summary" || sheetName === "Data Dictionary" || sheetName === "Feed Summary"
    ? "A1:M30"
    : "A1:AB14";
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(previewDir, `${sheetName.replaceAll(" ", "_").toLowerCase()}.png`), new Uint8Array(await preview.arrayBuffer()));
}

const check = await workbook.inspect({
  kind: "table",
  range: "Summary!A1:C20",
  include: "values,formulas",
  tableMaxRows: 20,
  tableMaxCols: 3,
});
console.log("summary_inspect=" + check.ndjson);
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log("formula_error_scan=" + errors.ndjson);

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
console.log("xlsx_output=" + outputPath);
console.log("sheet_info=" + JSON.stringify(sheetInfo));
