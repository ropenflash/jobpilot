const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

export async function getBackendHealth() {
  try {
    const response = await fetch(`${API_URL}/api/health`, { cache: "no-store" });
    if (!response.ok) throw new Error(`Backend returned ${response.status}`);
    return await response.json();
  } catch (error) {
    return { status: "UNAVAILABLE", mongodb: "UNKNOWN", error: String(error) };
  }
}
