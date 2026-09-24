"use client";

import { useEffect, useState } from "react";
import { getSupabaseBrowserClient } from "../lib/supabaseClient";

type SignalRow = {
  id: number;
  direction: "BUY" | "SELL";
  signal_time: string;
  broker_time: string | null;
  entry_price: number | null;
  stop_price: number | null;
  target1_price: number | null;
  target2_price: number | null;
  score: number | null;
  vcpr_pivot: number | null;
  paper_status: string;
  outcome_1r: string | null;
  outcome_2r: string | null;
  mfe_r: number | null;
  mae_r: number | null;
};

function fmt(value: number | null | undefined) {
  return value === null || value === undefined ? "—" : Number(value).toFixed(2);
}

function pretty(value: string | null | undefined) {
  return value ? value.replaceAll("_", " ") : "—";
}

export default function StrategySignalsPanel() {
  const [rows, setRows] = useState<SignalRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const supabase = getSupabaseBrowserClient();

    const load = async () => {
      const { data, error: queryError } = await supabase
        .from("strategy_signals")
        .select("id,direction,signal_time,broker_time,entry_price,stop_price,target1_price,target2_price,score,vcpr_pivot,paper_status,outcome_1r,outcome_2r,mfe_r,mae_r")
        .eq("strategy_id", "INTRADAY_MTF_V1")
        .order("signal_time", { ascending: false })
        .limit(12);

      if (queryError) {
        if (active) setError(queryError.message);
        return;
      }

      if (active) {
        setRows((data || []) as SignalRow[]);
        setError(null);
      }
    };

    void load();

    const channel = supabase
      .channel("intraday-strategy-signals")
      .on("postgres_changes", { event: "*", schema: "public", table: "strategy_signals" }, () => void load())
      .subscribe();

    return () => {
      active = false;
      try { supabase.removeChannel(channel); } catch {}
    };
  }, []);

  return (
    <section style={{ maxWidth: 1500, margin: "0 auto", padding: "0 22px 36px" }}>
      <div className="panel" style={{ padding: 18 }}>
        <div className="label">PAPER SIGNAL LEDGER</div>
        <h2 style={{ margin: "5px 0 4px", fontSize: 21 }}>Intraday MTF Paper Trades</h2>
        <div className="muted">
          Live paper/demo tracking for INTRADAY_MTF_V1. Results are research observations, not live-money execution.
        </div>

        {error && <div className="negative" style={{ marginTop: 14 }}>{error}</div>}

        {!error && rows.length === 0 && (
          <div className="muted" style={{ marginTop: 14 }}>
            No paper signal has triggered yet. The engine will add the first row automatically when all frozen conditions pass.
          </div>
        )}

        {rows.length > 0 && (
          <div style={{ overflowX: "auto", marginTop: 16 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 980 }}>
              <thead>
                <tr>
                  {["Time","Dir","Status","Score","Entry","Stop","T1","T2","VCPR","1R","2R","MFE","MAE"].map(h => (
                    <th key={h} style={{ textAlign: "left", padding: "8px 10px", borderBottom: "1px solid #243244" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map(row => (
                  <tr key={row.id}>
                    <td style={{ padding: "9px 10px", borderBottom: "1px solid #172330", whiteSpace: "nowrap" }}>
                      {new Date(row.signal_time).toLocaleString()}
                    </td>
                    <td style={{ padding: "9px 10px", borderBottom: "1px solid #172330" }}><strong>{row.direction}</strong></td>
                    <td style={{ padding: "9px 10px", borderBottom: "1px solid #172330" }}>{pretty(row.paper_status)}</td>
                    <td style={{ padding: "9px 10px", borderBottom: "1px solid #172330" }}>{row.score ?? "—"}</td>
                    <td style={{ padding: "9px 10px", borderBottom: "1px solid #172330" }}>{fmt(row.entry_price)}</td>
                    <td style={{ padding: "9px 10px", borderBottom: "1px solid #172330" }}>{fmt(row.stop_price)}</td>
                    <td style={{ padding: "9px 10px", borderBottom: "1px solid #172330" }}>{fmt(row.target1_price)}</td>
                    <td style={{ padding: "9px 10px", borderBottom: "1px solid #172330" }}>{fmt(row.target2_price)}</td>
                    <td style={{ padding: "9px 10px", borderBottom: "1px solid #172330" }}>{fmt(row.vcpr_pivot)}</td>
                    <td style={{ padding: "9px 10px", borderBottom: "1px solid #172330" }}>{pretty(row.outcome_1r)}</td>
                    <td style={{ padding: "9px 10px", borderBottom: "1px solid #172330" }}>{pretty(row.outcome_2r)}</td>
                    <td style={{ padding: "9px 10px", borderBottom: "1px solid #172330" }}>{row.mfe_r == null ? "—" : Number(row.mfe_r).toFixed(2) + "R"}</td>
                    <td style={{ padding: "9px 10px", borderBottom: "1px solid #172330" }}>{row.mae_r == null ? "—" : Number(row.mae_r).toFixed(2) + "R"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
