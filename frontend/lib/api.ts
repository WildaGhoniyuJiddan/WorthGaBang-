export type Mode = "pc" | "laptop";

export type AnalyzePayload = {
  mode: Mode;
  query: string;
  price: number;
  component_type?: string;
  brand?: string;
  model?: string;
  cpu?: string;
  gpu?: string;
  ram_gb?: number;
  storage_gb?: number;
  screen_size?: number;
  condition?: string;
};

export type Comparison = {
  title: string;
  price: number;
  source: string;
  listing_url?: string | null;
  similarity: number;
  condition?: string | null;
};

export type AnalyzeResult = {
  mode: Mode;
  query: string;
  input_price: number;
  score: number;
  verdict: string;
  recommendation: string;
  reference_price: number;
  price_delta_percent: number;
  comparisons: Comparison[];
  freshness: {
    last_updated_at?: string | null;
    age_seconds?: number | null;
    label: string;
    is_stale: boolean;
    primary_source: string;
  };
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export async function analyzePrice(payload: AnalyzePayload): Promise<AnalyzeResult> {
  const response = await fetch(`${API_BASE_URL}/api/v1/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail || "Analisis gagal dijalankan.");
  }
  return response.json();
}

