const $ = (id) => document.getElementById(id);
let draft, selected;
const showMessage = (s) => { $('review-message').textContent = s; };
async function api(url, options = {}) {
  const response = await fetch(url, {headers: {'Content-Type': 'application/json'}, ...options});
  const body = response.headers.get('content-type')?.includes('json') ? await response.json() : await response.text();
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail || body));
  return body;
}
const base = () => `/review/api/drafts/${draft.id}`;
function showPanel(name) {
  document.querySelectorAll('.review-panel').forEach(e => e.hidden = e.id !== `panel-${name}`);
  document.querySelectorAll('.review-tabs button').forEach(e => e.classList.toggle('active', e.dataset.panel === name));
}
function draw() {
  $('review-status').textContent = `Revision ${draft.revision} · ${draft.status}` + (draft.approval ? ` · approved by ${draft.approval.reviewer} at ${draft.approval.time}` : '');
  $('export').hidden = draft.status !== 'approved';
  $('export').href = `${base()}/export`;
  $('pdf-frame').src = draft.pdf || 'about:blank';
  const filter = $('filter').value.toLowerCase();
  const list = $('provisions'); list.replaceChildren();
  const fragment = document.createDocumentFragment();
  draft.outline.filter(n => `${n.num} ${n.heading} ${n.eid}`.toLowerCase().includes(filter)).forEach(n => {
    const button = document.createElement('button'); button.type = 'button';
    button.textContent = `${n.tag} ${n.num} ${n.heading}`.trim();
    button.title = n.eid; button.className = n.eid === selected ? 'active' : '';
    button.onclick = () => select(n.eid); fragment.append(button);
  }); list.append(fragment);
  $('history').replaceChildren();
  [...draft.history].reverse().forEach(h => {
    const li = document.createElement('li'); li.textContent = `r${h.revision} · ${h.time} · ${h.eid || 'source'} · ${h.description}`;
    $('history').append(li);
  });
  $('validation').textContent = draft.validation.summary;
}
async function refresh() {
  draft = await api(base()); draw();
}
async function select(eid) {
  try {
    selected = eid; draw();
    const p = await api(`${base()}/provisions/${encodeURIComponent(eid)}`);
    $('selected-title').textContent = eid;
    $('original-html').innerHTML = p.original_html;
    $('original-xml').textContent = p.original_xml;
    $('draft-html').innerHTML = p.draft_html;
    $('draft-xml').textContent = p.draft_xml;
    $('changes-text').textContent = draft.history.filter(h => h.eid === eid).map(h => h.diff || '').join('\n\n') || 'No saved changes to this provision.';
    window.renderReviewEditor(p.editor);
    $('preview').disabled = $('save').disabled = !p.editor.enabled;
    showMessage(p.editor.reason || '');
  } catch (error) { showMessage(error.message); }
}
async function change(save) {
  try {
    const payload = window.collectReviewEdit();
    const result = await api(`${base()}/${save ? 'revisions' : 'preview'}`, {method: 'POST', body: JSON.stringify({revision: draft.revision, eid: selected, payload})});
    $('changes-text').textContent = result.diff || 'No XML change';
    $('validation').textContent = result.validation.summary;
    $('draft-html').innerHTML = result.html;
    showPanel('changes');
    showMessage(save ? `Saved revision ${result.revision}` : 'Preview is valid. Save to keep it.');
    if (save) { await refresh(); await select(result.selected_eid || draft.outline.find(n => n.tag === 'section')?.eid); }
  } catch (error) { showMessage(error.message); }
}
document.querySelectorAll('.review-tabs button').forEach(b => b.onclick = () => showPanel(b.dataset.panel));
$('filter').oninput = () => draw();
$('preview').onclick = () => change(false);
$('save').onclick = () => change(true);
$('validate').onclick = async () => { try { const r = await api(`${base()}/validate`); $('validation').textContent = r.summary; showMessage(r.ok ? 'Current revision is valid.' : 'Validation failed.'); } catch(e) {showMessage(e.message);} };
$('approve').onclick = async () => { try { await api(`${base()}/approve`, {method: 'POST', body: JSON.stringify({revision: draft.revision, reviewer: $('reviewer').value})}); await refresh(); showMessage('Approved. Download is ready.'); } catch(e) {showMessage(e.message);} };
(async () => { try { draft = await api('/review/api/drafts', {method: 'POST', body: JSON.stringify({path: window.REVIEW_PATH})}); draw(); if (draft.outline.length) await select(draft.outline.find(n => n.tag === 'section')?.eid || draft.outline[0].eid); } catch(e) {showMessage(e.message);} })();
