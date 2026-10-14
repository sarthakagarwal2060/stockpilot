async function request(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body.detail === 'string') message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d) => `${d.loc?.at(-1)}: ${d.msg}`).join('; ');
    } catch {
      /* non-JSON error body */
    }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

export const api = {
  listProducts: (params = {}) => {
    const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
    return request(`/products${query ? `?${query}` : ''}`);
  },
  stats: () => request('/products/stats'),
  movements: (limit = 12) => request(`/movements?limit=${limit}`),
  createProduct: (data) => request('/products', { method: 'POST', body: JSON.stringify(data) }),
  updateProduct: (id, data) => request(`/products/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteProduct: (id) => request(`/products/${id}`, { method: 'DELETE' }),
  adjustStock: (id, data) => request(`/products/${id}/adjust`, { method: 'POST', body: JSON.stringify(data) }),
};
