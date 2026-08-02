"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import Brand from "../../../components/Brand";
import {
  PracticeSession,
  TASK_CONFIG,
  countWords,
  parseTaskNumber,
  readSession,
  writeSession,
} from "../../../lib/practice";

export default function PracticeResultPage() {
  const params = useParams<{ taskNumber: string }>();
  const router = useRouter();
  const taskNumber = parseTaskNumber(params.taskNumber);
  const [session, setSession] = useState<PracticeSession | null>(null);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    if (!taskNumber) {
      router.replace("/account");
      return;
    }
    const stored = readSession(taskNumber);
    if (!stored || stored.stage !== "result") {
      router.replace("/account");
      return;
    }
    setSession(stored);
  }, [router, taskNumber]);

  async function retryEvaluation() {
    if (!session?.submissionId) return;
    setRetrying(true);
    try {
      const response = await fetch(`/api/writing/submissions/${session.submissionId}/evaluation`, {
        method: "POST",
        credentials: "include",
      });
      if (response.ok) {
        const updated = { ...session, evaluation: await response.json(), evaluationError: undefined };
        writeSession(updated);
        setSession(updated);
      } else {
        const updated = { ...session, evaluationError: "Feedback is still unavailable. Please try again later." };
        writeSession(updated);
        setSession(updated);
      }
    } catch {
      const updated = { ...session, evaluationError: "We could not reach the evaluation service. Please try again." };
      writeSession(updated);
      setSession(updated);
    } finally {
      setRetrying(false);
    }
  }

  if (!taskNumber || !session) return <main className="state-page"><div className="loader" /><p>Preparing your results…</p></main>;

  const config = TASK_CONFIG[taskNumber];
  const evaluation = session.evaluation;
  const words = countWords(session.answer);

  return (
    <main className="result-shell">
      <header className="topbar result-topbar"><Brand /><nav><Link href="/account">My account</Link></nav></header>
      <div className="result-content">
        <section className="result-hero panel">
          <div><p className="eyebrow">TASK {taskNumber} COMPLETE</p><h1>{config.title}</h1><p>{session.finishReason === "blank" ? "The timed session is locked. Start a new attempt when you are ready." : "Your response is locked and saved. Review the result, then use the recommendations in your next practice."}</p><div className="result-meta"><span>{words} words</span><span>{session.finishReason === "expired" ? "Submitted when time expired" : session.finishReason === "blank" ? "No response submitted" : "Submitted early"}</span></div></div>
          <div className="result-score"><strong>{evaluation?.estimated_score ?? "—"}</strong><span>{evaluation ? "estimated CELPIP score" : "not scored"}</span></div>
        </section>

        {!evaluation ? (
          <section className="result-message panel">
            <span>!</span>
            <div><h2>{session.finishReason === "blank" ? "This attempt could not be scored" : "Your response is saved"}</h2><p>{session.finishReason === "blank" ? "The timer finished without a written response. Start a new attempt when you are ready." : session.evaluationError || "Feedback is not available yet."}</p>{session.submissionId && <button type="button" onClick={retryEvaluation} disabled={retrying}>{retrying ? "Trying again…" : "Try evaluation again"}</button>}</div>
          </section>
        ) : (
          <>
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
              <article className="panel result-corrections"><p className="eyebrow">SUGGESTED CORRECTIONS</p><h2>Make the language stronger</h2>{evaluation.corrections.map((item) => <div key={`${item.original}-${item.revised}`}><del>{item.original}</del><p>{item.revised}</p></div>)}</article>
              <article className="panel result-next"><p className="eyebrow">NEXT PRACTICE</p><h2>Recommended exercises</h2><ol>{evaluation.recommended_exercises.map((item) => <li key={item}>{item}</li>)}</ol></article>
            </section>
          </>
        )}

        <div className="result-actions"><Link className="button" href={`/practice/${taskNumber}/intro`}>Practise Task {taskNumber} again</Link><Link className="text-action" href="/account">Return to my account</Link></div>
      </div>
    </main>
  );
}
