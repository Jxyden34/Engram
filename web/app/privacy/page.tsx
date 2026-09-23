import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy Policy · MemoryBank",
  description: "How this MemoryBank instance handles account, source, and Gmail data.",
};

export default function PrivacyPage() {
  return (
    <main className="publicPage legalPage">
      <header className="publicHeader">
        <Link className="publicBrand" href="/about"><span>M</span> MemoryBank</Link>
        <nav aria-label="Information">
          <Link href="/about">About</Link>
          <Link href="/terms">Terms</Link>
          <Link className="publicSignIn" href="/login">Sign in</Link>
        </nav>
      </header>
      <article className="legalContent">
        <div className="publicEyebrow">PRIVACY</div>
        <h1>MemoryBank Privacy Policy</h1>
        <p className="legalUpdated">Effective September 23, 2026</p>
        <p>
          This policy describes the self-hosted MemoryBank service at
          memory.hindley.tech, operated by its instance administrator. It
          explains what data this instance handles when you use it, including
          when you connect a Google account.
        </p>

        <h2>Information you provide</h2>
        <p>
          MemoryBank stores the notes, documents, memories, and account details
          you submit to this instance. Its operational records may include
          connector configuration, sync status, and security audit events.
        </p>

        <h2>Google user data and Gmail</h2>
        <p>
          If you connect Gmail, MemoryBank requests only the
          <code> gmail.readonly </code> permission. It uses that permission to
          read messages that match the search query and labels you selected.
          For those messages, it processes the Gmail address, message and thread
          identifiers, sender, subject, date, labels, snippet, and message body.
          It does not import attachments or send, modify, label, archive, or
          delete messages.
        </p>
        <p>
          The message text is stored as a MemoryBank source document so you can
          search it and, if enabled, analyze it into suggested memories for
          review. MemoryBank does not sell Google user data, use it for
          advertising, or use it to train general-purpose AI models. Processing
          uses the AI and embedding services configured for this self-hosted
          instance; its default model service runs alongside MemoryBank.
        </p>
        <p>
          MemoryBank stores the Google refresh token encrypted in its database
          using AES-256-GCM. The token is used to obtain access tokens for
          scheduled read-only syncs and is not returned by the MemoryBank API.
        </p>

        <h2>Storage, access, and sharing</h2>
        <p>
          This instance stores application data in its configured database and
          object storage on the MemoryBank deployment. The instance
          administrator can access and administer that data. Administrators may
          maintain backups under their own retention and security controls.
          Google data is shared only as needed with Google to authorize and
          retrieve the messages you selected, and with the services configured
          to operate this MemoryBank instance.
        </p>

        <h2>Retention and deletion</h2>
        <p>
          Disconnecting Gmail stops future syncs and asks Google to revoke the
          stored token. Disconnecting does not delete messages already imported
          into MemoryBank or memories you accepted from them. Remove those
          source documents and memories in MemoryBank, and contact the instance
          administrator for account or instance-level deletion requests.
          Administrators' backups may retain data until their normal backup
          retention period ends. You can also review or revoke MemoryBank's
          access from your Google Account security settings.
        </p>

        <h2>Security</h2>
        <p>
          The instance uses access controls and encrypts Google refresh tokens
          before storing them. No internet service can guarantee absolute
          security; protect your MemoryBank account and contact the instance
          administrator if you suspect unauthorized access.
        </p>

        <h2>Changes and contact</h2>
        <p>
          This policy may be updated when the service or its data practices
          change. For questions or deletion requests, contact the MemoryBank
          instance administrator using the support address shown on the Google
          OAuth consent screen.
        </p>
        <p>
          MemoryBank's use of information received from Google APIs adheres to
          the Google API Services User Data Policy, including the Limited Use
          requirements.
        </p>
      </article>
      <footer className="publicFooter"><Link href="/about">MemoryBank</Link><Link href="/terms">Terms of service</Link></footer>
    </main>
  );
}
