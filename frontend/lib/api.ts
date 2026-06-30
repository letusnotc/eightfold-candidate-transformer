const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function transformCandidate(formData: FormData): Promise<unknown> {
  const response = await fetch(`${API_URL}/transform`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`API error ${response.status}: ${text || response.statusText}`);
  }
  return response.json();
}

export async function runSample(): Promise<unknown> {
  const response = await fetch(`${API_URL}/transform/sample`, {
    method: "POST",
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`Sample API error ${response.status}: ${text || response.statusText}`);
  }
  return response.json();
}

export async function checkHealth(): Promise<{ status: string; version: string }> {
  const response = await fetch(`${API_URL}/health`);
  return response.json();
}
