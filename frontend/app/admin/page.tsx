"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import Brand from "../components/Brand";

type TaskStatus = "DRAFT" | "IN_REVIEW" | "APPROVED" | "RETIRED";
type TaskType = "EMAIL" | "SURVEY";

type BankTask = {
  id: string;
  family_id: string;
  task_type: TaskType;
  category: string;
  difficulty: "BEGINNER" | "INTERMEDIATE" | "ADVANCED";
  prompt: string;
  status: TaskStatus;
  source: "HUMAN" | "AI";
  scenario_key: string | null;
  focus_tags: string[];
  target_score_min: number;
  target_score_max: number;
  reviewed_at: string | null;
  assignment_count: number;
  submission_count: number;
  style_issues: string[];
};

type Summary = {
  total_tasks: number;
  approved_tasks: number;
  draft_tasks: number;
  in_review_tasks: number;
  retired_tasks: number;
  email_tasks: number;
  survey_tasks: number;
  total_assignments: number;
  total_submissions: number;
  unique_students: number;
};

type Usage = {
  totals: {
    request_count: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number;
  };
  provider: { billed_cost_usd: number | null; status: string };
};

type Consistency = {
  metrics: Array<{
    prompt_version: string;
    attempt_type: "GUIDED_PRACTICE" | "TEST_SIMULATION";
    evaluation_count: number;
    average_score: number;
    score_standard_deviation: number;
    average_change_from_prior: number | null;
  }>;
  guidance: string;
};

type Editor = {
  task_type: TaskType;
  category: string;
  difficulty: "BEGINNER" | "INTERMEDIATE" | "ADVANCED";
  prompt: string;
  scenario_key: string;
  focus_tags: string;
  target_score_min: number;
  target_score_max: number;
};

const EMPTY_EDITOR: Editor = {
  task_type: "EMAIL",
  category: "",
  difficulty: "INTERMEDIATE",
  prompt: "",
  scenario_key: "",
  focus_tags: "TASK_COMPLETENESS, TONE, ORGANIZATION",
  target_score_min: 1,
  target_score_max: 12,
};

function isoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function money(value: number | null): string {
  if (value === null) return "—";
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value < 0.01 ? 4 : 2,
    maximumFractionDigits: 6,
  }).format(value);
}

function number(value: number): string {
  return new Intl.NumberFormat("en-CA").format(value);
}

async function failureMessage(response: Response): Promise<string> {
  const body = await response.json().catch(() => null) as { detail?: string | { message?: string; issues?: string[] } } | null;
  if (typeof body?.detail === "string") return body.detail;
  if (body?.detail && typeof body.detail === "object") {
    return [body.detail.message, ...(body.detail.issues || [])].filter(Boolean).join(" ");
  }
  return "The request could not be completed.";
}

