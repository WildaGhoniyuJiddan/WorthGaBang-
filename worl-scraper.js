// worl-scraper.js — mesin inti hasil ekstraksi llm-scraper (mishushakov/llm-scraper, MIT),
// di-port jadi modul sendiri dengan API desain sendiri.
//
// API:
//   const { WorLScraper } = require('./worl-scraper')
//   const scraper = new WorLScraper(model)            // model = AI SDK LanguageModel
//   await scraper.extract(page, schema, { format })  // -> { data, url }
//   scraper.stream(page, schema, opts)               // -> { stream, url }
//   await scraper.generateCode(page, schema, opts)   // -> { code, url }
//
// Perbedaan dari aslinya:
//   - format default 'text' (hemat token, Readability) bukan 'html'
//   - schema langsung Zod (tidak perlu Output.object() wrapper)
//   - system prompt bisa dioverride per call

const turndown = require('turndown')
const { generateText, streamText, Output } = require('ai')

const SYSTEM_EXTRACT =
  'You are a sophisticated web scraper. Extract the contents of the webpage'

const SYSTEM_CODE =
  "Provide a scraping function in JavaScript that extracts and returns data according to a schema from the current page. The function must be IIFE. No comments or imports. No console.log. The code you generate will be executed straight away, you shouldn't output anything besides runnable code."

// ---- preprocess (dari src/preprocess.ts + cleanup.ts, digabung) ----

const CLEANUP_JS = `
() => {
  const remove = ['script','style','noscript','iframe','svg','img','audio','video','canvas','map','source','dialog','menu','menuitem','track','object','embed','form','input','button','select','textarea','label','option','optgroup','aside','footer','header','nav','head'];
  const attrs = ['style','src','alt','title','role','aria-','tabindex','on','data-'];
  document.querySelectorAll('*').forEach(el => {
    if (remove.includes(el.tagName.toLowerCase())) el.remove();
    Array.from(el.attributes || []).forEach(a => {
      if (attrs.some(p => a.name.startsWith(p))) el.removeAttribute(a.name);
    });
  });
}
`

async function preprocess(page, options = {}) {
  const url = page.url()
  const format = options.format ?? 'text'
  let content

  switch (format) {
    case 'raw_html':
      content = await page.content()
      break
    case 'markdown': {
      const body = await page.innerHTML('body')
      content = new turndown().turndown(body)
      break
    }
    case 'text': {
      // Readability via CDN seperti aslinya
      const readable = await page.evaluate(async () => {
        const readability = await import('https://cdn.skypack.dev/@mozilla/readability')
        return new readability.Readability(document).parse()
      })
      content = `Page Title: ${readable.title}\n${readable.textContent}`
      break
    }
    case 'html':
      await page.evaluate(CLEANUP_JS)
      content = await page.content()
      break
    case 'image': {
      const image = await page.screenshot({
        fullPage: 'fullPage' in options ? options.fullPage : undefined,
      })
      content = image.toString('base64')
      break
    }
    case 'custom':
      if (typeof options.formatFunction !== 'function') {
        throw new Error("format 'custom' butuh options.formatFunction")
      }
      content = await options.formatFunction(page)
      break
    default:
      throw new Error(`format tidak dikenal: ${format}`)
  }

  return { url, content, format }
}

// ---- helpers ----

function toPageInput(pre) {
  if (pre.format === 'image') {
    return [{ type: 'image', image: pre.content }]
  }
  return [{ type: 'text', text: pre.content }]
}

function stripBackticks(text) {
  return text.trim().replace(/^```(?:javascript)?\s*/i, '').replace(/\s*```$/i, '')
}

// ---- engine ----

class WorLScraper {
  constructor(model) {
    this.model = model
  }

  /** Ekstrak data terstruktur dari halaman. schema = Zod object. */
  async extract(page, schema, options = {}) {
    const pre = await preprocess(page, options)
    const result = await generateText({
      model: this.model,
      output: Output.object({ schema }),
      system: options.system ?? SYSTEM_EXTRACT,
      messages: [
        { role: 'user', content: toPageInput(pre) },
        ...(options.messages ?? []),
      ],
      ...(options.callSettings ?? {}),
    })
    return { data: result.output, url: pre.url }
  }

  /** Stream data parsial saat LLM generate. */
  stream(page, schema, options = {}) {
    // preprocess async dilakukan dulu lalu mulai streaming — return Promise
    return preprocess(page, options).then((pre) => {
      const { partialOutputStream } = streamText({
        model: this.model,
        output: Output.object({ schema }),
        system: options.system ?? SYSTEM_EXTRACT,
        messages: [
          { role: 'user', content: toPageInput(pre) },
          ...(options.messages ?? []),
        ],
        ...(options.callSettings ?? {}),
      })
      return { stream: partialOutputStream, url: pre.url }
    })
  }

  /** Generate kode scraping reusable (IIFE JS) sesuai schema. */
  async generateCode(page, schema, options = {}) {
    const pre = await preprocess(page, { format: 'html', ...options })
    const jsonSchema = JSON.stringify(schema)
    const result = await generateText({
      model: this.model,
      system: options.system ?? SYSTEM_CODE,
      messages: [
        {
          role: 'user',
          content: `Website: ${pre.url}\nSchema: ${jsonSchema}\nContent: ${pre.content}`,
        },
      ],
      ...(options.callSettings ?? {}),
    })
    return { code: stripBackticks(result.text), url: pre.url }
  }
}

module.exports = { WorLScraper, preprocess, CLEANUP_JS }
