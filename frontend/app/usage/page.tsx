"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import Brand from "../components/Brand";

type UsageTotals = {
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
};

type UsageReport = {
  period_start: string;
  period_end: string;
  scope: "personal" | "organization";
  totals: UsageTotals;
  daily: Array<UsageTotals & { date: string; provider_cost_usd: number | null }>;
  by_model: Array<UsageTotals & { model: string }>;
  by_user: Array<UsageTotals & { user_id: string; email: string; first_name: string }>;
  provider: {
    status: "available" | "not_configured" | "personal_scope" | "unavailable";
    billed_cost_usd: number | null;
    difference_usd: number | null;
    currency: string;
    note: string;
  };
};

function isoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function formatCost(value: number | null): string {
  if (value === null) return "—";
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value < 0.01 ? 4 : 2,
    maximumFractionDigits: 6,
  }).format(value);
}

function formatTokens(value: number): string {
  return new Intl.NumberFormat("en-CA").format(value);
}

export default function UsagePage() {
  const router = useRouter();
  const today = new Date();
  const monthAgo = new Date(today);
  monthAgo.setDate(today.getDate() - 29);
  const [startDate, setStartDate] = useState(isoDate(monthAgo));
  const [endDate, setEndDate] = useState(isoDate(today));
  const [report, setReport] = useState<UsageReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadReport = useCallback(async (start: string, end: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/usage/report?start_date=${encodeURIComponent(start)}&end_date=${encodeURIComponent(end)}`,
        { credentials: "include", cache: "no-store" },
      );
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || "We could not load the usage report.");
      }
      setReport(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "We could not load the usage report.");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    void loadReport(startDate, endDate);
  }, [endDate, loadReport, startDate]);

  function applyDates(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadReport(startDate, endDate);
  }

  return (
    <main className="usage-shell">
      <header className="topbar usage-topbar">
        <Brand />
        <nav><Link href="/account">My account</Link></nav>
      </header>
      <div className="usage-content">
        <section className="usage-heading">
          <div><p className="eyebrow">AI COST CONTROL</p><h1>Usage report</h1><p>Compare the tokens used by CELPIP Coach with locally estimated and provider-billed costs.</p></div>
          <form className="usage-period" onSubmit={applyDates}>
            <label><span>From</span><input type="date" value={startDate} max={endDate} onChange={(event) => setStartDate(event.target.value)} required /></label>
            <label><span>To</span><input type="date" value={endDate} min={startDate} max={isoDate(today)} onChange={(event) => setEndDate(event.target.value)} required /></label>
            <button type="submit" disabled={loading}>Apply</button>
          </form>
        </section>

        {error && <div className="form-alert" role="alert">{error}</div>}
        {loading && !report ? <section className="usage-loading"><div className="loader" /><p>Calculating usage…</p></section> : report && (
          <>
            <section className="usage-metrics" aria-label="Usage totals">
              <article className="panel"><span>Successful AI calls</span><strong>{formatTokens(report.totals.request_count)}</strong><small>{report.scope === "organization" ? "All application users" : "Your evaluations"}</small></article>
              <article className="panel"><span>Total tokens</span><strong>{formatTokens(report.totals.total_tokens)}</strong><small>{formatTokens(report.totals.input_tokens)} input · {formatTokens(report.totals.output_tokens)} output</small></article>
              <article className="panel"><span>Local estimate</span><strong>{formatCost(report.totals.estimated_cost_usd)}</strong><small>Calculated from response usage</small></article>
              <article className="panel provider-total"><span>OpenAI billed cost</span><strong>{formatCost(report.provider.billed_cost_usd)}</strong><small>{report.provider.status === "available" ? `${formatCost(report.provider.difference_usd)} variance` : "Admin reconciliation required"}</small></article>
            </section>

            <section className={`usage-provider panel ${report.provider.status}`}>
              <span>{report.provider.status === "available" ? "✓" : "i"}</span>
              <div><h2>{report.provider.status === "available" ? "Provider comparison is active" : report.scope === "personal" ? "Personal usage report" : "Provider comparison is not configured"}</h2><p>{report.provider.note}</p></div>
            </section>

            <section className="usage-section">
              <div className="section-heading"><div><p className="eyebrow">DAILY DETAIL</p><h2>Usage by day</h2></div><span>{report.period_start} to {report.period_end}</span></div>
              <div className="usage-table panel">
                <div className="usage-table-head"><span>Date</span><span>Calls</span><span>Input</span><span>Output</span><span>Estimate</span><span>OpenAI cost</span></div>
                {report.daily.length ? report.daily.map((item) => (
                  <div className="usage-table-row" key={item.date}><strong>{item.date}</strong><span>{formatTokens(item.request_count)}</span><span>{formatTokens(item.input_tokens)}</span><span>{formatTokens(item.output_tokens)}</span><span>{formatCost(item.estimated_cost_usd)}</span><span>{formatCost(item.provider_cost_usd)}</span></div>
                )) : <div className="usage-empty">No successful AI usage was recorded in this period.</div>}
              </div>
            </section>

            <section className="usage-section">
              <div className="section-heading"><div><p className="eyebrow">MODEL DETAIL</p><h2>Usage by model</h2></div></div>
              <div className="usage-model-grid">
                {report.by_model.length ? report.by_model.map((item) => (
                  <article className="panel usage-model" key={item.model}><span>{item.model}</span><strong>{formatCost(item.estimated_cost_usd)}</strong><div><small>{formatTokens(item.request_count)} calls</small><small>{formatTokens(item.total_tokens)} tokens</small></div></article>
                )) : <article className="panel usage-empty">Model totals will appear after the first successful evaluation.</article>}
              </div>
            </section>

            {report.by_user.length > 0 && <section className="usage-section">
              <div className="section-heading"><div><p className="eyebrow">ADMIN VIEW</p><h2>Usage by user</h2></div></div>
              <div className="usage-table usage-user-table panel">
                <div className="usage-table-head"><span>User</span><span>Email</span><span>Calls</span><span>Tokens</span><span>Estimate</span></div>
                {report.by_user.map((item) => <div className="usage-table-row" key={item.user_id}><strong>{item.first_name}</strong><span>{item.email}</span><span>{formatTokens(item.request_count)}</span><span>{formatTokens(item.total_tokens)}</span><span>{formatCost(item.estimated_cost_usd)}</span></div>)}
              </div>
            </section>}

            <p className="usage-footnote">Local totals include successful AI requests made by this application, including evaluations and question generation. OpenAI Costs data may include other API activity in the configured project and should be treated as the billing source of truth.</p>
          </>
        )}
      </div>
    </main>
  );
}
