#property copyright "OpenAI"
#property version   "2.00"
#property indicator_chart_window
#property indicator_buffers 4
#property indicator_plots   4

#property indicator_label1  "Buy setup"
#property indicator_type1   DRAW_ARROW
#property indicator_color1  clrLimeGreen
#property indicator_width1  2

#property indicator_label2  "Sell setup"
#property indicator_type2   DRAW_ARROW
#property indicator_color2  clrTomato
#property indicator_width2  2

#property indicator_label3  "EMA Fast"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrDodgerBlue
#property indicator_width3  1

#property indicator_label4  "EMA Slow"
#property indicator_type4   DRAW_LINE
#property indicator_color4  clrOrange
#property indicator_width4  2

input int                InpFastEmaPeriod       = 50;
input int                InpSlowEmaPeriod       = 200;
input ENUM_TIMEFRAMES    InpHigherTimeframe     = PERIOD_H4;
input int                InpRsiPeriod           = 14;
input int                InpAtrPeriod           = 14;
input int                InpAdxPeriod           = 14;
input int                InpBandsPeriod         = 20;
input double             InpBandsDeviation      = 2.0;
input int                InpSwingStrength       = 3;
input int                InpStructureLookback   = 150;
input int                InpPullbackLookback    = 3;
input int                InpVolumePeriod        = 20;
input double             InpRelativeVolumeMin   = 1.2;
input double             InpMinAdx              = 18.0;
input double             InpMinBandWidthPercent = 0.0;
input double             InpMaxBandWidthPercent = 0.0;
input double             InpPullbackAtrZone     = 0.35;
input int                InpMinSetupScore       = 70;
input double             InpStopAtrMultiplier   = 1.5;
input double             InpSwingStopBufferAtr  = 0.15;
input double             InpMaxStopAtr          = 3.0;
input double             InpTarget1RiskReward   = 1.0;
input double             InpTarget2RiskReward   = 2.0;
input bool               InpUseSessionFilter    = false;
input int                InpSessionStartHour    = 7;
input int                InpSessionEndHour      = 17;
input double             InpMaxSpreadPoints     = 0.0;
input bool               InpShowRiskLevels      = true;
input bool               InpEnableAlerts        = false;
input int                InpMaxBarsToCalculate  = 3000;

double BuyBuffer[];
double SellBuffer[];
double FastEmaBuffer[];
double SlowEmaBuffer[];

int FastEmaHandle = INVALID_HANDLE;
int SlowEmaHandle = INVALID_HANDLE;
int RsiHandle = INVALID_HANDLE;
int AtrHandle = INVALID_HANDLE;
int AdxHandle = INVALID_HANDLE;
int BandsHandle = INVALID_HANDLE;
int HigherFastEmaHandle = INVALID_HANDLE;
int HigherSlowEmaHandle = INVALID_HANDLE;

string ObjectPrefix;
datetime LastProcessedBar = 0;
bool HasInitializedAlerts = false;

