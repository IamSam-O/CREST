let _token = null

export async function getToken() {
  if (_token) return _token
  try {
    const res = await fetch('/api/account/token/')
    if (res.ok) _token = (await res.json()).token
  } catch (_) {}
  return _token
}

export async function api(url, options = {}) {
  const token = await getToken()
  const res = await fetch(url, {
    ...options,
    headers: {
      ...(token ? { Authorization: `Token ${token}` } : {}),
      ...options.headers,
    },
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`)
  return data
}

export function clearToken() {
  _token = null
}
