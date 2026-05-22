import { useState } from "react";

/**
 * Island de verificacion del stack. Confirma que la hidratacion de React
 * funciona dentro de Astro. Placeholder: se elimina al construir la home real.
 */
export default function StackCheck() {
  const [ok, setOk] = useState(false);
  return (
    <button
      type="button"
      onClick={() => setOk(true)}
      className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium transition-colors hover:bg-neutral-100"
    >
      {ok ? "React island hidratado ✓" : "Probar hidratacion de React"}
    </button>
  );
}
