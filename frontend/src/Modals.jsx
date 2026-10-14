import { useEffect, useState } from 'react';

const EMPTY = {
  sku: '', name: '', description: '', category: 'General', supplier: '', location: 'Main Warehouse',
  quantity: 0, reorder_level: 10, unit_price: '0.00',
};

const REASONS = ['RESTOCK', 'SALE', 'RETURN', 'DAMAGED', 'CORRECTION'];

function Modal({ title, onClose, children }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <header>
          <h2>{title}</h2>
          <button className="icon" aria-label="Close" onClick={onClose}>×</button>
        </header>
        {children}
      </div>
    </div>
  );
}

function useSubmit(onSave) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  async function submit(data) {
    setSaving(true);
    setError('');
    try {
      await onSave(data);
    } catch (e) {
      setError(e.message);
      setSaving(false);
    }
  }
  return { saving, error, submit };
}

export function ProductModal({ product, onClose, onSave }) {
  const isNew = !product.id;
  const [form, setForm] = useState({ ...EMPTY, ...product });
  const { saving, error, submit } = useSubmit(onSave);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  function handleSubmit(e) {
    e.preventDefault();
    const data = {
      sku: form.sku.trim(),
      name: form.name.trim(),
      description: form.description,
      category: form.category.trim() || 'General',
      supplier: form.supplier.trim() || 'Unknown',
      location: form.location.trim() || 'Main Warehouse',
      reorder_level: Number(form.reorder_level),
      unit_price: Number(form.unit_price).toFixed(2),
    };
    if (isNew) data.quantity = Number(form.quantity);
    submit(data);
  }

  return (
    <Modal title={isNew ? 'New product' : `Edit ${product.name}`} onClose={onClose}>
      <form onSubmit={handleSubmit} className="form">
        <label>SKU<input required minLength={2} maxLength={40} pattern="[A-Za-z0-9_\-]+" value={form.sku} onChange={set('sku')} placeholder="ELEC-1003" /></label>
        <label>Name<input required maxLength={200} value={form.name} onChange={set('name')} placeholder="USB-C Charging Hub" /></label>
        <label>Category<input maxLength={60} value={form.category} onChange={set('category')} /></label>
        <label>Supplier<input maxLength={120} value={form.supplier} onChange={set('supplier')} /></label>
        <label>Location<input maxLength={60} value={form.location} onChange={set('location')} /></label>
        <label>Unit price (₹)<input type="number" min="0" step="0.01" value={form.unit_price} onChange={set('unit_price')} /></label>
        {isNew && <label>Opening stock<input type="number" min="0" value={form.quantity} onChange={set('quantity')} /></label>}
        <label>Reorder level<input type="number" min="0" value={form.reorder_level} onChange={set('reorder_level')} /></label>
        <label className="wide">Description<textarea rows="2" value={form.description} onChange={set('description')} /></label>
        {!isNew && <p className="wide muted">To change quantity, use <strong>Adjust</strong> so the movement is recorded.</p>}
        {error && <p className="wide form-error">{error}</p>}
        <footer className="wide">
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="submit" className="primary" disabled={saving}>{saving ? 'Saving…' : isNew ? 'Create product' : 'Save changes'}</button>
        </footer>
      </form>
    </Modal>
  );
}

export function AdjustModal({ product, onClose, onSave }) {
  const [direction, setDirection] = useState(product.presetRestock ? 'in' : 'out');
  const [amount, setAmount] = useState(product.presetRestock ? Math.max(product.reorder_level * 2 - product.quantity, 1) : 1);
  const [reason, setReason] = useState(product.presetRestock ? 'RESTOCK' : 'SALE');
  const [note, setNote] = useState('');
  const { saving, error, submit } = useSubmit(onSave);

  const change = (direction === 'in' ? 1 : -1) * Number(amount || 0);
  const after = product.quantity + change;

  function pickDirection(d) {
    setDirection(d);
    setReason(d === 'in' ? 'RESTOCK' : 'SALE');
  }

  return (
    <Modal title={`Adjust stock · ${product.name}`} onClose={onClose}>
      <form className="form" onSubmit={(e) => { e.preventDefault(); submit({ change, reason, note }); }}>
        <div className="wide segmented" role="group" aria-label="Direction">
          <button type="button" className={direction === 'in' ? 'active' : ''} onClick={() => pickDirection('in')}>Stock in</button>
          <button type="button" className={direction === 'out' ? 'active' : ''} onClick={() => pickDirection('out')}>Stock out</button>
        </div>
        <label>Units<input type="number" min="1" required value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
        <label>Reason
          <select value={reason} onChange={(e) => setReason(e.target.value)}>
            {REASONS.map((r) => <option key={r} value={r}>{r.charAt(0) + r.slice(1).toLowerCase()}</option>)}
          </select>
        </label>
        <label className="wide">Note<input maxLength={255} value={note} onChange={(e) => setNote(e.target.value)} placeholder="PO number, order ID…" /></label>
        <p className={`wide preview ${after < 0 ? 'bad' : ''}`}>
          {product.quantity} on hand → <strong>{after}</strong> after this adjustment
        </p>
        {error && <p className="wide form-error">{error}</p>}
        <footer className="wide">
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="submit" className="primary" disabled={saving || after < 0 || change === 0}>{saving ? 'Saving…' : 'Apply'}</button>
        </footer>
      </form>
    </Modal>
  );
}
