"use client";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(e.currentTarget);
    try {
      await api("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username: form.get("username"),
          password: form.get("password"),
        }),
      });
      const params = new URLSearchParams(window.location.search);
      const returnTo = params.get("returnTo");
      if (returnTo && returnTo.startsWith("/") && !returnTo.startsWith("//")) {
        router.push(returnTo);
      } else {
        router.push("/");
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="loginPage">
      <form className="loginCard" onSubmit={submit}>
        <div className="loginLogo">M</div>
        <h1>Enter MemoryBank</h1>
        <p>Your private cognition layer. Human-readable, AI-accessible, and under your control.</p>
        {error && <div className="errorBox">{error}</div>}
        <div className="field">
          <label>Username</label>
          <input className="input" name="username" autoComplete="username" required />
        </div>
        <div className="field" style={{ marginTop: 13 }}>
          <label>Password</label>
          <input className="input" type="password" name="password" autoComplete="current-password" required />
        </div>
        <button className="button primary" style={{ width: "100%", marginTop: 18 }} disabled={busy}>
          {busy ? "Authenticating…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
