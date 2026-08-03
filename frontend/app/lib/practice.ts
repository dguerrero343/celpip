export const INTRO_SECONDS = 59;

export const TASK_CONFIG = {
  1: {
    number: 1,
    type: "EMAIL",
    title: "Writing an Email",
    durationSeconds: 27 * 60,
    durationLabel: "27 minutes",
    instruction: "Write an email about an everyday situation and address every point in the prompt.",
  },
  2: {
    number: 2,
    type: "SURVEY",
    title: "Responding to Survey Questions",
    durationSeconds: 26 * 60,
    durationLabel: "26 minutes",
    instruction: "Choose one survey option, state your position clearly, and support it with reasons and details.",
  },
} as const;

export type TaskNumber = keyof typeof TASK_CONFIG;

export type PracticeTask = {
  id: string;
  task_type: "EMAIL" | "SURVEY";
  category: string;
  difficulty: string;
  prompt: string;
};

export type PracticeEvaluation = {
  estimated_score: number;
  task_fulfillment_score: number;
  organization_score: number;
  vocabulary_score: number;
  grammar_score: number;
  score_gap: number;
  strengths: string[];
  weaknesses: string[];
  corrections: { original: string; revised: string }[];
  recommended_exercises: string[];
  weakness_signals: { skill: string; issue_key: string; label: string }[];
  next_objective: { skill: string; objective: string; success_criteria: string };
  previous_objective_assessment: { status: string; explanation: string };
  evaluator_prompt_version: string;
};

export type AttemptType = "GUIDED_PRACTICE" | "TEST_SIMULATION";
export type AttemptStatus = "PREPARING" | "WRITING" | "SUBMITTED" | "EXPIRED";

export type WritingAttempt = {
  id: string;
  task: PracticeTask;
  help_mode_enabled: boolean;
  attempt_type: AttemptType;
  status: AttemptStatus;
  preparation_started_at: string;
  preparation_expires_at: string;
  writing_started_at: string;
  writing_expires_at: string;
  submitted_at: string | null;
  answer_text: string;
  word_count: number;
  help_sections_opened: string[];
  help_panel_open_count: number;
  help_visible_seconds: number;
  last_saved_at: string | null;
  server_time: string;
  submission: { id: string } | null;
};

export type WritingHelpContent = {
  recommended_structure: { section: string; guidance: string }[];
  sentence_frameworks: { purpose: string; framework: string }[];
  vocabulary_groups: { category: string; items: { phrase: string; meaning: string; example: string; usage_note: string }[] }[];
  task_completion_checklist: { label: string }[];
  level_12_quality_checklist: { label: string }[];
};

export type PracticeSession = {
  attemptId: string;
  taskNumber: TaskNumber;
  task: PracticeTask;
  introEndsAt: number;
  writingEndsAt: number | null;
  answer: string;
  stage: "intro" | "writing" | "submitting" | "result";
  submissionId?: string;
  evaluation?: PracticeEvaluation;
  evaluationError?: string;
  finishReason?: "submitted" | "expired" | "blank";
  helpModeEnabled: boolean;
  attemptType: AttemptType;
};

export function sessionFromAttempt(taskNumber: TaskNumber, attempt: WritingAttempt): PracticeSession {
  const serverClockOffset = Date.parse(attempt.server_time) - Date.now();
  return {
    attemptId: attempt.id,
    taskNumber,
    task: attempt.task,
    introEndsAt: Date.parse(attempt.preparation_expires_at) - serverClockOffset,
    writingEndsAt: Date.parse(attempt.writing_expires_at) - serverClockOffset,
    answer: attempt.answer_text,
    stage: attempt.submission ? "result" : attempt.status === "PREPARING" ? "intro" : "writing",
    submissionId: attempt.submission?.id,
    helpModeEnabled: attempt.help_mode_enabled,
    attemptType: attempt.attempt_type,
  };
}

export function parseTaskNumber(value: string | string[] | undefined): TaskNumber | null {
  const parsed = Number(Array.isArray(value) ? value[0] : value);
  return parsed === 1 || parsed === 2 ? parsed : null;
}

export function sessionKey(taskNumber: TaskNumber): string {
  return `celpip-practice-task-${taskNumber}`;
}

export function readSession(taskNumber: TaskNumber): PracticeSession | null {
  try {
    const value = sessionStorage.getItem(sessionKey(taskNumber));
    return value ? JSON.parse(value) as PracticeSession : null;
  } catch {
    return null;
  }
}

export function writeSession(session: PracticeSession): void {
  sessionStorage.setItem(sessionKey(session.taskNumber), JSON.stringify(session));
}

export function countWords(value: string): number {
  return value.trim() ? value.trim().split(/\s+/u).length : 0;
}

export function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}
