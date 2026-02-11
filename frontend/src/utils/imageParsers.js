function addBaseUrl(path, apiBaseUrl) {
  if (!apiBaseUrl) return path
  return `${apiBaseUrl}${path}`
}

export function normalizeImageSource(value, apiBaseUrl = '', mimeType = 'image/png') {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed) return null

  if (
    trimmed.startsWith('http://') ||
    trimmed.startsWith('https://') ||
    trimmed.startsWith('data:') ||
    trimmed.startsWith('blob:')
  ) {
    return trimmed
  }

  if (trimmed.startsWith('/')) {
    return addBaseUrl(trimmed, apiBaseUrl)
  }

  if (apiBaseUrl && (trimmed.startsWith('./') || trimmed.startsWith('../'))) {
    try {
      return new URL(trimmed, `${apiBaseUrl}/`).toString()
    } catch {
      return null
    }
  }

  if (/^[A-Za-z0-9+/=\s]+$/.test(trimmed)) {
    return `data:${mimeType};base64,${trimmed}`
  }

  return null
}

export function dedupeImages(items) {
  const seen = new Set()
  return items.filter((item) => {
    if (!item?.src || seen.has(item.src)) return false
    seen.add(item.src)
    return true
  })
}

function pickStringField(value) {
  return typeof value === 'string' ? value.trim() : ''
}

export function formatTimestamp(value) {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return ''
  return parsed.toLocaleString()
}

function candidateMetadata(candidate) {
  return {
    id: pickStringField(candidate.id || candidate.image_id),
    runId: pickStringField(candidate.run_id),
    prompt: pickStringField(candidate.prompt),
    provider: pickStringField(candidate.provider),
    model: pickStringField(candidate.model),
    createdAt: formatTimestamp(candidate.created_at),
  }
}

export function parseImageCandidate(candidate, index, apiBaseUrl = '') {
  if (typeof candidate === 'string') {
    const src = normalizeImageSource(candidate, apiBaseUrl)
    return src ? { src, alt: `Generated image ${index + 1}` } : null
  }

  if (!candidate || typeof candidate !== 'object') return null

  const mimeType = candidate.mime_type || candidate.content_type || 'image/png'
  const src =
    normalizeImageSource(candidate.url, apiBaseUrl) ||
    normalizeImageSource(candidate.src, apiBaseUrl) ||
    normalizeImageSource(candidate.image_url, apiBaseUrl) ||
    normalizeImageSource(candidate.image_base64, apiBaseUrl, mimeType) ||
    normalizeImageSource(candidate.b64_json, apiBaseUrl, mimeType) ||
    normalizeImageSource(candidate.base64, apiBaseUrl, mimeType)

  if (!src) return null

  return {
    src,
    alt: candidate.alt || `Generated image ${index + 1}`,
    ...candidateMetadata(candidate),
  }
}

export function parseStoredImageRecord(record, index, apiBaseUrl = '') {
  if (!record || typeof record !== 'object') return null
  const parsed = parseImageCandidate(record, index, apiBaseUrl)
  if (!parsed) return null

  return {
    ...parsed,
    id: typeof record.id === 'string' ? record.id : `archived-${index}`,
    runId: typeof record.run_id === 'string' ? record.run_id : '',
    prompt: pickStringField(record.prompt),
    provider: pickStringField(record.provider),
    model: pickStringField(record.model),
    createdAt: formatTimestamp(record.created_at),
  }
}

export function parseRunRecord(run, index, apiBaseUrl = '') {
  if (!run || typeof run !== 'object') return null

  const runId = typeof run.run_id === 'string' ? run.run_id : `run-${index}`
  const createdAt = formatTimestamp(run.created_at)
  const images = Array.isArray(run.images)
    ? run.images.map((item, imageIndex) => parseStoredImageRecord(item, imageIndex, apiBaseUrl)).filter(Boolean)
    : []

  return {
    runId,
    createdAt,
    imageCount: typeof run.image_count === 'number' ? run.image_count : images.length,
    images,
  }
}

export function extractImages(payload, apiBaseUrl = '', extra = {}) {
  const candidates = []

  const singleImageCandidate = payload?.image_url || payload?.image_base64 || payload?.b64_json
  if (singleImageCandidate) {
    candidates.push(singleImageCandidate)
  }

  if (Array.isArray(payload?.images)) candidates.push(...payload.images)
  if (Array.isArray(payload?.data)) candidates.push(...payload.data)
  if (Array.isArray(payload?.image_urls)) candidates.push(...payload.image_urls)

  return dedupeImages(
    candidates
      .map((item, index) => parseImageCandidate(item, index, apiBaseUrl))
      .filter(Boolean)
      .map((item) => ({ ...item, ...extra })),
  )
}
