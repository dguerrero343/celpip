"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import Brand from "../../components/Brand";
import {
  dateTime,
  duration,
  failureMessage,
  money,
  number,
  score,
  UserSummary,
} from "./types";

type UserReport = {
  items: UserSummary[];
  total: number;
  limit: number;
  offset: number;
};

const PAGE_SIZE = 25;

export default function AdminUsersPage() {
  const router = useRouter();
  const [report, setReport] = useState<UserReport | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
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
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (search) params.set("search", search);
    const response = await fetch(`/api/admin/users/summary?${params}`, {
      credentials: "include",
      cache: "no-store",
    });
    if (!response.ok) throw new Error(await failureMessage(response));
    setReport(await response.json());
  }, [offset, router, search]);

  useEffect(() => {
    void load().catch((reason) => {
      setError(reason instanceof Error ? reason.message : "The user report could not be loaded.");
    });
  }, [load]);

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setOffset(0);
    setReport(null);
    setSearch(searchInput.trim());
  }

  return <main className="admin-shell">
    <header className="topbar admin-topbar">
      <Brand />
      <nav><Link href="/admin">Question bank</Link><Link href="/usage">Full usage report</Link></nav>
    </header>
    <div className="admin-content admin-user-page">
      <section className="admin-user-report">
        <div className="section-heading">
          <div><p className="eyebrow">USER REPORTING</p><h1>Practice and AI usage by user</h1><p>Lifetime totals from server-timed attempts, evaluations, assignments, and recorded AI requests. Open a user to inspect individual attempts and AI usage.</p></div>
          <form className="admin-user-search" onSubmit={submitSearch}>
            <label htmlFor="admin-user-search">Search users</label>
            <div><input id="admin-user-search" type="search" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Name or email" /><button type="submit">Search</button></div>
          </form>
        </div>
        {error && <div className="form-alert" role="alert">{error}</div>}
        {!error && report ? <div className="panel admin-user-table-wrap">
          <table className="admin-user-table">
            <thead><tr><th>User</th><th>Exercises</th><th>Timed practice</th><th>Scores</th><th>AI usage</th><th>Last activity</th><th /></tr></thead>
            <tbody>{report.items.map((item) => <tr key={item.id}>
              <td data-label="User"><strong>{item.first_name}</strong><span>{item.email}</span><small>{item.role === "ADMIN" ? "Administrator" : `Current ${item.current_score ?? "—"} · Target ${item.target_score ?? "—"}`}</small></td>
              <td data-label="Exercises"><strong>{number(item.exercises_completed)} completed</strong><span>{number(item.assigned_exercises)} assigned · {number(item.attempts_started)} started</span>{item.active_attempts > 0 && <small className="admin-active-attempt">{item.active_attempts} active now</small>}</td>
              <td data-label="Timed practice"><strong>{duration(item.total_practice_seconds)}</strong><span>{item.test_simulation_completed} test · {item.guided_practice_completed} guided</span></td>
              <td data-label="Scores"><strong>Test {score(item.average_test_score)}</strong><span>Guided {score(item.average_guided_score)}</span></td>
              <td data-label="AI usage"><strong>{number(item.total_tokens)} tokens</strong><span>{number(item.ai_request_count)} calls · {money(item.estimated_cost_usd)}</span></td>
              <td data-label="Last activity"><strong>{dateTime(item.last_activity_at)}</strong><span>Joined {dateTime(item.registered_at)}</span></td>
              <td data-label="Details"><Link className="admin-user-detail-link" href={`/admin/users/${item.id}`}>View details →</Link></td>
            </tr>)}</tbody>
          </table>
          {!report.items.length && <div className="usage-empty">No users match this search.</div>}
          <footer className="admin-user-pagination"><span>{number(report.total)} users</span><div><button type="button" disabled={offset === 0} onClick={() => { setReport(null); setOffset(Math.max(0, offset - PAGE_SIZE)); }}>Previous</button><button type="button" disabled={offset + PAGE_SIZE >= report.total} onClick={() => { setReport(null); setOffset(offset + PAGE_SIZE); }}>Next</button></div></footer>
        </div> : !error && <section className="usage-loading"><div className="loader" /><p>Loading user activity…</p></section>}
      </section>
    </div>
  </main>;
}
