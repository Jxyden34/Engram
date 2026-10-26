import { ReactNode } from "react";

export default function ActionGroup({ label, children }: { label: string; children: ReactNode }) {
  return <div className="actionGroup" role="group" aria-label={label}>{children}</div>;
}
