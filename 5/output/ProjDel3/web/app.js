'use strict';
/* Research Lab Manager D3 — classroom frontend.
   Vanilla JS, no framework, no CDN: everything comes from the local JSON API,
   which in turn reuses the same LabService / run_report as the terminal. */

const $ = (sel, root) => (root || document).querySelector(sel);
const el = (tag, attrs, ...kids) => {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'html') node.innerHTML = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (value !== null && value !== undefined) node.setAttribute(key, value);
  }
  for (const kid of kids) {
    if (kid === null || kid === undefined) continue;
    node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return node;
};

let META = null;

const EXTRA_LABELS = {
  title: '标题', full_name: '姓名', status: '状态', leader_name: '负责人姓名',
  total_funding_usd: '总资助 USD', mentor_id: '导师编号', mentor_name: '导师姓名',
  mentee_id: '被指导者编号', mentee_name: '被指导者姓名', publication_count: '成果数',
  grant_count: '资助数', device_count: '装置数', available_device_count: '可用数',
  in_use_device_count: '使用中数', retired_device_count: '退役数', devices: '装置明细',
  mentorship_start_date: '指导开始日', mentorship_end_date: '指导结束日',
  end_before: '截止日期 X',
  project_role: '角色', weekly_hours: '每周工时', member_type: '类型',
  project_id: '项目编号', member_id: '成员编号', grant_id: '资助编号',
  equipment_id: '设备编号', device_number: '装置编号', publication_id: '成果编号',
  usage_id: '使用编号', started_at: '开始时刻', ended_at: '结束时刻', purpose: '目的',
};
const labelOf = (key) => {
  for (const table of Object.keys(META.tables)) {
    const field = META.tables[table].fields[key];
    if (field) return field.label;
  }
  return EXTRA_LABELS[key] || key;
};

const MENUS = {
  1: {
    entities: ['lab_member', 'research_project', 'project_participation',
               'faculty', 'student', 'external_collaborator', 'mentorship'],
    reports: ['project_status', 'grant_members', 'shared_project_mentorship'],
  },
  2: {
    entities: ['equipment', 'equipment_usage', 'device'],
    reports: ['equipment_status', 'equipment_current_users'],
  },
  3: {
    entities: ['research_grant', 'publication', 'authorship'],
    reports: ['top_funded_projects', 'mentor_publications',
              'student_publications_by_major_year', 'ended_projects', 'top_student_years'],
  },
};

const REPORT_NOTES = {
  project_status: '项目编号、负责人与实际状态；项目不存在时返回零行而不是空值行。',
  grant_members: '先定位资助所属项目，再按参与关系列成员；同项目多项资助不会重复成员。',
  shared_project_mentorship: '导师与被指导者必须参与同一项目；保留已保存的历史指导记录。',
  equipment_status: '状态属于具体装置而非设备；给出装置总数、三类状态计数与每台明细。',
  equipment_current_users: '当前使用由未结束记录判定；项目只取 status=active，没有活跃项目的使用者保留为 NULL。',
  top_funded_projects: 'SUM(budget) 而非 SUM(DISTINCT budget)，相同金额的两笔资助分别计算；LEFT JOIN 保留零资助项目。',
  mentor_publications: '按导师对全部被指导者的成果取 COUNT(DISTINCT publication_id)，合著只算一次；最大值全并列返回。',
  student_publications_by_major_year: '同专业合著计一次，跨专业在各专业分别计一次；统计成果数而非学生数。',
  ended_projects: '严格 end_date < X；COUNT(grant_id) 使零资助项目正确显示 0。',
  top_student_years: '在所有学生作者之间按年全局去重，不能把各专业分组相加；同数按年份降序稳定截断。',
};

async function api(path, options) {
  const res = await fetch(path, options);
  let data = null;
  try { data = await res.json(); } catch (error) { data = null; }
  if (!res.ok || !data || data.ok !== true) {
    throw new Error((data && data.error) || ('HTTP ' + res.status));
  }
  return data;
}

function toast(message, isError) {
  const box = el('div', { class: isError ? 'err' : '', text: message });
  $('#toast').append(box);
  setTimeout(() => box.remove(), isError ? 6000 : 2600);
}