int OnInit()
{
   if(InpFastEmaPeriod <= 0 || InpSlowEmaPeriod <= InpFastEmaPeriod ||
      InpRsiPeriod <= 0 || InpAtrPeriod <= 0 || InpAdxPeriod <= 0 ||
      InpBandsPeriod <= 0 || InpBandsDeviation <= 0.0 ||
      InpSwingStrength < 1 || InpStructureLookback < InpSwingStrength * 2 + 2 ||
      InpPullbackLookback < 1 || InpVolumePeriod < 1 ||
      InpRelativeVolumeMin <= 0.0 || InpMinAdx < 0.0 ||
      InpMinBandWidthPercent < 0.0 || InpMaxBandWidthPercent < 0.0 ||
      (InpMaxBandWidthPercent > 0.0 &&
       InpMinBandWidthPercent > InpMaxBandWidthPercent) ||
      InpPullbackAtrZone < 0.0 || InpMinSetupScore < 0 ||
      InpMinSetupScore > 100 || InpStopAtrMultiplier <= 0.0 ||
      InpSwingStopBufferAtr < 0.0 || InpMaxStopAtr <= 0.0 ||
      InpTarget1RiskReward <= 0.0 ||
      InpTarget2RiskReward <= InpTarget1RiskReward ||
      InpSessionStartHour < 0 || InpSessionStartHour > 23 ||
      InpSessionEndHour < 0 || InpSessionEndHour > 23 ||
      InpMaxSpreadPoints < 0.0 || InpMaxBarsToCalculate < 100)
   {
      return INIT_PARAMETERS_INCORRECT;
   }

   SetIndexBuffer(0, BuyBuffer, INDICATOR_DATA);
   SetIndexBuffer(1, SellBuffer, INDICATOR_DATA);
   SetIndexBuffer(2, FastEmaBuffer, INDICATOR_DATA);
   SetIndexBuffer(3, SlowEmaBuffer, INDICATOR_DATA);

   ArraySetAsSeries(BuyBuffer, true);
   ArraySetAsSeries(SellBuffer, true);
   ArraySetAsSeries(FastEmaBuffer, true);
   ArraySetAsSeries(SlowEmaBuffer, true);

   PlotIndexSetInteger(0, PLOT_ARROW, 233);
   PlotIndexSetInteger(1, PLOT_ARROW, 234);
   for(int plot = 0; plot < 4; plot++)
      PlotIndexSetDouble(plot, PLOT_EMPTY_VALUE, EMPTY_VALUE);

   FastEmaHandle = iMA(_Symbol, _Period, InpFastEmaPeriod, 0, MODE_EMA, PRICE_CLOSE);
   SlowEmaHandle = iMA(_Symbol, _Period, InpSlowEmaPeriod, 0, MODE_EMA, PRICE_CLOSE);
   RsiHandle = iRSI(_Symbol, _Period, InpRsiPeriod, PRICE_CLOSE);
   AtrHandle = iATR(_Symbol, _Period, InpAtrPeriod);
   AdxHandle = iADX(_Symbol, _Period, InpAdxPeriod);
   BandsHandle = iBands(_Symbol, _Period, InpBandsPeriod, 0,
                        InpBandsDeviation, PRICE_CLOSE);
   HigherFastEmaHandle = iMA(_Symbol, InpHigherTimeframe, InpFastEmaPeriod,
                             0, MODE_EMA, PRICE_CLOSE);
   HigherSlowEmaHandle = iMA(_Symbol, InpHigherTimeframe, InpSlowEmaPeriod,
                             0, MODE_EMA, PRICE_CLOSE);

   if(FastEmaHandle == INVALID_HANDLE || SlowEmaHandle == INVALID_HANDLE ||
      RsiHandle == INVALID_HANDLE || AtrHandle == INVALID_HANDLE ||
      AdxHandle == INVALID_HANDLE || BandsHandle == INVALID_HANDLE ||
      HigherFastEmaHandle == INVALID_HANDLE || HigherSlowEmaHandle == INVALID_HANDLE)
   {
      Print("Pro Regime-Structure: gagal membuat handle indikator. Error: ",
            GetLastError());
      return INIT_FAILED;
   }

   ObjectPrefix = StringFormat("ProRegimeStructure_%I64d_", ChartID());
   IndicatorSetString(INDICATOR_SHORTNAME, "Pro Regime-Structure Confluence");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   ReleaseHandle(FastEmaHandle);
   ReleaseHandle(SlowEmaHandle);
   ReleaseHandle(RsiHandle);
   ReleaseHandle(AtrHandle);
   ReleaseHandle(AdxHandle);
   ReleaseHandle(BandsHandle);
   ReleaseHandle(HigherFastEmaHandle);
   ReleaseHandle(HigherSlowEmaHandle);

   ObjectDelete(0, ObjectPrefix + "Entry");
   ObjectDelete(0, ObjectPrefix + "Stop");
   ObjectDelete(0, ObjectPrefix + "Target1");
   ObjectDelete(0, ObjectPrefix + "Target2");
   ObjectDelete(0, ObjectPrefix + "Panel");
}

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{
   if(rates_total < InpSlowEmaPeriod + InpStructureLookback +
                    InpSwingStrength * 2 + 5)
      return 0;

   ArraySetAsSeries(time, true);
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);
   ArraySetAsSeries(close, true);
   ArraySetAsSeries(tick_volume, true);
   ArraySetAsSeries(spread, true);

   double fastEma[];
   double slowEma[];
   double rsi[];
   double atr[];
   double adx[];
   double bandsMiddle[];
   double bandsUpper[];
   double bandsLower[];

   ArraySetAsSeries(fastEma, true);
   ArraySetAsSeries(slowEma, true);
   ArraySetAsSeries(rsi, true);
   ArraySetAsSeries(atr, true);
   ArraySetAsSeries(adx, true);
   ArraySetAsSeries(bandsMiddle, true);
   ArraySetAsSeries(bandsUpper, true);
   ArraySetAsSeries(bandsLower, true);

   if(CopyBuffer(FastEmaHandle, 0, 0, rates_total, fastEma) < rates_total ||
      CopyBuffer(SlowEmaHandle, 0, 0, rates_total, slowEma) < rates_total ||
      CopyBuffer(RsiHandle, 0, 0, rates_total, rsi) < rates_total ||
      CopyBuffer(AtrHandle, 0, 0, rates_total, atr) < rates_total ||
      CopyBuffer(AdxHandle, 0, 0, rates_total, adx) < rates_total ||
      CopyBuffer(BandsHandle, 0, 0, rates_total, bandsMiddle) < rates_total ||
      CopyBuffer(BandsHandle, 1, 0, rates_total, bandsUpper) < rates_total ||
      CopyBuffer(BandsHandle, 2, 0, rates_total, bandsLower) < rates_total)
   {
      return prev_calculated;
   }

   int higherBars = Bars(_Symbol, InpHigherTimeframe);
   if(higherBars < InpSlowEmaPeriod + 2)
      return prev_calculated;

   double higherFastEma[];
   double higherSlowEma[];
   ArraySetAsSeries(higherFastEma, true);
   ArraySetAsSeries(higherSlowEma, true);
   if(CopyBuffer(HigherFastEmaHandle, 0, 0, higherBars, higherFastEma) <
         InpSlowEmaPeriod + 2 ||
      CopyBuffer(HigherSlowEmaHandle, 0, 0, higherBars, higherSlowEma) <
         InpSlowEmaPeriod + 2)
   {
      return prev_calculated;
   }

   for(int i = rates_total - 1; i >= 0; i--)
   {
      BuyBuffer[i] = EMPTY_VALUE;
      SellBuffer[i] = EMPTY_VALUE;
      FastEmaBuffer[i] = fastEma[i];
      SlowEmaBuffer[i] = slowEma[i];
   }

   int oldestShift = (int)MathMin(rates_total - InpSwingStrength * 2 - 2,
                                  InpMaxBarsToCalculate);
   for(int i = oldestShift; i >= 1; i--)
   {
      bool localBull = IsLocalBullTrend(i, fastEma, slowEma);
      bool localBear = IsLocalBearTrend(i, fastEma, slowEma);
      bool higherBull = false;
      bool higherBear = false;
      if(!GetConfirmedHigherTrend(time[i], higherFastEma, higherSlowEma,
                                  higherBull, higherBear))
         continue;

      bool bullishStructure = false;
      bool bearishStructure = false;
      bool bullishBos = false;
      bool bearishBos = false;
      int latestHighShift = -1;
      int latestLowShift = -1;
      double latestHigh = 0.0;
      double latestLow = 0.0;
      EvaluateStructure(i, rates_total, high, low, close,
                        bullishStructure, bearishStructure,
                        bullishBos, bearishBos,
                        latestHighShift, latestHigh,
                        latestLowShift, latestLow);

      bool bullishPullback = HasBullishPullback(i, rates_total, low, close,
                                                fastEma, atr, rsi);
      bool bearishPullback = HasBearishPullback(i, rates_total, high, close,
                                                fastEma, atr, rsi);
      bool regimeValid = IsRegimeValid(i, adx, bandsMiddle, bandsUpper, bandsLower);
      bool sessionValid = IsSessionValid(time[i]);
      bool volumeConfirmed = IsRelativeVolumeConfirmed(i, rates_total, tick_volume);

      double buyStop = CalculateStop(true, i, rates_total, close, atr,
                                     latestLowShift, latestLow);
      double sellStop = CalculateStop(false, i, rates_total, close, atr,
                                      latestHighShift, latestHigh);
      bool buyRiskValid = IsRiskValid(close[i], buyStop, atr[i]);
      bool sellRiskValid = IsRiskValid(close[i], sellStop, atr[i]);

      int buyScore = CalculateScore(localBull && higherBull,
                                    bullishStructure || bullishBos,
                                    bullishPullback, volumeConfirmed, regimeValid);
      int sellScore = CalculateScore(localBear && higherBear,
                                     bearishStructure || bearishBos,
                                     bearishPullback, volumeConfirmed, regimeValid);

      bool buySignal = localBull && higherBull &&
                       (bullishStructure || bullishBos) &&
                       bullishPullback && regimeValid && sessionValid &&
                       buyRiskValid && buyScore >= InpMinSetupScore;
      bool sellSignal = localBear && higherBear &&
                        (bearishStructure || bearishBos) &&
                        bearishPullback && regimeValid && sessionValid &&
                        sellRiskValid && sellScore >= InpMinSetupScore;

      if(buySignal)
         BuyBuffer[i] = low[i] - atr[i] * 0.15;
      else if(sellSignal)
         SellBuffer[i] = high[i] + atr[i] * 0.15;
   }

   UpdateDashboardAndLevels(rates_total, time, high, low, close, tick_volume,
                            spread, fastEma, slowEma, rsi, atr, adx,
                            bandsMiddle, bandsUpper, bandsLower,
                            higherFastEma, higherSlowEma);
   return rates_total;
}

