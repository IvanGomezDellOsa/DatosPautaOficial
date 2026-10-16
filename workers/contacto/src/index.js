// Worker del formulario de contacto (datospautaoficial.com.ar/contacto).
//
// Pages lo llama por service binding desde functions/api/contacto.js: no tiene URL
// pública propia (workers_dev: false). Valida el mensaje y lo reenvía por mail a
// DESTINO, una dirección verificada en Email Routing del dominio. DESTINO es un
// secreto del Worker: la dirección no está en el sitio ni en el repositorio.
// Enviar a una dirección verificada es gratis en cualquier plan.
import { EmailMessage } from "cloudflare:email";

const REMITENTE = "contacto@datospautaoficial.com.ar";
const LARGO_MAX = { nombre: 100, email: 200, mensaje: 5000, cuerpo: 20000 };
const MENSAJE_MIN = 10;
// Un humano tarda más que esto en completar el formulario; un bot suele no tardar nada.
const MS_MIN = 3000;
const ORIGENES = new Set([
  "https://datospautaoficial.com.ar",
  "https://www.datospautaoficial.com.ar",
  "https://datospautaoficial.pages.dev",
]);
const RE_EMAIL = /^[^\s@<>"(),;:]+@[^\s@<>"(),;:]+\.[^\s@<>"(),;:]{2,}$/;

function respuesta(status, cuerpo) {
  return new Response(JSON.stringify(cuerpo), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

// Una sola línea, sin saltos: evita inyectar encabezados en el mail.
function linea(valor, max) {
  return String(valor ?? "").replace(/[\r\n\t]+/g, " ").trim().slice(0, max);
}

function base64(texto) {
  const bytes = new TextEncoder().encode(texto);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(bin);
}

function mime({ para, responderA, asunto, texto }) {
  const cuerpo = base64(texto.replace(/\r?\n/g, "\r\n")).replace(/.{76}/g, "$&\r\n");
  return [
    `From: Datos Pauta Oficial <${REMITENTE}>`,
    `To: <${para}>`,
    ...(responderA ? [`Reply-To: <${responderA}>`] : []),
    `Subject: ${asunto}`,
    `Date: ${new Date().toUTCString()}`,
    `Message-ID: <${crypto.randomUUID()}@datospautaoficial.com.ar>`,
    "MIME-Version: 1.0",
    "Content-Type: text/plain; charset=UTF-8",
    "Content-Transfer-Encoding: base64",
    "",
    cuerpo,
  ].join("\r\n");
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return respuesta(405, { ok: false, error: "metodo" });
    if (!env.DESTINO || !env.CORREO) return respuesta(503, { ok: false, error: "no_configurado" });

    const origen = request.headers.get("origin");
    if (origen && !ORIGENES.has(origen)) return respuesta(403, { ok: false, error: "origen" });
    if (Number(request.headers.get("content-length") || 0) > LARGO_MAX.cuerpo) {
      return respuesta(413, { ok: false, error: "mensaje_largo" });
    }

    let datos;
    try {
      datos = await request.json();
    } catch {
      return respuesta(400, { ok: false, error: "formato" });
    }
    if (!datos || typeof datos !== "object") return respuesta(400, { ok: false, error: "formato" });

    // Trampas para bots (campo oculto completado o envío instantáneo): se responde ok
    // para no darles pistas, pero no se envía nada.
    const ms = Number(datos.ms);
    if (linea(datos.sitio, 200) !== "" || !Number.isFinite(ms) || ms < MS_MIN) {
      return respuesta(200, { ok: true });
    }

    const mensaje = String(datos.mensaje ?? "").trim();
    if (mensaje.length < MENSAJE_MIN) return respuesta(400, { ok: false, error: "mensaje_corto" });
    if (mensaje.length > LARGO_MAX.mensaje) return respuesta(400, { ok: false, error: "mensaje_largo" });
    const nombre = linea(datos.nombre, LARGO_MAX.nombre);
    const email = linea(datos.email, LARGO_MAX.email);
    if (email && !RE_EMAIL.test(email)) return respuesta(400, { ok: false, error: "email" });

    const texto = [
      "Mensaje enviado desde el formulario de contacto de datospautaoficial.com.ar.",
      "",
      `Nombre: ${nombre || "(no lo indicó)"}`,
      `Email para responder: ${email || "(no lo indicó)"}`,
      "",
      "----",
      "",
      mensaje,
    ].join("\n");

    try {
      await env.CORREO.send(new EmailMessage(REMITENTE, env.DESTINO, mime({
        para: env.DESTINO,
        responderA: email || null,
        asunto: "Contacto desde datospautaoficial.com.ar",
        texto,
      })));
    } catch (e) {
      console.error("No se pudo enviar el mail de contacto:", e && e.message);
      return respuesta(502, { ok: false, error: "envio" });
    }
    return respuesta(200, { ok: true });
  },
};
