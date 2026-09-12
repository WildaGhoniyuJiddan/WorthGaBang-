"use client";

import { FormEvent, useState } from "react";
import {
  analyzeBundle,
  analyzePrice,
  AnalyzeResult,
  BundleItem,
  BundleResult,
  Mode,
} from "../lib/api";
import SuggestInput from "../components/SuggestInput";

const formatRupiah = (value: number) =>
  new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(value);

type BundleCard = { query: string; component_type: string; price: string };

const EMPTY_CARD: BundleCard = { query: "", component_type: "cpu", price: "" };

export default function HomePage() {
  const [mode, setMode] = useState<Mode>("pc");
  const [query, setQuery] = useState("RTX 3060");
  const [price, setPrice] = useState("8000000");
  const [componentType, setComponentType] = useState("gpu");
  const [cpu, setCpu] = useState("");
  const [gpu, setGpu] = useState("");
  const [ram, setRam] = useState("");
  const [storage, setStorage] = useState("");
  const [condition, setCondition] = useState("any");
  const [bundleCards, setBundleCards] = useState<BundleCard[]>([{ ...EMPTY_CARD }, { ...EMPTY_CARD, component_type: "motherboard" }]);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [bundleResult, setBundleResult] = useState<BundleResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function switchMode(next: Mode) {
    setMode(next);
    setResult(null);
    setBundleResult(null);
    setError("");
  }

  function updateCard(index: number, patch: Partial<BundleCard>) {
    setBundleCards((cards) => cards.map((card, i) => (i === index ? { ...card, ...patch } : card)));
  }

  async function handleBundleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setBundleResult(null);
    try {
      const items: BundleItem[] = bundleCards
        .filter((card) => card.query.trim())
        .map((card) => ({
          query: card.query.trim(),
          component_type: card.component_type,
          price: card.price ? Number(card.price) : undefined,
        }));
      if (!items.length) throw new Error("Isi minimal satu komponen.");
      setBundleResult(await analyzeBundle(items, Number(price)));
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : "Terjadi kesalahan.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const analysis = await analyzePrice({
        mode,
        query,
        price: Number(price),
        component_type: mode === "pc" ? componentType : undefined,
        cpu: mode === "laptop" ? cpu || undefined : undefined,
        gpu: mode === "laptop" ? gpu || undefined : undefined,
        ram_gb: mode === "laptop" && ram ? Number(ram) : undefined,
        storage_gb: mode === "laptop" && storage ? Number(storage) : undefined,
        condition,
      });
      setResult(analysis);
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : "Terjadi kesalahan.");
    } finally {
      setLoading(false);
    }
  }

  const suggestSection =
    mode === "laptop"
      ? "laptop"
      : { gpu: "gpu", cpu: "cpu", ram: "ram", storage: "storage", motherboard: "motherboard" }[componentType] ?? "";

  return (
    <main className="page-shell">
      <section className="hero">
        <div className="eyebrow">WorthGaBang / marketplace intelligence</div>
        <h1>Harga yang kamu temukan, <span>masuk akal nggak?</span></h1>
        <p>Bandingkan dengan data listing yang sudah dikumpulkan dari marketplace, tanpa menunggu scraping saat request.</p>
      </section>

      <section className="workspace">
        <div className="mode-toggle" role="tablist" aria-label="Mode analisis">
          <button className={mode === "pc" ? "active" : ""} onClick={() => switchMode("pc")} type="button">PC Components</button>
          <button className={mode === "laptop" ? "active" : ""} onClick={() => switchMode("laptop")} type="button">Laptop</button>
          <button className={mode === "bundle" ? "active" : ""} onClick={() => switchMode("bundle")} type="button">Bundle Paket</button>
        </div>

        {mode === "bundle" ? (
          <form className="checker-card" onSubmit={handleBundleSubmit}>
            <div className="form-heading">
              <div>
                <div className="section-kicker">Mode Bundle</div>
                <h2>Cek paket bundling komponen</h2>
              </div>
              <span className="status-pill"><i /> Referensi katalog retail</span>
            </div>

            {bundleCards.map((card, index) => (
              <div className="bundle-card" key={index}>
                <div className="bundle-card-head">
                  <span className="rank">0{index + 1}</span>
                  <select value={card.component_type} onChange={(event) => updateCard(index, { component_type: event.target.value })} aria-label={`Jenis komponen ${index + 1}`}>
                    <option value="cpu">CPU</option>
                    <option value="motherboard">Mobo</option>
                    <option value="gpu">GPU</option>
                    <option value="ram">RAM</option>
                    <option value="storage">Storage</option>
                  </select>
                  {bundleCards.length > 1 && (
                    <button type="button" className="bundle-remove" onClick={() => setBundleCards((cards) => cards.filter((_, i) => i !== index))} aria-label={`Hapus komponen ${index + 1}`}>✕</button>
                  )}
                </div>
                <label>
                  Model komponen
                  <SuggestInput
                    value={card.query}
                    onChange={(value) => updateCard(index, { query: value })}
                    section={card.component_type}
                    condition="new"
                    placeholder={card.component_type === "motherboard" ? "contoh: MSI PRO B650M-B" : card.component_type === "cpu" ? "contoh: Ryzen 5 7500F" : "nama model"}
                  />
                </label>
                <label>
                  Harga per item — opsional, kosongkan kalau harga gabungan
                  <div className="input-prefix"><span>Rp</span><input value={card.price} onChange={(event) => updateCard(index, { price: event.target.value.replace(/\D/g, "") })} inputMode="numeric" placeholder="kosong = ikut bundle" /></div>
                </label>
              </div>
            ))}

            {bundleCards.length < 6 && (
              <button type="button" className="bundle-add" onClick={() => setBundleCards((cards) => [...cards, { ...EMPTY_CARD }])}>+ Tambah komponen</button>
            )}

            <label>
              Harga bundle yang ditemukan
              <div className="input-prefix"><span>Rp</span><input value={price} onChange={(event) => setPrice(event.target.value.replace(/\D/g, ""))} inputMode="numeric" required /></div>
            </label>

            {error && <div className="error-box">{error}</div>}
            <button className="submit-button" disabled={loading} type="submit">{loading ? "Menganalisis..." : "Cek worth it"}<span>↗</span></button>
          </form>
        ) : (
        <form className="checker-card" onSubmit={handleSubmit}>
          <div className="form-heading">
            <div>
              <div className="section-kicker">Mode {mode === "pc" ? "PC" : "Laptop"}</div>
              <h2>Masukkan produk yang mau dicek</h2>
            </div>
            <span className="status-pill"><i /> {condition === "new" ? "Pool Baru · katalog retail" : condition === "second" ? "Pool Bekas · marketplace" : "Data katalog"}</span>
          </div>

          <label>
            Nama / query produk
            <SuggestInput
              value={query}
              onChange={setQuery}
              section={suggestSection}
              condition={condition}
              placeholder={mode === "pc" ? "contoh: RTX 4060" : "contoh: ASUS ROG RTX 4060"}
            />
          </label>

          <div className="form-grid">
            <label>
              Harga yang ditemukan
              <div className="input-prefix"><span>Rp</span><input value={price} onChange={(event) => setPrice(event.target.value.replace(/\D/g, ""))} inputMode="numeric" required /></div>
            </label>
            {mode === "pc" ? (
              <>
                <label>
                  Jenis komponen
                  <select value={componentType} onChange={(event) => setComponentType(event.target.value)}>
                    <option value="gpu">GPU / VGA</option>
                    <option value="cpu">CPU / Processor</option>
                    <option value="ram">RAM</option>
                    <option value="storage">Storage</option>
                    <option value="motherboard">Motherboard</option>
                  </select>
                </label>
                <label>
                  Kondisi komponen
                  <select value={condition} onChange={(event) => setCondition(event.target.value)}>
                    <option value="any">Semua kondisi</option>
                    <option value="new">Baru</option>
                    <option value="second">Bekas</option>
                  </select>
                </label>
              </>
            ) : (
              <label>
                Kondisi unit
                <select value={condition} onChange={(event) => setCondition(event.target.value)}>
                  <option value="any">Semua kondisi</option>
                  <option value="new">Baru</option>
                  <option value="second">Bekas</option>
                </select>
              </label>
            )}
          </div>

          {mode === "laptop" && (
            <div className="form-grid three-cols">
              <label>CPU<input value={cpu} onChange={(event) => setCpu(event.target.value)} placeholder="Core i5 / Ryzen 5" autoComplete="off" /></label>
              <label>GPU<input value={gpu} onChange={(event) => setGpu(event.target.value)} placeholder="RTX 4060" autoComplete="off" /></label>
              <label>RAM / Storage<div className="dual-input"><input value={ram} onChange={(event) => setRam(event.target.value.replace(/\D/g, ""))} placeholder="16 GB" /><input value={storage} onChange={(event) => setStorage(event.target.value.replace(/\D/g, ""))} placeholder="512 GB" /></div></label>
            </div>
          )}

          {error && <div className="error-box">{error}</div>}
          <button className="submit-button" disabled={loading} type="submit">{loading ? "Menganalisis..." : "Cek worth it"}<span>↗</span></button>
        </form>
        )}

        {mode === "bundle"
          ? bundleResult
            ? <BundleResultCard result={bundleResult} />
            : <div className="empty-state"><span>✦</span><p>Hasil cek bundle akan muncul di sini.<br />Tambahkan komponen lalu masukkan harga paketnya.</p></div>
          : result
            ? <ResultCard result={result} />
            : <div className="empty-state"><span>✦</span><p>Hasil analisis akan muncul di sini.<br />Masukkan produk untuk mulai membandingkan.</p></div>}
      </section>

      <footer><span>WorthGaBang</span><span>Data pembanding diperbarui terjadwal · v1 MVP</span></footer>
    </main>
  );
}

