'use strict';

// ─── STORAGE ─────────────────────────────────────────────────────────────────

var PROJ_KEY = 'fu_projects';

function getProjects() {
  try { return JSON.parse(localStorage.getItem(PROJ_KEY) || '[]'); }
  catch (e) { return []; }
}

function saveProjects(arr) {
  localStorage.setItem(PROJ_KEY, JSON.stringify(arr));
}

function upsertProject(proj) {
  var arr = getProjects();
  var idx = arr.findIndex(function (p) { return p.id === proj.id; });
  if (idx >= 0) arr[idx] = proj;
  else arr.unshift(proj);
  saveProjects(arr);
}

// ─── DETECÇÃO E PROCESSAMENTO DE ARQUIVO ─────────────────────────────────────

function detectTipo(data) {
  // Formato unificado: chaves 'hidrantes' e/ou 'saidas' aninhadas
  if ((data.hidrantes && typeof data.hidrantes === 'object') ||
      (data.saidas    && typeof data.saidas    === 'object')) return 'unificado';
  // Formatos individuais (legado)
  if (data.resultados && 'sigla_estado' in data) return 'saidas';
  if (data.res        && data.dados_sistema)     return 'hidrantes';
  return null;
}

function dirToId(dir) {
  try { return btoa(unescape(encodeURIComponent(dir || ''))).replace(/[+=\/]/g, '_'); }
  catch (e) { return Date.now().toString(36); }
}

function _parseTs(s) {
  if (!s) return 0;
  var a = s.match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})/);
  if (a) return new Date(+a[1], +a[2]-1, +a[3], +a[4], +a[5]).getTime();
  var b = s.match(/^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})/);
  if (b) return new Date(+b[3], +b[2]-1, +b[1], +b[4], +b[5]).getTime();
  return 0;
}

function _maisRecente(arr) {
  var valid = arr.filter(Boolean);
  if (!valid.length) return null;
  return valid.reduce(function(best, ts) { return _parseTs(ts) > _parseTs(best) ? ts : best; });
}

function _nomeFallback(filename) {
  return (filename || '').replace(/\.(json)$/i, '').replace(/^firedata_?|^fireutils_?/i, '') || 'Projeto';
}

function _extrairNomeDeDir(dir) {
  if (!dir) return '';
  var partes = dir.replace(/\\/g, '/').split('/').filter(Boolean);
  var last = partes[partes.length - 1] || '';
  if (/\.rvt$/i.test(last) && partes.length > 1) return partes[partes.length - 2];
  return last;
}

function _extrairMeta(hidData, saiData, projData, filename) {
  var dir = (hidData  && hidData._projeto_dir)  ||
            (saiData  && saiData._projeto_dir)  ||
            (projData && projData._projeto_dir) || '';

  // Identificador definido pelo usuário no botão "Dados do Projeto"
  var identificador = (projData && (projData.identificador || projData.nome)) || null;
  // Fallback: doc.Title do Revit gravado pelo plugin
  var nomeRevit = (hidData && hidData._nome_projeto) ||
                  (saiData && saiData._nome_projeto) || '';
  var nome = identificador || nomeRevit || _extrairNomeDeDir(dir) || _nomeFallback(filename);

  var uf     = (projData && projData.uf)     || (saiData && saiData.sigla_estado) || null;
  var estado = (projData && projData.estado) ||
               (saiData && saiData._estado && saiData._estado.nome) || null;

  var lastModified = _maisRecente([
    projData && projData._timestamp,
    hidData  && hidData._timestamp,
    saiData  && saiData.timestamp,
  ]);

  return { dir: dir, nome: nome, identificador: identificador, uf: uf, estado: estado, lastModified: lastModified };
}

