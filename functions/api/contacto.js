// POST /api/contacto (Pages Function): pasa el formulario al Worker
// "datospautaoficial-contacto" por el service binding CONTACTO, que valida y envía
// el mail (workers/contacto). Pages Functions no puede enviar mails por sí mismo.
export async function onRequestPost({ request, env }) {
  if (!env.CONTACTO) {
    return new Response(JSON.stringify({ ok: false, error: "no_configurado" }), {
      status: 503,
      headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
    });
  }
  return env.CONTACTO.fetch(request);
}
