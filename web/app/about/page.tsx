import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "About MemoryBank",
  description: "A self-hosted personal memory and AI context platform.",
};

export default function AboutPage() {
  return (
    <main className="publicPage">
      <header className="publicHeader">
        <Link className="publicBrand" href="/about"><span>M</span> MemoryBank</Link>
        <nav aria-label="Information">
          <Link href="/privacy">Privacy</Link>
          <Link href="/terms">Terms</Link>
          <Link className="publicSignIn" href="/login">Sign in</Link>
        </nav>
      </header>

      <section className="publicHero">
        <div className="publicEyebrow">YOUR SELF-HOSTED KNOWLEDGE BASE</div>
        <h1>Keep the context that matters.</h1>
        <p>
          MemoryBank brings personal notes and selected sources into a searchable
          knowledge base. You decide what to connect, review suggested memories,
          and keep the service under your control.
        </p>
        <Link className="publicButton" href="/login">Sign in to MemoryBank</Link>
      </section>

      <section className="publicDetails">
        <article>
          <h2>How Gmail connection works</h2>
          <p>
            If you connect Gmail, MemoryBank requests read-only access and syncs
            only messages matching the search and label you choose. Message text
            is stored as source documents and can be processed into suggested
            memories for your review. Attachments are not imported.
          </p>
        </article>
        <article>
          <h2>You stay in control</h2>
          <p>
            MemoryBank does not send, modify, label, archive, or delete Gmail
            messages. Disconnecting stops future syncs and attempts to revoke
            the Google token. Imported documents remain until you remove them
            from MemoryBank.
          </p>
        </article>
      </section>

      <footer className="publicFooter">
        <span>MemoryBank · self-hosted personal memory</span>
        <span><Link href="/privacy">Privacy policy</Link><Link href="/terms">Terms of service</Link></span>
      </footer>
    </main>
  );
}