const pretty = (value) => {
  if (value === null || value === undefined) return 'NULL';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

/* ---------------------------------------------------------------- tables */
function dataTable(rows, withActions) {
  if (!rows.length) return el('p', { class: 'empty', text: '无匹配记录。' });
  const columns = Object.keys(rows[0]).filter((c) => c !== '__table');
  const head = el('tr', null,
    ...columns.map((c) => el('th', { text: labelOf(c) })),
    withActions ? el('th', { text: '' }) : null);
  const body = rows.map((row) => el('tr', null,
    ...columns.map((c) => el('td', {
      class: /^[-\d.]+$/.test(pretty(row[c])) ? 'num' : '',
      text: pretty(row[c]),
    })),
    withActions ? el('td', { class: 'rowact' },
      el('button', { text: '修改', onclick: () => openUpdate(row.__table, row) }),
      el('button', { text: '删除', onclick: () => openDelete(row.__table, row) })) : null));
  return el('table', { class: 'data' }, el('thead', null, head), el('tbody', null, ...body));
}

async function idOptions(table) {
  const data = await api('/api/rows?table=' + table);
  const keys = META.tables[table].keys;
  const labelKey = ['full_name', 'title', 'equipment_name', 'grant_id']
    .find((k) => Object.keys(data.rows[0] || {}).includes(k)) || keys[0];
  return data.rows.map((row) => ({
    value: keys.map((k) => row[k]).join(' / '),
    text: keys.map((k) => row[k]).join(' / ') + '  ' + (row[labelKey] || ''),
  }));
}

async function attachDatalist(input, table) {
  const listId = 'dl-' + table + '-' + Math.random().toString(36).slice(2, 8);
  const list = el('datalist', { id: listId });
  input.setAttribute('list', listId);
  document.body.append(list);
  try {
    for (const option of await idOptions(table)) {
      list.append(el('option', { value: option.value, text: option.text }));
    }
  } catch (error) { /* 建议列表失败不阻塞录入 */ }
}

const ID_SOURCE = {
  project_id: 'research_project', member_id: 'lab_member', leader_id: 'faculty',
  equipment_id: 'equipment', publication_id: 'publication',
};

/* ---------------------------------------------------------------- entity */
async function openEntity(table) {
  const panel = $('#panel' + PANEL_OF[table]);
  panel.replaceChildren(el('p', { class: 'empty', text: '载入中…' }));
  const spec = META.tables[table];
  const search = el('input', { type: 'search', placeholder: '关键词（空 = 全表）' });
  const addButton = el('button', { class: 'btn btn--accent', text: '＋ 新增', onclick: () => openCreate(table) });
  const refresh = el('button', { class: 'btn btn--ghost', text: '刷新' });
  const holder = el('div');
  const toolbar = el('div', { class: 'toolbar' }, search, addButton, refresh);
  panel.replaceChildren(
    el('div', { class: 'panel-head' },
      el('h3', { style: 'font:600 18px/1.4 var(--serif);margin:0', text: spec.label + ' · ' + table }),
      el('span', { class: 'hint-chip', text: '可操作：新增 · 行内修改 / 删除' })),
    el('p', { class: 'countline', style: 'margin:0 0 14px', text: '主键：' + spec.keys.join(' + ') }),
    toolbar, holder);

  async function load() {
    holder.replaceChildren(el('p', { class: 'empty', text: '载入中…' }));
    try {
      const data = await api('/api/rows?table=' + table + '&q=' + encodeURIComponent(search.value || ''));
      const rows = data.rows.map((row) => Object.assign({ __table: table }, row));
      holder.replaceChildren(dataTable(rows, true),
        el('p', { class: 'countline', text: '共 ' + rows.length + ' 条记录' }));
    } catch (error) {
      holder.replaceChildren(el('p', { class: 'empty', text: '载入失败：' + error.message }));
    }
  }
  search.addEventListener('keydown', (event) => { if (event.key === 'Enter') load(); });
  refresh.addEventListener('click', load);
  await load();
}

/* ---------------------------------------------------------------- forms */
function fieldRow(table, key, value, forUpdate) {
  const spec = META.tables[table].fields[key];
  const kind = spec.kind;
  let input;
  const choices = {
    member_type: ['faculty', 'student', 'collaborator'],
  };
  if (table === 'research_project' && key === 'status') choices.status = ['active', 'completed', 'paused'];
  if (table === 'device' && key === 'status') choices.status = ['available', 'in_use', 'retired'];
  if (choices[key]) {
    input = el('select', null,
      ...(forUpdate ? [el('option', { value: '', text: '（留空保留）' })] : []),
      ...choices[key].map((c) => el('option', { value: c, text: c })));
    if (value) input.value = value;
  } else if (kind === 'date' || kind === 'date?') {
    input = el('input', { type: 'date', value: value || '' });
  } else {
    input = el('input', { type: 'text', value: value === null || value === undefined ? '' : value });
    if (ID_SOURCE[key]) attachDatalist(input, ID_SOURCE[key]);
  }
  if (forUpdate) input.placeholder = value === null ? 'NULL（留空保留）' : pretty(value);
  return el('div', { class: 'frow' },
    el('div', null,
      el('span', { class: 'flabel', text: spec.label + ' · ' + key }),
      spec.hint ? el('span', { class: 'fhint', text: spec.hint }) : null,
      kind.endsWith('?') ? el('span', { class: 'fhint', text: '可空：NULL 清除' }) : null),
    input);
}

const readValue = (row) => {
  const input = row.querySelector('input,select');
  return input.value;
};

function modalShell(title, sub, bodyNodes, actions) {
  const modal = $('#modal');
  modal.replaceChildren(
    el('h3', { text: title }),
    el('div', { class: 'msub', text: sub }),
    ...bodyNodes,
    el('div', { class: 'mactions' }, ...actions));
  $('#overlay').classList.add('open');
}
const closeModal = () => $('#overlay').classList.remove('open');
$('#overlay').addEventListener('click', (event) => {
  if (event.target.id === 'overlay') closeModal();
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') closeModal();
});

function openCreate(table) {
  const spec = META.tables[table];
  const groups = [];
  const collect = {};

  function group(title, tableOfFields, skip) {
    const rows = [];
    const grid = el('div', { class: 'fgrid' });
    for (const key of Object.keys(META.tables[tableOfFields].fields)) {
      if (skip && skip.includes(key)) continue;
      const row = fieldRow(tableOfFields, key, null, false);
      rows.push([key, row]);
      grid.append(row);
    }
    collect[tableOfFields] = rows;
    groups.push(el('div', { class: 'fgroup' }, el('h4', { text: title }), grid));
    return rows;
  }

  if (table === 'lab_member') {
    const memberRows = group('成员（超类）', 'lab_member');
    const subtypeHolder = el('div');
    let subtypeRows = null;
    const typeInput = memberRows.find(([k]) => k === 'member_type')[1].querySelector('select');
    const rebuild = () => {
      subtypeHolder.replaceChildren();
      const target = { faculty: 'faculty', student: 'student', collaborator: 'external_collaborator' }[typeInput.value];
      subtypeRows = target ? group('子类资料 · ' + target, target, ['member_id']) : null;
      subtypeHolder.append(...groups.slice(-1));
    };
    typeInput.addEventListener('change', rebuild);
    const participationHolder = el('div');
    const participationLists = [];
    const addParticipation = () => {
      const rows = [];
      const grid = el('div', { class: 'fgrid' });
      for (const key of ['project_id', 'project_role', 'weekly_hours']) {
        const row = fieldRow('project_participation', key, null, false);
        rows.push([key, row]);
        grid.append(row);
      }
      participationLists.push(rows);
      participationHolder.append(grid);
    };
    addParticipation();
    modalShell('新增成员', 'lab_member + 子类 + project_participation（一个事务）',
      [groups[0], subtypeHolder,
       el('div', { class: 'fgroup' }, el('h4', { text: '项目参与（至少一个）' }), participationHolder,
         el('button', { class: 'btn btn--ghost', style: 'margin-top:10px', text: '＋ 再加一个项目', onclick: addParticipation }))],
      [el('button', { class: 'btn btn--ghost', text: '取消', onclick: closeModal }),
       el('button', { class: 'btn btn--accent', text: '提交新增', onclick: async () => {
         try {
           const member = Object.fromEntries(memberRows.map(([k, r]) => [k, readValue(r)]));
           const target = { faculty: 'faculty', student: 'student', collaborator: 'external_collaborator' }[member.member_type];
           if (!target) throw new Error('成员类型只能为 faculty / student / collaborator');
           const subtype = Object.fromEntries((collect[target] || []).map(([k, r]) => [k, readValue(r)]));
           const participations = participationLists.map((rows) => Object.fromEntries(rows.map(([k, r]) => [k, readValue(r)])));
           await api('/api/rows', { method: 'POST', headers: { 'Content-Type': 'application/json' },
             body: JSON.stringify({ table, member, subtype, participations }) });
           closeModal(); toast('新增已提交'); openEntity(table);
         } catch (error) { toast(error.message, true); }
       } })]);
    rebuild();
    return;
  }

  if (table === 'research_project' || table === 'equipment') {
    const mainRows = group(spec.label, table);
    const childTable = table === 'research_project' ? null : 'device';
    const childHolder = el('div');
    const childLists = [];
    if (table === 'equipment') {
      const addChild = () => {
        const rows = [];
        const grid = el('div', { class: 'fgrid' });
        for (const key of ['device_number', 'purchase_date', 'status']) {
          const row = fieldRow('device', key, null, false);
          rows.push([key, row]);
          grid.append(row);
        }
        childLists.push(rows);
        childHolder.append(grid);
      };
      addChild();
    }
    const extra = table === 'research_project'
      ? el('p', { class: 'sec-note', style: 'margin:14px 0 0', text: '负责人会自动补一条参与记录（角色「负责人」，每周 0 工时），可在参与菜单修改。' })
      : el('div', { class: 'fgroup' }, el('h4', { text: '第一台装置' }), childHolder);
    modalShell('新增' + spec.label, table + '（一个事务）', [groups[0], extra],
      [el('button', { class: 'btn btn--ghost', text: '取消', onclick: closeModal }),
       el('button', { class: 'btn btn--accent', text: '提交新增', onclick: async () => {
         try {
           const main = Object.fromEntries(mainRows.map(([k, r]) => [k, readValue(r)]));
           if (table === 'equipment') {
             const devices = childLists.map((rows) => Object.fromEntries(rows.map(([k, r]) => [k, readValue(r)])));
             await api('/api/rows', { method: 'POST', headers: { 'Content-Type': 'application/json' },
               body: JSON.stringify({ table, equipment: main, devices }) });
           } else {
             await api('/api/rows', { method: 'POST', headers: { 'Content-Type': 'application/json' },
               body: JSON.stringify({ table, project: main, participants: [] }) });
           }
           closeModal(); toast('新增已提交'); openEntity(table);
         } catch (error) { toast(error.message, true); }
       } })]);
    return;
  }

  if (table === 'publication') {
    const mainRows = group('学术成果', table);
    const authors = el('input', { type: 'text', placeholder: '成员编号，逗号分隔，至少一个' });
    modalShell('新增成果', 'publication + authorship（一个事务）',
      [groups[0], el('div', { class: 'fgroup' }, el('h4', { text: '作者' }), authors)],
      [el('button', { class: 'btn btn--ghost', text: '取消', onclick: closeModal }),
       el('button', { class: 'btn btn--accent', text: '提交新增', onclick: async () => {
         try {
           const publication = Object.fromEntries(mainRows.map(([k, r]) => [k, readValue(r)]));
           const authorIds = authors.value.split(',').map((s) => s.trim()).filter(Boolean);
           await api('/api/rows', { method: 'POST', headers: { 'Content-Type': 'application/json' },
             body: JSON.stringify({ table, publication, author_ids: authorIds }) });
           closeModal(); toast('新增已提交'); openEntity(table);
         } catch (error) { toast(error.message, true); }
       } })]);
    return;
  }

  const rows = group(spec.label, table);
  modalShell('新增' + spec.label, table, [groups[0]],
    [el('button', { class: 'btn btn--ghost', text: '取消', onclick: closeModal }),
     el('button', { class: 'btn btn--accent', text: '提交新增', onclick: async () => {
       try {
         const data = Object.fromEntries(rows.map(([k, r]) => [k, readValue(r)]));
         await api('/api/rows', { method: 'POST', headers: { 'Content-Type': 'application/json' },
           body: JSON.stringify({ table, data }) });
         closeModal(); toast('新增已提交'); openEntity(table);
       } catch (error) { toast(error.message, true); }
     } })]);
}

function openUpdate(table, record) {
  const spec = META.tables[table];
  const rows = [];
  const grid = el('div', { class: 'fgrid' });
  for (const key of Object.keys(spec.fields)) {
    if (spec.keys.includes(key)) continue;
    if (table === 'lab_member' && key === 'member_type') continue;
    const row = fieldRow(table, key, record[key], true);
    rows.push([key, row]);
    grid.append(row);
  }
  const notes = ['留空保留原值；可空字段输入 NULL 清除。'];
  if (table === 'lab_member') {
    notes.push('成员类型固定；学生专业等子类资料请在对应子类表中修改，与终端一致。');
  }
  modalShell('修改' + spec.label, spec.keys.map((k) => k + '=' + record[k]).join('，') + '（编号不可改）',
    [...notes.map((t) => el('p', { class: 'sec-note', style: 'margin:0 0 12px', text: t })), grid],
    [el('button', { class: 'btn btn--ghost', text: '取消', onclick: closeModal }),
     el('button', { class: 'btn btn--accent', text: '提交修改', onclick: async () => {
       try {
         const changes = Object.fromEntries(rows.map(([k, r]) => [k, readValue(r)]));
         await api('/api/record', { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
           body: JSON.stringify({ table, key: spec.keys.map((k) => record[k]), changes }) });
         closeModal(); toast('修改已提交'); openEntity(table);
       } catch (error) { toast(error.message, true); }
     } })]);
}

function openDelete(table, record) {
  const spec = META.tables[table];
  const confirmInput = el('input', { type: 'text', placeholder: '输入 DELETE 以确认' });
  const confirmButton = el('button', { class: 'btn btn--accent', text: '确认删除', disabled: 'disabled' });
  confirmInput.addEventListener('input', () => {
    if (confirmInput.value.trim() === 'DELETE') confirmButton.removeAttribute('disabled');
    else confirmButton.setAttribute('disabled', 'disabled');
  });
  const detail = el('div', { class: 'fgrid' },
    ...spec.keys.map((k) => el('div', { class: 'frow' },
      el('div', null, el('span', { class: 'flabel', text: labelOf(k) })),
      el('div', { class: 'mono', style: 'font-size:13px', text: pretty(record[k]) }))));
  confirmButton.addEventListener('click', async () => {
    try {
      await api('/api/record', { method: 'DELETE', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ table, key: spec.keys.map((k) => record[k]) }) });
      closeModal(); toast('删除已提交'); openEntity(table);
    } catch (error) { toast(error.message, true); }
  });
  modalShell('删除' + spec.label, table,
    [detail,
     el('div', { class: 'warnbox', text: '删除主实体将同时清除其参与 / 作者 / 使用等依赖记录；'
       + '若会使其他对象失去必需关系（例如仍是项目负责人），整组回滚并给出原因。' }),
     el('div', { class: 'frow' }, el('div', null, el('span', { class: 'flabel', text: '确认' })), confirmInput)],
    [el('button', { class: 'btn btn--ghost', text: '取消', onclick: closeModal }), confirmButton]);
}