void ReleaseHandle(const int handle)
{
   if(handle != INVALID_HANDLE)
      IndicatorRelease(handle);
}

bool IsLocalBullTrend(const int shift,
                      const double &fastEma[],
                      const double &slowEma[])
{
   return fastEma[shift] > slowEma[shift] &&
          fastEma[shift] >= fastEma[shift + 1];
}

bool IsLocalBearTrend(const int shift,
                      const double &fastEma[],
                      const double &slowEma[])
{
   return fastEma[shift] < slowEma[shift] &&
          fastEma[shift] <= fastEma[shift + 1];
}

bool GetConfirmedHigherTrend(const datetime barTime,
                             const double &higherFastEma[],
                             const double &higherSlowEma[],
                             bool &bullish,
                             bool &bearish)
{
   bullish = false;
   bearish = false;
   int mappedShift = iBarShift(_Symbol, InpHigherTimeframe, barTime, false);
   int confirmedShift = mappedShift + 1;
   if(mappedShift < 0 || confirmedShift + 1 >= ArraySize(higherFastEma) ||
      confirmedShift + 1 >= ArraySize(higherSlowEma))
      return false;

   bullish = higherFastEma[confirmedShift] > higherSlowEma[confirmedShift] &&
             higherFastEma[confirmedShift] >= higherFastEma[confirmedShift + 1];
   bearish = higherFastEma[confirmedShift] < higherSlowEma[confirmedShift] &&
             higherFastEma[confirmedShift] <= higherFastEma[confirmedShift + 1];
   return true;
}

