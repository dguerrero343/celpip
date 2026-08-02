import Link from "next/link";

export default function Brand({ light = false }: { light?: boolean }) {
  return (
    <Link className={`brand${light ? " brand-light" : ""}`} href="/" aria-label="CELPIP Coach home">
      <span className="brand-mark">C</span>
      <span>CELPIP <b>Coach</b></span>
    </Link>
  );
}
