"use client";

import { useEffect, useRef, useState } from "react";
import { fetchSuggestions, Suggestion } from "../lib/api";

type Props = {
  value: string;
  onChange: (value: string) => void;
  section: string; // gpu | cpu | ram | storage | motherboard | laptop | ""
  condition?: string; // UI: new | second | any -> dipetakan ke API: baru | bekas | any
  placeholder?: string;
};

const formatRupiah = (value: number) =>
  new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(value);

export default function SuggestInput({ value, onChange, section, condition, placeholder }: Props) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(-1);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  useEffect(() => {
    if (!open || !section) {
      setSuggestions([]);
      return;
    }
    const apiCondition = condition === "new" ? "baru" : condition === "second" ? "bekas" : "any";
    const controller = new AbortController();
    const timer = setTimeout(() => {
      fetchSuggestions(section, value.trim(), controller.signal, apiCondition)
        .then(setSuggestions)
        .catch(() => undefined);
    }, 180); // debounce biar gak spam API tiap ketik
    setHighlighted(-1);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [value, open, section, condition]);

  function pick(suggestion: Suggestion) {
    onChange(suggestion.label);
    setOpen(false);
    setSuggestions([]);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!suggestions.length || !open) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlighted((index) => (index + 1) % suggestions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((index) => (index - 1 + suggestions.length) % suggestions.length);
    } else if (event.key === "Enter" && highlighted >= 0) {
      event.preventDefault();
      pick(suggestions[highlighted]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className="suggest-wrap" ref={wrapRef}>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        autoComplete="off"
        required
      />
      {open && suggestions.length > 0 && (
        <ul className="suggest-list" role="listbox">
          {suggestions.map((suggestion, index) => (
            <li
              key={`${suggestion.label}-${index}`}
              className={index === highlighted ? "active" : ""}
              onMouseDown={(event) => {
                event.preventDefault(); // jangan blur input sebelum pick
                pick(suggestion);
              }}
              onMouseEnter={() => setHighlighted(index)}
            >
              <span className="suggest-label">{suggestion.label}</span>
              <span className="suggest-meta">
                {suggestion.samples > 1 && <small>{suggestion.samples} data</small>}
                {suggestion.price ? <strong>{formatRupiah(suggestion.price)}</strong> : null}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
