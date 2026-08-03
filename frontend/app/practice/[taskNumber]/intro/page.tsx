"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import Brand from "../../../components/Brand";
import { INTRO_SECONDS, PracticeSession, TASK_CONFIG, TaskNumber, WritingAttempt, formatTime, parseTaskNumber, sessionFromAttempt, writeSession } from "../../../lib/practice";

export default function PracticeIntroPage() {
  const params = useParams<{ taskNumber: string }>();
  const router = useRouter();
  const taskNumber = parseTaskNumber(params.taskNumber);
  const [session, setSession] = useState<PracticeSession | null>(null);
  const [remaining, setRemaining] = useState(INTRO_SECONDS);
  const [savingMode, setSavingMode] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!taskNumber) { router.replace("/account"); return; }
    async function prepare(validTaskNumber: TaskNumber) {
      const response = await fetch("/api/writing/attempts", {
        method: "POST", credentials: "include", cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_type: TASK_CONFIG[validTaskNumber].type }),
      });
      if (response.status === 401) { router.replace("/login"); return; }
      if (!response.ok) {
        const failure = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(failure?.detail || "We could not prepare this practice task.");
      }
      const attempt = await response.json() as WritingAttempt;
      const next = sessionFromAttempt(validTaskNumber, attempt);
      writeSession(next);
      if (next.stage !== "intro") { router.replace(`/practice/${validTaskNumber}`); return; }
      setSession(next);
    }
    prepare(taskNumber).catch((reason: Error) => setError(reason.message));
  }, [router, taskNumber]);

  useEffect(() => {
    if (!session || !taskNumber) return;
    const activeSession = session;
    function tick() {
      const seconds = Math.max(0, Math.ceil((activeSession.introEndsAt - Date.now()) / 1000));
      setRemaining(seconds);
      if (seconds === 0) {
        const started = { ...activeSession, stage: "writing" as const };
        writeSession(started);
        router.replace(`/practice/${taskNumber}`);
      }
    }
    tick();
    const timer = window.setInterval(tick, 250);
    return () => window.clearInterval(timer);
  }, [router, session, taskNumber]);

  async function changeMode(enabled: boolean) {
    if (!session || savingMode || remaining === 0) return;
    setSavingMode(true);
    try {
      const response = await fetch(`/api/writing/attempts/${session.attemptId}/mode`, {
        method: "PATCH", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ help_mode_enabled: enabled }),
      });
      if (!response.ok) throw new Error("The preparation period ended, so your mode is now locked.");
      const attempt = await response.json() as WritingAttempt;
      const updated = sessionFromAttempt(session.taskNumber, attempt);
      writeSession(updated); setSession(updated);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "We could not update Help Mode."); }
    finally { setSavingMode(false); }
  }

  if (error) return <main className="state-page"><p className="eyebrow">PRACTICE ERROR</p><h1>We could not start this task.</h1><p>{error}</p><a className="button" href="/account">Return to your account</a></main>;
  if (!taskNumber || !session) return <main className="state-page"><div className="loader" /><p>Preparing your task…</p></main>;
  const config = TASK_CONFIG[taskNumber];
  const progress = ((INTRO_SECONDS - remaining) / INTRO_SECONDS) * 360;

  return <main className="exam-intro">
    <header className="exam-header"><Brand /><span>CELPIP Writing Simulation</span></header>
    <section className="intro-card">
      <div className="intro-countdown" style={{ "--intro-progress": `${progress}deg` } as React.CSSProperties}><div><strong>{formatTime(remaining)}</strong><span>before task begins</span></div></div>
      <p className="eyebrow">TASK {taskNumber} INTRODUCTION</p><h1>{config.title}</h1>
      <p className="intro-lead">Read the instructions carefully. Your writing timer starts automatically when this introduction ends.</p>
      <div className="intro-details"><article><span>Time</span><strong>{config.durationLabel}</strong></article><article><span>Suggested length</span><strong>150–200 words</strong></article><article><span>Task type</span><strong>{config.title}</strong></article></div>
      <div className="intro-instructions"><h2>What you need to do</h2><p>{config.instruction}</p><ul><li>Plan briefly, then write a complete response.</li><li>Watch the automatic word counter and timer.</li><li>Your response locks and submits automatically at 00:00.</li></ul></div>
      <div className={`help-mode-choice${session.helpModeEnabled ? " selected" : ""}`}>
        <div><p className="eyebrow">OPTIONAL GUIDED PRACTICE</p><h2>Help Mode</h2><p>Receive a task-specific structure, vocabulary suggestions, and Level 12 writing guidance during this exercise.</p></div>
        <label className="help-toggle"><input type="checkbox" checked={session.helpModeEnabled} disabled={savingMode || remaining === 0} onChange={(event) => void changeMode(event.target.checked)} /><span aria-hidden="true" /><b>{session.helpModeEnabled ? "On" : "Off"}</b></label>
      </div>
      <p className="mode-confirmation" role="status">Selected: <strong>{session.helpModeEnabled ? "Guided Practice" : "Test Simulation"}</strong>. This choice locks when writing begins.</p>
      <div className="intro-wait"><span /><p>The task prompt will appear automatically.</p></div>
    </section>
  </main>;
}
