export type UserSummary = {
  id: string;
  email: string;
  first_name: string;
  role: "STUDENT" | "ADMIN";
  current_score: number | null;
  target_score: number | null;
  registered_at: string;
  last_activity_at: string;
  assigned_exercises: number;
  attempts_started: number;
  active_attempts: number;
  exercises_completed: number;
  guided_practice_completed: number;
  test_simulation_completed: number;
  total_practice_seconds: number;
  average_test_score: number | null;
  average_guided_score: number | null;
  ai_request_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
};

export function number(value: number): string {
  return new Intl.NumberFormat("en-CA").format(value);
}

export function money(value: number): string {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value < 0.01 ? 4 : 2,
    maximumFractionDigits: 6,
  }).format(value);
}

export function duration(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m`;
  return `${totalSeconds}s`;
}

export function score(value: number | null): string {
  return value === null ? "—" : value.toFixed(1);
}

export function dateTime(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-CA", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export async function failureMessage(response: Response): Promise<string> {
  const body = await response.json().catch(() => null) as { detail?: string } | null;
  return body?.detail || "The report could not be loaded.";
}
