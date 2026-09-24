update public.strategy_registry
set status='FORWARD_TEST',
    mode='PAPER',
    enabled=true,
    dashboard_visible=true,
    telegram_enabled=true,
    evidence = coalesce(evidence,'{}'::jsonb) || jsonb_build_object(
      'robustness_decision','PRIMARY_FORWARD_TEST',
      'robustness_note','Positive descriptive results persisted under cooldown and non-overlap tests; still paper/demo research only.',
      'preferred_exit_research','1R primary; 2R tracked separately'
    ),
    updated_at=now()
where strategy_id='SESSION_BREAK_RETEST_V1';

update public.strategy_registry
set status='RESEARCH',
    mode='PAPER',
    enabled=true,
    dashboard_visible=true,
    telegram_enabled=false,
    evidence = coalesce(evidence,'{}'::jsonb) || jsonb_build_object(
      'robustness_decision','QUIET_FORWARD_RESEARCH',
      'robustness_note','Raw edge was thin and weakened materially after cooldown/non-overlap/cost tests. Continue collecting quietly without Telegram alerts.'
    ),
    updated_at=now()
where strategy_id='LIQUIDITY_SWEEP_REVERSAL_V1';

update public.strategy_registry
set status='RESEARCH',
    mode='PAPER',
    enabled=false,
    dashboard_visible=true,
    telegram_enabled=false,
    evidence = coalesce(evidence,'{}'::jsonb) || jsonb_build_object(
      'robustness_decision','DISABLED_PENDING_REDESIGN',
      'robustness_note','Historical sample was negative and small. Do not forward-alert or paper-signal until redesigned and retested.'
    ),
    updated_at=now()
where strategy_id='COMPRESSION_EXPANSION_V1';