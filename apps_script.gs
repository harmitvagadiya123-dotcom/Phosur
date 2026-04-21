// ============================================================
//  CONFIGURATION
// ============================================================
var BUYING_INTENT_URL   = "https://phosur.onrender.com/webhook/buying-intent";
var WATCHED_SHEET_LEADS = "Buying_intent_Linkedin"; // FIXED: Lowercase 'intent' to match sheet tab

/**
 * INSTALLATION: Run this once manually from the editor.
 */
function installTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    ScriptApp.deleteTrigger(triggers[i]);
  }

  ScriptApp.newTrigger("onSheetEdit")
    .forSpreadsheet(SpreadsheetApp.getActive())
    .onEdit()
    .create();

  SpreadsheetApp.getUi().alert("Done! Trigger installed for: " + WATCHED_SHEET_LEADS);
}

/**
 * MASTER HANDLER
 */
function onSheetEdit(e) {
  var sheet = e.range.getSheet();
  var sheetName = sheet.getName();

  if (sheetName === WATCHED_SHEET_LEADS) {
    handleBuyingIntentEdit(e);
  }
}

/**
 * PROCESS EDIT: Column H = "High"
 */
function handleBuyingIntentEdit(e) {
  var sheet = e.range.getSheet();
  var row   = e.range.getRow();
  var col   = e.range.getColumn();

  if (row < 2) return;
  if (col !== 8) return; // Column H

  var newValue = e.value ? e.value.toString().trim().toLowerCase() : "";
  if (newValue !== "high") return;

  processRow(sheet, row);
}

/**
 * SEND DATA TO RENDER
 */
function processRow(sheet, row) {
  var statusSent   = sheet.getRange(row, 9).getValue(); // Column I
  var buyingIntent = sheet.getRange(row, 8).getValue(); // Column H

  // 1. Skip if already processed
  if (statusSent === "Done" || statusSent === "Processing") {
    Logger.log("Row " + row + " skipped (already processed).");
    return;
  }

  // 2. Prepare payload
  var data = {
    row_number:           row,
    SNO:                  sheet.getRange(row, 1).getValue(),
    DATE:                 sheet.getRange(row, 2).getValue().toString(),
    NAME:                 sheet.getRange(row, 3).getValue(),
    COUNTRY:              sheet.getRange(row, 4).getValue(),
    DESIGNATIONORCOMPANY: sheet.getRange(row, 5).getValue(),
    LINKEDIN:             sheet.getRange(row, 6).getValue(),
    ConversationHistory:  sheet.getRange(row, 7).getValue(),
    BuyingIntent:         buyingIntent,
  };

  if (!data.NAME) {
    Logger.log("Row " + row + " skipped (no Name).");
    return;
  }

  // 3. Send POST request
  var options = {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(data),
    muteHttpExceptions: true
  };

  try {
    sheet.getRange(row, 9).setValue("Processing...");
    var response = UrlFetchApp.fetch(BUYING_INTENT_URL, options);
    var result   = JSON.parse(response.getContentText());

    if (response.getResponseCode() == 200) {
      sheet.getRange(row, 9).setValue("Done");
      Logger.log("✅ Success: " + result.message);
    } else {
      sheet.getRange(row, 9).setValue("Error");
      Logger.log("❌ Partial Error: " + (result.error || result.message));
    }
  } catch (err) {
    Logger.log("❌ Request Failed: " + err.message);
    sheet.getRange(row, 9).setValue("Failed");
  }
}