/* --------------------------------------------------------------- reports */
async function reportParamControl(name, key) {
  const wrap = el('label', null, el('div', { class: 'plabel', text: labelOf(key) + ' · ' + key }));
  if (key === 'end_before') {
    const input = el('input', { type: 'date', value: '2025-01-01' });
    input.dataset.key = key;
    wrap.append(input);
    return wrap;
  }
  const source = { project_id: 'research_project', grant_id: 'research_grant',
                   equipment_id: 'equipment' }[key];
  const select = el('select');
  select.dataset.key = key;
  wrap.append(select);
  const data = await api('/api/rows?table=' + source);
  const keys = META.tables[source].keys;
  const labelKey = { research_project: 'title', research_grant: 'funding_agency',
                     equipment: 'equipment_name' }[source];
  for (const row of data.rows) {
    select.append(el('option', { value: row[keys[0]], text: row[keys[0]] + '  ' + row[labelKey] }));
  }
  return wrap;
}

async function openReport(name) {
  const definition = META.reports.find((r) => r.name === name);
  const panel = $('#panel' + PANEL_OF[name]);
  const paramsBar = el('div', { class: 'params' });
  const holder = el('div');
  panel.replaceChildren(
    el('div', { class: 'panel-head' },
      el('h3', { style: 'font:600 18px/1.4 var(--serif);margin:0', text: definition.title }),
      el('span', { class: 'hint-chip', text: '可操作：换参数 · 运行 · 展开 SQL' })),
    el('p', { class: 'countline', style: 'margin:0 0 12px', text: name }),
    el('p', { class: 'sec-note', style: 'margin:0 0 16px', text: REPORT_NOTES[name] || '' }),
    paramsBar, holder,
    el('details', { class: 'sql' }, el('summary', { text: '查看真实 SQL' }),
      el('pre', { text: definition.sql })));
  for (const key of definition.params) {
    paramsBar.append(await reportParamControl(name, key));
  }
  const run = async () => {
    holder.replaceChildren(el('p', { class: 'empty', text: '查询中…' }));
    try {
      const parts = [];
      for (const control of paramsBar.children) {
        const input = control.querySelector('select,input');
        if (!input || !input.dataset.key) continue;  // 无参数报表只有运行按钮
        parts.push(input.dataset.key + '=' + encodeURIComponent(input.value));
      }
      const data = await api('/api/report?name=' + name + (parts.length ? '&' + parts.join('&') : ''));
      holder.replaceChildren(dataTable(data.rows, false),
        el('p', { class: 'countline', text: '共 ' + data.rows.length + ' 条记录' }));
    } catch (error) {
      holder.replaceChildren(el('p', { class: 'empty', text: '查询失败：' + error.message }));
    }
  };
  paramsBar.append(el('label', null, el('div', { class: 'plabel', text: ' ' }),
    el('button', { class: 'btn btn--accent', text: '运行', onclick: run })));
  await run();
}

