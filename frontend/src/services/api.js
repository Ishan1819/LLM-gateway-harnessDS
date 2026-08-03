const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')

const TOKEN_KEY = 'acg_token'

export const auth = {
  get token() {
    return localStorage.getItem(TOKEN_KEY)
  },
  set token(value) {
    if (value) localStorage.setItem(TOKEN_KEY, value)
    else localStorage.removeItem(TOKEN_KEY)
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY)
  },
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function request(path, { method = 'GET', body, auth: withAuth = true } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (withAuth && auth.token) headers.Authorization = `Bearer ${auth.token}`

  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (response.status === 401 && withAuth) {
    auth.clear()
    window.location.hash = '#/login'
    throw new ApiError('Your session expired. Please sign in again.', 401)
  }

  if (response.status === 204) return null

  const payload = await response.json().catch(() => null)

  if (!response.ok) {
    const detail = payload?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : detail?.error?.message ||
          (Array.isArray(detail) ? detail[0]?.msg : null) ||
          `Request failed (${response.status})`
    throw new ApiError(message, response.status)
  }

  return payload
}

export const api = {
  // --- auth ---
  login: (email, password) =>
    request('/api/auth/login', { method: 'POST', body: { email, password }, auth: false }),
  register: (payload) =>
    request('/api/auth/register', { method: 'POST', body: payload, auth: false }),
  me: () => request('/api/auth/me'),

  // --- analytics ---
  dashboard: () => request('/api/admin/dashboard'),
  usage: (groupBy = 'user', period = 'month') =>
    request(`/api/admin/usage?group_by=${groupBy}&period=${period}`),
  savings: () => request('/api/admin/savings'),

  // --- directory ---
  users: () => request('/api/admin/users'),
  createUser: (payload) => request('/api/admin/users', { method: 'POST', body: payload }),
  deleteUser: (id) => request(`/api/admin/users/${id}`, { method: 'DELETE' }),
  revealKey: (id) => request(`/api/admin/users/${id}/key`),

  teams: () => request('/api/admin/teams'),
  createTeam: (payload) => request('/api/admin/teams', { method: 'POST', body: payload }),

  // --- caps ---
  updateUserCaps: (id, payload) =>
    request(`/api/admin/caps/${id}`, { method: 'PUT', body: payload }),
  updateTeamCaps: (id, payload) =>
    request(`/api/admin/caps/team/${id}`, { method: 'PUT', body: payload }),
  bulkUpdateCaps: (payload) => request('/api/admin/caps/bulk', { method: 'PUT', body: payload }),

  // --- alerts ---
  alerts: (limit = 100) => request(`/api/admin/alerts?limit=${limit}`),
  markAlertRead: (id) => request(`/api/admin/alerts/${id}/read`, { method: 'PUT' }),

  // --- settings ---
  getKeys: () => request('/api/admin/settings/keys'),
  updateKeys: (payload) => request('/api/admin/settings/keys', { method: 'PUT', body: payload }),
  pricing: () => request('/api/admin/settings/pricing'),
}