function BundleResultCard({ result }: { result: BundleResult }) {
  const verdictClass = result.verdict.replace(/ /g, "-");
  const hemat = result.savings_percent >= 0;
  return (
    <section className="result-card">
      <div className="result-topline"><div className="section-kicker">HASIL CEK BUNDLE</div><span className={`verdict ${verdictClass}`}>{result.verdict}</span></div>
      <div className="score-row">
        <div><div className="score-number">{Math.round(result.score)}<small>/100</small></div><div className="score-caption">Skor worth-it paket bundling</div></div>
        <div className="price-summary"><span>Harga bundle</span><strong>{formatRupiah(result.bundle_price)}</strong><small>Total normal {formatRupiah(result.reference_total)} · <strong className={hemat ? "savings-pos" : "savings-neg"}>{hemat ? "hemat" : "lebih mahal"} {Math.abs(result.savings_percent)}%</strong></small></div>
      </div>
      <p className="recommendation">{result.recommendation}</p>
      <div className="comparisons"><div className="comparison-heading"><h3>Rincian referensi per komponen</h3><span>{result.items.length} komponen</span></div>{result.items.map((item, index) => <div className="comparison-row" key={`${item.query}-${index}`}><span className="rank">0{index + 1}</span><span className="comparison-title">{item.query}<small>{item.component_type}{item.price_input ? ` · harga item ${formatRupiah(item.price_input)}` : ""} · harga normal sendiri</small></span><strong>{formatRupiah(item.reference_price)}</strong><span className="arrow">—</span></div>)}</div>
    </section>
  );
}

