"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import Brand from "../components/Brand";

type User = {
  first_name: string;
  email: string;
  current_celpip_score: number | null;
  target_celpip_score: number | null;
  target_exam_date: string | null;
  role: "STUDENT" | "ADMIN";
};

type Task = {
  id: string;
  task_type: "EMAIL" | "SURVEY";
  category: string;
  difficulty: string;
  prompt: string;
};

type Submission = {
  id: string;
  task: Task;
  word_count: number;
  submitted_at: string;
  evaluation: { estimated_score: number } | null;
  attempt_type: "GUIDED_PRACTICE" | "TEST_SIMULATION";
};

type ProgressSummary = { total_submissions: number; evaluated_submissions: number; average_score: number | null; best_score: number | null };

type Progress = {
  total_submissions: number;
  evaluated_submissions: number;
  current_score: number | null;
  target_score: number | null;
  average_score: number | null;
  best_score: number | null;
  test_simulation: ProgressSummary;
  guided_practice: ProgressSummary;
};

type AccountData = {
  user: User;
  submissions: Submission[];
  progress: Progress;
};

export default function AccountPage() {
  const router = useRouter();
  const [data, setData] = useState<AccountData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    async function load() {
      const me = await fetch("/api/auth/me", { credentials: "include", cache: "no-store" });
      if (me.status === 401) {
        router.replace("/login");
        return;
      }
      if (!me.ok) throw new Error("We could not load your account.");
      const [user, progressResponse, submissionResponse] = await Promise.all([
        me.json() as Promise<User>,
        fetch("/api/writing/progress", { credentials: "include", cache: "no-store" }),
        fetch("/api/writing/submissions?limit=5", { credentials: "include", cache: "no-store" }),
      ]);
      if (!progressResponse.ok || !submissionResponse.ok) {
        throw new Error("We could not load your writing workspace.");
      }
      const progress = await progressResponse.json();
      const submissionBody = await submissionResponse.json();
      setData({ user, progress, submissions: submissionBody.items });
    }
    load().catch((reason: Error) => setError(reason.message));
  }, [router]);

  async function logout() {
    setLoggingOut(true);
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    router.replace("/login");
    router.refresh();
  }

  if (error) {
    return (
      <main className="state-page">
        <p className="eyebrow">ACCOUNT ERROR</p>
        <h1>We could not open your workspace.</h1>
        <p>{error}</p>
        <button className="button" onClick={() => location.reload()}>Try again</button>
      </main>
    );
  }
  if (!data) {
    return <main className="state-page"><div className="loader" /><p>Opening your writing workspace…</p></main>;
  }

  const currentScore = data.progress.current_score ?? data.user.current_celpip_score;
  const targetScore = data.progress.target_score ?? data.user.target_celpip_score;

  return (
    <main className="account-shell">
      <header className="topbar account-topbar">
        <Brand />
        <nav className="account-nav" aria-label="Account navigation">
          <Link href="/">Demo</Link>
          <Link href="/usage">AI usage</Link>
          {data.user.role === "ADMIN" && <Link href="/admin">Admin</Link>}
          <span className="user-chip" aria-label={`Signed in as ${data.user.first_name}`}>
            {data.user.first_name.slice(0, 1).toUpperCase()}
          </span>
          <button type="button" onClick={logout} disabled={loggingOut}>
            {loggingOut ? "Signing out…" : "Sign out"}
          </button>
        </nav>
      </header>

      <div className="account-content">
        <section className="account-welcome">
          <div>
            <p className="eyebrow">MY WRITING PLAN</p>
            <h1>Welcome, {data.user.first_name}.</h1>
            <p>Your practice space is ready. Choose Task 1 or Task 2 and complete it under CELPIP timing.</p>
          </div>
          <a className="button primary" href="#practice">Choose a task</a>
        </section>

        <section className="account-metrics" aria-label="Personal progress">
          <article className="account-metric panel"><span>Current score</span><strong>{currentScore ?? "—"}</strong><small>{currentScore ? "latest writing level" : "Complete an evaluation"}</small></article>
          <article className="account-metric panel"><span>Target score</span><strong>{targetScore ?? "—"}</strong><small>{data.user.target_exam_date ? `Exam ${new Date(`${data.user.target_exam_date}T12:00:00`).toLocaleDateString("en-CA", { month: "short", day: "numeric" })}` : "Your CELPIP goal"}</small></article>
          <article className="account-metric panel"><span>Completed</span><strong>{data.progress.total_submissions}</strong><small>{data.progress.evaluated_submissions} with feedback</small></article>
          <article className="account-metric panel"><span>Best score</span><strong>{data.progress.best_score ?? "—"}</strong><small>{data.progress.average_score ? `${data.progress.average_score} average` : "Start practising"}</small></article>
        </section>

        <section className="mode-progress" aria-label="Progress by practice mode">
          <article className="panel"><span>Test Simulation</span><strong>{data.progress.test_simulation.average_score ?? "—"}</strong><small>{data.progress.test_simulation.total_submissions} attempts · average score</small></article>
          <article className="panel"><span>Guided Practice</span><strong>{data.progress.guided_practice.average_score ?? "—"}</strong><small>{data.progress.guided_practice.total_submissions} attempts · average score</small></article>
        </section>

        {data.user.role === "ADMIN" && <Link className="admin-account-callout panel" href="/admin">
          <div><p className="eyebrow">ADMINISTRATION</p><h2>Manage the question bank</h2><p>Create and review exercises, approve publication, monitor unseen inventory, generate AI drafts, and see organization token usage.</p></div>
          <strong>Open admin site →</strong>
        </Link>}

        <Link className="usage-callout panel" href="/usage">
          <div><p className="eyebrow">AI USAGE & COSTS</p><h2>See exactly what your evaluations use</h2><p>Review calls, input and output tokens, estimated cost, and administrator billing reconciliation.</p></div>
          <strong>Open usage report →</strong>
        </Link>

        <section id="practice" className="account-section">
          <div className="section-heading">
            <div><p className="eyebrow">PRACTICE</p><h2>Choose Task 1 or Task 2</h2></div>
            <span>Official CELPIP Writing format</span>
          </div>
          <div className="official-task-grid">
            <Link className="official-task panel" href="/practice/1/intro">
              <div className="official-task-top"><span className="official-task-number">01</span><span>27 minutes</span></div>
              <p className="eyebrow">TASK 1</p>
              <h3>Writing an Email</h3>
              <p>Read a situation and write an email that addresses every required point.</p>
              <div className="official-task-footer"><span>150–200 words</span><strong>Start Task 1 →</strong></div>
            </Link>
            <Link className="official-task panel" href="/practice/2/intro">
              <div className="official-task-top"><span className="official-task-number survey">02</span><span>26 minutes</span></div>
              <p className="eyebrow">TASK 2</p>
              <h3>Responding to Survey Questions</h3>
              <p>Choose one of two options and support your opinion with clear reasons and examples.</p>
              <div className="official-task-footer"><span>150–200 words</span><strong>Start Task 2 →</strong></div>
            </Link>
          </div>
        </section>

        <section className="account-section">
          <div className="section-heading"><div><p className="eyebrow">HISTORY</p><h2>Your recent submissions</h2></div></div>
          {data.submissions.length ? (
            <div className="account-history panel">
              {data.submissions.map((submission) => (
                <article key={submission.id}>
                  <div><span>{submission.attempt_type === "GUIDED_PRACTICE" ? "GUIDED PRACTICE" : "TEST SIMULATION"}</span><strong>{submission.task.category}</strong><small>{new Date(submission.submitted_at).toLocaleDateString("en-CA")} · {submission.word_count} words</small></div>
                  <Link className={`history-action${submission.evaluation ? " complete" : ""}`} href={`/submissions/${submission.id}`}>{submission.evaluation ? `${submission.evaluation.estimated_score} / 12 · Review` : "Generate feedback →"}</Link>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty-history panel"><span>✎</span><h3>Your first submission will appear here.</h3><p>Select a task above to begin building your writing history.</p></div>
          )}
        </section>
      </div>
    </main>
  );
}
