#property strict
#property description "One-shot XAUUSD historical candle backfill for research/backtesting"

input string HistoryUrl = "http://127.0.0.1/ingest/history";
input string ApiToken = "CHANGE_ME";
input int YearsBack = 5;
input int BatchBars = 250;
input bool ExportD1 = true;
input bool ExportM5 = true;
input bool ExportM1 = false;
input bool RemoveWhenDone = true;

bool running = false;

string JsonEscape(string s)
{
   StringReplace(s, "\\", "\\\\");
   StringReplace(s, "\"", "\\\"");
   return s;
}

string TimeframeName(int tf)
{
   if(tf == PERIOD_M1) return "M1";
   if(tf == PERIOD_M5) return "M5";
   if(tf == PERIOD_D1) return "D1";
   return IntegerToString(tf);
}

bool PostJson(string json)
{
   char payload[];
   char result[];
   string resultHeaders;
   string headers = "Content-Type: application/json\r\nAuthorization: Bearer " + ApiToken + "\r\n";
   StringToCharArray(json, payload, 0, WHOLE_ARRAY, CP_UTF8);
   if(ArraySize(payload) > 0) ArrayResize(payload, ArraySize(payload) - 1);
   ResetLastError();
   int status = WebRequest("POST", HistoryUrl, headers, 15000, payload, result, resultHeaders);
   if(status < 200 || status >= 300)
   {
      Print("History POST failed HTTP=", status, " error=", GetLastError());
      return false;
   }
   return true;
}

bool SendBatch(int tf, int newestShift, int oldestShift)
{
   string json = "{\"type\":\"history\",\"symbol\":\"" + JsonEscape(Symbol()) + "\",\"timeframe\":\"" + TimeframeName(tf) + "\",\"candles\":[";
   bool first = true;
   for(int shift = oldestShift; shift >= newestShift; shift--)
   {
      datetime t = iTime(Symbol(), tf, shift);
      if(t <= 0) continue;
      if(!first) json += ",";
      first = false;
      json += "{\"time\":" + IntegerToString((int)t);
      json += ",\"open\":" + DoubleToString(iOpen(Symbol(), tf, shift), Digits);
      json += ",\"high\":" + DoubleToString(iHigh(Symbol(), tf, shift), Digits);
      json += ",\"low\":" + DoubleToString(iLow(Symbol(), tf, shift), Digits);
      json += ",\"close\":" + DoubleToString(iClose(Symbol(), tf, shift), Digits);
      json += ",\"is_closed\":true}";
   }
   json += "]}";
   if(first) return true;
   return PostJson(json);
}

bool ExportTimeframe(int tf, datetime cutoff)
{
   int bars = iBars(Symbol(), tf);
   if(bars <= 1)
   {
      Print("No history loaded for ", TimeframeName(tf));
      return false;
   }

   int oldestEligible = 1;
   for(int shift = 1; shift < bars; shift++)
   {
      datetime t = iTime(Symbol(), tf, shift);
      if(t <= 0 || t < cutoff) break;
      oldestEligible = shift;
   }

   Print("Backfill ", TimeframeName(tf), ": ", oldestEligible, " closed bars available in requested window.");
   int batch = MathMax(25, BatchBars);
   for(int oldest = oldestEligible; oldest >= 1; oldest -= batch)
   {
      int newest = MathMax(1, oldest - batch + 1);
      if(!SendBatch(tf, newest, oldest)) return false;
      Sleep(150);
   }
   return true;
}

int OnInit()
{
   EventSetTimer(2);
   Print("History backfill EA ready for ", Symbol(), ". Load MT4 history first; export starts shortly.");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   if(running) return;
   running = true;
   EventKillTimer();

   datetime cutoff = TimeCurrent() - MathMax(1, YearsBack) * 365 * 24 * 60 * 60;
   bool ok = true;
   if(ExportD1) ok = ExportTimeframe(PERIOD_D1, cutoff) && ok;
   if(ExportM5) ok = ExportTimeframe(PERIOD_M5, cutoff) && ok;
   if(ExportM1) ok = ExportTimeframe(PERIOD_M1, cutoff) && ok;

   Print(ok ? "HISTORY BACKFILL COMPLETE" : "HISTORY BACKFILL FAILED - check Experts log and bridge health");
   if(ok && RemoveWhenDone) ExpertRemove();
}

void OnTick() {}
