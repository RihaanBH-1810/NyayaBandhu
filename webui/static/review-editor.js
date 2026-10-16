let visualFields = [];
window.renderReviewEditor = function(editor) {
  const host = document.getElementById('editor'); host.replaceChildren();
  if (!editor.enabled) { host.textContent = editor.reason; return; }
  visualFields = editor.fields;
  const hint = document.createElement('p'); hint.textContent = 'Edit legal wording in the white spans. Shaded references, definitions and language spans are protected.'; host.append(hint);
  editor.fields.forEach((field, fieldIndex) => {
    const row = document.createElement('div'); row.className = 'visual-field';
    const label = document.createElement('strong'); label.textContent = `${field.tag} · ${field.eid || editor.eid}`; row.append(label);
    field.segments.forEach((text, index) => {
      const span = document.createElement('span'); span.contentEditable = 'true'; span.className = 'visual-text'; span.dataset.field = fieldIndex; span.dataset.segment = index;
      span.textContent = text; row.append(span);
      if (index < field.protected.length) {
        const lock = document.createElement('span'); lock.className = 'visual-protected'; lock.textContent = field.protected[index]; lock.title = 'Protected inline XML'; row.append(lock);
      }
    }); host.append(row);
  });
  const controls = document.createElement('div'); controls.className = 'review-actions';
  controls.innerHTML = '<label>Action <select id="visual-action"><option value="text">Edit text</option><option value="add">Add child</option><option value="remove">Remove provision</option><option value="renumber">Renumber</option><option value="move">Move</option></select></label>';
  const types = document.createElement('select'); types.id = 'child-type'; editor.add_types.forEach(t => { const o = document.createElement('option'); o.value = o.textContent = t; types.append(o); });
  controls.append(types);
  const number = document.createElement('input'); number.id = 'new-number'; number.placeholder = 'New number'; controls.append(number);
  const direction = document.createElement('select'); direction.id = 'direction'; ['up','down'].forEach(t => {const o = document.createElement('option'); o.value = o.textContent = t; direction.append(o);}); controls.append(direction);
  host.append(controls);
};
window.collectReviewEdit = function() {
  const action = document.getElementById('visual-action').value;
  if (action === 'text') {
    const fields = visualFields.map((f, i) => ({...f, segments: f.segments.map((_, j) => document.querySelector(`[data-field="${i}"][data-segment="${j}"]`).textContent)}));
    return {action, fields};
  }
  if (action === 'add') return {action, child_type: document.getElementById('child-type').value};
  if (action === 'renumber') return {action, number: document.getElementById('new-number').value};
  if (action === 'move') return {action, direction: document.getElementById('direction').value};
  return {action};
};