function getPinPercent(price: number, minVal: number, maxVal: number): number {
  if (!minVal || !maxVal || minVal >= maxVal) return 50;
  const pct = ((price - minVal) / (maxVal - minVal)) * 100;
  return Math.max(4, Math.min(96, Math.round(pct)));
}

function formatSource(source: string): { label: string; className: string } {
  if (source === "tokopedia") return { label: "Tokopedia", className: "source-tokopedia" };
  if (source === "facebook" || source === "facebook_marketplace") return { label: "FB Market", className: "source-facebook" };
  if (source === "komponen_retail" || source === "notebook_retail") return { label: "Retail EK", className: "source-retail" };
  return { label: "Katalog", className: "source-retail" };
}

function ResultCard({ result }: { result: AnalyzeResult }) {
  const [showAll, setShowAll] = useState(false);
  const [conditionFilter, setConditionFilter] = useState<"all" | "new" | "second">("all");

  const newCount = result.comparisons.filter((c) => (c.condition || "new") === "new").length;
  const usedCount = result.comparisons.filter((c) => c.condition === "second").length;

  const filteredComps = result.comparisons.filter((c) => {
    if (conditionFilter === "all") return true;
    if (conditionFilter === "new") return (c.condition || "new") === "new";
    if (conditionFilter === "second") return c.condition === "second";
    return true;
  });

  const visible = showAll ? filteredComps : filteredComps.slice(0, 5);
  const hiddenCount = filteredComps.length - 5;
  const verdictClass = result.verdict.replace(/ /g, "-");

  const lowBound = Math.min(result.input_price, result.fair_price_low || result.reference_price * 0.8) * 0.9;
  const highBound = Math.max(result.input_price, result.fair_price_high || result.reference_price * 1.2) * 1.1;
  const pinPos = getPinPercent(result.input_price, lowBound, highBound);

  return (
    <section className="result-card">
      <div className="result-topline">
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <div className="section-kicker">HASIL ANALISIS</div>
          {result.tier_label && <span className="tier-badge">⚡ {result.tier_label}</span>}
        </div>
        <span className={`verdict ${verdictClass}`}>{result.verdict}</span>
      </div>

      <div className="score-row">
        <div>
          <div className="score-number">{Math.round(result.score)}<small>/100</small></div>
          <div className="score-caption">Skor worth-it untuk <strong>{result.query}</strong></div>
        </div>
        <div className="price-summary">
          <span>Harga kamu</span>
          <strong>{formatRupiah(result.input_price)}</strong>
          <small>Median pasar {formatRupiah(result.reference_price)}</small>
        </div>
      </div>

      {(result.new_reference_price || result.used_reference_price) && (
        <div className="dual-market-grid">
          <div className={`market-card ${result.new_reference_price ? "market-new" : ""}`}>
            <div className="market-badge-label">🏷️ Pasar Baru (Retail / BNIB)</div>
            <div className="market-price-val">
              {result.new_reference_price ? formatRupiah(result.new_reference_price) : "Data Terbatas"}
            </div>
            <div className="market-desc">Median referensi harga unit baru</div>
          </div>
          <div className={`market-card ${result.used_reference_price ? "market-used" : ""}`}>
            <div className="market-badge-label">📦 Pasar Bekas (Second Hand)</div>
            <div className="market-price-val">
              {result.used_reference_price ? formatRupiah(result.used_reference_price) : "Data Terbatas"}
            </div>
            <div className="market-desc">Median referensi pasar bekas</div>
          </div>
        </div>
      )}

      <div className="spectrum-box">
        <div className="spectrum-title">
          <span>Spektrum Rentang Harga Pasar</span>
          <span>{result.price_delta_percent > 0 ? `+${result.price_delta_percent}% vs median` : `${result.price_delta_percent}% vs median`}</span>
        </div>
        <div className="spectrum-bar-wrap">
          <div className="spectrum-pin" style={{ left: `${pinPos}%` }}>
            <span className="spectrum-pin-tag">Harga Kamu</span>
            <div className="spectrum-pin-needle" />
          </div>
        </div>
        <div className="spectrum-labels">
          <div><span>Murah / Worth It</span><strong>{formatRupiah(result.fair_price_low || Math.round(result.reference_price * 0.85))}</strong></div>
          <div style={{ textAlign: "center" }}><span>Median Pasar</span><strong>{formatRupiah(result.reference_price)}</strong></div>
          <div style={{ textAlign: "right" }}><span>Mulai Kemahalan</span><strong>{formatRupiah(result.fair_price_high || Math.round(result.reference_price * 1.15))}</strong></div>
        </div>
      </div>

      <p className="recommendation">{result.recommendation}</p>

      {result.cross_market_advice && (
        <div className="cross-market-box">
          <div className="cross-market-header">
            <span className="cross-market-icon">💡</span>
            <strong>Analisis Lintas Pasar (Baru vs Bekas)</strong>
          </div>
          <p className="cross-market-text">{result.cross_market_advice}</p>
        </div>
      )}

      {result.alternatives && result.alternatives.length > 0 && (
        <div className="alternatives-section">
          <div className="comparison-heading">
            <h3>Alternatif Performa Lebih Tinggi</h3>
            <span>Rekomendasi di kisaran harga serupa</span>
          </div>
          <div className="alternatives-grid">
            {result.alternatives.map((alt, idx) => (
              <div className="alt-card" key={`alt-${idx}`}>
                <div className="alt-info">
                  <div className="alt-title">{alt.name}</div>
                  <div className="alt-badges">
                    <span className="gain-badge">+{alt.gain_percent}% Lebih Kencang</span>
                    {alt.vram_gb && <span className="vram-tag">{alt.vram_gb} GB VRAM</span>}
                    {alt.tier_label && <span style={{ fontSize: "9px", color: "var(--muted)" }}>{alt.tier_label}</span>}
                  </div>
                </div>
                <div className="alt-price">
                  {formatRupiah(alt.est_price_idr)}
                  <small>Estimasi pasar</small>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="result-meta" style={{ marginTop: "16px" }}>
        <span>Data {result.freshness.label}</span>
        <span>Sumber: {result.freshness.primary_source.replace("_", " ")}</span>
        {result.freshness.is_stale && <span className="stale">Perlu refresh</span>}
      </div>

      <div className="comparisons">
        <div className="comparison-heading">
          <div>
            <h3>Pembanding yang dipakai</h3>
            <span>{filteredComps.length} referensi ditampilkan · {new Set(result.comparisons.map((c) => c.source)).size} sumber pasar</span>
          </div>
        </div>

        {(newCount > 0 && usedCount > 0) && (
          <div className="comparison-filter-tabs">
            <button
              type="button"
              className={`comp-tab ${conditionFilter === "all" ? "active" : ""}`}
              onClick={() => { setConditionFilter("all"); setShowAll(false); }}
            >
              Semua ({result.comparisons.length})
            </button>
            <button
              type="button"
              className={`comp-tab ${conditionFilter === "new" ? "active" : ""}`}
              onClick={() => { setConditionFilter("new"); setShowAll(false); }}
            >
              🏷️ Unit Baru ({newCount})
            </button>
            <button
              type="button"
              className={`comp-tab ${conditionFilter === "second" ? "active" : ""}`}
              onClick={() => { setConditionFilter("second"); setShowAll(false); }}
            >
              📦 Unit Bekas ({usedCount})
            </button>
          </div>
        )}

        {visible.map((comparison, index) => {
          const src = formatSource(comparison.source);
          const isUsed = comparison.condition === "second";
          return (
            <a className="comparison-row" href={comparison.listing_url || undefined} key={`${comparison.source}-${index}`} target={comparison.listing_url ? "_blank" : undefined} rel="noreferrer">
              <span className="rank">0{index + 1}</span>
              <span className="comparison-title">
                {comparison.title}
                <small>
                  <span className={`condition-pill ${isUsed ? "pill-used" : "pill-new"}`}>
                    {isUsed ? "BEKAS" : "BARU"}
                  </span>
                  <span className={`source-tag ${src.className}`}>{src.label}</span>
                  · match {Math.round(comparison.similarity * 100)}%
                </small>
              </span>
              <strong>{formatRupiah(comparison.price)}</strong>
              <span className="arrow">{comparison.listing_url ? "↗" : "—"}</span>
            </a>
          );
        })}
        {hiddenCount > 0 && !showAll && (
          <button className="show-all-button" type="button" onClick={() => setShowAll(true)}>
            Lihat semua pembanding ({hiddenCount} lainnya)
          </button>
        )}
        {showAll && filteredComps.length > 5 && (
          <button className="show-all-button" type="button" onClick={() => setShowAll(false)}>
            Sembunyikan
          </button>
        )}
      </div>
    </section>
  );
}
