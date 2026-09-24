insert into public.strategy_registry (
  strategy_id,name,strategy_group,timeframe,status,mode,enabled,dashboard_visible,telegram_enabled,description,rules,evidence
) values
(
  'LIQUIDITY_SWEEP_REVERSAL_V1',
  'Liquidity Sweep + Reversal V1',
  'INTRADAY_REVERSAL',
  'M5/H1',
  'FORWARD_TEST',
  'PAPER',
  true,true,true,
  'Paper-test reversal setup around previous-day high/low, Asia high/low and nearby VCPR. Requires a sweep/reclaim followed by a separate M5 confirmation candle.',
  jsonb_build_object(
    'levels',jsonb_build_array('Previous Day High','Previous Day Low','Asia High','Asia Low','Nearby VCPR'),
    'setup','Previous closed M5 sweeps a level and closes back through it',
    'trigger','Next closed M5 breaks the sweep candle in the reversal direction',
    'risk','Sweep extreme plus 0.15 M5 ATR buffer; block if risk > 1.50 ATR',
    'targets','T1=1R, T2=2R'
  ),
  jsonb_build_object(
    'status','INITIAL SIGNAL TEST',
    'warning','New frozen paper-test rules; no out-of-sample edge established.'
  )
),
(
  'SESSION_BREAK_RETEST_V1',
  'Asia Range Break + Retest V1',
  'SESSION_BREAKOUT',
  'M5/H1',
  'FORWARD_TEST',
  'PAPER',
  true,true,true,
  'Paper-test continuation setup after the Asia range breaks during the active London/New York window and price retests the broken boundary.',
  jsonb_build_object(
    'range','Broker 00:00-08:00 Asia range',
    'window','Broker 08:00-18:00',
    'trend_filter','H1 close vs EMA99 plus SMA20/SMA44 direction',
    'breakout','Recent M5 close beyond Asia boundary by at least 0.10 ATR',
    'retest','Current M5 revisits boundary and closes back in breakout direction',
    'risk','Retest candle extreme plus 0.15 ATR; block if risk > 1.50 ATR',
    'targets','T1=1R, T2=2R'
  ),
  jsonb_build_object(
    'status','INITIAL SIGNAL TEST',
    'warning','New frozen paper-test rules; session behavior must be validated across larger samples.'
  )
),
(
  'COMPRESSION_EXPANSION_V1',
  'MA Compression → Expansion V1',
  'VOLATILITY_EXPANSION',
  'M5/M15/H1/H4',
  'FORWARD_TEST',
  'PAPER',
  true,true,true,
  'Paper-test volatility expansion setup. M15 moving averages and ATR must compress first; M5 then breaks local structure in the aligned H1/H4 direction.',
  jsonb_build_object(
    'compression','M15 SMA9/SMA20/SMA44 spread <= 0.45 ATR and ATR14 <= 0.95 x median recent ATR',
    'trend_filter','H1 and H4 agree using close vs EMA99 and SMA20/SMA44',
    'trigger','M5 closes beyond prior 12-bar range with candle range >= 1.20 ATR',
    'vcpr_filter','Block when a VCPR pivot sits too close directly ahead',
    'risk','Expansion candle extreme plus 0.15 ATR; block if risk > 1.50 ATR',
    'targets','T1=1R, T2=2R'
  ),
  jsonb_build_object(
    'status','INITIAL SIGNAL TEST',
    'warning','New frozen paper-test rules; no profitability claim until historical and forward validation.'
  )
)
on conflict (strategy_id) do update set
  name=excluded.name,
  strategy_group=excluded.strategy_group,
  timeframe=excluded.timeframe,
  status=excluded.status,
  mode=excluded.mode,
  enabled=excluded.enabled,
  dashboard_visible=excluded.dashboard_visible,
  telegram_enabled=excluded.telegram_enabled,
  description=excluded.description,
  rules=excluded.rules,
  evidence=excluded.evidence,
  updated_at=now();
