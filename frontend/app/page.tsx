"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import Brand from "./components/Brand";

type Task = {
  id: string;
  task_type: "EMAIL" | "SURVEY";
  category: string;
  difficulty: string;
  prompt: string;
};

type Evaluation = {
  estimated_score: number;
  task_fulfillment_score: number;
  organization_score: number;
  vocabulary_score: number;
  grammar_score: number;
  strengths: string[];
  weaknesses: string[];
  corrections: { original: string; revised: string }[];
  recommended_exercises: string[];
};

type Submission = {
  id: string;
  task: Task;
  answer_text: string;
  word_count: number;
  submitted_at: string;
  evaluation: Evaluation;
};

type Dashboard = {
  student: {
    first_name: string;
    current_score: number;
    target_score: number;
    recommended_strategy: string;
    focus_areas: string[];
  };
  progress: {
    total_submissions: number;
    evaluated_submissions: number;
    average_score: number;
    best_score: number;
  };
  exercises: Task[];
  submissions: Submission[];
  score_history: { date: string; score: number }[];
};

function ScoreRing({ score, target }: { score: number; target: number }) {
  const progress = Math.min((score / 12) * 360, 360);
  return (
    <div className="score-ring" style={{ "--score-progress": `${progress}deg` } as React.CSSProperties}>
      <div>
        <strong>{score}</strong>
        <span>of {target} target</span>
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <main className="state-page">
      <div className="loader" />
      <p>Loading your demo workspace…</p>
    </main>
  );
}

