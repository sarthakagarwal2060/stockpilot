import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './api.js';
import { AdjustModal, ProductModal } from './Modals.jsx';

const STATUS_TABS = [
  { key: '', label: 'All' },
  { key: 'IN_STOCK', label: 'In stock' },
  { key: 'LOW_STOCK', label: 'Low stock' },
  { key: 'OUT_OF_STOCK', label: 'Out of stock' },
];

const STATUS_LABEL = { IN_STOCK: 'In stock', LOW_STOCK: 'Low stock', OUT_OF_STOCK: 'Out of stock' };

const PIPELINE = ['Commit', 'Pytest', 'Build', 'Trivy', 'GHCR', 'Helm', 'EKS'];

export const currency = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 });
const number = new Intl.NumberFormat('en-IN');

function timeAgo(iso) {
  const seconds = Math.max(1, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  const units = [['d', 86400], ['h', 3600], ['m', 60]];
  for (const [label, size] of units) if (seconds >= size) return `${Math.floor(seconds / size)}${label} ago`;
  return `${seconds}s ago`;
}

function useDebounced(value, delay = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

export default function App() {
  const [products, setProducts] = useState([]);
  const [stats, setStats] = useState(null);
  const [movements, setMovements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [category, setCategory] = useState('');
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState(null); // null | {} (new) | product
  const [adjusting, setAdjusting] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const debouncedSearch = useDebounced(search);

  const load = useCallback(async () => {
    try {
      const [list, s, m] = await Promise.all([
        api.listProducts({ search: debouncedSearch, category, stock_status: statusFilter }),
        api.stats(),
        api.movements(),
      ]);
      setProducts(list);
      setStats(s);
      setMovements(m);
      setError('');
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [debouncedSearch, category, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!toast) return undefined;
    const id = setTimeout(() => setToast(''), 3000);
    return () => clearTimeout(id);
  }, [toast]);

  const [allCategories, setAllCategories] = useState([]);
  useEffect(() => {
    if (!category && !statusFilter && !debouncedSearch) {
      setAllCategories([...new Set(products.map((p) => p.category))].sort());
    }
  }, [products, category, statusFilter, debouncedSearch]);

  const reorderList = useMemo(
    () => products.filter((p) => p.stock_status !== 'IN_STOCK').sort((a, b) => a.quantity - b.quantity).slice(0, 5),
    [products],
  );

  async function handleSave(data) {
    if (editing?.id) {
      await api.updateProduct(editing.id, data);
      setToast(`Updated ${data.name}`);
    } else {
      await api.createProduct(data);
      setToast(`Added ${data.name}`);
    }
    setEditing(null);
    load();
  }

  async function handleAdjust(data) {
    const updated = await api.adjustStock(adjusting.id, data);
    setToast(`${updated.name}: ${data.change > 0 ? '+' : ''}${data.change} → ${updated.quantity} on hand`);
    setAdjusting(null);
    load();
  }

  async function handleDelete(product) {
    if (!window.confirm(`Delete ${product.name} (${product.sku})? Its movement history is deleted too.`)) return;
    try {
      await api.deleteProduct(product.id);
      setToast(`Deleted ${product.name}`);
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  const kpis = stats && [
    { label: 'Products', value: number.format(stats.totalProducts), hint: `${stats.categories} categories`, tone: 'blue' },
    { label: 'Units on hand', value: number.format(stats.totalUnits), hint: 'across all locations', tone: 'violet' },
    { label: 'Inventory value', value: currency.format(Number(stats.inventoryValue)), hint: 'at unit cost', tone: 'green' },
    { label: 'Low stock', value: stats.lowStock, hint: 'at or below reorder level', tone: 'amber' },
    { label: 'Out of stock', value: stats.outOfStock, hint: 'needs restocking', tone: 'red' },
  ];

  return (
    <div className="layout">
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="brand">
          <span className="logo">▤</span>
          <div>
            <strong>StockPilot</strong>
            <small>Inventory Cloud</small>
          </div>
        </div>
        <nav>
          <a className="active" href="#dashboard">Dashboard</a>
          <a href="#products">Products</a>
          <a href="#activity">Stock movements</a>
          <a href="/api/docs" target="_blank" rel="noreferrer">API docs ↗</a>
        </nav>
        <div className="workspace">
          <small>Warehouse</small>
          <strong>Main Warehouse · Pune</strong>
        </div>
      </aside>
      {sidebarOpen && <div className="scrim" onClick={() => setSidebarOpen(false)} />}

      <main id="dashboard">
        <header className="topbar">
          <button className="menu" aria-label="Open menu" onClick={() => setSidebarOpen(true)}>☰</button>
          <div>
            <h1>Inventory overview</h1>
            <p className="muted">Track stock levels, reorder points and every movement in one place.</p>
          </div>
          <button className="primary" onClick={() => setEditing({})}>+ New product</button>
        </header>

        {error && (
          <div className="banner error" role="alert">
            <strong>Backend unavailable.</strong> {error}
            <button className="link" onClick={() => { setLoading(true); load(); }}>Retry</button>
          </div>
        )}

        <section className="kpis">
          {loading && !stats
            ? Array.from({ length: 5 }, (_, i) => <div key={i} className="kpi skeleton" />)
            : kpis?.map((k) => (
                <div key={k.label} className={`kpi tone-${k.tone}`}>
                  <span>{k.label}</span>
                  <strong>{k.value}</strong>
                  <small>{k.hint}</small>
                </div>
              ))}
        </section>

        <section className="pipeline" aria-label="Delivery pipeline">
          {PIPELINE.map((step, i) => (
            <span key={step} className="step">
              <i>✓</i>{step}{i < PIPELINE.length - 1 && <b>→</b>}
            </span>
          ))}
        </section>

        <div className="grid">
          <section className="card" id="products">
            <div className="card-head">
              <h2>Products</h2>
              <div className="filters">
                <input
                  type="search"
                  placeholder="Search name, SKU, supplier…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
                  <option value="">All categories</option>
                  {allCategories.map((c) => <option key={c}>{c}</option>)}
                </select>
              </div>
            </div>
            <div className="tabs" role="tablist">
              {STATUS_TABS.map((t) => (
                <button
                  key={t.key}
                  role="tab"
                  aria-selected={statusFilter === t.key}
                  className={statusFilter === t.key ? 'active' : ''}
                  onClick={() => setStatusFilter(t.key)}
                >
                  {t.label}
                </button>
              ))}
            </div>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>Category / location</th>
                    <th className="num">On hand</th>
                    <th className="num">Unit price</th>
                    <th>Status</th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {loading && products.length === 0 && (
                    <tr><td colSpan="6" className="empty">Loading inventory…</td></tr>
                  )}
                  {!loading && products.length === 0 && (
                    <tr><td colSpan="6" className="empty">No products match these filters.</td></tr>
                  )}
                  {products.map((p) => (
                    <tr key={p.id}>
                      <td data-label="Product">
                        <strong>{p.name}</strong>
                        <small className="sku">{p.sku} · {p.supplier}</small>
                      </td>
                      <td data-label="Category">
                        <span>
                          {p.category}
                          <small className="muted">{p.location}</small>
                        </span>
                      </td>
                      <td data-label="On hand" className="num">
                        <span>
                          {number.format(p.quantity)}
                          <small className="muted"> / min {p.reorder_level}</small>
                        </span>
                      </td>
                      <td data-label="Unit price" className="num">{currency.format(Number(p.unit_price))}</td>
                      <td data-label="Status">
                        <span className={`badge ${p.stock_status.toLowerCase()}`}>{STATUS_LABEL[p.stock_status]}</span>
                      </td>
                      <td className="actions">
                        <button onClick={() => setAdjusting(p)}>Adjust</button>
                        <button onClick={() => setEditing(p)}>Edit</button>
                        <button className="danger" onClick={() => handleDelete(p)}>Delete</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <aside className="side">
            <section className="card">
              <h2>Reorder soon</h2>
              {reorderList.length === 0 ? (
                <p className="muted">All visible products are above their reorder level.</p>
              ) : (
                <ul className="reorder">
                  {reorderList.map((p) => (
                    <li key={p.id}>
                      <div>
                        <strong>{p.name}</strong>
                        <small className="muted">{p.quantity} left · reorder at {p.reorder_level}</small>
                      </div>
                      <button className="small" onClick={() => setAdjusting({ ...p, presetRestock: true })}>Restock</button>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="card" id="activity">
              <h2>Recent movements</h2>
              {movements.length === 0 ? (
                <p className="muted">No stock movements yet.</p>
              ) : (
                <ul className="feed">
                  {movements.map((m) => (
                    <li key={m.id}>
                      <span className={`delta ${m.change > 0 ? 'in' : 'out'}`}>{m.change > 0 ? `+${m.change}` : m.change}</span>
                      <div>
                        <strong>{m.product_name}</strong>
                        <small className="muted">
                          {m.reason.toLowerCase()} · {m.quantity_after} on hand · {timeAgo(m.created_at)}
                          {m.note && ` · ${m.note}`}
                        </small>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </aside>
        </div>
      </main>

      {editing && <ProductModal product={editing} onClose={() => setEditing(null)} onSave={handleSave} />}
      {adjusting && <AdjustModal product={adjusting} onClose={() => setAdjusting(null)} onSave={handleAdjust} />}
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
