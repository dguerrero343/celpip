"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import AuthShell from "../components/AuthShell";

type Registration = {
  firstName: string;
  email: string;
  password: string;
  confirmPassword: string;
  currentScore: string;
  targetScore: string;
  examDate: string;
};

const initialForm: Registration = {
  firstName: "",
  email: "",
  password: "",
  confirmPassword: "",
  currentScore: "",
  targetScore: "10",
  examDate: "",
};

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState(initialForm);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function update(field: keyof Registration, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (form.password !== form.confirmPassword) {
      setError("Your passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      const registration = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: form.email,
          password: form.password,
          first_name: form.firstName,
          current_celpip_score: form.currentScore ? Number(form.currentScore) : null,
          target_celpip_score: Number(form.targetScore),
          target_exam_date: form.examDate || null,
        }),
      });
      if (!registration.ok) {
        const body = await registration.json().catch(() => null);
        if (registration.status === 409) throw new Error("An account already exists for this email. Try signing in instead.");
        throw new Error(body?.detail?.[0]?.msg || body?.detail || "We could not create your account.");
      }

      const login = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: form.email, password: form.password }),
      });
      if (!login.ok) throw new Error("Your account was created, but automatic sign-in failed. Please sign in.");
      router.replace("/account");
      router.refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "We could not create your account.");
    } finally {
      setSubmitting(false);
    }
  }

  const scoreOptions = Array.from({ length: 12 }, (_, index) => index + 1);

  return (
    <AuthShell eyebrow="START PRACTISING" title="Create your account" description="Tell us where you are now and where you want your writing score to go.">
      <form className="auth-form register-form" onSubmit={submit}>
        {error && <div className="form-alert" role="alert">{error}</div>}
        <label>
          <span>First name</span>
          <input type="text" autoComplete="given-name" value={form.firstName} onChange={(event) => update("firstName", event.target.value)} placeholder="Your first name" maxLength={100} required autoFocus />
        </label>
        <label>
          <span>Email address</span>
          <input type="email" autoComplete="email" inputMode="email" value={form.email} onChange={(event) => update("email", event.target.value)} placeholder="you@example.com" required />
        </label>
        <div className="form-row">
          <label>
            <span>Current score <small>optional</small></span>
            <select value={form.currentScore} onChange={(event) => update("currentScore", event.target.value)}>
              <option value="">Not sure</option>
              {scoreOptions.map((score) => <option value={score} key={score}>{score}</option>)}
            </select>
          </label>
          <label>
            <span>Target score</span>
            <select value={form.targetScore} onChange={(event) => update("targetScore", event.target.value)} required>
              {scoreOptions.map((score) => <option value={score} key={score}>{score}</option>)}
            </select>
          </label>
        </div>
        <label>
          <span>Target exam date <small>optional</small></span>
          <input type="date" value={form.examDate} onChange={(event) => update("examDate", event.target.value)} />
        </label>
        <label>
          <span>Password</span>
          <div className="password-input">
            <input type={showPassword ? "text" : "password"} autoComplete="new-password" value={form.password} onChange={(event) => update("password", event.target.value)} placeholder="At least 8 characters" minLength={8} maxLength={128} required />
            <button type="button" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? "Hide" : "Show"}</button>
          </div>
        </label>
        <label>
          <span>Confirm password</span>
          <input type={showPassword ? "text" : "password"} autoComplete="new-password" value={form.confirmPassword} onChange={(event) => update("confirmPassword", event.target.value)} placeholder="Enter it again" minLength={8} maxLength={128} required />
        </label>
        <p className="form-note">By creating an account, you agree to use the coach for learning and practice.</p>
        <button className="submit-button" type="submit" disabled={submitting}>{submitting ? "Creating your account…" : "Create account"}</button>
      </form>
      <p className="auth-switch">Already registered? <Link href="/login">Sign in</Link></p>
    </AuthShell>
  );
}
