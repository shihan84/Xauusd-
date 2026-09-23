"use client";

import { useEffect, useMemo, useState } from "react";
import { getSupabaseBrowserClient } from "../lib/supabaseClient";

type StrategyRow = {
  strategy_id: string;
  name: string;
  strategy_group: string;
  timeframe: string;
  status: string;
  mode: string;
  enabled: boolean;
  telegram_enabled: boolean;
  description: string;
  rules: Record<string, unknown> | null;
  evidence: Record<string, unknown> | null;
  runtime_status: string | null;
  runtime_payload: Record<string, unknown> | null;
  runtime_updated_at: string | null;
  updated_at: string;
};

function pretty(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3);
  return String(value).replaceAll("_", " ");
}

function number2(value: unknown) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(2) : "—";
}

function runtimeFresh(value: string | null) {
  if (!value) return false;
  const ms = new Date(value).getTime();
  return Number.isFinite(ms) && Date.now() - ms < 120000;
}

export default function StrategyLabPanel() {
  const [rows, setRows] = useState<StrategyRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const supabase = getSupabaseBrowserClient();

    const load = async () => {
      try {
        const { data, error: queryError } = await supabase
          .from("strategy_registry")
          .select("strategy_id,name,strategy_group,timeframe,status,mode,enabled,telegram_enabled,description,rules,evidence,runtime_status,runtime_payload,runtime_updated_at,updated_at")
          .eq("dashboard_visible", true)
          .order("strategy_id");
        if (queryError) throw queryError;
        if (active) {
          setRows((data || []) as StrategyRow[]);
          setError(null);
        }
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : "Strategy registry unavailable");
      } finally {
        if (active) setLoading(false);
      }
    };

    void load();
    const channel = supabase
      .channel("strategy-registry-panel")
      .on("postgres_changes", { event: "*", schema: "public", table: "strategy_registry" }, () => void load())
      .subscribe();

    return () => {
      active = false;
      try { supabase.removeChannel(channel); } catch {}
    };
  }, []);

  const counts = useMemo(() => ({
    total: rows.length,
    paperReady: rows.filter(r => r.status === "PAPER_READY").length,
    research: rows.filter(r => r.status === "RESEARCH").length,
    liveRuntime: rows.filter(r => runtimeFresh(r.runtime_updated_at)).length,
    telegram: rows.filter(r => r.telegram_enabled).length,
  }), [rows]);

  const card: React.CSSProperties = {
    background: "#0d151f",
    border: "1px solid #1f2d3d",
    borderRadius: 12,
    padding: 14,
  };

  return (
    <section style={{ maxWidth: 1500, margin: "0 auto", padding: "0 22px 36px" }}>
      <div className="panel" style={{ padding: 18 }}>
        <div className="label">STRATEGY ENGINE</div>
        <h2 style={{ margin: "5px 0 4px", fontSize: 21 }}>XAUUSD Strategy Lab</h2>
        <div className="muted" style={{ maxWidth: 980 }}>
          Registry status and live forward-engine state. PAPER READY means rules are frozen for forward/demo observation; it does not mean proven profitability or live-money approval.
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 10, marginTop: 16 }}>
          <div style={card}><div className="label">Strategies</div><strong style={{ fontSize: 26 }}>{counts.total}</strong></div>
          <div style={card}><div className="label">Paper ready</div><strong style={{ fontSize: 26 }}>{counts.paperReady}</strong></div>
          <div style={card}><div className="label">Research</div><strong style={{ fontSize: 26 }}>{counts.research}</strong></div>
          <div style={card}><div className="label">Live runtimes</div><strong style={{ fontSize: 26 }}>{counts.liveRuntime}</strong></div>
          <div style={card}><div className="label">Telegram enabled</div><strong style={{ fontSize: 26 }}>{counts.telegram}</strong></div>
        </div>

        {loading && <div className="muted" style={{ marginTop: 16 }}>Loading strategy registry…</div>}
        {error && <div className="negative" style={{ marginTop: 16 }}>Strategy registry: {error}</div>}

        {!loading && !error && (
          <div style={{ display: "grid", gap: 12, marginTop: 16 }}>
            {rows.map(row => {
              const rules = row.rules || {};
              const evidence = row.evidence || {};
              const runtime = row.runtime_payload || {};
              const fresh = runtimeFresh(row.runtime_updated_at);
              const hasRuntime = Boolean(row.runtime_status);

              return (
                <div key={row.strategy_id} style={{ ...card, display: "grid", gap: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                    <div>
                      <div style={{ fontWeight: 800, fontSize: 18 }}>{row.name}</div>
                      <div className="muted">{row.strategy_id} · {row.timeframe}</div>
                    </div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-start" }}>
                      <span className="timeframe-btn active">{pretty(row.status)}</span>
                      <span className="timeframe-btn">{pretty(row.mode)}</span>
                      <span className="timeframe-btn">{row.telegram_enabled ? "TELEGRAM ON" : "TELEGRAM OFF"}</span>
                    </div>
                  </div>

                  <div>{row.description}</div>

                  {hasRuntime && (
                    <div style={{ ...card, background: "#0b1118" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                        <div>
                          <div className="label">LIVE FORWARD ENGINE</div>
                          <strong style={{ fontSize: 20 }}>{pretty(row.runtime_status)}</strong>
                        </div>
                        <span className={`timeframe-btn ${fresh ? "active" : ""}`}>
                          {fresh ? "● RUNTIME LIVE" : "● RUNTIME STALE"}
                        </span>
                      </div>

                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 10, marginTop: 12 }}>
                        <div><div className="label">Candidate</div><strong>{pretty(runtime.candidate_origin_date)}</strong></div>
                        <div><div className="label">VCPR PP</div><strong>{number2(runtime.pp)}</strong></div>
                        <div><div className="label">Arm level</div><strong>{number2(runtime.arm_level)}</strong></div>
                        <div><div className="label">Target</div><strong>{number2(runtime.target_price)}</strong></div>
                        <div><div className="label">Paper entry</div><strong>{number2(runtime.entry_price)}</strong></div>
                        <div><div className="label">Stop</div><strong>{number2(runtime.stop_price)}</strong></div>
                        <div><div className="label">Signals</div><strong>{pretty(runtime.signals_count)}</strong></div>
                        <div><div className="label">Result</div><strong>{pretty(runtime.result)}</strong></div>
                      </div>

                      {row.runtime_updated_at && (
                        <div className="muted" style={{ marginTop: 10, fontSize: 12 }}>
                          Runtime heartbeat: {new Date(row.runtime_updated_at).toLocaleString()}
                        </div>
                      )}
                    </div>
                  )}

                  {!hasRuntime && row.status === "PAPER_READY" && (
                    <div className="muted" style={{ ...card, background: "#0b1118" }}>
                      Live runtime waiting for the local strategy sync service.
                    </div>
                  )}

                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 10 }}>
                    <div>
                      <div className="label">Rules</div>
                      {Object.entries(rules).map(([k, v]) => (
                        <div key={k} className="muted" style={{ marginTop: 3 }}><strong>{pretty(k)}:</strong> {pretty(v)}</div>
                      ))}
                    </div>
                    <div>
                      <div className="label">Evidence / guardrail</div>
                      {Object.entries(evidence).map(([k, v]) => (
                        <div key={k} className="muted" style={{ marginTop: 3 }}><strong>{pretty(k)}:</strong> {pretty(v)}</div>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
