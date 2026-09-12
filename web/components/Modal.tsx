"use client";
import { ReactNode } from "react";

export default function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="modalShade" onMouseDown={onClose}>
      <section className="modalCard" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modalHead">
          <h2>{title}</h2>
          <button className="iconButton" onClick={onClose}>×</button>
        </div>
        {children}
      </section>
    </div>
  );
}
