"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import Brand from "../../components/Brand";
import {
  PracticeSession,
  TASK_CONFIG,
  countWords,
  formatTime,
  parseTaskNumber,
  readSession,
  writeSession,
} from "../../lib/practice";

export default function TimedPracticePage() {
  const params = useParams<{ taskNumber: string }>();
  const router = useRouter();
  const taskNumber = parseTaskNumber(params.taskNumber);
  const [session, setSession] = useState<PracticeSession | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [locked, setLocked] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const finishStarted = useRef(false);

  useEffect(() => {
    if (!taskNumber) {
      router.replace("/account");
      return;
    }
    const stored = readSession(taskNumber);
    if (!stored) {
      router.replace(`/practice/${taskNumber}/intro`);
      return;
    }
    if (stored.stage === "result") {
      router.replace(`/practice/${taskNumber}/result`);
      return;
    }
    if (stored.stage === "submitting") {
      const interrupted: PracticeSession = {
        ...stored,
        stage: "result",
        evaluationError: stored.submissionId
          ? "Feedback was interrupted. You can try the evaluation again."
          : "Submission was interrupted before it could be confirmed. Check your recent submissions before trying again.",
      };
      writeSession(interrupted);
      router.replace(`/practice/${taskNumber}/result`);
      return;
    }
    if (stored.stage === "intro") {
      router.replace(`/practice/${taskNumber}/intro`);
      return;
    }
    const active = stored.writingEndsAt ? stored : {
      ...stored,
      stage: "writing" as const,
      writingEndsAt: Date.now() + TASK_CONFIG[taskNumber].durationSeconds * 1000,
    };
    writeSession(active);
    setSession(active);
  }, [router, taskNumber]);

  const finish = useCallback(async (reason: "submitted" | "expired") => {
    if (!session || !taskNumber || finishStarted.current) return;
    finishStarted.current = true;
    setLocked(true);
    setStatus(reason === "expired" ? "Time is up. Locking and submitting your response…" : "Submitting your response…");

    if (!session.answer.trim()) {
      const blank: PracticeSession = { ...session, stage: "result", finishReason: "blank" };
      writeSession(blank);
      setSession(blank);
      router.replace(`/practice/${taskNumber}/result`);
      return;
    }

    const submitting: PracticeSession = { ...session, stage: "submitting", finishReason: reason };
    writeSession(submitting);
    try {
      const submissionResponse = await fetch("/api/writing/submissions", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: session.task.id, answer_text: session.answer }),
      });
      if (submissionResponse.status === 401) {
        router.replace("/login");
        return;
      }
      if (!submissionResponse.ok) throw new Error("Your response could not be saved.");
      const submission = await submissionResponse.json() as { id: string };
      setStatus("Response saved. Preparing your CELPIP feedback…");
      const saved: PracticeSession = {
        ...submitting,
        stage: "result",
        submissionId: submission.id,
        evaluationError: "Feedback is still being prepared. Try again if it does not appear.",
      };
      writeSession(saved);

      const evaluationResponse = await fetch(`/api/writing/submissions/${submission.id}/evaluation`, {
        method: "POST",
        credentials: "include",
      });
      let evaluation;
      let evaluationError;
      if (evaluationResponse.ok) {
        evaluation = await evaluationResponse.json();
      } else if (evaluationResponse.status === 409) {
        evaluationError = "Add a target CELPIP score to receive an evaluation.";
      } else if (evaluationResponse.status === 503) {
        evaluationError = "The evaluation service is temporarily unavailable. Your response is saved.";
      } else {
        evaluationError = "We saved your response, but feedback could not be generated yet.";
      }
      const result: PracticeSession = {
        ...saved,
        stage: "result",
        evaluation,
        evaluationError,
      };
      writeSession(result);
      setSession(result);
      router.replace(`/practice/${taskNumber}/result`);
    } catch (reasonValue) {
      finishStarted.current = false;
      setLocked(false);
      setStatus(reasonValue instanceof Error ? reasonValue.message : "Submission failed. Please try again.");
    }
  }, [router, session, taskNumber]);

  useEffect(() => {
    if (!session?.writingEndsAt || session.stage !== "writing") return;
    function tick() {
      const seconds = Math.max(0, Math.ceil((session!.writingEndsAt! - Date.now()) / 1000));
      setRemaining(seconds);
      if (seconds === 0) void finish("expired");
    }
    tick();
    const timer = window.setInterval(tick, 250);
    return () => window.clearInterval(timer);
  }, [finish, session]);

  function updateAnswer(value: string) {
    if (!session || locked) return;
    const updated = { ...session, answer: value };
    setSession(updated);
    writeSession(updated);
  }

  if (!taskNumber || !session) return <main className="state-page"><div className="loader" /><p>Opening the timed task…</p></main>;

  const config = TASK_CONFIG[taskNumber];
  const words = countWords(session.answer);
  const warning = remaining <= 5 * 60;

  return (
    <main className={`exam-workspace${locked ? " exam-locked" : ""}`}>
      <header className="exam-toolbar">
        <Brand />
        <div className="exam-task-label"><span>Writing</span><strong>Task {taskNumber} of 2</strong></div>
        <div className={`exam-timer${warning ? " timer-warning" : ""}`} aria-live="polite">
          <span>Time remaining</span><strong>{formatTime(remaining)}</strong>
        </div>
      </header>

      <div className="exam-body">
        <section className="exam-prompt">
          <div className="prompt-heading"><p className="eyebrow">TASK {taskNumber}</p><h1>{config.title}</h1><span>{session.task.category}</span></div>
          <div className="prompt-copy"><p>{session.task.prompt}</p></div>
          <div className="prompt-reminders">
            <strong>Remember</strong>
            <span>Address every part of the task.</span>
            <span>Write 150–200 words.</span>
            <span>Leave time to review your response.</span>
          </div>
        </section>

        <section className="exam-response">
          <div className="response-heading"><div><p className="eyebrow">YOUR RESPONSE</p><h2>Write your answer</h2></div><div className={`word-count${words >= 150 && words <= 200 ? " in-range" : ""}`}><strong>{words}</strong><span>words</span></div></div>
          <textarea
            aria-label="Writing response"
            value={session.answer}
            onChange={(event) => updateAnswer(event.target.value)}
            disabled={locked}
            spellCheck
            autoFocus
            placeholder={taskNumber === 1 ? "Begin your email here…" : "State your choice and explain your reasons…"}
          />
          <div className="response-footer">
            <span>{words < 150 ? `${150 - words} words to the suggested minimum` : words > 200 ? `${words - 200} words over the suggested maximum` : "Within the suggested word range"}</span>
            <button type="button" onClick={() => void finish("submitted")} disabled={locked || !session.answer.trim()}>Submit and get results</button>
          </div>
        </section>
      </div>

      {locked && <div className="lock-overlay" role="status"><div className="loader" /><h2>Response locked</h2><p>{status}</p></div>}
      {!locked && status && <div className="exam-status" role="alert">{status}</div>}
    </main>
  );
}