/* ---------------------------------------------------------------- menus */
const PANEL_OF = {};
for (const table of MENUS[1].entities.concat(MENUS[1].reports)) PANEL_OF[table] = 1;
for (const table of MENUS[2].entities.concat(MENUS[2].reports)) PANEL_OF[table] = 2;
for (const table of MENUS[3].entities.concat(MENUS[3].reports)) PANEL_OF[table] = 3;

function renderMenu(index) {
  const list = $('#fn' + index);
  const entityButtons = MENUS[index].entities.map((table) => el('button', {
    text: META.tables[table].label + ' · ' + table,
    onclick: (event) => { mark(event); openEntity(table); },
  }));
  const reportButtons = MENUS[index].reports.map((name) => el('button', {
    text: META.reports.find((r) => r.name === name).title,
    onclick: (event) => { mark(event); openReport(name); },
  }));
  list.replaceChildren(
    el('h4', { text: '数据维护' }), ...entityButtons,
    el('h4', { text: '指定查询 / 报表' }), ...reportButtons);
  entityButtons[0].classList.add('on');  // 首屏即标出当前项，避免"看不出选中了什么"
}
function mark(event) {
  const list = event.currentTarget.parentElement;
  for (const button of list.querySelectorAll('button')) button.classList.remove('on');
  event.currentTarget.classList.add('on');
}