void EvaluateStructure(const int shift,
                       const int ratesTotal,
                       const double &high[],
                       const double &low[],
                       const double &close[],
                       bool &bullishStructure,
                       bool &bearishStructure,
                       bool &bullishBos,
                       bool &bearishBos,
                       int &latestHighShift,
                       double &latestHigh,
                       int &latestLowShift,
                       double &latestLow)
{
   bullishStructure = false;
   bearishStructure = false;
   bullishBos = false;
   bearishBos = false;
   latestHighShift = -1;
   latestLowShift = -1;

   int oldestCandidate = (int)MathMin(ratesTotal - InpSwingStrength - 1,
                                      shift + InpStructureLookback);
   int highShifts[2] = {-1, -1};
   int lowShifts[2] = {-1, -1};

   for(int candidate = shift + InpSwingStrength + 1;
       candidate <= oldestCandidate; candidate++)
   {
      if(highShifts[1] < 0 && IsPivotHigh(candidate, ratesTotal, high))
      {
         highShifts[1] = highShifts[0];
         highShifts[0] = candidate;
      }
      if(lowShifts[1] < 0 && IsPivotLow(candidate, ratesTotal, low))
      {
         lowShifts[1] = lowShifts[0];
         lowShifts[0] = candidate;
      }
      if(highShifts[1] >= 0 && lowShifts[1] >= 0)
         break;
   }

   latestHighShift = highShifts[0];
   latestLowShift = lowShifts[0];
   if(latestHighShift >= 0)
      latestHigh = high[latestHighShift];
   if(latestLowShift >= 0)
      latestLow = low[latestLowShift];

   bullishBos = latestHighShift >= 0 && close[shift] > latestHigh;
   bearishBos = latestLowShift >= 0 && close[shift] < latestLow;

   if(highShifts[1] >= 0 && lowShifts[1] >= 0)
   {
      bullishStructure = high[highShifts[0]] > high[highShifts[1]] &&
                         low[lowShifts[0]] > low[lowShifts[1]];
      bearishStructure = high[highShifts[0]] < high[highShifts[1]] &&
                         low[lowShifts[0]] < low[lowShifts[1]];
   }
}

