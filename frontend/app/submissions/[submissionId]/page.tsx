"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import Brand from "../../components/Brand";

type Evaluation = {
  estimated_score: number;
  task_fulfillment_score: number;
  organization_score: number;
  vocabulary_score: number;
  grammar_score: number;
  score_gap: number;
  strengths: string[];
  weaknesses: string[];
  corrections: Array<{ original: string; revised: string; explanation?: string }>;
  recommended_exercises: string[];
};

type Submission = {
  id: string;
  task: { task_type: "EMAIL" | "SURVEY"; category: string; prompt: string };
  answer_text: string;
  word_count: number;
  submitted_at: string;
  evaluation: Evaluation | null;
};

export default function SubmissionFeedbackPage() {
  const params = useParams<{ submissionId: string }>();
  const router = useRouter();
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      const response = await fetch(`/api/writing/submissions/${params.submissionId}`, {
        credentials: "include",
        cache: "no-store",
      });
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (!response.ok) throw new Error("We could not load this submission.");
      setSubmission(await response.json());
      setLoading(false);
    }
    load().catch((reason: Error) => {
      setError(reason.message);
      setLoading(false);
    });
  }, [params.submissionId, router]);

  async function generateFeedback() {
    if (!submission || generating) return;
    setGenerating(true);
    setError(null);
    try {
      const response = await fetch(`/api/writing/submissions/${submission.id}/evaluation`, {
        method: "POST",
        credentials: "include",
      });
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        if (response.status === 503) throw new Error("OpenAI evaluation is not configured.");
        if (response.status === 409) throw new Error("Set a target CELPIP score before requesting feedback.");
        throw new Error(body?.detail || "Feedback could not be generated. Please try again.");
      }
      setSubmission({ ...submission, evaluation: await response.json() });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Feedback could not be generated.");
    } finally {
      setGenerating(false);
    }
  }

  if (loading) return <main className="state-page"><div className="loader" /><p>Opening your submission…</p></main>;
  if (!submission) return <main className="state-page"><p className="eyebrow">SUBMISSION ERROR</p><h1>We could not open this response.</h1><p>{error}</p><Link className="button" href="/account">Return to your account</Link></main>;

  const evaluation = submission.evaluation;
  const title = submission.task.task_type === "EMAIL" ? "Writing an Email" : "Responding to Survey Questions";

  return (
    <main className="result-shell submission-review">
      <header className="topbar result-topbar"><Brand /><nav><Link href="/account">My account</Link></nav></header>
      <div className="result-content">
        <section className="result-hero panel">
          <div><p className="eyebrow">{submission.task.task_type} · {submission.task.category}</p><h1>{title}</h1><p>Submitted {new Date(submission.submitted_at).toLocaleDateString("en-CA", { year: "numeric", month: "long", day: "numeric" })}</p><div className="result-meta"><span>{submission.word_count} words</span><span>{evaluation ? "Feedback complete" : "Awaiting feedback"}</span></div></div>
          <div className="result-score"><strong>{evaluation?.estimated_score ?? "—"}</strong><span>{evaluation ? "estimated CELPIP score" : "not scored"}</span></div>
        </section>

        {!evaluation ? <section className="feedback-request panel">
          <div><p className="eyebrow">SAVED RESPONSE</p><h2>Generate your CELPIP feedback</h2><p>Your writing is safely stored. Generate a score, rubric breakdown, corrections, strengths, and recommended next steps.</p></div>
          <button type="button" onClick={() => void generateFeedback()} disabled={generating}>{generating ? "Evaluating your writing…" : "Generate feedback"}</button>
        </section> : <>
          <section className="score-breakdown">
            {[
              ["Task fulfillment", evaluation.task_fulfillment_score],
              ["Organization", evaluation.organization_score],
              ["Vocabulary", evaluation.vocabulary_score],
              ["Grammar", evaluation.grammar_score],
            ].map(([label, score]) => <article className="panel" key={label}><span>{label}</span><strong>{score}</strong><div><i style={{ width: `${(Number(score) / 12) * 100}%` }} /></div></article>)}
          </section>
          <section className="result-feedback-grid">
            <article className="panel result-feedback"><p className="feedback-label success">What worked</p><ul>{evaluation.strengths.map((item) => <li key={item}>{item}</li>)}</ul></article>
            <article className="panel result-feedback"><p className="feedback-label improve">Improve next</p><ul>{evaluation.weaknesses.map((item) => <li key={item}>{item}</li>)}</ul></article>
          </section>
          <section className="result-detail-grid">
            <article className="panel result-corrections"><p className="eyebrow">SUGGESTED CORRECTIONS</p><h2>Make the language stronger</h2>{evaluation.corrections.map((item, index) => <div key={`${item.original}-${index}`}><del>{item.original}</del><p>{item.revised}</p>{item.explanation && <small>{item.explanation}</small>}</div>)}</article>
            <article className="panel result-next"><p className="eyebrow">NEXT PRACTICE</p><h2>Recommended exercises</h2><ol>{evaluation.recommended_exercises.map((item) => <li key={item}>{item}</li>)}</ol></article>
          </section>
        </>}

        {error && <div className="form-alert" role="alert">{error}</div>}

        <details className="submission-context panel">
          <summary>Review prompt and response</summary>
          <div><p className="eyebrow">PROMPT</p><p>{submission.task.prompt}</p><p className="eyebrow">YOUR RESPONSE</p><div className="submission-answer">{submission.answer_text}</div></div>
        </details>
        <div className="result-actions"><Link className="text-action" href="/account">Return to my account</Link></div>
      </div>
    </main>
  );
}

