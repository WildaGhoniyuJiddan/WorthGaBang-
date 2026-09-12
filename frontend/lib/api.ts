export type Mode = "pc" | "laptop" | "bundle";

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

export type Alternative = {
  name: string;
  score: number;
  est_price_idr: number;
  gain_percent: number;
  vram_gb?: number | null;
  tier_label?: string | null;
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
  fair_price_low?: number;
  fair_price_high?: number;
  tier_label?: string | null;
  new_reference_price?: number | null;
  used_reference_price?: number | null;
  cross_market_advice?: string | null;
  comparisons: Comparison[];
  alternatives?: Alternative[];
  freshness: {
    last_updated_at?: string | null;
    age_seconds?: number | null;
    label: string;
    is_stale: boolean;
    primary_source: string;
  };
};

export type BundleItem = {
  query: string;
  component_type: string;
  price?: number | null;
};

export type BundleItemBreakdown = {
  query: string;
  component_type: string;
  price_input?: number | null;
  reference_price: number;
};

export type BundleResult = {
  bundle_price: number;
  reference_total: number;
  score: number;
  verdict: string;
  recommendation: string;
  savings_percent: number;
  items: BundleItemBreakdown[];
};

export type Suggestion = {
  label: string;
  samples: number;
  price?: number | null;
};

// API pakai baru|bekas|any; UI state pakai new|second|any.
export async function fetchSuggestions(
  section: string,
  q: string,
  signal: AbortSignal,
  condition: "baru" | "bekas" | "any" = "any",
): Promise<Suggestion[]> {
  const params = new URLSearchParams({ q, limit: "8", condition });
  const response = await fetch(`${API_BASE_URL}/api/v1/suggest/${section}?${params}`, { signal });
  if (!response.ok) return [];
  const data = await response.json();
  return data.suggestions || [];
}

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

export async function analyzeBundle(
  items: BundleItem[],
  bundle_price: number,
): Promise<BundleResult> {
  const response = await fetch(`${API_BASE_URL}/api/v1/analyze-bundle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items, bundle_price }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail || "Analisis bundle gagal dijalankan.");
  }
  return response.json();
}