bool IsPivotHigh(const int candidate,
                 const int ratesTotal,
                 const double &high[])
{
   if(candidate - InpSwingStrength < 1 ||
      candidate + InpSwingStrength >= ratesTotal)
      return false;

   for(int offset = 1; offset <= InpSwingStrength; offset++)
   {
      if(high[candidate] <= high[candidate - offset] ||
         high[candidate] <= high[candidate + offset])
         return false;
   }
   return true;
}

bool IsPivotLow(const int candidate,
                const int ratesTotal,
                const double &low[])
{
   if(candidate - InpSwingStrength < 1 ||
      candidate + InpSwingStrength >= ratesTotal)
      return false;

   for(int offset = 1; offset <= InpSwingStrength; offset++)
   {
      if(low[candidate] >= low[candidate - offset] ||
         low[candidate] >= low[candidate + offset])
         return false;
   }
   return true;
}

bool HasBullishPullback(const int shift,
                        const int ratesTotal,
                        const double &low[],
                        const double &close[],
                        const double &fastEma[],
                        const double &atr[],
                        const double &rsi[])
{
   if(rsi[shift] <= 50.0 || rsi[shift + 1] > 50.0 ||
      close[shift] <= fastEma[shift] || atr[shift] <= 0.0)
      return false;

   int endShift = (int)MathMin(shift + InpPullbackLookback - 1,
                               ratesTotal - 1);
   for(int i = shift; i <= endShift; i++)
   {
      if(atr[i] > 0.0 &&
         low[i] <= fastEma[i] + atr[i] * InpPullbackAtrZone)
         return true;
   }
   return false;
}

bool HasBearishPullback(const int shift,
                        const int ratesTotal,
                        const double &high[],
                        const double &close[],
                        const double &fastEma[],
                        const double &atr[],
                        const double &rsi[])
{
   if(rsi[shift] >= 50.0 || rsi[shift + 1] < 50.0 ||
      close[shift] >= fastEma[shift] || atr[shift] <= 0.0)
      return false;

   int endShift = (int)MathMin(shift + InpPullbackLookback - 1,
                               ratesTotal - 1);
   for(int i = shift; i <= endShift; i++)
   {
      if(atr[i] > 0.0 &&
         high[i] >= fastEma[i] - atr[i] * InpPullbackAtrZone)
         return true;
   }
   return false;
}