export default function Home() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [viewer, setViewer] = useState<{ first_name: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/demo/dashboard", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Demo API returned ${response.status}`);
        return response.json() as Promise<Dashboard>;
      })
      .then(setDashboard)
      .catch((reason: Error) => setError(reason.message));
    fetch("/api/auth/me", { credentials: "include", cache: "no-store" })
      .then((response) => response.ok ? response.json() : null)
      .then(setViewer)
      .catch(() => null);
  }, []);

  if (error) {
    return (
      <main className="state-page">
        <p className="eyebrow">DEMO UNAVAILABLE</p>
        <h1>We could not load the practice dashboard.</h1>
        <p>{error}. Confirm the database migrations and demo mode are enabled.</p>
        <a className="button" href="/api/health">Check API health</a>
      </main>
    );
  }
  if (!dashboard) return <LoadingState />;

  return (
    <main className="dashboard-shell">
      <header className="topbar">
        <Brand />
        <div className="demo-badge"><span /> Demo data · no AI request</div>
        <nav className="landing-auth" aria-label="Account">
          {viewer ? (
            <Link className="nav-primary" href="/account">My account</Link>
          ) : (
            <>
              <Link href="/login">Sign in</Link>
              <Link className="nav-primary" href="/register">Create account</Link>
            </>
          )}
        </nav>
      </header>

      <div id="top" className="dashboard-grid">
        <section className="hero panel">
          <div>
            <p className="eyebrow">WRITING DASHBOARD</p>
            <h1>Good morning, {dashboard.student.first_name}.</h1>
            <p className="hero-copy">
              You’re building momentum. Your latest writing is one band closer to your goal.
            </p>
            <div className="hero-actions">
              <a className="button primary" href="#exercises">Start an exercise</a>
              <a className="text-link" href="#submissions">Review feedback →</a>
            </div>
          </div>
          <ScoreRing score={dashboard.student.current_score} target={dashboard.student.target_score} />
        </section>

        <section className="metrics" aria-label="Writing progress summary">
          <article className="metric panel">
            <span>Average score</span><strong>{dashboard.progress.average_score}</strong>
            <small>across evaluated writing</small>
          </article>
          <article className="metric panel">
            <span>Best score</span><strong>{dashboard.progress.best_score}</strong>
            <small>personal best</small>
          </article>
          <article className="metric panel">
            <span>Completed</span><strong>{dashboard.progress.evaluated_submissions}</strong>
            <small>exercises with feedback</small>
          </article>
        </section>

        <section className="progress-panel panel">
          <div className="section-heading">
            <div><p className="eyebrow">PROGRESS</p><h2>Your score trend</h2></div>
            <span className="positive">↑ 1.5 bands this month</span>
          </div>
          <div className="chart" aria-label="Score history">
            {dashboard.score_history.map((point) => (
              <div className="chart-point" key={point.date}>
                <span className="chart-score">{point.score}</span>
                <div className="bar-track"><div className="bar" style={{ height: `${(point.score / 12) * 100}%` }} /></div>
                <small>{new Date(`${point.date}T12:00:00`).toLocaleDateString("en-CA", { month: "short", day: "numeric" })}</small>
              </div>
            ))}
          </div>
        </section>

        <aside className="strategy panel">
          <p className="eyebrow">NEXT BEST STEP</p>
          <h2>Sharpen your supporting details</h2>
          <p>{dashboard.student.recommended_strategy}</p>
          <div className="focus-list">
            {dashboard.student.focus_areas.map((focus) => <span key={focus}>{focus}</span>)}
          </div>
        </aside>

        <section id="exercises" className="wide-section">
          <div className="section-heading">
            <div><p className="eyebrow">PRACTICE LIBRARY</p><h2>Demo exercises</h2></div>
            <span>{dashboard.exercises.length} prompts ready</span>
          </div>
          <div className="exercise-grid">
            {dashboard.exercises.map((exercise, index) => (
              <article className="exercise-card panel" key={exercise.id}>
                <div className="exercise-top">
                  <span className={`task-icon ${exercise.task_type.toLowerCase()}`}>{exercise.task_type === "EMAIL" ? "✉" : "◫"}</span>
                  <span className="difficulty">{exercise.difficulty.toLowerCase()}</span>
                </div>
                <p className="exercise-number">Task {index + 1} · {exercise.task_type}</p>
                <h3>{exercise.category}</h3>
                <p>{exercise.prompt}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="submissions" className="wide-section">
          <div className="section-heading">
            <div><p className="eyebrow">RECENT WORK</p><h2>Submissions and feedback</h2></div>
            <span>Pre-evaluated demo results</span>
          </div>
          <div className="submission-list">
            {dashboard.submissions.map((submission) => (
              <article className="submission panel" key={submission.id}>
                <div className="submission-main">
                  <div className="submission-title">
                    <div><span>{submission.task.task_type}</span><h3>{submission.task.category}</h3></div>
                    <div className="score-pill"><strong>{submission.evaluation.estimated_score}</strong><span>/ 12</span></div>
                  </div>
                  <p className="date-line">{new Date(submission.submitted_at).toLocaleDateString("en-CA", { month: "long", day: "numeric", year: "numeric" })} · {submission.word_count} words</p>
                  <blockquote>{submission.answer_text}</blockquote>
                  <div className="rubric">
                    {[
                      ["Task", submission.evaluation.task_fulfillment_score],
                      ["Organization", submission.evaluation.organization_score],
                      ["Vocabulary", submission.evaluation.vocabulary_score],
                      ["Grammar", submission.evaluation.grammar_score],
                    ].map(([label, value]) => (
                      <div key={label}><span>{label}</span><strong>{value}</strong></div>
                    ))}
                  </div>
                </div>
                <div className="feedback">
                  <p className="feedback-label success">✓ What worked</p>
                  <ul>{submission.evaluation.strengths.map((item) => <li key={item}>{item}</li>)}</ul>
                  <p className="feedback-label improve">↗ Improve next</p>
                  <ul>{submission.evaluation.weaknesses.map((item) => <li key={item}>{item}</li>)}</ul>
                  <div className="correction">
                    <span>Suggested revision</span>
                    <del>{submission.evaluation.corrections[0].original}</del>
                    <p>{submission.evaluation.corrections[0].revised}</p>
                  </div>
                  <p className="feedback-label practice">Practice</p>
                  <ul>{submission.evaluation.recommended_exercises.map((item) => <li key={item}>{item}</li>)}</ul>
                </div>
              </article>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