function processarArquivo(data, tipo, filename) {
  var hidData, saiData;

  if (tipo === 'unificado') {
    hidData = (data.hidrantes && typeof data.hidrantes === 'object') ? data.hidrantes : null;
    saiData = (data.saidas    && typeof data.saidas    === 'object') ? data.saidas    : null;
  } else if (tipo === 'saidas') {
    hidData = null; saiData = data;
  } else {
    hidData = data; saiData = null;
  }

  // Suporta "dados_projeto" (novo) e "projeto" (legado)
  var projData = data.dados_projeto || data.projeto || null;
  var meta     = _extrairMeta(hidData, saiData, projData, filename);
  var id       = dirToId(meta.dir || meta.nome);

  var arr      = getProjects();
  var existing = arr.find(function (p) { return p.id === id; });
  var proj     = existing || {
    id: id, nome: meta.nome, identificador: null,
    uf: null, estado: null, dir: meta.dir,
    hidrantes: null, saidas: null, lastModified: null,
  };

  proj.nome         = meta.nome;
  proj.identificador = meta.identificador || proj.identificador;
  proj.dir          = meta.dir  || proj.dir;
  proj.lastModified = meta.lastModified || proj.lastModified;
  if (meta.uf)     proj.uf     = meta.uf;
  if (meta.estado) proj.estado = meta.estado;
  if (hidData)     proj.hidrantes = hidData;
  if (saiData)     proj.saidas    = saiData;

  upsertProject(proj);
  return proj;
}

// ─── INICIALIZAÇÃO ────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function () {
  var user = Auth.require();
  if (!user) return;

  document.getElementById('topbar-user').textContent = user.email;
  document.getElementById('btn-logout').addEventListener('click', function () { Auth.logout(); });

  var fileInput = document.getElementById('file-input');
  var btnTrazer = document.getElementById('btn-trazer');

  btnTrazer.addEventListener('click', function () { fileInput.click(); });

  fileInput.addEventListener('change', function (e) {
    var file = e.target.files[0];
    if (!file) return;
    fileInput.value = '';                      // permite reimportar o mesmo arquivo

    var reader = new FileReader();
    reader.onload = function (ev) {
      try {
        var data = JSON.parse(ev.target.result);
        var tipo = detectTipo(data);
        if (!tipo) {
          alert('Arquivo não reconhecido.\nSelecione um arquivo de dimensionamento do Fire Utils (hidrantes ou saídas).');
          return;
        }
        processarArquivo(data, tipo, file.name);
        renderProjetos();
        // feedback visual breve
        var orig = btnTrazer.textContent;
        btnTrazer.textContent = '✓ Importado';
        setTimeout(function () { btnTrazer.textContent = orig; }, 2000);
      } catch (err) {
        alert('Erro ao ler o arquivo: ' + err.message);
      }
    };
    reader.readAsText(file, 'utf-8');
  });

  renderProjetos();
});

// ─── RENDER ───────────────────────────────────────────────────────────────────

function renderProjetos() {
  var grid     = document.getElementById('projetos-grid');
  var projects = getProjects();

  if (projects.length === 0) {
    grid.innerHTML = emptyState();
    return;
  }

  grid.innerHTML = projects.map(renderCard).join('');
}

function emptyState() {
  return '<div class="empty-state">' +
    '<p>Nenhum projeto ainda.</p>' +
    '<p style="font-size:11px;margin-top:8px;">' +
      'Clique em <strong>Trazer Projeto</strong> para importar um arquivo de dimensionamento.' +
    '</p></div>';
}

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function renderCard(proj) {
  var href         = '/project?id=' + encodeURIComponent(proj.id);
  var titulo       = proj.identificador || proj.nome || 'Projeto';
  var local        = proj.estado || proj.uf || '';
  var ts           = proj.lastModified || '—';
  var tagHid       = proj.hidrantes ? '<span class="badge badge-ok">Hidrantes</span>' : '<span class="badge badge-warn">Hidrantes</span>';
  var tagSai       = proj.saidas    ? '<span class="badge badge-ok">Saídas</span>'    : '<span class="badge badge-warn">Saídas</span>';

  return '<a href="' + href + '" class="projeto-card projeto-card-link">' +
    '<div class="proj-card-row">' +
      '<div class="proj-card-info">' +
        '<div class="projeto-nome">' + esc(titulo) + '</div>' +
        (local ? '<div class="projeto-estado">' + esc(local) + '</div>' : '') +
      '</div>' +
      '<div class="proj-card-right">' +
        '<div class="proj-card-badges">' + tagHid + ' ' + tagSai + '</div>' +
        '<div class="proj-card-ts">atualizado em ' + esc(ts) + '</div>' +
      '</div>' +
    '</div>' +
  '</a>';
}
