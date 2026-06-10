/**
 * useSugerenciasNav.ts — navegación por teclado para los dropdowns de
 * sugerencias (DataTable y Generador).
 *
 * Maneja ArrowUp/ArrowDown/Enter/Escape sobre una lista de n items.
 * El highlight visual se aplica con la clase .suggest-item.activo y el
 * input debe declarar aria-activedescendant con el id del item activo.
 */

import { useEffect, useState, type KeyboardEvent } from "react";

export function useSugerenciasNav(
  n: number,
  abierto: boolean,
  onPick: (i: number) => void,
  onClose: () => void,
) {
  const [idx, setIdx] = useState(-1);

  // Reset al cambiar los resultados o cerrar la lista
  useEffect(() => {
    setIdx(-1);
  }, [n, abierto]);

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      onClose();
      return;
    }
    if (!abierto || n === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIdx((i) => (i + 1) % n);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setIdx((i) => (i <= 0 ? n - 1 : i - 1));
    } else if (e.key === "Enter" && idx >= 0 && idx < n) {
      e.preventDefault();
      onPick(idx);
    }
  };

  return { idx, onKeyDown };
}
