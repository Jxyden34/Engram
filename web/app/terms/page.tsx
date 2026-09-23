import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terms of Service · MemoryBank",
  description: "Terms for using this self-hosted MemoryBank instance.",
};

export default function TermsPage() {
  return (
    <main className="publicPage legalPage">
      <header className="publicHeader">
        <Link className="publicBrand" href="/about"><span>M</span> MemoryBank</Link>
        <nav aria-label="Information">
          <Link href="/about">About</Link>
          <Link href="/privacy">Privacy</Link>
          <Link className="publicSignIn" href="/login">Sign in</Link>
        </nav>
      </header>
      <article className="legalContent">
        <div className="publicEyebrow">TERMS</div>
        <h1>MemoryBank Terms of Service</h1>
        <p className="legalUpdated">Effective September 23, 2026</p>
        <p>
          These terms apply to your use of the self-hosted MemoryBank instance
          at memory.hindley.tech. By using the service, you agree to use it
          responsibly and in accordance with these terms.
        </p>

        <h2>Your account and content</h2>
        <p>
          You are responsible for protecting your account credentials and for
          the content you add to MemoryBank. You retain your rights to that
          content. You must have the right to connect any external account and
          import its data. Do not use MemoryBank to access another person's
          account or information without permission.
        </p>

        <h2>Google and other connected services</h2>
        <p>
          When connecting a third-party service, you authorize MemoryBank to
          access only the permissions shown in that service's consent flow.
          Gmail access is read-only and limited by the search and labels you
          select. Your use of Google services remains subject to Google's own
          terms and policies. You can disconnect an integration in MemoryBank;
          imported copies may remain until you remove them separately.
        </p>

        <h2>Acceptable use</h2>
        <p>
          Do not use the service to break the law, violate another person's
          rights, interfere with the service, or attempt to gain unauthorized
          access to accounts, systems, or data. The instance administrator may
          suspend access to protect the service or its users.
        </p>

        <h2>Availability and changes</h2>
        <p>
          This is a self-hosted service operated by its instance administrator.
          Features, integrations, and availability may change, and the service
          is provided without a guaranteed uptime commitment. The administrator
          may update these terms when the service changes.
        </p>

        <h2>Contact</h2>
        <p>
          For questions about these terms, contact the MemoryBank instance
          administrator using the support address shown on the Google OAuth
          consent screen.
        </p>
      </article>
      <footer className="publicFooter"><Link href="/about">MemoryBank</Link><Link href="/privacy">Privacy policy</Link></footer>
    </main>
  );
}
