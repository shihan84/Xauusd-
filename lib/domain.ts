export type AccessTier = 'PUBLIC' | 'MEMBER' | 'PREMIUM' | 'OPERATOR' | 'ADMIN';

export type MarketRegime =
  | 'NORMAL'
  | 'TRENDING'
  | 'RANGING'
  | 'HIGH_VOLATILITY'
  | 'LOW_VOLATILITY'
  | 'PRE_NEWS'
  | 'NEWS_LIVE'
  | 'POST_NEWS'
  | 'RECOVERY_HEDGE';

export type SetupState =
  | 'WATCH'
  | 'FORMING'
  | 'READY'
  | 'ARMED'
  | 'EXECUTED'
  | 'MANAGED'
  | 'CLOSED'
  | 'INVALIDATED';

export type SetupGrade = 'A+' | 'A' | 'B' | 'WATCH';
export type Direction = 'BUY' | 'SELL';
export type GatewayClass = 'HARD' | 'WEIGHTED' | 'VETO';
export type GatewayResult = 'PASS' | 'FAIL' | 'NEUTRAL' | 'BLOCKED' | 'PENDING';

export type InteractionType =
  | 'APPROACH'
  | 'TOUCH'
  | 'REJECTION'
  | 'CROSS'
  | 'CONFIRMED_CROSS'
  | 'FAILED_CROSS';

export type ExecutionMode = 'SHADOW' | 'APPROVAL_REQUIRED' | 'AUTO' | 'PAUSED';

export type SessionId = 'SYDNEY' | 'TOKYO' | 'LONDON' | 'NEW_YORK' | 'LONDON_NEW_YORK_OVERLAP';
export type SessionStatus = 'OPEN' | 'CLOSED' | 'OPENING_SOON';

export interface MarketTick {
  symbol: string;
  bid: number;
  ask: number;
  spread: number;
  timestamp: string;
  source: 'MT4' | 'DEMO';
}

export interface Candle {
  symbol: string;
  timeframe: string;
  openTime: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface VcprRecord {
  id: string;
  tradingDate: string;
  pivot: number;
  cprLow: number;
  cprHigh: number;
  virginOnDay: true;
  laterTouched: boolean;
  firstLaterTouch?: string;
  daysUntilFirstTouch?: number;
}

export interface SessionSnapshot {
  id: SessionId;
  status: SessionStatus;
  timezone: string;
  localOpenTime: string;
  localCloseTime: string;
  openPrice?: number;
  high?: number;
  low?: number;
  range?: number;
  nextTransitionAt?: string;
}

export interface IndicatorValue {
  id: string;
  label: string;
  timeframe: string;
  value?: number;
  values?: Record<string, number | string | boolean | null>;
  timestamp: string;
  source: 'ENGINE' | 'MT4_CUSTOM';
}

export interface GatewayEvaluation {
  id: string;
  strategyVersion: string;
  class: GatewayClass;
  result: GatewayResult;
  weight?: number;
  internalName: string;
  premiumLabel?: string;
  publicLabel?: string;
  reason?: string;
  evaluatedAt: string;
}

export interface PublicGatewaySummary {
  passed: number;
  total: number;
  mandatoryPassed: number;
  mandatoryTotal: number;
  vetoBlocked: boolean;
  setupStrength?: number;
}

export interface TradeTarget {
  id: 'TP1' | 'TP2' | 'TP3';
  price: number;
  allocationPct?: number;
  riskReward?: number;
  hitAt?: string;
}

export interface TradePlan {
  callId: string;
  strategyVersion: string;
  symbol: string;
  timeframe: string;
  direction: Direction;
  state: SetupState;
  grade: SetupGrade;
  createdAt: string;
  publishedAt?: string;
  entryLow: number;
  entryHigh: number;
  initialStopLoss: number;
  targets: TradeTarget[];
  invalidationText: string;
  publicGatewaySummary: PublicGatewaySummary;
  gatewayEvaluations: GatewayEvaluation[];
  marketRegime: MarketRegime;
  session?: SessionId;
  theoreticalRiskR?: number;
}

export type TradeEventType =
  | 'PUBLISHED'
  | 'ENTRY_FILLED'
  | 'TP1_HIT'
  | 'TP2_HIT'
  | 'TP3_HIT'
  | 'SL_MOVED_TO_BE'
  | 'PARTIAL_CLOSE'
  | 'TRAILING_UPDATE'
  | 'INVALIDATED'
  | 'STOPPED'
  | 'MANUAL_CLOSE'
  | 'CLOSED';

export interface TradeEvent {
  id: string;
  callId: string;
  type: TradeEventType;
  timestamp: string;
  price?: number;
  quantity?: number;
  realizedPnl?: number;
  realizedR?: number;
  note?: string;
}

export interface DemoAccountSnapshot {
  accountId: string;
  balance: number;
  equity: number;
  margin: number;
  freeMargin: number;
  marginLevelPct: number;
  floatingPnl: number;
  timestamp: string;
  demo: true;
}

export interface ExposureSnapshot {
  buyLots: number;
  sellLots: number;
  netLots: number;
  lockedLots: number;
  basketBreakeven?: number;
  floatingPnl: number;
  equityDrawdownPct: number;
  marginLevelPct: number;
  timestamp: string;
}

export type RecoveryState =
  | 'NORMAL'
  | 'DRAWDOWN'
  | 'HEDGE_LOCK'
  | 'WAITING'
  | 'RECOVERY_READY'
  | 'PARTIAL_UNHEDGE'
  | 'RECOVERY'
  | 'PROFIT_LOCK';

export interface RecoverySnapshot {
  state: RecoveryState;
  exposure: ExposureSnapshot;
  gatewaySummary: PublicGatewaySummary;
  requiredRecoveryAmount?: number;
  calculatedAddLots?: number;
  calculatedReleaseLots?: number;
  updatedAt: string;
}

export interface PerformanceSnapshot {
  period: 'TODAY' | 'WEEK' | 'MONTH' | 'ALL';
  completedCalls: number;
  wins: number;
  losses: number;
  breakeven: number;
  winRatePct?: number;
  tp1HitRatePct?: number;
  tp2HitRatePct?: number;
  tp3HitRatePct?: number;
  netPoints?: number;
  netR?: number;
  averageR?: number;
  grossProfit?: number;
  grossLoss?: number;
  netPnl?: number;
  maxDrawdownPct?: number;
  consecutiveWins?: number;
  consecutiveLosses?: number;
}

export interface HostFocus {
  active: boolean;
  symbol: string;
  timeframe: string;
  focusType?: 'VCPR' | 'SMA' | 'SESSION' | 'NEWS' | 'CUSTOM';
  focusValue?: string;
  updatedAt: string;
}