bool IsRegimeValid(const int shift,
                   const double &adx[],
                   const double &bandsMiddle[],
                   const double &bandsUpper[],
                   const double &bandsLower[])
{
   if(adx[shift] < InpMinAdx || bandsMiddle[shift] == 0.0)
      return false;

   double bandWidthPercent =
      (bandsUpper[shift] - bandsLower[shift]) / bandsMiddle[shift] * 100.0;
   if(InpMinBandWidthPercent > 0.0 &&
      bandWidthPercent < InpMinBandWidthPercent)
      return false;
   if(InpMaxBandWidthPercent > 0.0 &&
      bandWidthPercent > InpMaxBandWidthPercent)
      return false;
   return true;
}

bool IsSessionValid(const datetime barTime)
{
   if(!InpUseSessionFilter)
      return true;

   MqlDateTime dateParts;
   TimeToStruct(barTime, dateParts);
   if(InpSessionStartHour == InpSessionEndHour)
      return true;
   if(InpSessionStartHour < InpSessionEndHour)
      return dateParts.hour >= InpSessionStartHour &&
             dateParts.hour < InpSessionEndHour;
   return dateParts.hour >= InpSessionStartHour ||
          dateParts.hour < InpSessionEndHour;
}

bool IsRelativeVolumeConfirmed(const int shift,
                               const int ratesTotal,
                               const long &tickVolume[])
{
   if(shift + InpVolumePeriod >= ratesTotal)
      return false;

   double averageVolume = 0.0;
   for(int i = shift + 1; i <= shift + InpVolumePeriod; i++)
      averageVolume += (double)tickVolume[i];
   averageVolume /= InpVolumePeriod;
   if(averageVolume <= 0.0)
      return false;

   return (double)tickVolume[shift] / averageVolume >= InpRelativeVolumeMin;
}

int CalculateScore(const bool trendAligned,
                   const bool structureAligned,
                   const bool pullbackConfirmed,
                   const bool volumeConfirmed,
                   const bool regimeValid)
{
   int score = 0;
   if(trendAligned)
      score += 30;
   if(structureAligned)
      score += 25;
   if(pullbackConfirmed)
      score += 20;
   if(volumeConfirmed)
      score += 15;
   if(regimeValid)
      score += 10;
   return score;
}

double CalculateStop(const bool isBuy,
                     const int shift,
                     const int ratesTotal,
                     const double &close[],
                     const double &atr[],
                     const int swingShift,
                     const double swingPrice)
{
   double atrStop = isBuy
                    ? close[shift] - atr[shift] * InpStopAtrMultiplier
                    : close[shift] + atr[shift] * InpStopAtrMultiplier;
   if(swingShift < 0 || atr[shift] <= 0.0)
      return atrStop;

   double structuralStop = isBuy
                           ? swingPrice - atr[shift] * InpSwingStopBufferAtr
                           : swingPrice + atr[shift] * InpSwingStopBufferAtr;
   return isBuy ? MathMin(atrStop, structuralStop)
                : MathMax(atrStop, structuralStop);
}

bool IsRiskValid(const double entry, const double stop, const double atr)
{
   if(atr <= 0.0)
      return false;
   double riskInAtr = MathAbs(entry - stop) / atr;
   return riskInAtr > 0.0 && riskInAtr <= InpMaxStopAtr;
}