/* ---------------------------------------------------------------- schema */
const NODE_POS = {
  lab_member: [10, 10], faculty: [10, 84], student: [10, 158], external_collaborator: [10, 232],
  research_project: [260, 10], project_participation: [260, 84], research_grant: [260, 158], mentorship: [260, 232],
  equipment: [510, 10], device: [510, 84], equipment_usage: [510, 158], publication: [510, 232],
  authorship: [760, 158],
};
const NODE_W = 216;
const NODE_H = 46;

function renderSchema() {
  const grid = $('#schema-grid');
  const fkBySrc = {};
  for (const fk of META.foreign_keys) (fkBySrc[fk.src] = fkBySrc[fk.src] || []).push(fk);
  for (const [name, spec] of Object.entries(META.tables)) {
    const fks = fkBySrc[name] || [];
    const fkCols = new Set(fks.flatMap((fk) => fk.cols));
    grid.append(el('div', { class: 'tcard' },
      el('span', { class: 'tcount', text: META.counts[name] + ' 行' }),
      el('div', { class: 'tname', text: name }),
      el('h3', { text: spec.label }),
      el('ul', null, ...Object.entries(spec.fields).map(([key, field]) => el('li', null,
        el('span', { class: 'fname', text: key }),
        spec.keys.includes(key) ? el('span', { class: 'badge', text: 'PK' })
          : fkCols.has(key) ? el('span', { class: 'badge', text: 'FK' })
          : field.kind.endsWith('?') ? el('span', { class: 'badge null', text: 'NULL' }) : null)))));
  }

  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', '0 0 990 292');
  const defs = document.createElementNS(svgNS, 'defs');
  const marker = document.createElementNS(svgNS, 'marker');
  marker.setAttribute('id', 'arrow'); marker.setAttribute('viewBox', '0 0 8 8');
  marker.setAttribute('refX', '7'); marker.setAttribute('refY', '4');
  marker.setAttribute('markerWidth', '7'); marker.setAttribute('markerHeight', '7');
  marker.setAttribute('orient', 'auto');
  const arrowPath = document.createElementNS(svgNS, 'path');
  arrowPath.setAttribute('d', 'M0,0 L8,4 L0,8 z'); arrowPath.setAttribute('class', 'arrow');
  marker.append(arrowPath); defs.append(marker); svg.append(defs);

  const boxOf = (table) => ({ x: NODE_POS[table][0], y: NODE_POS[table][1], w: NODE_W, h: NODE_H });
  const edges = [];
  const drawn = new Set();
  for (const fk of META.foreign_keys) {
    if (drawn.has(fk.src + '>' + fk.dst)) continue;  // mentorship 有两条自引用外键，图上一条线
    drawn.add(fk.src + '>' + fk.dst);
    const a = boxOf(fk.src); const b = boxOf(fk.dst);
    const leftToRight = b.x >= a.x + a.w;
    const rightToLeft = a.x >= b.x + b.w;
    let sx, sy, dx, dy;
    if (leftToRight) { sx = a.x + a.w; sy = a.y + a.h / 2; dx = b.x; dy = b.y + b.h / 2; }
    else if (rightToLeft) { sx = a.x; sy = a.y + a.h / 2; dx = b.x + b.w; dy = b.y + b.h / 2; }
    else { sx = a.x + a.w / 2; sy = a.y + (b.y > a.y ? a.h : 0); dx = b.x + b.w / 2; dy = b.y + (b.y > a.y ? 0 : b.h); }
    const midX = (sx + dx) / 2;
    const path = document.createElementNS(svgNS, 'path');
    const d = leftToRight || rightToLeft
      ? `M${sx},${sy} H${midX} V${dy} H${dx}`
      : `M${sx},${sy} V${dy}`;
    path.setAttribute('d', d);
    path.setAttribute('class', 'edge');
    path.setAttribute('marker-end', 'url(#arrow)');
    path.dataset.src = fk.src; path.dataset.dst = fk.dst;
    svg.append(path); edges.push(path);
  }
  for (const [name, spec] of Object.entries(META.tables)) {
    const box = boxOf(name);
    const g = document.createElementNS(svgNS, 'g');
    g.setAttribute('class', 'node');
    const rect = document.createElementNS(svgNS, 'rect');
    rect.setAttribute('x', box.x); rect.setAttribute('y', box.y);
    rect.setAttribute('width', box.w); rect.setAttribute('height', box.h);
    const text = document.createElementNS(svgNS, 'text');
    text.setAttribute('x', box.x + 10); text.setAttribute('y', box.y + 19);
    text.textContent = name;
    const sub = document.createElementNS(svgNS, 'text');
    sub.setAttribute('x', box.x + 10); sub.setAttribute('y', box.y + 34);
    sub.setAttribute('class', 'cnt');
    sub.textContent = spec.label + ' · ' + META.counts[name];
    g.append(rect, text, sub);
    g.addEventListener('mouseenter', () => {
      for (const path of edges) {
        path.classList.toggle('hl', path.dataset.src === name || path.dataset.dst === name);
      }
    });
    g.addEventListener('mouseleave', () => {
      for (const path of edges) path.classList.remove('hl');
    });
    svg.append(g);
  }
  $('#diagram').replaceChildren(svg);
}

