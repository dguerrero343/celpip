import Brand from "./Brand";

export default function AuthShell({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <main className="auth-page">
      <section className="auth-story">
        <Brand light />
        <div className="auth-story-copy">
          <p className="eyebrow">YOUR CELPIP PLAN</p>
          <h1>Write with clarity.<br />Improve with purpose.</h1>
          <p>Practise realistic prompts, receive structured feedback, and follow your progress toward the score you need.</p>
          <div className="auth-benefits">
            <span><b>01</b> Original CELPIP-style tasks</span>
            <span><b>02</b> Actionable writing feedback</span>
            <span><b>03</b> Personal score tracking</span>
          </div>
        </div>
        <p className="auth-privacy">Your writing and account remain private to you.</p>
      </section>
      <section className="auth-form-side">
        <div className="auth-card">
          <p className="eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
          <p className="auth-description">{description}</p>
          {children}
        </div>
      </section>
    </main>
  );
}
