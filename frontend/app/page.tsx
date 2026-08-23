"use client";

import { FormEvent, useState } from "react";
import { analyzePrice, AnalyzeResult, Mode } from "../lib/api";

const formatRupiah = (value: number) =>
  new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(value);

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
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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

  return (
    <main className="page-shell">
      <section className="hero">
        <div className="eyebrow">HargaPas / marketplace intelligence</div>
        <h1>Harga yang kamu temukan, <span>masuk akal nggak?</span></h1>
        <p>Bandingkan dengan data listing yang sudah dikumpulkan dari marketplace, tanpa menunggu scraping saat request.</p>
      </section>

      <section className="workspace">
        <div className="mode-toggle" role="tablist" aria-label="Mode analisis">
          <button className={mode === "pc" ? "active" : ""} onClick={() => setMode("pc")} type="button">PC Components</button>
          <button className={mode === "laptop" ? "active" : ""} onClick={() => setMode("laptop")} type="button">Laptop</button>
        </div>

        <form className="checker-card" onSubmit={handleSubmit}>
          <div className="form-heading">
            <div>
              <div className="section-kicker">Mode {mode === "pc" ? "PC" : "Laptop"}</div>
              <h2>Masukkan produk yang mau dicek</h2>
            </div>
            <span className="status-pill"><i /> Data katalog</span>
          </div>

          <label>
            Nama / query produk
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={mode === "pc" ? "contoh: RTX 4060" : "contoh: ASUS ROG RTX 4060"} required />
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
              <label>CPU<input value={cpu} onChange={(event) => setCpu(event.target.value)} placeholder="Core i5 / Ryzen 5" /></label>
              <label>GPU<input value={gpu} onChange={(event) => setGpu(event.target.value)} placeholder="RTX 4060" /></label>
              <label>RAM / Storage<div className="dual-input"><input value={ram} onChange={(event) => setRam(event.target.value.replace(/\D/g, ""))} placeholder="16 GB" /><input value={storage} onChange={(event) => setStorage(event.target.value.replace(/\D/g, ""))} placeholder="512 GB" /></div></label>
            </div>
          )}

          {error && <div className="error-box">{error}</div>}
          <button className="submit-button" disabled={loading} type="submit">{loading ? "Menganalisis..." : "Cek worth it"}<span>↗</span></button>
        </form>

        {result ? <ResultCard result={result} /> : <div className="empty-state"><span>✦</span><p>Hasil analisis akan muncul di sini.<br />Masukkan produk untuk mulai membandingkan.</p></div>}
      </section>

      <footer><span>HargaPas</span><span>Data pembanding diperbarui terjadwal · v1 MVP</span></footer>
    </main>
  );
}

function ResultCard({ result }: { result: AnalyzeResult }) {
  const verdictClass = result.verdict.replace(/ /g, "-");
  return (
    <section className="result-card">
      <div className="result-topline"><div className="section-kicker">HASIL ANALISIS</div><span className={`verdict ${verdictClass}`}>{result.verdict}</span></div>
      <div className="score-row">
        <div><div className="score-number">{Math.round(result.score)}<small>/100</small></div><div className="score-caption">Skor worth-it untuk <strong>{result.query}</strong></div></div>
        <div className="price-summary"><span>Harga kamu</span><strong>{formatRupiah(result.input_price)}</strong><small>Median pembanding {formatRupiah(result.reference_price)}</small></div>
      </div>
      <p className="recommendation">{result.recommendation}</p>
      <div className="result-meta"><span>Data {result.freshness.label}</span><span>Sumber utama: {result.freshness.primary_source}</span>{result.freshness.is_stale && <span className="stale">Perlu refresh</span>}</div>
      <div className="comparisons"><div className="comparison-heading"><h3>Pembanding yang dipakai</h3><span>{result.comparisons.length} referensi</span></div>{result.comparisons.map((comparison, index) => <a className="comparison-row" href={comparison.listing_url || undefined} key={`${comparison.source}-${index}`} target={comparison.listing_url ? "_blank" : undefined} rel="noreferrer"><span className="rank">0{index + 1}</span><span className="comparison-title">{comparison.title}<small>{comparison.source === "price_reference" ? "referensi katalog, bukan listing marketplace" : comparison.source} · match {Math.round(comparison.similarity * 100)}%</small></span><strong>{formatRupiah(comparison.price)}</strong><span className="arrow">{comparison.listing_url ? "↗" : "—"}</span></a>)}</div>
    </section>
  );
}
