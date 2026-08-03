"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import Brand from "../../../components/Brand";
import {
  dateTime,
  duration,
  failureMessage,
  money,
  number,
  score,
  UserSummary,
} from "../types";

type Attempt = {
  id: string;
  task_type: "EMAIL" | "SURVEY";
  category: string;
  status: "PREPARING" | "WRITING" | "SUBMITTED" | "EXPIRED";
  attempt_type: "GUIDED_PRACTICE" | "TEST_SIMULATION";
  help_mode_enabled: boolean;
  started_at: string;
  submitted_at: string | null;
  elapsed_seconds: number;
  word_count: number;
  estimated_score: number | null;
};

type UsageBreakdown = {
  request_type: string;
  model: string;
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
};

type UserDetail = {
  summary: UserSummary;
  recent_attempts: Attempt[];
  ai_usage_breakdown: UsageBreakdown[];
};

function label(value: string): string {
  return value.toLowerCase().replaceAll("_", " ").replace(/^./, (first) => first.toUpperCase());
}

export default function AdminUserDetailPage() {
  const { userId } = useParams<{ userId: string }>();
  const router = useRouter();
  const [detail, setDetail] = useState<UserDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const me = await fetch("/api/auth/me", { credentials: "include", cache: "no-store" });
    if (me.status === 401) {
      router.replace("/login");
      return;
    }
    const currentUser = await me.json() as { role: string };
    if (currentUser.role !== "ADMIN") {
      setError("Administrator access is required.");
      return;
    }
    const response = await fetch(`/api/admin/users/${encodeURIComponent(userId)}`, {
      credentials: "include",
      cache: "no-store",
    });
    if (!response.ok) throw new Error(await failureMessage(response));
    setDetail(await response.json());
  }, [router, userId]);

  useEffect(() => {
    void load().catch((reason) => {
      setError(reason instanceof Error ? reason.message : "The user details could not be loaded.");
    });
  }, [load]);

  return <main className="admin-shell">
    <header className="topbar admin-topbar">
      <Brand />
      <nav><Link href="/admin/users">All users</Link><Link href="/admin">Question bank</Link></nav>
    </header>
    <div className="admin-content admin-user-detail-page">
      {error && <div className="form-alert" role="alert">{error}</div>}
      {!error && !detail && <section className="usage-loading"><div className="loader" /><p>Loading user details…</p></section>}
      {detail && <>
        <section className="admin-heading admin-user-profile-heading">
          <div><p className="eyebrow">USER DETAIL</p><h1>{detail.summary.first_name}</h1><p>{detail.summary.email} · {detail.summary.role === "ADMIN" ? "Administrator" : "Student"}</p></div>
          <Link className="button" href="/admin/users">← Back to users</Link>
        </section>

        <section className="admin-detail-metrics">
          <article className="panel"><span>Completed</span><strong>{number(detail.summary.exercises_completed)}</strong><small>{detail.summary.test_simulation_completed} test · {detail.summary.guided_practice_completed} guided</small></article>
          <article className="panel"><span>Practice time</span><strong>{duration(detail.summary.total_practice_seconds)}</strong><small>{detail.summary.active_attempts} active attempt{detail.summary.active_attempts === 1 ? "" : "s"}</small></article>
          <article className="panel"><span>Average scores</span><strong>{score(detail.summary.average_test_score)}</strong><small>Test · Guided {score(detail.summary.average_guided_score)}</small></article>
          <article className="panel"><span>AI usage</span><strong>{number(detail.summary.total_tokens)}</strong><small>{detail.summary.ai_request_count} calls · {money(detail.summary.estimated_cost_usd)}</small></article>
        </section>

        <section className="admin-detail-section">
          <div className="section-heading"><div><p className="eyebrow">RECENT ATTEMPTS</p><h2>Exercise history</h2><p>Up to 50 recent attempts, with authoritative elapsed time and evaluation result.</p></div></div>
          <div className="panel admin-user-table-wrap">
            <table className="admin-user-table admin-attempt-table">
              <thead><tr><th>Exercise</th><th>Mode</th><th>Status</th><th>Time</th><th>Response</th><th>Score</th><th>Started</th></tr></thead>
              <tbody>{detail.recent_attempts.map((attempt) => <tr key={attempt.id}>
                <td data-label="Exercise"><strong>{attempt.task_type === "EMAIL" ? "Task 1 · Email" : "Task 2 · Survey"}</strong><span>{attempt.category}</span></td>
                <td data-label="Mode"><strong>{attempt.attempt_type === "GUIDED_PRACTICE" ? "Guided Practice" : "Test Simulation"}</strong><span>{attempt.help_mode_enabled ? "Help Mode used" : "No help"}</span></td>
                <td data-label="Status"><span className={`status-pill ${attempt.status.toLowerCase()}`}>{label(attempt.status)}</span></td>
                <td data-label="Time"><strong>{duration(attempt.elapsed_seconds)}</strong></td>
                <td data-label="Response"><strong>{number(attempt.word_count)} words</strong></td>
                <td data-label="Score"><strong>{score(attempt.estimated_score)}</strong></td>
                <td data-label="Started"><strong>{dateTime(attempt.started_at)}</strong>{attempt.submitted_at && <span>Submitted {dateTime(attempt.submitted_at)}</span>}</td>
              </tr>)}</tbody>
            </table>
            {!detail.recent_attempts.length && <div className="usage-empty">This user has no writing attempts yet.</div>}
          </div>
        </section>

        <section className="admin-detail-section">
          <div className="section-heading"><div><p className="eyebrow">AI USAGE</p><h2>Usage by model and purpose</h2><p>Recorded token and estimated cost totals for this user.</p></div></div>
          <div className="panel admin-user-table-wrap">
            <table className="admin-user-table admin-usage-breakdown-table">
              <thead><tr><th>Purpose</th><th>Model</th><th>Calls</th><th>Input tokens</th><th>Output tokens</th><th>Total</th><th>Estimated cost</th></tr></thead>
              <tbody>{detail.ai_usage_breakdown.map((item) => <tr key={`${item.request_type}-${item.model}`}>
                <td data-label="Purpose"><strong>{label(item.request_type)}</strong></td>
                <td data-label="Model"><strong>{item.model}</strong></td>
                <td data-label="Calls"><strong>{number(item.request_count)}</strong></td>
                <td data-label="Input tokens"><strong>{number(item.input_tokens)}</strong></td>
                <td data-label="Output tokens"><strong>{number(item.output_tokens)}</strong></td>
                <td data-label="Total"><strong>{number(item.total_tokens)}</strong></td>
                <td data-label="Estimated cost"><strong>{money(item.estimated_cost_usd)}</strong></td>
              </tr>)}</tbody>
            </table>
            {!detail.ai_usage_breakdown.length && <div className="usage-empty">No AI usage has been recorded for this user.</div>}
          </div>
        </section>
      </>}
    </div>
  </main>;
}
