#property strict
#property description "XAUUSD live market bridge for the XAUUSD research dashboard"

input string BridgeUrl = "http://127.0.0.1/ingest/tick";
input string CandlesUrl = "http://127.0.0.1/ingest/candles";
input string ApiToken = "CHANGE_ME";
input int SendIntervalMs = 1000;
input int CandleSyncIntervalSec = 30;
input int CandleBarsPerTimeframe = 120;
input bool SendIndicators = true;
input int EmaFastPeriod = 20;
input int EmaSlowPeriod = 50;
input int RsiPeriod = 14;
input int AtrPeriod = 14;

ulong lastCandleSyncMs = 0;

string JsonEscape(string s)
{
   StringReplace(s, "\\", "\\\\");
   StringReplace(s, "\"", "\\\"");
   return s;
}

bool PostJson(string url, string json)
{
   char payload[];
   char result[];
   string resultHeaders;
   string headers = "Content-Type: application/json\r\nAuthorization: Bearer " + ApiToken + "\r\n";

   StringToCharArray(json, payload, 0, WHOLE_ARRAY, CP_UTF8);
   if(ArraySize(payload) > 0)
      ArrayResize(payload, ArraySize(payload) - 1);

   ResetLastError();
   int status = WebRequest("POST", url, headers, 5000, payload, result, resultHeaders);
   if(status < 200 || status >= 300)
   {
      Print("Bridge POST failed. URL=", url, " HTTP=", status, " error=", GetLastError());
      return false;
   }
   return true;
}

string TimeframeName(int tf)
{
   if(tf == PERIOD_M1) return "M1";
   if(tf == PERIOD_M5) return "M5";
   if(tf == PERIOD_M15) return "M15";
   if(tf == PERIOD_M30) return "M30";
   if(tf == PERIOD_H1) return "H1";
   if(tf == PERIOD_H4) return "H4";
   if(tf == PERIOD_D1) return "D1";
   return IntegerToString(tf);
}

string BuildTickJson()
{
   RefreshRates();

   double bid = MarketInfo(Symbol(), MODE_BID);
   double ask = MarketInfo(Symbol(), MODE_ASK);
   double spreadPoints = MarketInfo(Symbol(), MODE_SPREAD);

   double m1Open = iOpen(Symbol(), PERIOD_M1, 0);
   double m1High = iHigh(Symbol(), PERIOD_M1, 0);
   double m1Low = iLow(Symbol(), PERIOD_M1, 0);
   double m1Close = iClose(Symbol(), PERIOD_M1, 0);
   datetime m1Time = iTime(Symbol(), PERIOD_M1, 0);

   string json = "{";
   json += "\"type\":\"tick\",";
   json += "\"symbol\":\"" + JsonEscape(Symbol()) + "\",";
   json += "\"server_time\":" + IntegerToString((int)TimeCurrent()) + ",";
   json += "\"digits\":" + IntegerToString(Digits) + ",";
   json += "\"bid\":" + DoubleToString(bid, Digits) + ",";
   json += "\"ask\":" + DoubleToString(ask, Digits) + ",";
   json += "\"spread_points\":" + DoubleToString(spreadPoints, 1) + ",";
   json += "\"m1\":{";
   json += "\"time\":" + IntegerToString((int)m1Time) + ",";
   json += "\"open\":" + DoubleToString(m1Open, Digits) + ",";
   json += "\"high\":" + DoubleToString(m1High, Digits) + ",";
   json += "\"low\":" + DoubleToString(m1Low, Digits) + ",";
   json += "\"close\":" + DoubleToString(m1Close, Digits);
   json += "}";

   if(SendIndicators)
   {
      double emaFast = iMA(Symbol(), PERIOD_M5, EmaFastPeriod, 0, MODE_EMA, PRICE_CLOSE, 0);
      double emaSlow = iMA(Symbol(), PERIOD_M5, EmaSlowPeriod, 0, MODE_EMA, PRICE_CLOSE, 0);
      double rsi = iRSI(Symbol(), PERIOD_M5, RsiPeriod, PRICE_CLOSE, 0);
      double atr = iATR(Symbol(), PERIOD_M5, AtrPeriod, 0);

      json += ",\"indicators\":{";
      json += "\"ema_fast_m5\":" + DoubleToString(emaFast, Digits) + ",";
      json += "\"ema_slow_m5\":" + DoubleToString(emaSlow, Digits) + ",";
      json += "\"rsi_m5\":" + DoubleToString(rsi, 2) + ",";
      json += "\"atr_m5\":" + DoubleToString(atr, Digits);
      json += "}";
   }

   json += "}";
   return json;
}

void AppendTimeframeCandles(string &json, int tf, bool &first)
{
   int available = iBars(Symbol(), tf);
   int count = MathMin(CandleBarsPerTimeframe, available);
   if(count <= 0) return;

   for(int shift = count - 1; shift >= 0; shift--)
   {
      datetime barTime = iTime(Symbol(), tf, shift);
      if(barTime <= 0) continue;

      double o = iOpen(Symbol(), tf, shift);
      double h = iHigh(Symbol(), tf, shift);
      double l = iLow(Symbol(), tf, shift);
      double c = iClose(Symbol(), tf, shift);

      if(!first) json += ",";
      first = false;

      json += "{";
      json += "\"timeframe\":\"" + TimeframeName(tf) + "\",";
      json += "\"time\":" + IntegerToString((int)barTime) + ",";
      json += "\"open\":" + DoubleToString(o, Digits) + ",";
      json += "\"high\":" + DoubleToString(h, Digits) + ",";
      json += "\"low\":" + DoubleToString(l, Digits) + ",";
      json += "\"close\":" + DoubleToString(c, Digits) + ",";
      json += "\"is_closed\":" + (shift > 0 ? "true" : "false");
      json += "}";
   }
}

string BuildCandlesJson()
{
   string json = "{";
   json += "\"type\":\"candles\",";
   json += "\"symbol\":\"" + JsonEscape(Symbol()) + "\",";
   json += "\"server_time\":" + IntegerToString((int)TimeCurrent()) + ",";
   json += "\"candles\":[";

   bool first = true;
   AppendTimeframeCandles(json, PERIOD_M1, first);
   AppendTimeframeCandles(json, PERIOD_M5, first);
   AppendTimeframeCandles(json, PERIOD_M15, first);
   AppendTimeframeCandles(json, PERIOD_M30, first);
   AppendTimeframeCandles(json, PERIOD_H1, first);
   AppendTimeframeCandles(json, PERIOD_H4, first);
   AppendTimeframeCandles(json, PERIOD_D1, first);

   json += "]}";
   return json;
}

int OnInit()
{
   EventSetMillisecondTimer(MathMax(250, SendIntervalMs));
   Print("XauusdBridgeEA started for ", Symbol(), ". Tick URL: ", BridgeUrl, " Candle URL: ", CandlesUrl);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   PostJson(BridgeUrl, BuildTickJson());

   ulong nowMs = GetTickCount();
   ulong intervalMs = (ulong)MathMax(5, CandleSyncIntervalSec) * 1000;
   if(lastCandleSyncMs == 0 || nowMs - lastCandleSyncMs >= intervalMs)
   {
      if(PostJson(CandlesUrl, BuildCandlesJson()))
         lastCandleSyncMs = nowMs;
   }
}

void OnTick()
{
   // Timer-driven transmission keeps network work out of the tick path.
}
