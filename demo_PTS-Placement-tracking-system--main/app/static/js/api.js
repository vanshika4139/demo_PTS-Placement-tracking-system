class APIClient {
  constructor(baseUrl = '/api/v1') {
    this.baseUrl = baseUrl;
  }

  async request(endpoint, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (!headers['Content-Type'] && options.body && typeof options.body === 'object') {
      headers['Content-Type'] = 'application/json';
    }
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      throw new Error('Session expired');
    }

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.message || 'Request failed');
    }
    return payload;
  }

  async get(endpoint, params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`${endpoint}${query ? `?${query}` : ''}`);
  }

  async post(endpoint, data = {}) {
    return this.request(endpoint, { method: 'POST', body: JSON.stringify(data) });
  }

  async put(endpoint, data = {}) {
    return this.request(endpoint, { method: 'PUT', body: JSON.stringify(data) });
  }

  async delete(endpoint) {
    return this.request(endpoint, { method: 'DELETE' });
  }
}

window.APIClient = APIClient;
