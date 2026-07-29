'use strict';

// ─── PRIMITIVOS ──────────────────────────────────────────────────────────────

function badge(tipo, texto) {
  return `<span class="badge badge-${tipo}">${texto}</span>`;
}

function badgeStatus(valor, min, max) {
  if (valor < min) return badge('err', 'ABAIXO DO MÍNIMO');
  if (max !== null && max !== undefined && valor > max) return badge('err', 'ACIMA DO MÁXIMO');
  return badge('ok', 'ATENDE');
}

function nota(texto) { return `<p class="nota">${texto}</p>`; }
function formula(texto) { return `<div class="formula">${texto}</div>`; }

function tabela(cab, linhas, cls) {
  cls = cls || '';
  const ths = cab.map(c => `<th>${c}</th>`).join('');
  const trs = linhas.map(l =>
    `<tr>${l.map(c => `<td>${c}</td>`).join('')}</tr>`
  ).join('');
  return `<table class="tabela ${cls}"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
}

function secao(num, titulo, conteudo, colapsavel) {
  if (colapsavel) {
    return `<section class="secao"><details>
      <summary class="secao-header secao-header-details">
        <span class="secao-num">${num}</span>
        <h2 class="secao-titulo">${titulo}</h2>
        <span class="secao-chevron">&#9660;</span>
      </summary>
      <div class="secao-corpo">${conteudo}</div>
    </details></section>`;
  }
  return `<section class="secao">
    <div class="secao-header">
      <span class="secao-num">${num}</span>
      <h2 class="secao-titulo">${titulo}</h2>
    </div>
    <div class="secao-corpo">${conteudo}</div>
  </section>`;
}

function fmt(n, dec) { return Number(n).toFixed(dec); }

// ─── HIDRANTES ───────────────────────────────────────────────────────────────

function hidDadosSistema(c) {
  const d = c.dados_sistema;
  const Qs = d.vazao_min;
  const Qt = Qs * 2;
  return tabela(['Parâmetro', 'Valor', 'Referência'], [
    ['Classificação',             `<strong>${c.valor_sistema}</strong>`,                                                'NT 22 CBMMA'],
    ['Método de cálculo',         `<strong>${c.calculo_escolha}</strong>`,                                              '—'],
    ['Vazão mínima (Qmin)',       `<strong>${Qs} L/min = ${fmt(Qs/60000,4)} m³/s</strong>`,                            'NT 22'],
    ['Vazão total (Qt)',          `<strong>${Qt} L/min = ${fmt(Qt/60000,4)} m³/s</strong>`,                            '2 hidrantes simultâneos'],
    ['Pressão mínima (Pmin)',     `<strong>${d.pressao_min} mca</strong>`,                                              'NT 22'],
    ['Pressão máxima',            `<strong>100 mca</strong>`,                                                           'NT 22'],
    ['Coef. Hazen-Williams (C)',  `<strong>${c.C_HW}</strong>`,                                                         'Aço / Ferro galvanizado'],
    ['Velocidade máxima',         `<strong>3,0 m/s</strong>`,                                                           'NBR 13714'],
  ]);
}

function condBadge(hz) {
  if (hz < -0.05) return badge('warn', 'Hidrante acima da RTI');
  if (hz >  0.05) return badge('ok',   'Hidrante abaixo da RTI');
  return badge('ok', 'Mesmo nível da RTI');
}

function velBadge(v) {
  return v <= 3.0
    ? badge('ok',  `✓ ${fmt(v,3)} m/s`)
    : badge('err', `⚠ ${fmt(v,3)} m/s`);
}

function hidElevacoes(c) {
  const tabCotas = tabela(['Ponto', 'Cota Z (m)'], [
    ['RTI',    `<mono>${fmt(c.Z_RTI,3)} m</mono>`],
    ['HID-01', `<mono>${fmt(c.Z_HID01,3)} m</mono>`],
    ['HID-02', `<mono>${fmt(c.Z_HID02,3)} m</mono>`],
  ]);
  const tabDesn = tabela(['Percurso', 'ΔZ (m)', 'Condição'], [
    ['RTI → HID-01', `<mono>${fmt(c.Hz_H1,3)}</mono>`, condBadge(c.Hz_H1)],
    ['RTI → HID-02', `<mono>${fmt(c.Hz_H2,3)}</mono>`, condBadge(c.Hz_H2)],
  ]);
  return tabCotas + '<br>' + tabDesn +
    nota('ΔZ = Z<sub>RTI</sub> − Z<sub>hidrante</sub>. Negativo indica hidrante <strong>acima</strong> da RTI — a bomba precisa vencer essa altura.');
}

function hidTrechoCard(t, C, idx) {
  const tabDados = tabela(['Item', 'Valor'], [
    ['Comprimento real (L)',        `<mono>${fmt(t.L,4)} m</mono>`],
    ['Diâmetro interno médio (D)',  `<mono>${fmt(t.D*1000,1)} mm (${fmt(t.D,4)} m)</mono>`],
    ['Vazão no trecho (Q)',         `<mono>${fmt(t.Q_lmin,2)} L/min (${fmt(t.Q_m3s,4)} m³/s)</mono>`],
    ['Velocidade (V = Q/A)',        velBadge(t.V)],
  ]);

  let tabAces = '';
  if (t.acessorios && t.acessorios.length) {
    const linhas = t.acessorios.map(a => [
      `<mono><strong>${a.qtd}</strong></mono>`, a.nome,
      `<mono>${fmt(a.leq_unit,4)}</mono>`, `<mono>${fmt(a.leq_tot,4)}</mono>`,
    ]);
    linhas.push(['—', '<strong>Total</strong>', '—', `<mono><strong>${fmt(t.Leq,4)} m</strong></mono>`]);
    tabAces = `<p class="sub-titulo">Acessórios (${t.n_aces} tipo(s)):</p>` +
      tabela(['Qtd', 'Descrição', 'Le unit. (m)', 'Σ Le (m)'], linhas, 'tabela-aces');
  } else {
    tabAces = nota('Nenhum acessório registrado neste trecho.');
  }

  return `<div class="trecho-card">
    <div class="trecho-header">
      <span class="trecho-num">T${idx}</span>
      <span class="trecho-label">${t.label}</span>
    </div>
    ${tabDados}${tabAces}
    ${formula(`Lt = L + Σ Le = ${fmt(t.L,4)} + ${fmt(t.Leq,4)} = <strong>${fmt(t.Lt,4)} m</strong>`)}
    ${formula(`hf = 10,643 × ${fmt(t.Lt,4)} × ${fmt(t.Q_m3s,4)}<sup>1,852</sup> / (${C}<sup>1,852</sup> × ${fmt(t.D,4)}<sup>4,871</sup>) = <strong>${fmt(t.Hf,4)} mca</strong>`)}
  </div>`;
}

function hidTrechos(c) {
  const hf = c.res.hf;
  const C  = c.C_HW;
  const cards = ['t1','t2','t3','t4'].map((k, i) => hidTrechoCard(hf[k], C, i+1)).join('');
  const linhasRes = ['t1','t2','t3','t4'].map(k => {
    const t = hf[k];
    return [
      t.label,
      `<mono>${fmt(t.Q_lmin,2)}</mono>`,
      `<mono>${fmt(t.D*1000,1)}</mono>`,
      `<mono>${fmt(t.Lt,4)}</mono>`,
      velBadge(t.V),
      `<mono><strong>${fmt(t.Hf,4)}</strong></mono>`,
    ];
  });
  return cards +
    '<h3 class="sub-secao">Resumo dos Trechos</h3>' +
    tabela(['Trecho','Q (L/min)','D (mm)','Lt (m)','V (m/s)','hf (mca)'], linhasRes);
}

function hidHMT(c) {
  const res = c.res;
  const hz  = res.Hz_governa;
  const Pmin = c.dados_sistema.pressao_min;
  const hzDesc = hz > 0.05  ? 'RTI acima do hidrante — favorável (reduz Ht)'
               : hz < -0.05 ? 'RTI abaixo do hidrante — desfavorável (aumenta Ht)'
               :               'Mesmo nível';
  const linhas = [
    ['Σhf (percurso crítico)', `<mono><strong>${fmt(res.Hf_governa,4)} mca</strong></mono>`, 'Soma das perdas por atrito'],
    ['ΔZ (com sinal)',         `<mono><strong>${fmt(hz,4)} m</strong></mono>`,               hzDesc],
  ];
  if (c.Hm_mangueira > 0) linhas.push(['Hm (mangueira)',   `<mono>${fmt(c.Hm_mangueira,4)} mca</mono>`, 'Darcy-Weisbach']);
  if (c.Hesg        > 0) linhas.push(['Hesg (esguicho)',   `<mono>${fmt(c.Hesg,4)} mca</mono>`,         '—']);
  linhas.push(['Pmin', `<mono><strong>${Pmin} mca</strong></mono>`, 'NT 22 CBMMA']);

  const eq = c.Hm_mangueira > 0
    ? `Ht = Σhf − ΔZ + Hm + Hesg + Pmin = ${fmt(res.Hf_governa,4)} − (${fmt(hz,4)}) + ${fmt(c.Hm_mangueira,4)} + ${fmt(c.Hesg,4)} + ${Pmin} = <strong>${fmt(res.Ht,4)} mca</strong>`
    : `Ht = Σhf − ΔZ + Pmin = ${fmt(res.Hf_governa,4)} − (${fmt(hz,4)}) + ${Pmin} = <strong>${fmt(res.Ht,4)} mca</strong>`;

  return nota(`Percurso crítico: <strong>${res.hid_governa}</strong>`) +
    tabela(['Parcela', 'Valor', 'Descrição'], linhas) + formula(eq);
}

function hidHidrantes(c) {
  const res  = c.res;
  const Pmin = c.dados_sistema.pressao_min;

  function blocoHid(label, Hz, Hf, P, Q, ordem) {
    return `<div class="hid-card">
      <div class="hid-header">
        <span class="hid-tag">${label}</span>
        <span class="hid-ordem">${ordem}</span>
      </div>
      ${tabela(['Parâmetro','Desenvolvimento','Resultado'], [
        ['Σhf do percurso',        'T1 + T2 + trecho exclusivo',                                    `<mono><strong>${fmt(Hf,4)} mca</strong></mono>`],
        ['ΔZ',                     `Z<sub>RTI</sub> − Z<sub>${label}</sub>`,                         `<mono><strong>${fmt(Hz,4)} m</strong></mono>`],
        ['Pressão na válvula (P)', `<mono>${fmt(res.Ht,4)} + (${fmt(Hz,4)}) − ${fmt(Hf,4)}</mono>`, `<mono><strong>${fmt(P,4)} mca</strong></mono>`],
        ['Vazão real (Q)',         `<mono>${fmt(res.K,4)} × √${fmt(P,4)}</mono>`,                    `<mono><strong>${fmt(Q,2)} L/min</strong></mono>`],
        ['Verificação normativa',  `Pmin = ${Pmin} / Pmax = 100 mca`,                               badgeStatus(P, Pmin, 100)],
      ])}
    </div>`;
  }

  const diff = Math.abs(res.p_hid02 - res.p_hid01);
  return formula('P = Ht + ΔZ − Σhf  &nbsp;|&nbsp;  Q = K × √P')
    + nota(`Iteração convergida em <strong>${res.iteracoes} ciclo(s)</strong> · K = <mono>${fmt(res.K,4)}</mono> · ΔP = <mono>${fmt(diff,4)} mca</mono>`)
    + `<div class="hid-grid">
        ${blocoHid('HID-01', c.Hz_H1, res.Hf_Hid01, res.p_hid01, res.Q_h01, '1º mais desfavorável')}
        ${blocoHid('HID-02', c.Hz_H2, res.Hf_Hid02, res.p_hid02, res.Q_h02, '2º mais desfavorável')}
       </div>`;
}

function hidBomba(c) {
  const res    = c.res;
  const etaDec = c.eta / 100;
  const tab = tabela(['Parâmetro', 'Valor', 'Observação'], [
    ['Vazão total convergida (Qt)', `<mono><strong>${fmt(res.Qt_final,2)} L/min = ${fmt(res.Qt_final/60000,4)} m³/s</strong></mono>`, 'Q<sub>HID-01</sub> + Q<sub>HID-02</sub>'],
    ['Altura manométrica (Ht)',     `<mono><strong>${fmt(res.Ht,4)} mca</strong></mono>`,                                             `Percurso crítico: ${res.hid_governa}`],
    ['Eficiência global (η)',       `<mono><strong>${c.eta}%</strong></mono>`,                                                        'Informada pelo projetista'],
  ]);
  const eq = formula(
    `Pcv = (1000 × ${fmt(res.Qt_final/60000,4)} × ${fmt(res.Ht,4)}) / (75 × ${fmt(etaDec,2)}) = <strong>${fmt(c.pot_cv,2)} cv</strong>`
  );
  const tabOp = tabela(['Q (m³/h)', 'Hm (mca)', 'Potência mínima (cv)', 'Potência mínima (kW)'], [[
    `<mono><strong>${fmt(res.Qt_final/1000*60,2)}</strong></mono>`,
    `<mono><strong>${fmt(res.Ht,2)}</strong></mono>`,
    `<mono><strong>${fmt(c.pot_cv,2)}</strong></mono>`,
    `<mono><strong>${fmt(c.pot_kw,2)}</strong></mono>`,
  ]]);
  return tab + eq + '<h3 class="sub-secao">Ponto de operação para seleção</h3>' + tabOp;
}

function hidResumo(c) {
  const res  = c.res;
  const Pmin = c.dados_sistema.pressao_min;

  function row(label, valor, unidade) {
    return `<div class="resumo-row">
      <span class="resumo-row-label">${label}</span>
      <span class="resumo-row-valor">${valor}<span class="unidade"> ${unidade || ''}</span></span>
    </div>`;
  }
  function card(tag, titulo, corpo) {
    return `<div class="resumo-card">
      <div class="resumo-card-header"><span class="tag">${tag}</span>${titulo}</div>
      <div class="resumo-card-body">${corpo}</div>
    </div>`;
  }

  return `<div class="resumo-grid">
    ${card('HID-01', '1º mais desfavorável',
      row('Pressão na válvula', fmt(res.p_hid01,4), 'mca') +
      row('Vazão real',         fmt(res.Q_h01,2),   'L/min') +
      row('Σhf percurso',       fmt(res.Hf_Hid01,4),'mca') +
      `<hr class="resumo-divider"><div class="resumo-status">${badgeStatus(res.p_hid01,Pmin,100)}</div>`
    )}
    ${card('HID-02', '2º mais desfavorável',
      row('Pressão na válvula', fmt(res.p_hid02,4), 'mca') +
      row('Vazão real',         fmt(res.Q_h02,2),   'L/min') +
      row('Σhf percurso',       fmt(res.Hf_Hid02,4),'mca') +
      `<hr class="resumo-divider"><div class="resumo-status">${badgeStatus(res.p_hid02,Pmin,100)}</div>`
    )}
    ${card('BOMBA', 'Ponto de operação',
      row('Altura manométrica (Ht)', fmt(res.Ht,4),                    'mca') +
      row('Vazão total (Qt)',        fmt(res.Qt_final,2),              'L/min') +
      row('Qt em m³/h',             fmt(res.Qt_final/1000*60,2),      'm³/h') +
      `<hr class="resumo-divider">` +
      row('Potência mínima',        fmt(c.pot_cv,2),                   'cv') +
      row('Potência mínima',        fmt(c.pot_kw,2),                   'kW')
    )}
  </div>`;
}

function renderHidrantes(c) {
  let s3n='3', s4n='4', s5n='5', s6n='6', secMang='';
  if (c.Hm_mangueira > 0) {
    secMang = secao('3', 'Perda de Carga na Mangueira (Darcy-Weisbach)',
      formula(`Hm = (2 × f × Lm) / (g × π² × Dm⁵) × Q² = <strong>${fmt(c.Hm_mangueira,4)} mca</strong>`)
    );
    s3n='4'; s4n='5'; s5n='6'; s6n='7';
  }
  return `
  <div class="cabecalho">
    <p class="cab-eyebrow">Medida de Segurança</p>
    <h1 class="cab-titulo"><strong>Hidrantes</strong></h1>
    <div class="cab-sub">
      <div class="cab-meta"><span class="cab-meta-label">Tipo de Sistema</span><span>${c.valor_sistema}</span></div>
      <div class="cab-meta"><span class="cab-meta-label">Método de Cálculo</span><span>${c.calculo_escolha}</span></div>
    </div>
  </div>
  ${secao('↗', 'Resumo Executivo', hidResumo(c))}
  ${secao('1', 'Dados Normativos do Sistema', hidDadosSistema(c))}
  ${secao('2', 'Cotas Altimétricas e Desníveis', hidElevacoes(c))}
  ${secMang}
  ${secao(s3n, 'Perdas de Carga por Trecho (Hazen-Williams)', hidTrechos(c))}
  ${secao(s4n, 'Altura Manométrica Total (Ht)', hidHMT(c))}
  ${secao(s5n, 'Pressão e Vazão nos Hidrantes', hidHidrantes(c))}
  ${secao(s6n, 'Dimensionamento da Bomba de Recalque', hidBomba(c))}`;
}

// ─── SAÍDAS DE EMERGÊNCIA ────────────────────────────────────────────────────

function saidaNormativos(c) {
  const e = c._estado || {};
  let norma, largAD, largER, largPT;
  if (e.norma_saidas) {
    norma  = `${e.norma_saidas} — ${e.corpo || ''}`;
    const lm = e.larguras_minimas || {};
    largAD = `<mono>${fmt(lm.AD || 1.20, 2)} m</mono>`;
    largER = `<mono>${fmt(lm.ER || 1.20, 2)} m</mono>`;
    const pt = (lm.PT || []).slice().sort((a,b) => a.n_up - b.n_up);
    largPT = pt.length
      ? `Conforme N° de UPs (${pt.map(x => `${fmt(x.largura,2)} m`).join(' / ')})`
      : 'Conforme N° de UPs';
  } else {
    norma  = 'IT 11 CBMSP — Saídas de Emergência';
    largAD = '<mono>1,20 m</mono>';
    largER = '<mono>1,20 m</mono>';
    largPT = 'Conforme N° de UPs (0,80 / 1,00 / 1,50 / 2,00 m)';
  }
  return tabela(['Parâmetro', 'Valor / Referência'], [
    ['Norma de referência',       norma],
    ['Unidade de Passagem (UP)',  '<mono>1 UP = 0,55 m</mono>'],
    ['Largura mín. — AD',         largAD],
    ['Largura mín. — ER',         largER],
    ['Largura mín. — PT',         largPT],
    ['Capacidade por UP',         'Menor valor entre as ocupações do pavimento'],
    ['ER — critério de projeto',  'Pavimento de maior população, excluindo o térreo'],
  ]);
}

function saidaAmbientes(c) {
  var rooms = c.rooms_data || [];
  if (!rooms.length) return nota('Nenhum ambiente identificado.');

  var map = {}, order = [];
  for (var i = 0; i < rooms.length; i++) {
    var r  = rooms[i];
    var nv = r.nivel || '(sem nível)';
    if (!map[nv]) { map[nv] = []; order.push(nv); }
    map[nv].push(r);
  }

  var key = '_fuPav_' + Date.now();
  window._fuPavRooms = window._fuPavRooms || {};
  window._fuPavRooms[key] = {
    rooms:     map,
    tabela:    (c._estado && c._estado.tabela)    || null,
    ocupacoes: (c._estado && c._estado.ocupacoes) || null,
  };

  var popup = '<div id="pav-popup-overlay" class="pav-popup-overlay pav-popup-hidden"'
    + ' onclick="_fuFecharPav(event)">'
    + '<div class="pav-popup" onclick="event.stopPropagation()">'
    + '<div class="pav-popup-header">'
    + '<span id="pav-popup-titulo" class="pav-popup-titulo"></span>'
    + '<button class="pav-popup-close" onclick="_fuFecharPav()">&#10005;</button>'
    + '</div><div id="pav-popup-body" class="pav-popup-body"></div>'
    + '</div></div>';

  var html = '<table class="tabela pav-rows-table">'
    + '<thead><tr><th>Pavimento</th><th>Ambientes</th><th>Pop. Total</th><th>Divisões</th></tr></thead>'
    + '<tbody>';

  for (var j = 0; j < order.length; j++) {
    var nivel   = order[j];
    var pav     = map[nivel];
    var popTot  = pav.reduce(function(s,r){ return s + (r.pop||0); }, 0);
    var qtd     = pav.length;
    var grupos  = [];
    for (var k = 0; k < pav.length; k++) { if (pav[k].grupo && grupos.indexOf(pav[k].grupo)<0) grupos.push(pav[k].grupo); }
    grupos.sort();
    var tags    = grupos.map(function(o){ return '<span class="tag">' + o + '</span>'; }).join(' ') || '—';
    var safeNivel = nivel.replace(/&/g, '&amp;').replace(/"/g, '&quot;');

    html += '<tr class="pav-row" style="cursor:pointer"'
          + ' data-key="' + key + '" data-nivel="' + safeNivel + '"'
          + ' onclick="_fuAbrirPav(this.dataset.key,this.dataset.nivel)">';
    html += '<td><strong>' + nivel + '</strong></td>';
    html += '<td><mono>' + qtd + '</mono></td>';
    html += '<td><mono><strong>' + popTot + '</strong> pess.</mono></td>';
    html += '<td>' + tags + '</td>';
    html += '</tr>';
  }

  html += '</tbody></table>';
  return popup + html;
}

function saidaAD(c) {
  const linhas = (c.resultados.ad || []).map(nd => [
    `<strong>${nd.nivel}</strong>`,
    `<mono>${nd.pop}</mono>`,
    nd.cap    ? `<mono>${nd.cap}</mono>`                   : '—',
    nd.n_up !== null && nd.n_up !== undefined ? `<mono>${nd.n_up} UP</mono>` : '—',
    nd.largura_calc   ? `<mono>${fmt(nd.largura_calc,2)} m</mono>`   : '—',
    nd.largura_min    ? `<mono>${fmt(nd.largura_min,2)} m</mono>`    : '—',
    nd.largura_adotada ? badge('ok', `${fmt(nd.largura_adotada,2)} m`) : '—',
  ]);
  return formula('N = ⌈P ÷ C⌉  &nbsp;·&nbsp;  L = N × 0,55  &nbsp;·&nbsp;  L<sub>adotada</sub> = max(L, L<sub>mín</sub>)')
    + tabela(['Pavimento','Pop.','Cap./UP','N° UPs','L calculada','L mínima','L adotada'], linhas);
}

function saidaER(c) {
  const er  = c.resultados.er;
  const tem = c.resultados.tem_multiplos_pavimentos;
  const lmEr = er.largura_min || 1.20;
  return nota(tem
      ? 'Critério: pavimento de maior população excluindo o térreo (IT 11).'
      : 'Edifício com pavimento único.')
    + formula(`N = ⌈P ÷ C⌉  &nbsp;·&nbsp;  L = N × 0,55  &nbsp;·&nbsp;  L<sub>adotada</sub> = max(L, ${fmt(lmEr,2)} m)`)
    + tabela(['Pavimento governante','Pop.','Cap./UP','N° UPs','L calculada','L mínima','L adotada'], [[
      `<strong>${er.nivel}</strong>`,
      `<mono>${er.pop}</mono>`,
      er.cap   ? `<mono>${er.cap}</mono>`                   : '—',
      er.n_up !== null && er.n_up !== undefined ? `<mono>${er.n_up} UP</mono>` : '—',
      er.largura_calc   ? `<mono>${fmt(er.largura_calc,2)} m</mono>`   : '—',
      er.largura_min    ? `<mono>${fmt(er.largura_min,2)} m</mono>`    : '—',
      er.largura_adotada ? badge('ok', `${fmt(er.largura_adotada,2)} m`) : '—',
    ]]);
}

function saidaPT(c) {
  const linhas = (c.resultados.pt || []).map(nd => [
    `<strong>${nd.nivel}</strong>`,
    `<mono>${nd.pop}</mono>`,
    nd.cap    ? `<mono>${nd.cap}</mono>`                   : '—',
    nd.n_up !== null && nd.n_up !== undefined ? `<mono>${nd.n_up} UP</mono>` : '—',
    nd.largura_calc   ? `<mono>${fmt(nd.largura_calc,2)} m</mono>`   : '—',
    nd.largura_min    ? `<mono>${fmt(nd.largura_min,2)} m</mono>`    : '—',
    nd.tipo_porta || '—',
    nd.largura_adotada ? badge('ok', `${fmt(nd.largura_adotada,2)} m`) : '—',
  ]);
  return formula('N = ⌈P ÷ C⌉  &nbsp;·&nbsp;  L<sub>adotada</sub> = max(N × 0,55, L<sub>mín por UPs</sub>)')
    + tabela(['Pavimento','Pop.','Cap./UP','N° UPs','L calculada','L mínima','Tipo','L adotada'], linhas);
}

function saidaDistancias(c) {
  var e  = c._estado;
  if (!e) return null;
  var dc = e.distancias_maximas;
  if (!dc) return null;
  var cd = c.config_distancias;
  if (!cd) return null;

  var mapa   = dc.mapa_ocupacao || {};
  var grupos = dc.grupos || {};
  var g      = mapa[cd.ocupacao_principal];
  if (!g || !grupos[g]) return null;

  var chu = cd.chuveiro    ? 'com_chuveiro' : 'sem_chuveiro';
  var sai = cd.saida_unica ? 'saida_unica'  : 'mais_saidas';
  var det = cd.deteccao    ? 'com_deteccao' : 'sem_deteccao';
  var cfg = grupos[g];

  function dv(pav) {
    try { var v = cfg[pav][chu][sai][det]; return (v != null) ? '<mono><strong>' + v + ' m</strong></mono>' : '<span style="color:var(--text3)">—</span>'; }
    catch(e) { return '<span style="color:var(--text3)">—</span>'; }
  }

  return tabela(
    ['Tipo de Pavimento', 'Distância Máxima a Percorrer'],
    [
      ['Piso de descarga (Térreo)', dv('terreo')],
      ['Demais pavimentos',         dv('demais')],
    ]
  );
}

function saidaResumo(c) {
  const res        = c.resultados;
  const er         = res.er;
  const nomeTerreo = res.nome_terreo || c.nome_terreo || '';
  const ad         = res.ad || [];
  const pt         = res.pt || [];

  // ── Distâncias máximas ────────────────────────────────────────────────────
  const hasDist = !!(c.config_distancias && c._estado && c._estado.distancias_maximas);

  function distPav(nivel) {
    if (!hasDist) return null;
    const cd = c.config_distancias, dc = c._estado.distancias_maximas;
    const g  = (dc.mapa_ocupacao || {})[cd.ocupacao_principal];
    if (!g || !(dc.grupos || {})[g]) return null;
    const pav = nivel === nomeTerreo ? 'terreo' : 'demais';
    const chu = cd.chuveiro    ? 'com_chuveiro' : 'sem_chuveiro';
    const sai = cd.saida_unica ? 'saida_unica'  : 'mais_saidas';
    const det = cd.deteccao    ? 'com_deteccao' : 'sem_deteccao';
    try { return dc.grupos[g][pav][chu][sai][det]; } catch { return null; }
  }

  // ── Mapa de pavimentos ────────────────────────────────────────────────────
  const map = {}, order = [];
  for (const nd of ad) { map[nd.nivel] = { ad: nd, pt: null, er: null }; order.push(nd.nivel); }
  for (const nd of pt)     { if (map[nd.nivel]) map[nd.nivel].pt = nd; }
  if (er && map[er.nivel]) { map[er.nivel].er = er; }

  // ── Helper: apenas L adotada ──────────────────────────────────────────────
  function larg(nd) {
    if (!nd || nd.largura_adotada == null) return '<span style="color:var(--text3)">—</span>';
    return badge('ok', fmt(nd.largura_adotada, 2) + ' m');
  }

  const cab = ['Pavimento', 'Pop.', 'AD', 'ER', 'PT'];
  if (hasDist) cab.push('Dist. máx.');

  const linhas = order.map(nivel => {
    const d = map[nivel];
    const ptTipo = d.pt?.tipo_porta ? `<br><small style="color:var(--text2)">${d.pt.tipo_porta}</small>` : '';
    const row = [
      `<strong>${nivel}</strong>`,
      `<mono>${d.ad.pop} pess.</mono>`,
      larg(d.ad),
      d.er ? larg(d.er) : '<span style="color:var(--text3)">—</span>',
      d.pt ? larg(d.pt) + ptTipo : '<span style="color:var(--text3)">—</span>',
    ];
    if (hasDist) {
      const dv = distPav(nivel);
      row.push(dv != null ? `<mono><strong>${dv} m</strong></mono>` : '<span style="color:var(--text3)">—</span>');
    }
    return row;
  });

  const erNota = er
    ? nota(`ER dimensionada pelo pavimento de maior população excluindo o térreo: <strong>${er.nivel}</strong> (${er.pop} pessoas).`)
    : '';

  return erNota + tabela(cab, linhas, 'resumo-tab resumo-tab-pav');
}

function renderSaidas(c) {
  const e        = c._estado || {};
  const normaRef = e.norma_saidas || 'IT 11';
  const corpo    = e.corpo ? ` — ${e.corpo}` : '';
  const s6html   = saidaDistancias(c);
  return `
  <div class="cabecalho">
    <p class="cab-eyebrow">Medida de Segurança</p>
    <h1 class="cab-titulo"><strong>Saídas de Emergência</strong></h1>
    <div class="cab-sub">
      <div class="cab-meta"><span class="cab-meta-label">Norma</span><span>${normaRef}${corpo}</span></div>
      <div class="cab-meta"><span class="cab-meta-label">Pavimentos</span><span>${(c.resultados.ad || []).length}</span></div>
    </div>
  </div>
  ${secao('↗', 'Resumo Executivo',               saidaResumo(c))}
  ${secao('1', 'Dados Normativos e Critérios',    saidaNormativos(c))}
  ${secao('2', 'Ambientes Identificados',         saidaAmbientes(c))}
  ${secao('3', 'Acessos e Descargas (AD)',        saidaAD(c))}
  ${secao('4', 'Escadas e Rampas (ER)',           saidaER(c))}
  ${secao('5', 'Portas (PT)',                     saidaPT(c))}
  ${s6html ? secao('6', 'Distâncias Máximas a Percorrer', s6html) : ''}`;
}

// ─── MONTAGEM FINAL ──────────────────────────────────────────────────────────

function renderMemorial(data) {
  const hid = data.hidrantes;
  const sai = data.saidas;
  if (!hid && !sai) return null;

  const partes = [];
  if (hid) partes.push(['I',  'Dimensionamento do Sistema de <strong>Hidrantes</strong>',         renderHidrantes(hid)]);
  if (sai) partes.push(['II', 'Dimensionamento das <strong>Saídas de Emergência</strong>',        renderSaidas(sai)]);

  const sistemas = partes.map(p => p[0] === 'I' ? 'Hidrantes' : 'Saídas de Emergência').join(' | ');

  const cabecalho = `<div class="cabecalho">
    <h1 class="cab-titulo"><strong>MEMORIAL DESCRITIVO</strong></h1>
    <div class="cab-sub"><div class="cab-meta">
      <span class="cab-meta-label">Sistemas</span>
      <span>${sistemas}</span>
    </div></div>
  </div>`;

  const conteudo = partes.map(([num, titulo, corpo]) => `
    <section class="section-sep">
      <div class="capitulo-sep">
        <h1 class="capitulo-sep-num">${num}</h1>
        <h1 class="capitulo-sep-titulo">${titulo}</h1>
      </div>
      ${corpo}
    </section>
    <div class="page-break"></div>`).join('');

  const rodape = `<div class="rodape">
    <span>Fire Utils · pyRevit Extension</span>
    <span>Gerado em ${new Date().toLocaleString('pt-BR')}</span>
  </div>`;

  return cabecalho + conteudo + rodape;
}

// ─── FETCH & AUTO-REFRESH ────────────────────────────────────────────────────

let _lastHash = null;

function simpleHash(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) { h = ((h << 5) - h) + str.charCodeAt(i); h |= 0; }
  return h;
}

function setIndicator(msg) {
  const el = document.getElementById('update-indicator');
  if (el) el.textContent = msg;
}

function _isFlaskOrigin() {
  const loc = window.location;
  return loc.protocol === 'http:' && loc.hostname === '127.0.0.1' && loc.port === '5000';
}

async function fetchAndRender() {
  const app = document.getElementById('app');
  if (!app || !app.dataset.autoSync) return;  // só roda na página /memorial
  setIndicator('Atualizando...');

  if (!_isFlaskOrigin()) {
    app.innerHTML = `<div class="empty-state">
      <p><strong>Site não está sendo servido pelo Flask.</strong></p>
      <p style="margin-top:8px;">
        Acesse via <code style="font-family:var(--mono);color:var(--accent2)">
        http://127.0.0.1:5000/memorial</code>
      </p>
      <p style="margin-top:12px;color:var(--text3);font-size:11px;">
        No Revit: clique em <strong>Memorial Descritivo</strong> para iniciar o servidor.<br>
        Sem Revit: execute <code style="font-family:var(--mono)">python app.py</code>
        dentro da pasta <code style="font-family:var(--mono)">lib/server/</code>.
      </p>
    </div>`;
    setIndicator('Servidor não detectado');
    return;
  }

  try {
    const resp = await fetch('/api/dados');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const text = await resp.text();
    const hash = simpleHash(text);

    if (hash === _lastHash) {
      setIndicator(`Sem alterações (${new Date().toLocaleTimeString('pt-BR')})`);
      return;
    }
    _lastHash = hash;

    const data = JSON.parse(text);
    const html = renderMemorial(data);

    if (!html) {
      app.innerHTML = `<div class="empty-state">
        <p>Nenhum dado disponível ainda.</p>
        <p>Execute <strong>Dimensionar Hidrantes</strong> e/ou
           <strong>Dimensionar Saídas</strong> no Revit.</p>
        <p style="margin-top:16px;color:var(--text3);font-size:11px;">
          Aguardando dados — verificando a cada 3 s
        </p>
      </div>`;
    } else {
      app.innerHTML = html;
    }

    setIndicator(`Sincronizado às ${new Date().toLocaleTimeString('pt-BR')}`);
  } catch (err) {
    setIndicator(`Erro: ${err.message}`);
    app.innerHTML = `<div class="error-state">
      <p><strong>Não foi possível conectar ao servidor.</strong></p>
      <p style="margin-top:8px;">Verifique se o servidor Flask está ativo e tente novamente.</p>
    </div>`;
  }
}

// ─── POPUP — Ambientes por Pavimento ─────────────────────────────────────────

window._fuPavRooms = window._fuPavRooms || {};

window._fuAbrirPav = function (key, nivel) {
  var store   = window._fuPavRooms[key] || {};
  var rooms   = (store.rooms ? store.rooms[nivel] : store[nivel]) || [];
  var itTab   = store.tabela    || null;
  var ocups   = store.ocupacoes || null;
  var overlay = document.getElementById('pav-popup-overlay');
  if (!overlay) return;

  document.getElementById('pav-popup-titulo').textContent = nivel;

  var linhas = rooms.map(function (r) {
    var taxa = '—';
    if (ocups && ocups[r.grupo] && ocups[r.grupo].descricao) {
      // Descrição da ocupação conforme cadastro do estado
      taxa = ocups[r.grupo].descricao;
    } else if (itTab && itTab[r.grupo] && itTab[r.grupo].AD != null) {
      // Fallback: capacidade normativa
      taxa = itTab[r.grupo].AD + ' pess./UP';
    } else if (r.area && r.pop) {
      // Fallback: taxa calculada pela relação área/população
      taxa = (r.area / r.pop).toFixed(2) + ' m²/p.';
    }
    return '<tr>'
      + '<td>' + (r.nome  || '—') + '</td>'
      + '<td><mono>' + (r.grupo || '—') + '</mono></td>'
      + '<td style="font-size:11px;color:var(--text2)">' + taxa + '</td>'
      + '<td><mono>' + Math.round(r.area || 0) + ' m²</mono></td>'
      + '<td><mono><strong>' + (r.pop || 0) + '</strong></mono></td>'
      + '</tr>';
  }).join('');

  document.getElementById('pav-popup-body').innerHTML =
    '<table class="tabela">'
    + '<thead><tr><th>Nome</th><th>Divisão</th><th>Taxa de Ocupação</th><th>Área</th><th>Pop.</th></tr></thead>'
    + '<tbody>' + linhas + '</tbody></table>';

  overlay.classList.remove('pav-popup-hidden');
};

window._fuFecharPav = function (e) {
  const overlay = document.getElementById('pav-popup-overlay');
  if (!overlay) return;
  if (!e || e.target === overlay) overlay.classList.add('pav-popup-hidden');
};

document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') {
    const el = document.getElementById('pav-popup-overlay');
    if (el) el.classList.add('pav-popup-hidden');
  }
});

document.addEventListener('DOMContentLoaded', fetchAndRender);
