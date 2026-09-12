"use client";

import { FormEvent, useEffect, useState } from "react";
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
    setResult(null);
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
      <header className="hero">
        <div className="eyebrow">WorthGaBang? / marketplace intelligence</div>
        <h1>Worth <span>ga bang?</span></h1>
        <p>Cek harga pasar komponen PC, laptop, dan paket bundle rakitan secara instan berbasis data riil marketplace dan katalog retail resmi.</p>
      </header>

      <section className="workspace">
        <div className="mode-toggle">
          <button className={mode === "pc" ? "active" : ""} onClick={() => switchMode("pc")} type="button">Komponen PC</button>
          <button className={mode === "laptop" ? "active" : ""} onClick={() => switchMode("laptop")} type="button">Laptop</button>
          <button className={mode === "bundle" ? "active" : ""} onClick={() => switchMode("bundle")} type="button">Paket Bundle</button>
        </div>

        {mode === "bundle" ? (
          <form className="checker-card" onSubmit={handleBundleSubmit}>
            <div className="form-heading">
              <div>
                <div className="section-kicker">Mode Bundle Rakitan</div>
                <h2>Cek kelayakan harga paket PC</h2>
              </div>
              <span className="status-pill"><i /> Multi-komponen</span>
            </div>

            {bundleCards.map((card, index) => (
              <div key={index} className="bundle-card">
                <div className="bundle-card-head">
                  <span className="rank">0{index + 1}</span>
                  <select
                    value={card.component_type}
                    onChange={(event) => updateCard(index, { component_type: event.target.value })}
                  >
                    <option value="cpu">CPU</option>
                    <option value="gpu">GPU</option>
                    <option value="motherboard">Motherboard</option>
                    <option value="ram">RAM</option>
                    <option value="storage">Storage</option>
                  </select>
                  {bundleCards.length > 1 && (
                    <button
                      type="button"
                      className="bundle-remove"
                      onClick={() => setBundleCards((cards) => cards.filter((_, i) => i !== index))}
                      title="Hapus baris"
                    >
                      ×
                    </button>
                  )}
                </div>
                <label>
                  Nama / Tipe Komponen
                  <SuggestInput
                    section={card.component_type}
                    value={card.query}
                    onChange={(val) => updateCard(index, { query: val })}
                    placeholder={`Contoh: ${card.component_type === "cpu" ? "Ryzen 5 5600" : card.component_type === "gpu" ? "RTX 3060" : "B550M"}`}
                    required
                  />
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
            <button className="submit-button" disabled={loading} type="submit">
              {loading ? (
                <span className="button-loading-content">
                  <span className="button-spinner" />
                  <span>Menganalisis bundle...</span>
                </span>
              ) : (
                <>
                  <span>Cek worth it</span>
                  <span>↗</span>
                </>
              )}
            </button>
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

          <div className="form-grid">
            {mode === "pc" && (
              <label>
                Tipe Komponen
                <select value={componentType} onChange={(event) => setComponentType(event.target.value)}>
                  <option value="gpu">GPU / VGA</option>
                  <option value="cpu">Processor / CPU</option>
                  <option value="ram">RAM</option>
                  <option value="storage">Storage / SSD</option>
                  <option value="motherboard">Motherboard</option>
                </select>
              </label>
            )}

            <label>
              Kondisi Unit
              <select value={condition} onChange={(event) => setCondition(event.target.value)}>
                <option value="any">Semua Kondisi (Baru &amp; Bekas)</option>
                <option value="new">Baru Saja (Katalog Retail / BNIB)</option>
                <option value="second">Bekas Saja (Marketplace)</option>
              </select>
            </label>
          </div>

          <label>
            {mode === "pc" ? "Model Komponen" : "Model Laptop"}
            <SuggestInput
              section={suggestSection}
              value={query}
              onChange={setQuery}
              onSelectPrice={(p) => setPrice(String(p))}
              placeholder={mode === "pc" ? "Contoh: RTX 3060 atau RX 6600" : "Contoh: Lenovo Legion 5 atau Asus TUF"}
              required
            />
          </label>

          <label>
            Harga yang Anda Temukan
            <div className="input-prefix"><span>Rp</span><input value={price} onChange={(event) => setPrice(event.target.value.replace(/\D/g, ""))} inputMode="numeric" required /></div>
          </label>

          {mode === "laptop" && (
            <div className="form-grid three-cols">
              <label>CPU<input value={cpu} onChange={(event) => setCpu(event.target.value)} placeholder="Ryzen 7 5800H" autoComplete="off" /></label>
              <label>GPU<input value={gpu} onChange={(event) => setGpu(event.target.value)} placeholder="RTX 4060" autoComplete="off" /></label>
              <label>RAM / Storage<div className="dual-input"><input value={ram} onChange={(event) => setRam(event.target.value.replace(/\D/g, ""))} placeholder="16 GB" /><input value={storage} onChange={(event) => setStorage(event.target.value.replace(/\D/g, ""))} placeholder="512 GB" /></div></label>
            </div>
          )}

          {error && <div className="error-box">{error}</div>}
          <button className="submit-button" disabled={loading} type="submit">
            {loading ? (
              <span className="button-loading-content">
                <span className="button-spinner" />
                <span>Menganalisis pasar...</span>
              </span>
            ) : (
              <>
                <span>Cek worth it</span>
                <span>↗</span>
              </>
            )}
          </button>
        </form>
        )}

        {loading ? (
          <LoadingCard mode={mode} />
        ) : mode === "bundle"
          ? bundleResult
            ? <BundleResultCard result={bundleResult} />
            : <div className="empty-state"><span>✦</span><p>Hasil cek bundle akan muncul di sini.<br />Tambahkan komponen lalu masukkan harga paketnya.</p></div>
          : result
            ? <ResultCard result={result} />
            : <div className="empty-state"><span>✦</span><p>Hasil analisis akan muncul di sini.<br />Masukkan produk untuk mulai membandingkan.</p></div>}
      </section>

      <footer><span>WorthGaBang?</span><span>Data pembanding diperbarui terjadwal · v1 MVP</span></footer>
    </main>
  );
}

function LoadingCard({ mode }: { mode: Mode }) {
  const [step, setStep] = useState(0);

  const steps =
    mode === "bundle"
      ? [
          "Mengurai komponen paket bundle...",
          "Mengecek katalog harga retail resmi...",
          "Memindai harga pasar bekas lepasan...",
          "Menghitung kalkulasi dual-market & penghematan...",
          "Menyusun rekomendasi kelayakan paket bundle...",
        ]
      : mode === "laptop"
      ? [
          "Menganalisis konfigurasi CPU, GPU, & RAM...",
          "Memeriksa katalog retail unit baru (BNIB)...",
          "Memindai ribuan listing laptop di pasar bekas...",
          "Mengevaluasi skor worth-it & kalkulasi pasar...",
          "Menyusun analisis lintas pasar baru vs bekas...",
        ]
      : [
          "Mencocokkan model & tier spesifikasi komponen...",
          "Mengambil harga retail baru dari katalog resmi...",
          "Memindai listing aktif di pasar marketplace...",
          "Mengevaluasi harga vs performa (worth-it score)...",
          "Menyiapkan daftar opsi pembanding terbaik...",
        ];

  useEffect(() => {
    const interval = setInterval(() => {
      setStep((prev) => (prev + 1) % steps.length);
    }, 1100);
    return () => clearInterval(interval);
  }, [steps.length]);

  return (
    <section className="result-card loading-card">
      <div className="result-topline">
        <div className="section-kicker">MEMERIKSA DATA PASAR...</div>
        <span className="loading-badge">
          <span className="pulse-dot" /> SEDANG MEMINDAI
        </span>
      </div>

      <div className="loading-progress-bar">
        <div className="loading-progress-fill" />
      </div>

      <div className="loading-status-box">
        <div className="loading-pulse-radar">⚡</div>
        <div className="loading-status-text">
          <span className="loading-status-title">{steps[step]}</span>
          <span className="loading-status-sub">Menghubungkan ke database harga baru &amp; pasar bekas</span>
        </div>
      </div>

      <div className="skeleton-score-row">
        <div>
          <div className="skeleton-shimmer skeleton-score-val" />
          <div className="skeleton-shimmer skeleton-score-desc" />
        </div>
        <div className="skeleton-price-meta">
          <div className="skeleton-shimmer skeleton-price-line-1" />
          <div className="skeleton-shimmer skeleton-price-line-2" />
          <div className="skeleton-shimmer skeleton-price-line-3" />
        </div>
      </div>

      <div className="skeleton-dual-market">
        <div className="skeleton-shimmer skeleton-market-card" />
        <div className="skeleton-shimmer skeleton-market-card" />
      </div>

      <div className="skeleton-shimmer skeleton-box" />

      <div className="skeleton-comparisons">
        <div className="skeleton-shimmer skeleton-row-item" />
        <div className="skeleton-shimmer skeleton-row-item" />
        <div className="skeleton-shimmer skeleton-row-item" />
      </div>
    </section>
  );
}

function BundleResultCard({ result }: { result: BundleResult }) {
  const verdictClass = result.verdict.replace(/ /g, "-");
  const hemat = result.savings_percent >= 0;
  const selisihRupiah = Math.abs(result.reference_total - result.bundle_price);

  return (
    <section className="result-card">
      <div className="result-topline">
        <div className="section-kicker">HASIL CEK BUNDLE</div>
        <span className={`verdict ${verdictClass}`}>
          {result.verdict === "kemahalan" && "⚠️ "}
          {result.verdict === "worth it" && "🔥 "}
          {result.verdict === "wajar" && "⚖️ "}
          {result.verdict}
        </span>
      </div>

      {/* HERO VERDICT BANNER - SANGAT MENONJOL & JELAS */}
      <div className={`hero-verdict-banner banner-${verdictClass}`}>
        <div className="banner-icon-col">
          {result.verdict === "kemahalan" ? "🚨" : result.verdict === "worth it" ? "🔥" : "⚖️"}
        </div>
        <div className="banner-text-col">
          <div className="banner-heading">
            {result.verdict === "kemahalan" && "KEMAHALAN — TIDAK DISARANKAN"}
            {result.verdict === "worth it" && "WORTH IT BANGET — SANGAT MENGUNTUNGKAN"}
            {result.verdict === "wajar" && "HARGA WAJAR — SESUAI PASAR"}
            {result.verdict === "ada opsi lebih baik" && "ADA OPSI LEBIH BAIK"}
            {result.verdict === "data terbatas" && "DATA PASAR TERBATAS"}
          </div>
          <div className="banner-explanation">
            {hemat ? (
              <>
                Paket ini <strong>lebih hemat {formatRupiah(selisihRupiah)} ({result.savings_percent}%)</strong> dibanding membeli komponen satuan di pasar!
              </>
            ) : (
              <>
                Paket ini <strong>lebih mahal {formatRupiah(selisihRupiah)} ({Math.abs(result.savings_percent)}%)</strong> dibanding membeli komponen satuan di pasar normal!
              </>
            )}
          </div>
        </div>
      </div>

      <div className="score-row">
        <div>
          <div className={`score-number score-${verdictClass}`}>
            {Math.round(result.score)}
            <small>/100</small>
          </div>
          <div className="score-caption">Skor kelayakan paket bundling</div>
        </div>
        <div className="price-summary">
          <span>Harga paket bundle</span>
          <strong>{formatRupiah(result.bundle_price)}</strong>
          <small>
            Total normal {formatRupiah(result.reference_total)} ·{" "}
            <strong className={hemat ? "savings-pos" : "savings-neg"}>
              {hemat ? `hemat ${result.savings_percent}%` : `lebih mahal ${Math.abs(result.savings_percent)}%`}
            </strong>
          </small>
        </div>
      </div>

      {(result.new_reference_total || result.used_reference_total) && (
        <div className="dual-market-grid">
          <div className="market-card market-new">
            <div className="market-badge-label">🏷️ Total Normal Baru (Retail)</div>
            <div className="market-price-val">
              {result.new_reference_total ? formatRupiah(result.new_reference_total) : formatRupiah(result.reference_total)}
            </div>
            <div className="market-desc">
              {result.savings_percent >= 0 ? `Hemat ${result.savings_percent}% beli paket` : `Lebih mahal ${Math.abs(result.savings_percent)}%`}
            </div>
          </div>
          <div className="market-card market-used">
            <div className="market-badge-label">📦 Total Estimasi Bekas (Eceran)</div>
            <div className="market-price-val">
              {result.used_reference_total ? formatRupiah(result.used_reference_total) : "Data Terbatas"}
            </div>
            <div className="market-desc">
              {result.savings_used_percent !== undefined && result.savings_used_percent !== null
                ? (result.savings_used_percent >= 0
                    ? `Hemat ${result.savings_used_percent}% vs total bekas`
                    : `Lebih mahal ${Math.abs(result.savings_used_percent)}% vs bekas`)
                : "Estimasi part second terpisah"}
            </div>
          </div>
        </div>
      )}

      {/* KESIMPULAN AKHIR & SARAN PEMBELIAN */}
      <div className={`bundle-conclusion-box conclusion-${verdictClass}`}>
        <div className="bundle-conclusion-title">
          <span>{result.verdict === "kemahalan" ? "⚠️" : result.verdict === "worth it" ? "💡" : "📌"}</span>
          <span>Kesimpulan Akhir &amp; Saran Pembelian</span>
        </div>
        <p className="bundle-conclusion-desc">
          {result.verdict === "kemahalan" ? (
            <>
              Hindari membeli paket ini di harga <strong>{formatRupiah(result.bundle_price)}</strong> karena Anda membayar sekitar <strong>{formatRupiah(selisihRupiah)} lebih mahal</strong> dari harga pasaran. Disarankan untuk menawar harga paket ini menjadi sekitar <strong>{formatRupiah(result.reference_total)}</strong> atau lebih baik membeli komponen lepasan secara mandiri.
            </>
          ) : result.verdict === "worth it" ? (
            <>
              Paket ini merupakan <strong>penawaran yang sangat menguntungkan</strong>. Anda menghemat <strong>{formatRupiah(selisihRupiah)} ({result.savings_percent}%)</strong> dibanding membeli dan merakit sendiri dari harga normal pasar.
            </>
          ) : (
            <>
              Harga paket ini relatif wajar dan seimbang dengan harga pasaran normal ({formatRupiah(result.reference_total)}). Anda bisa mencoba menawar sedikit untuk mendapatkan nilai lebih menguntungkan.
            </>
          )}
        </p>
      </div>

      {result.cross_market_advice && (
        <div className="cross-market-box">
          <div className="cross-market-header">
            <span className="cross-market-icon">💡</span>
            <strong>Analisis Nilai Paket Bundle</strong>
          </div>
          <p className="cross-market-text">{result.cross_market_advice}</p>
        </div>
      )}

      <div className="comparisons">
        <div className="comparison-heading">
          <h3>Rincian referensi per komponen</h3>
          <span>{result.items.length} komponen dalam paket</span>
        </div>
        {result.items.map((item, index) => (
          <div className="comparison-row" key={`${item.query}-${index}`}>
            <span className="rank">0{index + 1}</span>
            <span className="comparison-title">
              {item.query}
              <small>
                <span className="source-tag source-retail">{item.component_type.toUpperCase()}</span>
                {item.price_input ? ` · input ${formatRupiah(item.price_input)}` : " · ikut harga bundle"}
                {item.used_reference_price ? ` · bekas est. ${formatRupiah(item.used_reference_price)}` : ""}
              </small>
            </span>
            <div style={{ textAlign: "right" }}>
              <strong>{formatRupiah(item.new_reference_price || item.reference_price)}</strong>
              <small style={{ display: "block", color: "var(--muted)", fontSize: "9px" }}>
                {item.used_reference_price ? `bekas: ${formatRupiah(item.used_reference_price)}` : "normal baru"}
              </small>
            </div>
            <span className="arrow">—</span>
          </div>
        ))}
      </div>
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
        <span className={`verdict ${verdictClass}`}>
          {result.verdict === "kemahalan" && "⚠️ "}
          {result.verdict === "worth it" && "🔥 "}
          {result.verdict === "wajar" && "⚖️ "}
          {result.verdict}
        </span>
      </div>

      {/* HERO VERDICT BANNER */}
      <div className={`hero-verdict-banner banner-${verdictClass}`}>
        <div className="banner-icon-col">
          {result.verdict === "kemahalan" ? "🚨" : result.verdict === "worth it" ? "🔥" : result.verdict === "ada opsi lebih baik" ? "💡" : "⚖️"}
        </div>
        <div className="banner-text-col">
          <div className="banner-heading">
            {result.verdict === "kemahalan" && "KEMAHALAN — DI ATAS HARGA WAJAR"}
            {result.verdict === "worth it" && "WORTH IT — HARGA SANGAT BAGUS"}
            {result.verdict === "wajar" && "HARGA WAJAR — SESUAI PASAR"}
            {result.verdict === "ada opsi lebih baik" && "ADA OPSI LEBIH BAIK"}
            {result.verdict === "data terbatas" && "DATA PASAR TERBATAS"}
          </div>
          <div className="banner-explanation">
            {result.verdict === "kemahalan" && "Harga yang Anda temukan lebih tinggi dari median pasaran normal. Disarankan untuk menawar atau mencari penjual lain."}
            {result.verdict === "worth it" && "Harga ini di bawah rata-rata pasar saat ini. Sangat direkomendasikan untuk segera diamankan jika kondisi unit normal!"}
            {result.verdict === "wajar" && "Harga ini berada dalam rentang wajar dan masuk akal untuk pasaran saat ini."}
            {result.verdict === "ada opsi lebih baik" && "Di rentang harga ini, tersedia opsi alternatif dengan performa atau spesifikasi yang lebih tinggi."}
            {result.verdict === "data terbatas" && "Jumlah pembanding di database masih terbatas untuk produk ini."}
          </div>
        </div>
      </div>

      <div className="score-row">
        <div>
          <div className={`score-number score-${verdictClass}`}>
            {Math.round(result.score)}
            <small>/100</small>
          </div>
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