export default function AdminPage() {
  const router = useRouter();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [tasks, setTasks] = useState<BankTask[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [consistency, setConsistency] = useState<Consistency | null>(null);
  const [statusFilter, setStatusFilter] = useState<TaskStatus | "">("");
  const [typeFilter, setTypeFilter] = useState<TaskType | "">("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<BankTask | null>(null);
  const [editor, setEditor] = useState<Editor>(EMPTY_EDITOR);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generateType, setGenerateType] = useState<TaskType>("EMAIL");
  const [generateCount, setGenerateCount] = useState(3);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (statusFilter) params.set("status", statusFilter);
    if (typeFilter) params.set("task_type", typeFilter);
    if (search.trim()) params.set("search", search.trim());
    return params.toString();
  }, [search, statusFilter, typeFilter]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const me = await fetch("/api/auth/me", { credentials: "include", cache: "no-store" });
    if (me.status === 401) {
      router.replace("/login");
      return;
    }
    const user = await me.json() as { role: string };
    if (user.role !== "ADMIN") {
      setError("Administrator access is required.");
      setLoading(false);
      return;
    }
    const end = new Date();
    const start = new Date(end);
    start.setDate(end.getDate() - 29);
    const [summaryResponse, bankResponse, usageResponse, consistencyResponse] = await Promise.all([
      fetch("/api/admin/question-bank/summary", { credentials: "include", cache: "no-store" }),
      fetch(`/api/admin/question-bank${query ? `?${query}` : ""}`, { credentials: "include", cache: "no-store" }),
      fetch(`/api/usage/report?start_date=${isoDate(start)}&end_date=${isoDate(end)}`, { credentials: "include", cache: "no-store" }),
      fetch("/api/admin/evaluation-consistency", { credentials: "include", cache: "no-store" }),
    ]);
    if (!summaryResponse.ok || !bankResponse.ok || !usageResponse.ok || !consistencyResponse.ok) {
      throw new Error("We could not load the administration workspace.");
    }
    const bank = await bankResponse.json() as { items: BankTask[] };
    setSummary(await summaryResponse.json());
    setTasks(bank.items);
    setUsage(await usageResponse.json());
    setConsistency(await consistencyResponse.json());
    setLoading(false);
  }, [query, router]);

  useEffect(() => {
    void load().catch((reason) => {
      setError(reason instanceof Error ? reason.message : "The admin site could not be loaded.");
      setLoading(false);
    });
  }, [load]);

  function editTask(task: BankTask) {
    setSelected(task);
    setEditor({
      task_type: task.task_type,
      category: task.category,
      difficulty: task.difficulty,
      prompt: task.prompt,
      scenario_key: task.scenario_key || "",
      focus_tags: task.focus_tags.join(", "),
      target_score_min: task.target_score_min,
      target_score_max: task.target_score_max,
    });
    setNotice(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function newTask() {
    setSelected(null);
    setEditor(EMPTY_EDITOR);
    setNotice(null);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setNotice(null);
    const payload = {
      ...editor,
      scenario_key: editor.scenario_key || null,
      focus_tags: editor.focus_tags.split(",").map((item) => item.trim()).filter(Boolean),
    };
    const response = await fetch(
      selected ? `/api/admin/question-bank/${selected.id}` : "/api/admin/question-bank",
      {
        method: selected ? "PUT" : "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    );
    if (!response.ok) {
      setError(await failureMessage(response));
    } else {
      setNotice(selected ? "Exercise saved and returned to review." : "Draft exercise created.");
      const saved = await response.json() as BankTask;
      editTask(saved);
      await load();
    }
    setSaving(false);
  }

  async function changeStatus(task: BankTask, status: TaskStatus) {
    setSaving(true);
    setError(null);
    setNotice(null);
    const response = await fetch(`/api/admin/question-bank/${task.id}/status`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (!response.ok) setError(await failureMessage(response));
    else {
      setNotice(`Exercise moved to ${status.toLowerCase().replace("_", " ")}.`);
      setSelected(null);
      setEditor(EMPTY_EDITOR);
      await load();
    }
    setSaving(false);
  }

  async function generateDrafts() {
    setGenerating(true);
    setError(null);
    setNotice(null);
    const response = await fetch("/api/admin/question-bank/generate", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_type: generateType, count: generateCount }),
    });
    if (!response.ok) setError(await failureMessage(response));
    else {
      const result = await response.json() as { items: BankTask[]; input_tokens: number; output_tokens: number; estimated_cost_usd: number };
      setNotice(`${result.items.length} AI drafts created using ${number(result.input_tokens + result.output_tokens)} tokens (${money(result.estimated_cost_usd)} estimated). Review is required.`);
      await load();
    }
    setGenerating(false);
  }

  return (
    <main className="admin-shell">
      <header className="topbar admin-topbar">
        <Brand />
        <nav><Link href="/admin/users">User reporting</Link><Link href="/account">Student view</Link><Link href="/usage">Full usage report</Link></nav>
      </header>
      <div className="admin-content">
        <section className="admin-heading">
          <div><p className="eyebrow">ADMINISTRATION</p><h1>Question bank</h1><p>Maintain original CELPIP-style exercises, control publication, monitor inventory, and reconcile AI usage.</p></div>
          <button className="button primary" type="button" onClick={newTask}>New exercise</button>
        </section>

        {error && <div className="form-alert" role="alert">{error}</div>}
        {notice && <div className="admin-notice" role="status">{notice}</div>}
        {loading && !summary ? <section className="usage-loading"><div className="loader" /><p>Loading administration data…</p></section> : summary && usage && <>
          <section className="admin-metrics">
            <article className="panel"><span>Approved inventory</span><strong>{summary.approved_tasks}</strong><small>{summary.email_tasks} email · {summary.survey_tasks} survey</small></article>
            <article className="panel"><span>Review queue</span><strong>{summary.draft_tasks + summary.in_review_tasks}</strong><small>{summary.draft_tasks} drafts · {summary.in_review_tasks} in review</small></article>
            <article className="panel"><span>Assigned</span><strong>{number(summary.total_assignments)}</strong><small>{number(summary.unique_students)} students</small></article>
            <article className="panel admin-token-card"><span>Tokens · 30 days</span><strong>{number(usage.totals.total_tokens)}</strong><small>{money(usage.totals.estimated_cost_usd)} estimated · {money(usage.provider.billed_cost_usd)} billed</small></article>
          </section>

          <section className="admin-workspace">
            <form className="admin-editor panel" onSubmit={save}>
              <div className="admin-editor-title"><div><p className="eyebrow">{selected ? "EDIT EXERCISE" : "NEW DRAFT"}</p><h2>{selected ? selected.category : "Create an exercise"}</h2></div>{selected && <span className={`status-pill ${selected.status.toLowerCase()}`}>{selected.status.replace("_", " ")}</span>}</div>
              <div className="admin-form-grid">
                <label><span>Task</span><select value={editor.task_type} onChange={(event) => setEditor({ ...editor, task_type: event.target.value as TaskType })}><option value="EMAIL">Task 1 · Email</option><option value="SURVEY">Task 2 · Survey</option></select></label>
                <label><span>Category</span><input value={editor.category} onChange={(event) => setEditor({ ...editor, category: event.target.value })} placeholder="Community" required /></label>
                <label><span>Internal challenge</span><select value={editor.difficulty} onChange={(event) => setEditor({ ...editor, difficulty: event.target.value as Editor["difficulty"] })}><option>BEGINNER</option><option>INTERMEDIATE</option><option>ADVANCED</option></select></label>
                <label><span>Scenario key</span><input value={editor.scenario_key} onChange={(event) => setEditor({ ...editor, scenario_key: event.target.value })} placeholder="community-noise-complaint" /></label>
                <label><span>Target score from</span><input type="number" min="1" max="12" value={editor.target_score_min} onChange={(event) => setEditor({ ...editor, target_score_min: Number(event.target.value) })} /></label>
                <label><span>Target score to</span><input type="number" min="1" max="12" value={editor.target_score_max} onChange={(event) => setEditor({ ...editor, target_score_max: Number(event.target.value) })} /></label>
              </div>
              <label className="admin-wide-field"><span>Focus tags</span><input value={editor.focus_tags} onChange={(event) => setEditor({ ...editor, focus_tags: event.target.value })} placeholder="TONE, ORGANIZATION, VOCABULARY" /></label>
              <label className="admin-wide-field"><span>Prompt</span><textarea value={editor.prompt} onChange={(event) => setEditor({ ...editor, prompt: event.target.value })} rows={10} placeholder="Write an original CELPIP-style prompt…" required /></label>
              {selected?.style_issues.length ? <div className="admin-validation"><strong>Style checks</strong><ul>{selected.style_issues.map((issue) => <li key={issue}>{issue}</li>)}</ul></div> : selected && <div className="admin-validation passed">✓ CELPIP-style checks passed</div>}
              <div className="admin-editor-actions"><button className="button primary" disabled={saving}>{saving ? "Saving…" : selected ? "Save changes" : "Create draft"}</button>{selected && <>
                {selected.status === "DRAFT" && <button type="button" onClick={() => void changeStatus(selected, "IN_REVIEW")} disabled={saving}>Send to review</button>}
                {selected.status === "IN_REVIEW" && <button type="button" className="approve" onClick={() => void changeStatus(selected, "APPROVED")} disabled={saving || selected.style_issues.length > 0}>Approve</button>}
                {selected.status === "APPROVED" && <button type="button" className="retire" onClick={() => void changeStatus(selected, "RETIRED")} disabled={saving}>Retire</button>}
                {selected.status === "RETIRED" && <button type="button" onClick={() => void changeStatus(selected, "DRAFT")} disabled={saving}>Restore as draft</button>}
              </>}</div>
            </form>

            <aside className="admin-side">
              <article className="panel admin-policy"><p className="eyebrow">EVALUATOR STABILITY</p><h2>Prompt versions are measured</h2>{consistency?.metrics.length ? <ul>{consistency.metrics.map((metric) => <li key={`${metric.prompt_version}-${metric.attempt_type}`}><strong>{metric.prompt_version}</strong> · {metric.attempt_type === "TEST_SIMULATION" ? "Test" : "Guided"}: {metric.evaluation_count} evaluations, {metric.score_standard_deviation.toFixed(2)} score spread</li>)}</ul> : <p>No versioned evaluations yet.</p>}<small>{consistency?.guidance}</small></article>
              <article className="panel admin-policy"><p className="eyebrow">PUBLICATION RULE</p><h2>Human approval required</h2><p>Only approved exercises are assignable. Editing an approved prompt automatically returns it to review.</p></article>
              <article className="panel admin-generator"><p className="eyebrow">OPTIONAL AI DRAFTS</p><h2>Replenish the bank</h2><p>Generate original drafts. Nothing is published until an administrator reviews and approves it.</p><label><span>Task</span><select value={generateType} onChange={(event) => setGenerateType(event.target.value as TaskType)}><option value="EMAIL">Task 1</option><option value="SURVEY">Task 2</option></select></label><label><span>Drafts</span><input type="number" min="1" max="5" value={generateCount} onChange={(event) => setGenerateCount(Number(event.target.value))} /></label><button type="button" onClick={() => void generateDrafts()} disabled={generating}>{generating ? "Generating…" : "Generate drafts"}</button></article>
              <Link className="panel admin-usage-link" href="/usage"><span>AI usage and billing</span><strong>{number(usage.totals.request_count)} calls</strong><small>Open full reconciliation →</small></Link>
            </aside>
          </section>

          <section className="admin-library">
            <div className="section-heading"><div><p className="eyebrow">CURATED LIBRARY</p><h2>{tasks.length} exercises</h2></div></div>
            <div className="admin-filters panel">
              <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search category or prompt" />
              <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value as TaskType | "")}><option value="">All tasks</option><option value="EMAIL">Task 1</option><option value="SURVEY">Task 2</option></select>
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as TaskStatus | "")}><option value="">All statuses</option><option value="DRAFT">Draft</option><option value="IN_REVIEW">In review</option><option value="APPROVED">Approved</option><option value="RETIRED">Retired</option></select>
            </div>
            <div className="admin-task-list">
              {tasks.map((task) => <article className="panel admin-task-card" key={task.id}>
                <div className="admin-task-meta"><span className={`status-pill ${task.status.toLowerCase()}`}>{task.status.replace("_", " ")}</span><span>{task.source}</span><span>{task.task_type === "EMAIL" ? "Task 1" : "Task 2"}</span></div>
                <h3>{task.category}</h3><p>{task.prompt}</p>
                <div className="admin-tags">{task.focus_tags.map((tag) => <span key={tag}>{tag.replaceAll("_", " ")}</span>)}</div>
                <footer><span>{task.assignment_count} assigned · {task.submission_count} submitted</span><button type="button" onClick={() => editTask(task)}>Open editor →</button></footer>
              </article>)}
              {!tasks.length && <div className="panel usage-empty">No exercises match these filters.</div>}
            </div>
          </section>
        </>}
      </div>
    </main>
  );
}
