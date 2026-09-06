#property strict
#property description "XAUUSD live market bridge for the XAUUSD research dashboard"

input string BridgeUrl = "http://127.0.0.1:8787/ingest/tick";
input string ApiToken = "CHANGE_ME";
input int SendIntervalMs = 1000;
input bool SendIndicators = true;
input int EmaFastPeriod = 20;
input int EmaSlowPeriod = 50;
input int RsiPeriod = 14;
input int AtrPeriod = 14;

ulong lastSendMs = 0;

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
   int status = WebRequest("POST", url, headers, 2000, payload, result, resultHeaders);
   if(status < 200 || status >= 300)
   {
      Print("Bridge POST failed. HTTP=", status, " error=", GetLastError());
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

int OnInit()
{
   EventSetMillisecondTimer(MathMax(250, SendIntervalMs));
   Print("XauusdBridgeEA started for ", Symbol(), ". Allow URL in MT4: ", BridgeUrl);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   PostJson(BridgeUrl, BuildTickJson());
}

void OnTick()
{
   // Timer-driven transmission keeps network work out of the tick path.
}
