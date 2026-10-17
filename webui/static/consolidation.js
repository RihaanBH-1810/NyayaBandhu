/* Local consolidation CMS. Source data is always inserted as text, never HTML. */
(() => {
  'use strict';
  const API = '/consolidation/api';
  const $ = id => document.getElementById(id);
  const state = {workId: null, workspace: null, catalog: null, manifest: null,
    body: null, selectedOp: 0, inspected: null, preview: null,
    expression: null, tab: 'sources', dirty: false};
  const actions = ['effect','text_replace','text_insert','text_omit','slot_edits','insert_provision',
    'replace_provision','omit_provision','renumber','schedule_add','table_insert','blocked'];
  const labels = {effect:'Separate legal effect',text_replace:'Replace words',text_insert:'Insert words',
    text_omit:'Omit words',slot_edits:'Edit text slots',insert_provision:'Insert provision',
    replace_provision:'Replace provision',omit_provision:'Omit provision',renumber:'Renumber provision',
    schedule_add:'Add schedule',table_insert:'Insert table rows',blocked:'Needs interpretation'};
  const newNode = (tag, className, value) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = String(value);
    return node;
  };
  const clear = el => el.replaceChildren();
  const niceDate = value => value ? new Date(value).toLocaleString() : '—';
  const short = value => value ? value.slice(0, 12) : '—';
  const text = value => value == null ? '' : String(value);
  const makeOption = (value, label) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    return option;
  };
  function fillSelect(id, choices, placeholder, selected) {
    const select = $(id); clear(select);
    if (placeholder) select.append(makeOption('', placeholder));
    for (const [value,label] of choices) select.append(makeOption(value,label));
    if (selected && choices.some(([value]) => value === selected)) select.value = selected;
  }
  function notice(message, error = false) {
    const el = $('notice'); el.textContent = message; el.classList.toggle('error',error); el.hidden = false;
    el.scrollIntoView({block:'nearest'});
  }
  function hideNotice() { $('notice').hidden = true; }
  async function request(path, options = {}) {
    const response = await fetch(API + path, {
      headers: options.body === undefined ? {} : {'Content-Type':'application/json'},
      ...options,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
    if (!response.ok) {
      let message;
      try { const data = await response.json(); message = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail); }
      catch { message = response.statusText; }
      throw new Error(message || `Request failed (${response.status})`);
    }
    const contentType = response.headers.get('content-type') || '';
    return contentType.includes('application/json') ? response.json() : response.text();
  }
  async function task(fn) {
    try { hideNotice(); await fn(); }
    catch (error) { notice(error.message || String(error), true); }
  }
  function identity() {
    const actor = $('actor').value.trim(), reason = $('reason').value.trim();
    if (!actor || !reason) throw new Error('Enter your name and a reason before saving a review action.');
    localStorage.setItem('nyayaReviewer', actor);
    return {actor,reason};
  }
  function ensureReviewSaved() {
    if (state.dirty) throw new Error('Save the instruction review before previewing or changing versions.');
  }
  function markDirty() {
    state.dirty = true; $('save-manifest').classList.add('unsaved');
    if (state.manifest) $('manifest-status').textContent = 'Unsaved review changes';
  }
  function changeTab(tab) {
    state.tab = tab;
    document.querySelectorAll('[data-tab]').forEach(button => button.classList.toggle('active', button.dataset.tab === tab));
    document.querySelectorAll('.tab-panel').forEach(panel => panel.hidden = panel.id !== `tab-${tab}`);
  }
  async function loadWorks(preferred) {
    const works = await request('/works');
    fillSelect('work-select', works.map(w => [w.id, `${w.uri} · r${w.revision}`]), 'Choose an Act', preferred || state.workId);
    if (preferred || state.workId) await loadWork(preferred || state.workId);
    else { $('empty-state').hidden = false; $('work-area').hidden = true; changeTab('sources'); }
  }
  async function loadWork(workId, opts = {}) {
    if (!workId) { state.workId = null; state.workspace = null; await loadWorks(); return; }
    const sameWork = state.workId === workId;
    const manifestId = opts.manifestId || (sameWork ? state.manifest?.id : null);
    const operationId = opts.operationId || (sameWork ? currentOp()?.id : null);
    if (!sameWork) {
      state.manifest = null; state.body = null; state.expression = null;
      $('preview-date').value = '';
    }
    state.workId = workId;
    state.workspace = await request(`/works/${encodeURIComponent(workId)}/workspace`);
    state.preview = null; $('preview-result').hidden = true;
    if (state.expression && !state.workspace.expressions.some(e => e.id === state.expression.id)) state.expression = null;
    const work = state.workspace.work;
    $('empty-state').hidden = true; $('work-area').hidden = false;
    $('work-title').textContent = work.uri;
    $('work-subtitle').textContent = `Current work revision ${work.revision} · local review store`;
    $('metric-sources').textContent = state.workspace.sources.length;
    $('metric-instructions').textContent = state.workspace.manifests.reduce((n,m) => n + m.body.operations.length, 0);
    $('metric-expressions').textContent = state.workspace.expressions.length;
    const amendments = state.workspace.sources.filter(source => source.kind === 'amendment');
    const unextracted = amendments.filter(source => !state.workspace.manifests.some(m => m.source_id === source.id));
    const pending = state.workspace.manifests.filter(m => m.body.status !== 'ready');
    $('coverage-summary').textContent = unextracted.length
      ? `${unextracted.length} registered amendment source(s) still need extraction.`
      : pending.length ? `${pending.length} instruction manifest(s) still need review.`
      : amendments.length ? 'Registered instruments reviewed. Use dated lookup to check version coverage.'
      : 'No amending instruments registered in this local work.';
    const old = $('work-select').value;
    if (old !== workId) $('work-select').value = workId;
    history.replaceState(null, '', `/consolidation?work=${encodeURIComponent(workId)}`);
    renderSources(); renderManifestSelect(manifestId); renderVersions(opts.expressionId);
    renderPreviewControls(); state.dirty = false; $('save-manifest').classList.remove('unsaved');
    if (manifestId) selectManifest(manifestId, operationId);
    if (opts.expressionId) await selectExpression(opts.expressionId);
  }
  function renderSources() {
    const list = $('source-list'); clear(list);
    if (!state.workspace) { list.append(newNode('p','empty-note','No sources in this work yet.')); return; }
    for (const source of state.workspace.sources) {
      const card = newNode('article','card source-card');
      const meta = state.workspace.manifests.find(m => m.source_id === source.id);
      const header = newNode('div','source-card-head');
      header.append(newNode('span','chip',source.kind === 'base' ? 'Principal Act' : 'Amending Act'));
      header.append(newNode('span',`chip ${meta?.body.status === 'ready' ? 'approved' : 'draft'}`,
        source.kind === 'base' ? 'Source snapshot' : meta ? meta.body.status.replace('_',' ') : 'Not extracted'));
      card.append(header);
      card.append(newNode('h3','',source.metadata.work_uri));
      card.append(newNode('p','source-hash',`XML ${short(source.xml_hash)} · PDF ${short(source.pdf_hash)}`));
      const row = newNode('div','button-row');
      for (const [label,kind] of [['Gazette PDF','pdf'],['Original XML','xml']]) {
        const a = newNode('a','button secondary',label);
        a.href = `${API}/sources/${encodeURIComponent(source.id)}/${kind}`;
        a.target = '_blank'; a.rel = 'noopener'; row.append(a);
      }
      if (source.kind === 'amendment') {
        const button = newNode('button','button primary',meta ? 'Review instructions' : 'Extract instructions');
        button.type = 'button';
        button.addEventListener('click', () => task(async () => {
          if (meta) { selectManifest(meta.id); changeTab('instructions'); }
          else {
            ensureReviewSaved();
            const output = await request(`/sources/${source.id}/extract`,{method:'POST',body:{revision:state.workspace.work.revision,...identity()}});
            await loadWork(state.workId,{manifestId:output.manifest.id});
            changeTab('instructions'); notice('Instructions extracted. Review every candidate against the gazette.');
          }
        }));
        row.append(button);
      }
      card.append(row); list.append(card);
    }
  }
  function setImportKind() {
    if (!state.catalog) return;
    const kind = $('import-kind').value;
    const values = state.catalog[kind === 'base' ? 'base_xml' : 'amendment_xml'];
    fillSelect('import-xml',values.map(v => [v,v]),'Choose XML');
    fillSelect('import-pdf',state.catalog.pdf.map(v => [v,v]),'Choose PDF');
    if (values.length === 1) $('import-xml').value = values[0];
    suggestPdf();
  }
  function suggestPdf() {
    const xml = $('import-xml').value;
    if (!xml) return;
    const stem = xml.split('/').pop().replace(/\.xml$/,'').toLowerCase();
    const match = state.catalog.pdf.find(path => path.split('/').pop().replace(/\.pdf$/i,'').toLowerCase() === stem);
    if (match) $('import-pdf').value = match;
  }
  async function showImport() {
    if (!state.catalog) state.catalog = await request('/catalog');
    $('import-panel').hidden = false;
    $('import-kind').value = state.workId ? 'amendment' : 'base';
    setImportKind(); changeTab('sources'); $('import-panel').scrollIntoView({block:'nearest'});
  }
  async function importSource() {
    if (state.dirty && !confirm('Discard unsaved instruction edits before importing a source?')) return;
    const kind = $('import-kind').value;
    const xml_path = $('import-xml').value, pdf_path = $('import-pdf').value;
    if (!xml_path || !pdf_path) throw new Error('Select matching XML and PDF source files.');
    if (kind === 'amendment' && !state.workId) throw new Error('Choose a base Act before importing an amendment.');
    const body = {kind, xml_path,pdf_path,...identity()};
    if (kind === 'amendment') { body.work_id = state.workId; body.revision = state.workspace.work.revision; }
    const imported = await request('/sources',{method:'POST',body});
    $('import-panel').hidden = true;
    await loadWorks(imported.work_id);
    notice(kind === 'base' ? 'Base imported as a draft. Approve its snapshot before applying amendments.' : 'Amending instrument imported. Extract its instructions to begin review.');
    changeTab(kind === 'base' ? 'versions' : 'sources');
  }
  function renderManifestSelect(preferred) {
    const manifests = state.workspace?.manifests || [];
    fillSelect('manifest-select',manifests.map(m => [m.id,`${m.body.source_work_uri} · ${m.body.status.replace('_',' ')}`]),'Choose an amendment',preferred || state.manifest?.id);
    if (!manifests.length) { state.manifest = null; state.body = null; $('instruction-workspace').hidden = true; $('manifest-empty').hidden = false; }
  }
  function selectManifest(id, operationId) {
    if (state.dirty && !confirm('Discard unsaved instruction edits?')) {
      $('manifest-select').value = state.manifest?.id || '';
      return;
    }
    const manifest = state.workspace?.manifests.find(m => m.id === id);
    state.manifest = manifest || null;
    state.body = manifest ? structuredClone(manifest.body) : null;
    state.dirty = false; state.inspected = null;
    $('save-manifest').classList.remove('unsaved');
    $('manifest-select').value = manifest?.id || '';
    $('instruction-workspace').hidden = !manifest; $('manifest-empty').hidden = !!manifest;
    if (!manifest) return;
    $('manifest-status').textContent = state.body.status === 'ready' ? 'Ready for effective-date preview' : 'Review pending';
    $('manifest-revision').textContent = `Instruction revision ${manifest.revision}`;
    $('identity-confirmed').checked = !!state.body.identity_confirmed;
    $('instrument-sequence').value = state.body.sequence || 1;
    $('effective-date').value = state.body.effective_date || '';
    $('date-confirmed').checked = !!state.body.date_confirmed;
    $('date-evidence').value = state.body.date_evidence || '';
    const expected = state.body.target_identity || {};
    $('identity-summary').textContent = `Principal Act recorded in the amendment: ${expected.jurisdiction || '?'} / ${expected.year || '?'} / ${expected.number || '?'}. Confirm against the base Act above.`;
    const sourceId = manifest.source_id;
    $('source-pdf').src = `${API}/sources/${encodeURIComponent(sourceId)}/pdf`;
    $('source-pdf-open').href = `${API}/sources/${encodeURIComponent(sourceId)}/pdf`;
    $('source-xml').hidden = true; $('source-xml').textContent = '';
    $('source-xml-toggle').textContent = 'Show original XML';
    state.selectedOp = Math.max(0,state.body.operations.findIndex(op => op.id === operationId));
    renderOperationList(); renderOperation();
    $('preview-date').value = state.body.effective_date || $('preview-date').value;
  }
  function renderOperationList() {
    const list = $('operation-list'); clear(list);
    const operations = state.body?.operations || [];
    $('instruction-progress').textContent = `${operations.filter(op => op.review_status === 'accepted').length}/${operations.length} reviewed`;
    operations.forEach((op,i) => {
      const button = newNode('button',`operation-item ${i === state.selectedOp ? 'active' : ''}`);
      button.type = 'button';
      button.append(newNode('span','operation-number',String(i + 1).padStart(2,'0')));
      const contents = newNode('span','operation-item-text');
      contents.append(newNode('strong','',labels[op.action] || op.action));
      contents.append(newNode('small','',`${op.source?.source_eid || ''} · ${op.target?.eid || op.target?.path?.map(p => p.join(' ')).join(' › ') || op.target?.region || 'legal effect'}`));
      button.append(contents);
      button.append(newNode('span',`status-dot ${op.review_status === 'accepted' ? 'accepted' : ''}`,'●'));
      button.addEventListener('click', () => { state.selectedOp = i; state.inspected = null; renderOperationList(); renderOperation(); });
      list.append(button);
    });
  }
  function currentOp() { return state.body?.operations[state.selectedOp]; }
  function renderOperation() {
    const op = currentOp(); $('operation-editor').hidden = !op;
    if (!op) return;
    $('operation-code').textContent = `${op.id} · source ${op.source?.source_eid || 'unknown'}`;
    $('operation-title').textContent = labels[op.action] || op.action;
    $('operation-badge').textContent = op.review_status === 'accepted' ? 'Reviewed' : 'Pending';
    $('source-quote').textContent = op.source?.quote || '';
    $('quote-pages').textContent = (op.source?.pdf_pages || []).join(', ') || 'page unavailable';
    const pdf = `${API}/sources/${encodeURIComponent(state.manifest.source_id)}/pdf#page=${op.source?.pdf_pages?.[0] || 1}`;
    if ($('source-pdf').src !== new URL(pdf,location.href).href) $('source-pdf').src = pdf;
    $('source-pdf-open').href = pdf;
    fillSelect('op-action',actions.map(value => [value,labels[value]]),null,op.action);
    $('op-status').value = op.review_status || 'pending';
    $('target-eid').value = op.target?.eid || '';
    $('target-json').value = JSON.stringify(op.target || {},null,2);
    $('op-date').value = op.effective_date || '';
    $('op-old').value = op.old || '';
    $('op-new').value = op.new || '';
    $('op-count').value = op.count ?? '';
    $('op-position').value = op.position || 'after';
    $('op-whole-word').checked = !!op.whole_word;
    $('op-global').checked = !!op.global;
    $('op-protected').checked = !!op.allow_protected;
    $('op-new-number').value = op.new_number || '';
    $('op-classification').value = op.classification || '';
    $('op-note').value = op.review_note || '';
    $('text-fields').hidden = !op.action.startsWith('text_');
    renderStructuralEditor();
    $('operation-json').value = JSON.stringify(op,null,2);
    $('target-binding').textContent = op.expected_hash ? `Bound to ${short(op.expected_hash)}` : 'Target hash not yet bound';
    $('target-inspection').hidden = true; state.inspected = null;
  }
  function payloadChanged() {
    $('operation-json').value = JSON.stringify(currentOp(),null,2);
    invalidateInspection(); markDirty();
  }
  function renderStructuralEditor() {
    const op = currentOp();
    const structural = ['insert_provision','replace_provision','schedule_add'].includes(op.action);
    $('fragment-panel').hidden = !structural;
    $('table-panel').hidden = !['table_insert','schedule_add'].includes(op.action);
    $('add-fragment').hidden = op.action !== 'insert_provision';
    const list = $('fragment-list'); clear(list);
    if (structural) {
      const specs = op.action === 'insert_provision' ? (op.fragments || (op.fragment ? [op.fragment] : [])) : (op.fragment ? [op.fragment] : []);
      specs.forEach((spec,index) => {
        list.append(fragmentFields(spec, specs, index, 0));
      });
      if (!specs.length) list.append(newNode('p','field-help','Add a provision or edit the instruction JSON to define its structure.'));
    }
    $('table-after-group').value = op.after_group || '';
    const rows = op.action === 'table_insert' ? op.rows : op.fragment?.table;
    renderTableRows(rows || []);
  }
  function fragmentFields(spec, siblings, index, depth) {
    const wrap = newNode('div',`fragment-node depth-${Math.min(depth,3)}`);
    const title = newNode('div','fragment-title');
    title.append(newNode('strong','',`${spec.tag || 'provision'} ${spec.num || ''}`));
    const remove = newNode('button','button subtle','Remove'); remove.type = 'button';
    remove.addEventListener('click',() => { siblings.splice(index,1); renderStructuralEditor(); payloadChanged(); });
    title.append(remove); wrap.append(title);
    const fields = newNode('div','form-grid');
    function field(label,value,key,multiline = false) {
      const box = newNode('label',''); box.append(newNode('span','',label));
      const input = document.createElement(multiline ? 'textarea' : 'input');
      input.value = value || ''; if (multiline) input.rows = 3;
      input.addEventListener('change',() => { spec[key] = input.value; title.querySelector('strong').textContent = `${spec.tag || 'provision'} ${spec.num || ''}`; payloadChanged(); });
      box.append(input); fields.append(box);
    }
    field('Printed number',spec.num,'num');
    field('Heading',spec.heading,'heading');
    field('Subheading',spec.subheading,'subheading');
    field('Legal text',spec.text,'text',true);
    wrap.append(fields);
    const children = newNode('div','fragment-children');
    (spec.children || []).forEach((child,childIndex) => children.append(fragmentFields(child,spec.children,childIndex,depth+1)));
    wrap.append(children);
    if (depth < 4 && ['section','subsection','clause','hcontainer'].includes(spec.tag)) {
      const add = newNode('button','button subtle','Add child provision'); add.type = 'button';
      add.addEventListener('click',() => {
        const childTag = {section:'subsection',subsection:'clause',clause:'subclause',hcontainer:'proviso'}[spec.tag];
        spec.children ||= []; spec.children.push({tag:childTag,text:''});
        renderStructuralEditor(); payloadChanged();
      });
      wrap.append(add);
    }
    return wrap;
  }
  function renderTableRows(rows) {
    const host = $('table-rows'); clear(host);
    if (!rows.length && !$('table-panel').hidden) host.append(newNode('p','field-help','No rows were extracted. Add a row and compare each cell with the gazette.'));
    rows.forEach((row,index) => {
      const line = newNode('div','table-edit-row');
      line.append(newNode('strong','',`Row ${index + 1}`));
      row.forEach((cell,column) => {
        const label = newNode('label','',`Column ${column + 1}`);
        const input = document.createElement('textarea'); input.rows = 2; input.value = cell;
        input.addEventListener('change',() => { row[column] = input.value; payloadChanged(); });
        label.append(input); line.append(label);
      });
      const remove = newNode('button','button subtle','Remove row'); remove.type = 'button';
      remove.addEventListener('click',() => { rows.splice(index,1); renderTableRows(rows); payloadChanged(); });
      line.append(remove); host.append(line);
    });
  }
  function addFragment() {
    const op = currentOp();
    if (!op || op.action !== 'insert_provision') return;
    if (!op.fragments) { op.fragments = op.fragment ? [op.fragment] : []; delete op.fragment; }
    op.fragments.push({tag:'clause',num:'',text:''});
    renderStructuralEditor(); payloadChanged();
  }
  function addTableRow() {
    const op = currentOp();
    if (!op) return;
    if (op.action === 'schedule_add') {
      op.fragment ||= {tag:'hcontainer',name:'schedule',heading:'',table:[]};
      op.fragment.table ||= [];
      op.fragment.table.push(['','']);
    } else {
      op.rows ||= []; op.rows.push(['','']);
    }
    renderStructuralEditor(); payloadChanged();
  }
  function invalidateInspection(targetChanged = false) {
    state.inspected = null; $('target-inspection').hidden = true;
    const op = currentOp(); if (!op) return;
    if (targetChanged) {
      delete op.expected_hash; delete op.target_identity;
      delete op.occurrences; delete op.inline_removals; delete op.reference_updates;
    }
    $('target-binding').textContent = op.expected_hash ? `Bound to ${short(op.expected_hash)} · inspect after edits` : 'Inspect staged target before accepting';
    $('operation-json').value = JSON.stringify(op,null,2);
  }
  function syncManifestField(event) {
    if (!state.body) return;
    const id = event.target.id;
    if (id === 'identity-confirmed') state.body.identity_confirmed = event.target.checked;
    if (id === 'date-confirmed') state.body.date_confirmed = event.target.checked;
    if (id === 'instrument-sequence') state.body.sequence = Number(event.target.value);
    if (id === 'effective-date') state.body.effective_date = event.target.value || null;
    if (id === 'date-evidence') state.body.date_evidence = event.target.value;
    markDirty();
  }
  function syncOperationField(event) {
    const op = currentOp(); if (!op) return;
    const el = event.target, id = el.id;
    if (id === 'op-action') {
      op.action = el.value;
      if (op.action === 'insert_provision' && !op.fragments && !op.fragment) op.fragments = [{tag:'clause',num:'',text:''}];
      if (op.action === 'replace_provision' && !op.fragment) op.fragment = {tag:'section',num:'',text:''};
      if (op.action === 'schedule_add' && !op.fragment) op.fragment = {tag:'hcontainer',name:'schedule',heading:'',table:[]};
      if (op.action === 'table_insert' && !op.rows) op.rows = [];
      renderOperationList(); renderOperation();
    }
    else if (id === 'op-status') { op.review_status = el.value; renderOperationList(); $('operation-badge').textContent = el.value === 'accepted' ? 'Reviewed' : 'Pending'; }
    else if (id === 'target-eid') { op.target = {eid:el.value.trim()}; $('target-json').value = JSON.stringify(op.target,null,2); invalidateInspection(true); renderOperationList(); }
    else if (id === 'op-date') { if (el.value) op.effective_date = el.value; else delete op.effective_date; }
    else if (id === 'op-old') { op.old = el.value; delete op.occurrences; delete op.inline_removals; invalidateInspection(); }
    else if (id === 'op-new') op.new = el.value;
    else if (id === 'op-count') op.count = el.value ? Number(el.value) : null;
    else if (id === 'op-position') op.position = el.value;
    else if (id === 'op-whole-word') { op.whole_word = el.checked; delete op.occurrences; invalidateInspection(); }
    else if (id === 'op-global') op.global = el.checked;
    else if (id === 'op-protected') op.allow_protected = el.checked;
    else if (id === 'op-new-number') op.new_number = el.value;
    else if (id === 'op-classification') op.classification = el.value;
    else if (id === 'op-note') op.review_note = el.value;
    if (id !== 'op-action') $('operation-json').value = JSON.stringify(op,null,2);
    markDirty();
  }
  async function inspectTarget() {
    const op = currentOp();
    if (!op || !state.manifest) return;
    const expressionId = $('preview-parent').value || latestApproved()?.id;
    if (!expressionId) throw new Error('Approve a base expression before inspecting amendment targets.');
    const result = await request(`/manifests/${state.manifest.id}/inspect`,{
      method:'POST',body:{expression_id:expressionId,operation_id:op.id,body:state.body},
    });
    state.inspected = result;
    const options = $('provision-options'); clear(options);
    for (const item of result.provisions || []) {
      const option = makeOption(item.eid,`${item.tag} ${item.num} ${item.heading || item.excerpt.slice(0,60)}`);
      options.append(option);
    }
    $('target-inspection').hidden = false;
    $('inspect-error').hidden = !result.target_error;
    $('inspect-error').textContent = result.target_error || '';
    $('target-preview').textContent = result.target_text || '';
    $('target-xml').textContent = result.target_xml || '';
    if (result.target_truncated) $('target-preview').append(newNode('span','muted',' … excerpt shown; open the original XML or full Act to inspect the rest.'));
    $('bind-target').disabled = !!result.target_error || !result.target_eid;
    $('matches-panel').hidden = !result.occurrences;
    $('bind-matches').disabled = !result.occurrences?.length;
    const matches = $('match-list'); clear(matches);
    for (const match of result.occurrences || []) {
      const line = newNode('div','match-item');
      line.append(newNode('strong','',match.field || 'text field'));
      line.append(newNode('span','',`“${match.text}” · offset ${match.offset}`));
      if (match.protected) line.append(newNode('span','chip warning','Protected inline'));
      if (match.cross_inline) line.append(newNode('span','chip warning','Crosses inline boundary'));
      matches.append(line);
    }
    $('references-panel').hidden = !result.incoming_references?.length;
    const refs = $('reference-list'); clear(refs);
    for (const ref of result.incoming_references || []) {
      const decision = (op.reference_updates || []).find(item => item.eid === ref.eid) || {...ref};
      const row = newNode('div','reference-row');
      row.append(newNode('p','reference-caption',`${ref.eid} · ${ref.old_text} → ${ref.old_href}`));
      for (const [key,label,placeholder] of [
        ['new_href','New href','#sec_10'],['new_text','New label','(viii)'],['resolved_by','Removed by later instruction','sec_6_op_3']]) {
        const wrapper = newNode('label',''); wrapper.append(newNode('span','',label));
        const input = document.createElement('input'); input.value = decision[key] || ''; input.placeholder = placeholder;
        input.addEventListener('input', () => {
          const updates = op.reference_updates || [];
          let current = updates.find(item => item.eid === ref.eid);
          if (!current) { current = {...ref}; updates.push(current); }
          if (input.value.trim()) current[key] = input.value.trim(); else delete current[key];
          op.reference_updates = updates;
          $('operation-json').value = JSON.stringify(op,null,2); markDirty();
        });
        wrapper.append(input); row.append(wrapper);
      }
      refs.append(row);
    }
    $('inline-panel').hidden = !result.inline_candidates?.length;
    const inline = $('inline-list'); clear(inline);
    for (const item of result.inline_candidates || []) {
      const label = newNode('label','check-field');
      const checkbox = document.createElement('input'); checkbox.type = 'checkbox';
      checkbox.checked = (op.inline_removals || []).some(r => r.eid === item.eid);
      checkbox.addEventListener('change', () => {
        op.inline_removals = (op.inline_removals || []).filter(r => r.eid !== item.eid);
        if (checkbox.checked) op.inline_removals.push(item);
        $('operation-json').value = JSON.stringify(op,null,2); markDirty();
      });
      label.append(checkbox,newNode('span','',`Omit ${item.text} · ${item.href} (${item.eid})`)); inline.append(label);
    }
    const noMatch = result.occurrences && !result.occurrences.length;
    notice(result.target_error ? `Target needs review: ${result.target_error}` : noMatch
      ? 'No exact wording match. Compare the source and base text, then record the chosen anchor and reason.'
      : 'Target inspected. Bind its hash and review every match or incoming reference.',!!result.target_error || !!noMatch);
  }
  function bindTarget() {
    if (!state.inspected?.expected_hash) return;
    const op = currentOp(); op.expected_hash = state.inspected.expected_hash;
    if (state.inspected.target_identity) op.target_identity = state.inspected.target_identity;
    $('target-binding').textContent = `Bound to ${short(op.expected_hash)}`;
    $('operation-json').value = JSON.stringify(op,null,2); markDirty();
  }
  function bindMatches() {
    if (!state.inspected?.occurrences) return;
    const op = currentOp(); op.occurrences = structuredClone(state.inspected.occurrences);
    op.count = op.occurrences.length; $('op-count').value = op.count;
    $('operation-json').value = JSON.stringify(op,null,2); markDirty();
    notice(`Recorded ${op.count} exact occurrence${op.count === 1 ? '' : 's'} for this instruction.`);
  }
  async function toggleSourceXml() {
    if (!state.manifest) return;
    const view = $('source-xml');
    if (!view.textContent) view.textContent = await request(`/sources/${state.manifest.source_id}/xml`);
    view.hidden = !view.hidden;
    $('source-xml-toggle').textContent = view.hidden ? 'Show original XML' : 'Hide original XML';
  }
  async function saveManifest() {
    if (!state.manifest) throw new Error('Choose an instrument.');
    const op = currentOp();
    for (const item of state.body.operations) {
      if (item.review_status === 'accepted' && item.action !== 'effect' && item.action !== 'blocked' && !item.expected_hash)
        throw new Error(`Inspect and bind the target for ${item.id} before saving its acceptance.`);
    }
    const output = await request(`/manifests/${state.manifest.id}/review`,{
      method:'POST',body:{revision:state.workspace.work.revision,manifest_revision:state.manifest.revision,
        body:state.body,...identity()},
    });
    await loadWork(state.workId,{manifestId:output.manifest.id,operationId:op?.id});
    changeTab('instructions');
    notice(output.manifest.body.status === 'ready'
      ? 'Review revision saved. All instructions are ready for batch preview.'
      : 'Review revision saved. Remaining instructions or dates still need decisions.');
  }
  function latestApproved() {
    return [...(state.workspace?.expressions || [])].reverse().find(e => e.approved_at && !e.invalidated_at);
  }
  function renderPreviewControls() {
    const approved = (state.workspace?.expressions || []).filter(e => e.approved_at && !e.invalidated_at);
    const previous = $('preview-parent').value || latestApproved()?.id;
    fillSelect('preview-parent',approved.map(e => [e.id,`${e.effective_date} · ${e.kind.replace('_',' ')} · ${short(e.id)}`]),'Choose approved predecessor',previous);
    if (!$('preview-date').value && state.body?.effective_date) $('preview-date').value = state.body.effective_date;
  }
  async function preview() {
    ensureReviewSaved();
    if (!state.workId) throw new Error('Choose an Act.');
    const parent_id = $('preview-parent').value, effective_date = $('preview-date').value;
    if (!parent_id || !effective_date) throw new Error('Choose an approved predecessor and legal effective date.');
    const result = await request(`/works/${state.workId}/preview`,{method:'POST',body:{parent_id,effective_date}});
    state.preview = result;
    $('preview-result').hidden = false;
    const summary = $('preview-summary'); clear(summary);
    summary.className = `card preview-summary ${result.ok ? 'valid' : 'invalid'}`;
    summary.append(newNode('h3','',result.ok ? 'Validation passed' : 'Application blocked'));
    summary.append(newNode('p','',`${result.changes.length} operation${result.changes.length === 1 ? '' : 's'} replayed · work revision ${result.work_revision}`));
    if (result.validation) summary.append(newNode('pre','validation-text',result.validation.summary));
    for (const conflict of result.conflicts || []) summary.append(newNode('p','error-text',`${conflict.operation}: ${conflict.reason}`));
    const list = $('preview-changes'); clear(list);
    for (const item of result.changes || []) {
      const card = newNode('article','card change-card');
      card.append(newNode('strong','',`${item.operation} · ${item.target_eid || item.effect || 'legal effect'}`));
      if (item.before !== undefined) {
        const grid = newNode('div','change-grid');
        const before = newNode('div','change-before'); before.append(newNode('span','eyebrow','Before'),newNode('p','',item.before || '(none)'));
        const after = newNode('div','change-after'); after.append(newNode('span','eyebrow','After'),newNode('p','',item.after || '(removed)'));
        grid.append(before,after); card.append(grid);
      }
      list.append(card);
    }
    $('preview-diff').textContent = result.diff || 'No XML text diff for this batch.';
    $('apply-preview').disabled = !result.ok;
    notice(result.ok ? 'Preview passed. Compare the changes and gazette before saving a draft.' : 'Preview is blocked. Review the reported instruction or validation conflict.',!result.ok);
  }
  async function applyPreview() {
    ensureReviewSaved();
    const result = state.preview;
    if (!result?.ok) throw new Error('Run a valid preview first.');
    if (result.work_revision !== state.workspace.work.revision) throw new Error('The work changed. Refresh and run a new preview.');
    const output = await request(`/works/${state.workId}/apply`,{
      method:'POST',body:{parent_id:result.parent_id,effective_date:result.effective_date,
        preview_hash:result.preview_hash,revision:result.work_revision,...identity()},
    });
    state.preview = null;
    await loadWork(state.workId,{expressionId:output.expression.id});
    changeTab('versions'); notice('Validated draft saved. Inspect its XML and exact hash before approval.');
  }
  function statusOf(e) { return e.invalidated_at ? 'Stale' : e.approved_at ? 'Approved' : 'Draft'; }
  function renderVersions(preferred) {
    const entries = state.workspace?.expressions || [];
    const list = $('version-list'); clear(list);
    for (const e of [...entries].reverse()) {
      const button = newNode('button',`card version-item ${state.expression?.id === e.id || preferred === e.id ? 'active' : ''}`);
      button.type = 'button';
      const top = newNode('div','version-top'); top.append(newNode('strong','',e.effective_date),newNode('span',`chip ${statusOf(e).toLowerCase()}`,statusOf(e)));
      button.append(top,newNode('span','',`${e.kind.replace('_',' ')} · ${short(e.id)}`));
      button.append(newNode('small','muted',e.approved_at ? `Approved ${niceDate(e.approved_at)}` : `Created ${niceDate(e.created)}`));
      button.addEventListener('click',() => task(() => selectExpression(e.id)));
      list.append(button);
    }
    const mapped = entries.map(e => [e.id,`${e.effective_date} · ${statusOf(e)} · ${short(e.id)}`]);
    fillSelect('diff-left',mapped,'Choose earlier version',entries.at(-2)?.id);
    fillSelect('diff-right',mapped,'Choose later version',entries.at(-1)?.id);
    const approved = entries.filter(e => e.approved_at && !e.invalidated_at);
    fillSelect('correction-parent',approved.map(e => [e.id,`${e.effective_date} · ${short(e.id)}`]),'Choose approved version');
    fillSelect('correction-source',(state.workspace?.sources || []).map(s => [s.id,`${s.kind} · ${s.metadata.work_uri}`]),'Choose evidence source');
    const audit = $('audit-list'); clear(audit);
    for (const event of (state.workspace?.events || []).slice(0,30)) {
      const row = newNode('div','audit-row');
      row.append(newNode('strong','',event.kind.replaceAll('_',' ')));
      row.append(newNode('span','',`${event.actor} · ${niceDate(event.created)}`));
      row.append(newNode('small','',event.reason)); audit.append(row);
    }
    if (!state.expression && !preferred) { $('version-empty').hidden = false; $('version-selected').hidden = true; }
  }
  async function selectExpression(id) {
    const expression = (state.workspace?.expressions || []).find(e => e.id === id);
    if (!expression) return;
    state.expression = expression;
    $('version-empty').hidden = true; $('version-selected').hidden = false;
    $('version-type').textContent = expression.kind.replace('_',' ');
    $('version-title').textContent = `Version effective ${expression.effective_date}`;
    $('version-status').textContent = statusOf(expression);
    $('version-status').className = `chip ${statusOf(expression).toLowerCase()}`;
    $('version-hash').textContent = expression.xml_hash;
    $('version-created').textContent = niceDate(expression.created);
    $('version-approved').textContent = expression.approved_at ? `${expression.approved_by} · ${niceDate(expression.approved_at)}` : 'Pending approval';
    $('version-validation').textContent = expression.validation?.summary || 'See XML validation in expression history';
    $('version-read').href = `/consolidation/read/${encodeURIComponent(id)}`;
    $('version-xml').href = `${API}/expressions/${id}/xml`;
    $('version-export').hidden = statusOf(expression) !== 'Approved';
    $('version-export').href = `${API}/expressions/${id}/export`;
    $('approve-version').hidden = statusOf(expression) !== 'Draft';
    $('version-changes').textContent = expression.change_count ? `${expression.change_count} change records · ${expression.applied_count} applied instructions` : 'Source snapshot';
    document.querySelectorAll('.version-item').forEach(el => el.classList.toggle('active',el.textContent.includes(short(id))));
  }
  async function approveVersion() {
    ensureReviewSaved();
    const e = state.expression;
    if (!e || statusOf(e) !== 'Draft') throw new Error('Choose a current draft.');
    const output = await request(`/expressions/${e.id}/approve`,{
      method:'POST',body:{revision:state.workspace.work.revision,xml_hash:e.xml_hash,...identity()},
    });
    await loadWork(state.workId,{expressionId:output.expression.id});
    changeTab('versions'); notice('Exact XML hash approved. The evidence ZIP is ready to download.');
  }
  async function loadDiff() {
    const left = $('diff-left').value, right = $('diff-right').value;
    if (!left || !right || left === right) throw new Error('Choose two different expressions to compare.');
    const diff = await request(`/diff?left=${encodeURIComponent(left)}&right=${encodeURIComponent(right)}`);
    $('history-diff').textContent = diff || 'These expressions have no XML differences.';
    $('history-diff').hidden = false;
  }
  async function lookupDate() {
    if (!state.workId || !$('lookup-date').value) throw new Error('Enter a legal date.');
    const params = new URLSearchParams({as_of:$('lookup-date').value});
    if ($('lookup-known').value) params.set('known_at',new Date($('lookup-known').value).toISOString());
    const result = await request(`/works/${state.workId}/lookup?${params}`);
    const expression = result.expression;
    $('lookup-result').textContent = expression
      ? `Version ${short(expression.id)} effective ${expression.effective_date}. ${result.coverage.complete_for_registered_sources ? 'All registered sources covered for this date.' : `${result.coverage.unresolved.length} registered source(s) unresolved.`} External source completeness is not established.`
      : 'No approved expression is recorded for that date.';
    if (expression) await selectExpression(expression.id);
  }
  async function createCorrection() {
    ensureReviewSaved();
    const parent = $('correction-parent').value, source = $('correction-source').value;
    const eid = $('correction-eid').value.trim(), old = $('correction-old').value;
    const replacement = $('correction-new').value, page = Number($('correction-page').value);
    const quote = $('correction-quote').value.trim();
    if (!parent || !source || !eid || !old || !Number.isInteger(page) || page < 1 || !quote)
      throw new Error('Complete the approved version, source, target, old/new words, PDF page, and quotation.');
    const target = {eid};
    const inventory = await request(`/expressions/${parent}/inventory`,{method:'POST',body:{target,old,whole_word:false}});
    const hits = inventory.occurrences || [];
    if (hits.length !== 1 || hits[0].protected || hits[0].cross_inline)
      throw new Error(`Correction requires one ordinary text occurrence; found ${hits.length}. Use the API for complex inline decisions.`);
    const operation = {action:'text_replace',target,old,new:replacement,count:1,
      expected_hash:inventory.expected_hash,target_identity:inventory.target_identity,occurrences:hits};
    const output = await request(`/expressions/${parent}/correct`,{
      method:'POST',body:{revision:state.workspace.work.revision,operations:[operation],
        evidence:{source_id:source,pdf_pages:[page],quote},...identity()},
    });
    await loadWork(state.workId,{expressionId:output.expression.id});
    changeTab('versions'); notice('Separate editorial correction saved as a draft. Review and approve its exact XML.');
  }
  function wire() {
    $('actor').value = localStorage.getItem('nyayaReviewer') || '';
    document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => changeTab(button.dataset.tab)));
    $('work-select').addEventListener('change', () => task(async () => {
      if (state.dirty && !confirm('Discard unsaved instruction edits?')) { $('work-select').value = state.workId || ''; return; }
      state.manifest = null; state.body = null; state.expression = null; state.dirty = false;
      await loadWork($('work-select').value); changeTab('sources');
    }));
    $('refresh-work').addEventListener('click', () => task(async () => {
      if (state.dirty && !confirm('Discard unsaved instruction edits?')) return;
      await loadWorks(state.workId); notice('Current work revision loaded.');
    }));
    for (const id of ['empty-import','show-import']) $(id).addEventListener('click', () => task(showImport));
    $('hide-import').addEventListener('click', () => { $('import-panel').hidden = true; });
    $('import-kind').addEventListener('change',setImportKind);
    $('import-xml').addEventListener('change',suggestPdf);
    $('import-submit').addEventListener('click',() => task(importSource));
    $('manifest-select').addEventListener('change',event => selectManifest(event.target.value));
    for (const id of ['identity-confirmed','instrument-sequence','effective-date','date-confirmed','date-evidence'])
      $(id).addEventListener('change',syncManifestField);
    for (const id of ['op-action','op-status','target-eid','op-date','op-old','op-new','op-count','op-position',
      'op-whole-word','op-global','op-protected','op-new-number','op-classification','op-note'])
      $(id).addEventListener('change',syncOperationField);
    $('target-json').addEventListener('change',() => task(async () => {
      const op = currentOp(); if (!op) return;
      const target = JSON.parse($('target-json').value);
      if (!target || typeof target !== 'object' || Array.isArray(target)) throw new Error('Target selector must be a JSON object.');
      op.target = target; $('target-eid').value = target.eid || ''; invalidateInspection(true); markDirty(); renderOperationList();
    }));
    $('apply-operation-json').addEventListener('click',() => task(async () => {
      const original = currentOp(), modified = JSON.parse($('operation-json').value);
      if (modified.id !== original.id || JSON.stringify(modified.source) !== JSON.stringify(original.source))
        throw new Error('Instruction ID and original source quotation are immutable.');
      state.body.operations[state.selectedOp] = modified; markDirty(); renderOperationList(); renderOperation();
    }));
    $('add-fragment').addEventListener('click',addFragment);
    $('add-table-row').addEventListener('click',addTableRow);
    $('table-after-group').addEventListener('change',event => {
      const op = currentOp(); if (!op) return;
      op.after_group = event.target.value; payloadChanged();
    });
    $('inspect-target').addEventListener('click',() => task(inspectTarget));
    $('bind-target').addEventListener('click',bindTarget);
    $('bind-matches').addEventListener('click',bindMatches);
    $('source-xml-toggle').addEventListener('click',() => task(toggleSourceXml));
    $('save-manifest').addEventListener('click',() => task(saveManifest));
    $('preview-button').addEventListener('click',() => task(preview));
    $('apply-preview').addEventListener('click',() => task(applyPreview));
    $('approve-version').addEventListener('click',() => task(approveVersion));
    $('load-diff').addEventListener('click',() => task(loadDiff));
    $('lookup-button').addEventListener('click',() => task(lookupDate));
    $('correction-create').addEventListener('click',() => task(createCorrection));
    addEventListener('beforeunload',event => { if (state.dirty) { event.preventDefault(); event.returnValue = ''; } });
  }
  wire();
  task(async () => {
    const preferred = new URLSearchParams(location.search).get('work');
    await loadWorks(preferred);
    if (!preferred && !state.workId) changeTab('sources');
  });
})();
