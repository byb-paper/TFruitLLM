const json = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });

export async function onRequestPost({ request, env }) {
  if (!env.SUGON_CHAT_URL) {
    return json(
      { error: "The TFruitLLM inference endpoint is not configured." },
      503,
    );
  }

  try {
    const input = await request.json();
    const suppliedMessages = Array.isArray(input.messages)
      ? input.messages
      : [];
    const question = String(input.question || "").trim();
    const messages = suppliedMessages.length
      ? suppliedMessages
      : question
        ? [{ role: "user", content: question }]
        : [];

    if (!messages.length) {
      return json({ error: "A research question is required." }, 400);
    }

    const upstream = await fetch(env.SUGON_CHAT_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(env.SUGON_API_KEY
          ? { Authorization: `Bearer ${env.SUGON_API_KEY}` }
          : {}),
      },
      body: JSON.stringify({
        model: "TFruitLLM",
        messages: messages.slice(-12),
        temperature: Number.isFinite(input.temperature)
          ? input.temperature
          : 0.3,
        max_tokens: Math.min(Math.max(Number(input.max_tokens) || 1024, 64), 2048),
        stream: false,
      }),
    });

    const body = await upstream.text();
    return new Response(body, {
      status: upstream.status,
      headers: {
        "Content-Type":
          upstream.headers.get("Content-Type") ||
          "application/json; charset=utf-8",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    return json(
      {
        error: "TFruitLLM could not complete this request.",
        detail: String(error),
      },
      502,
    );
  }
}

export function onRequestOptions() {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
      "Access-Control-Max-Age": "86400",
    },
  });
}
