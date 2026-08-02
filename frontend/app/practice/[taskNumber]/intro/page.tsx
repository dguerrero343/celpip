"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import Brand from "../../../components/Brand";
import {
  INTRO_SECONDS,
  PracticeSession,
  PracticeTask,
  TASK_CONFIG,
  TaskNumber,
  formatTime,
  parseTaskNumber,
  readSession,
  writeSession,
} from "../../../lib/practice";

export default function PracticeIntroPage() {
  const params = useParams<{ taskNumber: string }>();
  const router = useRouter();
  const taskNumber = parseTaskNumber(params.taskNumber);
  const [session, setSession] = useState<PracticeSession | null>(null);
  const [remaining, setRemaining] = useState(INTRO_SECONDS);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!taskNumber) {
      router.replace("/account");
      return;
    }
    async function prepare(validTaskNumber: TaskNumber) {
      const existing = readSession(validTaskNumber);
      if (existing && (existing.stage === "intro" || existing.stage === "writing")) {
        if (existing.stage === "writing") {
          router.replace(`/practice/${validTaskNumber}`);
          return;
        }
        setSession(existing);
        return;
      }
      const config = TASK_CONFIG[validTaskNumber];
      const response = await fetch("/api/writing/tasks/next", {
        method: "POST",
        credentials: "include",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_type: config.type }),
      });
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (!response.ok) {
        const failure = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(failure?.detail || "We could not prepare this practice task.");
      }
      const body = await response.json() as { assignment_id: string; task: PracticeTask };
      const task = body.task;
      const next: PracticeSession = {
        taskNumber: validTaskNumber,
        task,
        introEndsAt: Date.now() + INTRO_SECONDS * 1000,
        writingEndsAt: null,
        answer: "",
        stage: "intro",
      };
      writeSession(next);
      setSession(next);
    }
    prepare(taskNumber).catch((reason: Error) => setError(reason.message));
  }, [router, taskNumber]);

  useEffect(() => {
    if (!session || !taskNumber) return;
    function tick() {
      const seconds = Math.max(0, Math.ceil((session!.introEndsAt - Date.now()) / 1000));
      setRemaining(seconds);
      if (seconds === 0) {
        const started: PracticeSession = {
          ...session!,
          stage: "writing",
          writingEndsAt: Date.now() + TASK_CONFIG[taskNumber!].durationSeconds * 1000,
        };
        writeSession(started);
        router.replace(`/practice/${taskNumber}`);
      }
    }
    tick();
    const timer = window.setInterval(tick, 250);
    return () => window.clearInterval(timer);
  }, [router, session, taskNumber]);

  if (error) return <main className="state-page"><p className="eyebrow">PRACTICE ERROR</p><h1>We could not start this task.</h1><p>{error}</p><a className="button" href="/account">Return to your account</a></main>;
  if (!taskNumber || !session) return <main className="state-page"><div className="loader" /><p>Preparing your task…</p></main>;

  const config = TASK_CONFIG[taskNumber];
  const progress = ((INTRO_SECONDS - remaining) / INTRO_SECONDS) * 360;

  return (
    <main className="exam-intro">
      <header className="exam-header"><Brand /><span>CELPIP Writing Simulation</span></header>
      <section className="intro-card">
        <div className="intro-countdown" style={{ "--intro-progress": `${progress}deg` } as React.CSSProperties}>
          <div><strong>{formatTime(remaining)}</strong><span>before task begins</span></div>
        </div>
        <p className="eyebrow">TASK {taskNumber} INTRODUCTION</p>
        <h1>{config.title}</h1>
        <p className="intro-lead">Read the instructions carefully. Your writing timer starts automatically when this introduction ends.</p>
        <div className="intro-details">
          <article><span>Time</span><strong>{config.durationLabel}</strong></article>
          <article><span>Suggested length</span><strong>150–200 words</strong></article>
          <article><span>Task type</span><strong>{config.title}</strong></article>
        </div>
        <div className="intro-instructions">
          <h2>What you need to do</h2>
          <p>{config.instruction}</p>
          <ul>
            <li>Plan briefly, then write a complete response.</li>
            <li>Watch the automatic word counter and timer.</li>
            <li>Your response locks and submits automatically at 00:00.</li>
          </ul>
        </div>
        <div className="intro-wait"><span /><p>The task prompt will appear automatically.</p></div>
      </section>
    </main>
  );
}
