"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import Brand from "../../components/Brand";
import { PracticeSession, TASK_CONFIG, WritingAttempt, WritingHelpContent, countWords, formatTime, parseTaskNumber, readSession, sessionFromAttempt, writeSession } from "../../lib/practice";

const HELP_SECTIONS = [
  ["structure", "Recommended Structure"], ["frameworks", "Sentence Frameworks"],
  ["vocabulary", "Vocabulary & Phrase Bank"], ["task_checklist", "Task-Completion Checklist"],
  ["quality_checklist", "Level 12 Quality Checklist"],
] as const;

export default function TimedPracticePage() {
  const params = useParams<{ taskNumber: string }>();
  const router = useRouter();
  const taskNumber = parseTaskNumber(params.taskNumber);
  const [session, setSession] = useState<PracticeSession | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [locked, setLocked] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [saveState, setSaveState] = useState("Saved");
  const [help, setHelp] = useState<WritingHelpContent | null>(null);
  const [helpError, setHelpError] = useState<string | null>(null);
  const [helpIsDemo, setHelpIsDemo] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [openSections, setOpenSections] = useState<string[]>([]);
  const [usedSections, setUsedSections] = useState<string[]>([]);
  const [panelOpenCount, setPanelOpenCount] = useState(0);
  const visibleSeconds = useRef(0);
  const visibleStarted = useRef<number | null>(null);
  const finishStarted = useRef(false);

  useEffect(() => {
    if (!taskNumber) { router.replace("/account"); return; }
    const attemptId = readSession(taskNumber)?.attemptId;
    if (!attemptId) { router.replace(`/practice/${taskNumber}/intro`); return; }
    fetch(`/api/writing/attempts/${attemptId}`, { credentials: "include", cache: "no-store" }).then(async (response) => {
      if (response.status === 401) { router.replace("/login"); return; }
      if (!response.ok) { router.replace(`/practice/${taskNumber}/intro`); return; }
      const attempt = await response.json() as WritingAttempt;
      const restored = sessionFromAttempt(taskNumber, attempt);
      if (restored.stage === "intro") { router.replace(`/practice/${taskNumber}/intro`); return; }
      if (restored.stage === "result") { writeSession(restored); router.replace(`/practice/${taskNumber}/result`); return; }
      setUsedSections(attempt.help_sections_opened); setPanelOpenCount(attempt.help_panel_open_count); visibleSeconds.current = attempt.help_visible_seconds;
      writeSession(restored); setSession(restored);
    }).catch(() => setStatus("We could not restore this attempt. Please check your connection."));
  }, [router, taskNumber]);

  useEffect(() => {
    if (!session?.helpModeEnabled) return;
    fetch(`/api/writing/attempts/${session.attemptId}/help`, { credentials: "include", cache: "no-store" }).then(async (response) => {
      if (!response.ok) throw new Error("Guided help is temporarily unavailable. You can continue writing normally.");
      const body = await response.json() as { content: WritingHelpContent; is_demo: boolean };
      setHelp(body.content); setHelpIsDemo(body.is_demo);
    }).catch((reason: Error) => setHelpError(reason.message));
  }, [session?.attemptId, session?.helpModeEnabled]);

  const currentVisibleSeconds = useCallback(() => visibleSeconds.current + (visibleStarted.current ? Math.floor((Date.now() - visibleStarted.current) / 1000) : 0), []);

  const save = useCallback(async (active: PracticeSession) => {
    setSaveState("Saving…");
    try {
      const response = await fetch(`/api/writing/attempts/${active.attemptId}/autosave`, {
        method: "PATCH", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answer_text: active.answer, help_sections_opened: usedSections, help_panel_open_count: panelOpenCount, help_visible_seconds: currentVisibleSeconds() }),
      });
      if (response.ok) setSaveState("Saved"); else if (response.status !== 409) setSaveState("Save unavailable");
    } catch { setSaveState("Save unavailable"); }
  }, [currentVisibleSeconds, panelOpenCount, usedSections]);

  useEffect(() => {
    if (!session || session.stage !== "writing") return;
    setSaveState("Unsaved changes");
    const timeout = window.setTimeout(() => void save(session), 1500);
    return () => window.clearTimeout(timeout);
  }, [session?.answer, usedSections, panelOpenCount, save]);

  const finish = useCallback(async (reason: "submitted" | "expired") => {
    if (!session || !taskNumber || finishStarted.current) return;
    finishStarted.current = true; setLocked(true);
    setStatus(reason === "expired" ? "Time is up. Locking and submitting your saved response…" : "Submitting your response…");
    try {
      const response = await fetch(`/api/writing/attempts/${session.attemptId}/submit`, {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answer_text: session.answer, help_sections_opened: usedSections, help_panel_open_count: panelOpenCount, help_visible_seconds: currentVisibleSeconds() }),
      });
      if (!response.ok) throw new Error("Your response could not be saved.");
      const attempt = await response.json() as WritingAttempt;
      const submissionId = attempt.submission?.id;
      const saved: PracticeSession = { ...session, stage: "result", finishReason: submissionId ? reason : "blank", submissionId };
      writeSession(saved);
      if (submissionId) {
        setStatus("Response saved. Preparing your CELPIP feedback…");
        const evaluationResponse = await fetch(`/api/writing/submissions/${submissionId}/evaluation`, { method: "POST", credentials: "include" });
        if (evaluationResponse.ok) saved.evaluation = await evaluationResponse.json();
        else if (evaluationResponse.status === 409) saved.evaluationError = "Add a target CELPIP score to receive an evaluation.";
        else if (evaluationResponse.status === 503) saved.evaluationError = "The evaluation service is temporarily unavailable. Your response is saved.";
        else saved.evaluationError = "We saved your response, but feedback could not be generated yet.";
      }
      writeSession(saved); router.replace(`/practice/${taskNumber}/result`);
    } catch (value) { finishStarted.current = false; setLocked(false); setStatus(value instanceof Error ? value.message : "Submission failed. Please try again."); }
  }, [currentVisibleSeconds, panelOpenCount, router, session, taskNumber, usedSections]);

  useEffect(() => {
    if (!session?.writingEndsAt || session.stage !== "writing") return;
    const writingEndsAt = session.writingEndsAt;
    function tick() { const seconds = Math.max(0, Math.ceil((writingEndsAt - Date.now()) / 1000)); setRemaining(seconds); if (seconds === 0) void finish("expired"); }
    tick(); const timer = window.setInterval(tick, 250); return () => window.clearInterval(timer);
  }, [finish, session]);

  function updateAnswer(answer: string) { if (!session || locked) return; const updated = { ...session, answer }; setSession(updated); writeSession(updated); }
  function togglePanel() {
    if (!panelOpen) { setPanelOpenCount((value) => value + 1); visibleStarted.current = Date.now(); }
    else if (visibleStarted.current) { visibleSeconds.current += Math.floor((Date.now() - visibleStarted.current) / 1000); visibleStarted.current = null; }
    setPanelOpen((value) => !value);
  }
  function toggleSection(id: string) {
    setOpenSections((items) => {
      const opening = !items.includes(id);
      if (opening) setUsedSections((used) => used.includes(id) ? used : [...used, id]);
      return opening ? [...items, id] : items.filter((item) => item !== id);
    });
  }

  if (!taskNumber || !session) return <main className="state-page"><div className="loader" /><p>Opening the timed task…</p></main>;
  const config = TASK_CONFIG[taskNumber]; const words = countWords(session.answer); const warning = remaining <= 5 * 60;

  return <main className={`exam-workspace${locked ? " exam-locked" : ""}`}>
    <header className="exam-toolbar"><Brand /><div className="exam-task-label"><span>Writing</span><strong>Task {taskNumber} of 2</strong></div><span className={`attempt-badge ${session.helpModeEnabled ? "guided" : "simulation"}`}>{session.helpModeEnabled ? "Guided Practice" : "Test Simulation"}</span><div className={`exam-timer${warning ? " timer-warning" : ""}`} aria-live="polite"><span>Time remaining</span><strong>{formatTime(remaining)}</strong></div></header>
    <div className={`exam-body${session.helpModeEnabled ? " with-help" : ""}`}>
      <section className="exam-prompt"><div className="prompt-heading"><p className="eyebrow">TASK {taskNumber}</p><h1>{config.title}</h1><span>{session.task.category}</span></div><div className="prompt-copy"><p>{session.task.prompt}</p></div><div className="prompt-reminders"><strong>Remember</strong><span>Address every part of the task.</span><span>Write 150–200 words.</span><span>Leave time to review your response.</span></div></section>
      <section className="exam-response"><div className="response-heading"><div><p className="eyebrow">YOUR RESPONSE</p><h2>Write your answer</h2><small aria-live="polite">{saveState}</small></div><div className={`word-count${words >= 150 && words <= 200 ? " in-range" : ""}`}><strong>{words}</strong><span>words</span></div></div><textarea aria-label="Writing response" value={session.answer} onChange={(event) => updateAnswer(event.target.value)} disabled={locked} spellCheck autoFocus placeholder={taskNumber === 1 ? "Begin your email here…" : "State your choice and explain your reasons…"} /><div className="response-footer"><span>{words < 150 ? `${150 - words} words to the suggested minimum` : words > 200 ? `${words - 200} words over the suggested maximum` : "Within the suggested word range"}</span><button type="button" onClick={() => void finish("submitted")} disabled={locked || !session.answer.trim()}>Submit and get results</button></div></section>
      {session.helpModeEnabled && <aside className={`help-panel${panelOpen ? " open" : ""}`} aria-label="Guided Practice help"><button className="help-panel-toggle" type="button" aria-expanded={panelOpen} onClick={togglePanel}>{panelOpen ? "Close Help Mode" : "Open Help Mode"}</button><div className="help-panel-content"><div className="help-panel-heading"><p className="eyebrow">GUIDED PRACTICE</p><h2>Help Mode</h2>{helpIsDemo && <span>Demo guidance</span>}<p>Strong scores depend on accurate, natural, appropriate language—not mechanically inserting advanced words.</p></div>{helpError && <p className="help-error" role="status">{helpError}</p>}{!help && !helpError && <p>Preparing task-specific guidance…</p>}{help && HELP_SECTIONS.map(([id, title]) => <section className="help-section" key={id}><button type="button" aria-expanded={openSections.includes(id)} onClick={() => toggleSection(id)}><span>{title}</span><b>{openSections.includes(id) ? "−" : "+"}</b></button>{openSections.includes(id) && <div>{id === "structure" && help.recommended_structure.map((item) => <article key={item.section}><strong>{item.section}</strong><p>{item.guidance}</p></article>)}{id === "frameworks" && help.sentence_frameworks.map((item) => <article key={item.framework}><small>{item.purpose}</small><p>{item.framework}</p></article>)}{id === "vocabulary" && help.vocabulary_groups.map((group) => <article key={group.category}><strong>{group.category}</strong>{group.items.map((item) => <div className="vocab-item" key={item.phrase}><b>{item.phrase}</b><p>{item.meaning}</p><em>{item.example}</em><small>{item.usage_note}</small></div>)}</article>)}{id === "task_checklist" && help.task_completion_checklist.map((item) => <label key={item.label}><input type="checkbox" />{item.label}</label>)}{id === "quality_checklist" && help.level_12_quality_checklist.map((item) => <label key={item.label}><input type="checkbox" />{item.label}</label>)}</div>}</section>)}</div></aside>}
    </div>
    {locked && <div className="lock-overlay" role="status"><div className="loader" /><h2>Response locked</h2><p>{status}</p></div>}{!locked && status && <div className="exam-status" role="alert">{status}</div>}
  </main>;
}
