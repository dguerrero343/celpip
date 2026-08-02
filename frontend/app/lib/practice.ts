export const INTRO_SECONDS = 50;

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
};

export type PracticeSession = {
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
};

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