/* ---------------------------------------------------------------- static */
function renderStats() {
  const v = META.verification || {};
  const items = [
    ['Tables', Object.keys(META.tables).length, '张表'],
    ['Foreign keys', META.foreign_keys.length, '个外键'],
    ['Sample tuples', META.total_tuples, '条元组'],
    ['Reports', META.reports.length, '项报表'],
    ['Tests', v.unittest_count || '—', '项通过'],
  ];
  $('#stats').replaceChildren(...items.map(([label, value, unit]) =>
    el('div', null, el('dt', { text: label }), el('dd', null, String(value), el('small', { text: unit })))));
}

function renderIntegrity() {
  const cards = [
    ['完全特化与互斥', '每名成员恰好属于与 member_type 相符的一个子类；延迟约束触发器在提交前检查，直接写 SQL 也绕不过。'],
    ['必需关系', '成员至少一个项目、负责人保留参与、设备至少一台装置、成果至少一位作者；破坏即整体回滚。'],
    ['装置并发上限', '同一装置任意时刻最多三名不同成员；区间为 [start, end)，零长度不占用，同人区间不得重叠。'],
    ['时间与退役', '实际使用不得晚于录入时刻（北京时间）；退役装置不接受新使用，退役前必须结束全部使用。'],
    ['写事务串行化', 'READ COMMITTED 下统一 advisory 事务锁加装置行锁，避免两个事务各自检查后写偏斜。'],
    ['TRUNCATE 防护', '13 张表均有 BEFORE TRUNCATE 拒绝触发器，防止清空关系表留下无作者成果。'],
  ];
  $('#integrity-cards').replaceChildren(...cards.map(([k, p]) =>
    el('div', { class: 'card' }, el('div', { class: 'k', text: k }), el('p', { text: p }))));
}