void UpdateDashboardAndLevels(const int ratesTotal,
                              const datetime &time[],
                              const double &high[],
                              const double &low[],
                              const double &close[],
                              const long &tickVolume[],
                              const int &spread[],
                              const double &fastEma[],
                              const double &slowEma[],
                              const double &rsi[],
                              const double &atr[],
                              const double &adx[],
                              const double &bandsMiddle[],
                              const double &bandsUpper[],
                              const double &bandsLower[],
                              const double &higherFastEma[],
                              const double &higherSlowEma[])
{
   const int shift = 1;
   bool localBull = IsLocalBullTrend(shift, fastEma, slowEma);
   bool localBear = IsLocalBearTrend(shift, fastEma, slowEma);
   bool higherBull = false;
   bool higherBear = false;
   GetConfirmedHigherTrend(time[shift], higherFastEma, higherSlowEma,
                           higherBull, higherBear);

   bool bullishStructure = false;
   bool bearishStructure = false;
   bool bullishBos = false;
   bool bearishBos = false;
   int latestHighShift = -1;
   int latestLowShift = -1;
   double latestHigh = 0.0;
   double latestLow = 0.0;
   EvaluateStructure(shift, ratesTotal, high, low, close,
                     bullishStructure, bearishStructure,
                     bullishBos, bearishBos,
                     latestHighShift, latestHigh,
                     latestLowShift, latestLow);

   bool bullishPullback = HasBullishPullback(shift, ratesTotal, low, close,
                                             fastEma, atr, rsi);
   bool bearishPullback = HasBearishPullback(shift, ratesTotal, high, close,
                                             fastEma, atr, rsi);
   bool regimeValid = IsRegimeValid(shift, adx, bandsMiddle, bandsUpper, bandsLower);
   bool sessionValid = IsSessionValid(time[shift]);
   bool volumeConfirmed = IsRelativeVolumeConfirmed(shift, ratesTotal, tickVolume);

   double buyStop = CalculateStop(true, shift, ratesTotal, close, atr,
                                  latestLowShift, latestLow);
   double sellStop = CalculateStop(false, shift, ratesTotal, close, atr,
                                   latestHighShift, latestHigh);
   bool buyRiskValid = IsRiskValid(close[shift], buyStop, atr[shift]);
   bool sellRiskValid = IsRiskValid(close[shift], sellStop, atr[shift]);

   int buyScore = CalculateScore(localBull && higherBull,
                                 bullishStructure || bullishBos,
                                 bullishPullback, volumeConfirmed, regimeValid);
   int sellScore = CalculateScore(localBear && higherBear,
                                  bearishStructure || bearishBos,
                                  bearishPullback, volumeConfirmed, regimeValid);
   bool buySignal = localBull && higherBull &&
                    (bullishStructure || bullishBos) &&
                    bullishPullback && regimeValid && sessionValid &&
                    buyRiskValid && buyScore >= InpMinSetupScore;
   bool sellSignal = localBear && higherBear &&
                     (bearishStructure || bearishBos) &&
                     bearishPullback && regimeValid && sessionValid &&
                     sellRiskValid && sellScore >= InpMinSetupScore;

   double currentSpread = (double)spread[0];
   bool spreadValid = InpMaxSpreadPoints <= 0.0 ||
                      currentSpread <= InpMaxSpreadPoints;
   string trendText = localBull && higherBull ? "BULLISH MTF" :
                      localBear && higherBear ? "BEARISH MTF" : "MIXED / NO TRADE";
   string structureText = bullishBos ? "BOS bullish" :
                          bearishBos ? "BOS bearish" :
                          bullishStructure ? "HH/HL" :
                          bearishStructure ? "LH/LL" : "belum jelas";
   int displayScore = localBull && higherBull ? buyScore :
                      localBear && higherBear ? sellScore :
                      (int)MathMax(buyScore, sellScore);
   string setupText = buySignal && spreadValid ? "BUY" :
                      sellSignal && spreadValid ? "SELL" :
                      !regimeValid ? "NO TRADE - regime" :
                      !sessionValid ? "NO TRADE - sesi" :
                      !spreadValid ? "NO TRADE - spread" :
                      "NO TRADE - syarat belum lengkap";

   double bandWidthPercent = bandsMiddle[shift] != 0.0
                             ? (bandsUpper[shift] - bandsLower[shift]) /
                               bandsMiddle[shift] * 100.0
                             : 0.0;
   string panelText = StringFormat(
      "PRO REGIME-STRUCTURE | %s: %s\nSkor konfluensi: %d/100 (bukan probabilitas menang) | Struktur: %s\nADX: %.1f | BB width: %.2f%% | RSI: %.1f | Rel. tick volume: %s\nSpread: %.1f points | ATR: %s | Sesi broker: %s\nEntry/SL/TP hanya referensi; validasi risiko dan biaya transaksi.",
      EnumToString(InpHigherTimeframe), trendText, displayScore, structureText,
      adx[shift], bandWidthPercent, rsi[shift],
      volumeConfirmed ? "tinggi" : "normal",
      currentSpread, DoubleToString(atr[shift], _Digits),
      sessionValid ? "aktif" : "di luar filter");
   color panelColor = buySignal && spreadValid ? clrLimeGreen :
                      sellSignal && spreadValid ? clrTomato : clrSilver;
   SetPanel(panelText + "\nStatus: " + setupText, panelColor);

   if(InpShowRiskLevels && spreadValid && (buySignal || sellSignal))
   {
      bool isBuy = buySignal;
      double entry = close[shift];
      double stop = isBuy ? buyStop : sellStop;
      double risk = MathAbs(entry - stop);
      double target1 = isBuy
                       ? entry + risk * InpTarget1RiskReward
                       : entry - risk * InpTarget1RiskReward;
      double target2 = isBuy
                       ? entry + risk * InpTarget2RiskReward
                       : entry - risk * InpTarget2RiskReward;

      SetHorizontalLine(ObjectPrefix + "Entry", entry, clrDodgerBlue, STYLE_DOT);
      SetHorizontalLine(ObjectPrefix + "Stop", stop, clrTomato, STYLE_DASH);
      SetHorizontalLine(ObjectPrefix + "Target1", target1, clrGold, STYLE_DASH);
      SetHorizontalLine(ObjectPrefix + "Target2", target2, clrLimeGreen, STYLE_DASH);
   }
   else
   {
      ObjectDelete(0, ObjectPrefix + "Entry");
      ObjectDelete(0, ObjectPrefix + "Stop");
      ObjectDelete(0, ObjectPrefix + "Target1");
      ObjectDelete(0, ObjectPrefix + "Target2");
   }

   if(!HasInitializedAlerts)
   {
      LastProcessedBar = time[shift];
      HasInitializedAlerts = true;
   }
   else if(time[shift] != LastProcessedBar)
   {
      LastProcessedBar = time[shift];
      if(InpEnableAlerts && spreadValid)
      {
         if(buySignal)
            Alert(_Symbol, " ", EnumToString(_Period),
                  ": BUY setup, skor ", buyScore, "/100 pada candle tertutup");
         else if(sellSignal)
            Alert(_Symbol, " ", EnumToString(_Period),
                  ": SELL setup, skor ", sellScore, "/100 pada candle tertutup");
      }
   }
}

void SetHorizontalLine(const string name,
                       const double price,
                       const color lineColor,
                       const ENUM_LINE_STYLE style)
{
   if(ObjectFind(0, name) < 0)
   {
      if(!ObjectCreate(0, name, OBJ_HLINE, 0, 0, price))
      {
         Print("Pro Regime-Structure: gagal membuat garis ", name,
               ". Error: ", GetLastError());
         return;
      }
   }

   ObjectSetDouble(0, name, OBJPROP_PRICE, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, lineColor);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 1);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
}

void SetPanel(const string text, const color textColor)
{
   string name = ObjectPrefix + "Panel";
   if(ObjectFind(0, name) < 0)
   {
      if(!ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0))
      {
         Print("Pro Regime-Structure: gagal membuat panel. Error: ",
               GetLastError());
         return;
      }
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 10);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 18);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 9);
      ObjectSetString(0, name, OBJPROP_FONT, "Arial");
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   }

   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, textColor);
}