function renderVerify() {
  const v = META.verification || {};
  const rows = [
    ['验证时间', v.verified_at || '—'],
    ['Python / PostgreSQL', (v.python || '—') + ' / ' + (v.postgresql || META.server_version)],
    ['单元测试', (v.unittest_count || '—') + ' 项，退出码 ' + (v.unittest_exit_code ?? '—')],
    ['独立 SQL 文件', '退出码 ' + (v.standalone_sql_exit_code ?? '—')],
    ['终端演示', '退出码 ' + (v.terminal_demo_exit_code ?? '—') + '，成功写入 ' + (v.terminal_demo_successful_mutations ?? '—') + ' 次、预期拒绝 ' + (v.terminal_demo_expected_rejections ?? '—') + ' 次'],
    ['样例元组', (v.total_sample_tuples || META.total_tuples) + ' 条，13 表计数吻合'],
    ['并发测试', v.concurrency_test || '—'],
    ['模式隔离', v.schema_isolation || '—'],
  ];
  $('#verify-kv').replaceChildren(...rows.map(([k, value]) =>
    el('div', null, el('dt', { text: k }), el('dd', { text: String(value) }))));
  $('#foot-line').textContent =
    'schema=' + META.schema + ' · PostgreSQL ' + META.server_version +
    ' · 仅监听 127.0.0.1 · 业务规则与终端同源（LabService / run_report）· 演示服务，不含登录与权限';
}

/* ---------------------------------------------------------------- boot */
async function boot() {
  try {
    META = (await api('/api/meta')).meta;
  } catch (error) {
    document.body.append(el('p', { class: 'empty', style: 'padding:40px', text: '无法连接本地 API：' + error.message }));
    return;
  }
  renderStats();
  renderSchema();
  renderMenu(1); renderMenu(2); renderMenu(3);
  renderIntegrity();
  renderVerify();
  openEntity('lab_member');
  openReport('top_funded_projects');
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!reduce && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) if (entry.isIntersecting) entry.target.classList.add('in');
    }, { threshold: 0.08 });
    for (const node of document.querySelectorAll('.reveal')) observer.observe(node);
  } else {
    for (const node of document.querySelectorAll('.reveal')) node.classList.add('in');
  }
}
boot();
