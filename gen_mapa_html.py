#!/usr/bin/env python3
import json
from pathlib import Path
BASE = Path('/Users/alexrangelalves/Downloads/Conexão mtds')
data = json.load(open(BASE/'mapa_cpl_data.json'))
estados = data['estados']
periodo = data.get('periodo',{})
DATA_JS = json.dumps(estados, ensure_ascii=False)

# CPL geral
tot_sp = sum(e['spend'] for e in estados); tot_ms = sum(e['msgs'] for e in estados)
cpl_geral = tot_sp/tot_ms if tot_ms else 0
melhor = estados[0]; pior = estados[-1]

html = f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mapa CPL por Estado · Gestores de Tráfego</title>
<link href="https://fonts.googleapis.com/css2?family=Mulish:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<script src="https://cdn.amcharts.com/lib/5/index.js"></script>
<script src="https://cdn.amcharts.com/lib/5/map.js"></script>
<script src="https://cdn.amcharts.com/lib/5/geodata/brazilLow.js"></script>
<script src="https://cdn.amcharts.com/lib/5/themes/Animated.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Mulish',sans-serif;background:#fffdf5;color:#2b2b2b}}
.wrap{{max-width:1200px;margin:0 auto;padding:24px}}
.head{{margin-bottom:8px}}
.head h1{{font-size:30px;font-weight:900;color:#1a1a1a;line-height:1.1}}
.head h1 .hl{{background:#FFE600;padding:0 8px;border-radius:4px}}
.head p{{font-size:13px;color:#777;margin-top:8px;max-width:560px;line-height:1.4}}
.kpis{{display:flex;gap:14px;flex-wrap:wrap;margin:18px 0}}
.kpi{{background:#fff;border:1px solid #eee;border-radius:12px;padding:14px 18px;box-shadow:0 1px 3px rgba(0,0,0,.05)}}
.kpi .l{{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#999;font-weight:700}}
.kpi .v{{font-size:24px;font-weight:900;color:#1a1a1a;margin-top:3px}}
.kpi.good .v{{color:#00A650}} .kpi.bad .v{{color:#E63946}}
.layout{{display:grid;grid-template-columns:1.4fr 1fr;gap:20px;align-items:start}}
#chartdiv{{width:100%;height:620px;background:#fff;border-radius:14px;border:1px solid #eee}}
.rank{{background:#fff;border:1px solid #eee;border-radius:14px;overflow:hidden}}
.rank h3{{font-size:13px;font-weight:800;padding:14px 16px;background:#2D3277;color:#fff;text-transform:uppercase;letter-spacing:.05em}}
.rrow{{display:flex;align-items:center;gap:10px;padding:9px 16px;border-bottom:1px solid #f3f3f3;cursor:pointer;transition:background .12s}}
.rrow:hover{{background:#FFFBE0}}
.rpos{{font-size:12px;font-weight:800;color:#bbb;width:26px}}
.rdot{{width:12px;height:12px;border-radius:3px;flex-shrink:0}}
.rname{{flex:1;font-size:13px;font-weight:600}}
.rsub{{font-size:10px;color:#999}}
.rcpl{{font-size:14px;font-weight:800;font-variant-numeric:tabular-nums}}
.legend{{display:flex;align-items:center;gap:8px;margin-top:12px;font-size:11px;color:#777}}
.legbar{{height:12px;width:200px;border-radius:6px;background:linear-gradient(90deg,#00A650,#FFE600,#FF8C00,#E63946)}}
.foot{{font-size:11px;color:#aaa;text-align:center;margin-top:20px}}
@media(max-width:860px){{.layout{{grid-template-columns:1fr}}#chartdiv{{height:440px}}}}
</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <h1>Ranking dos Estados por <span class="hl">CPL médio</span><br>nas unidades que atendemos</h1>
    <p>Custo por lead (mensagens iniciadas 7d) médio ponderado por estado, agregando todas as cidades/clínicas ativas. Passe o mouse sobre o estado para ver as cidades e seus CPLs. Período: <b>{periodo.get('since','—')} a {periodo.get('until','—')}</b>.</p>
  </div>
  <div class="kpis">
    <div class="kpi"><div class="l">CPL Geral</div><div class="v">R$ {cpl_geral:.2f}</div></div>
    <div class="kpi good"><div class="l">Melhor estado</div><div class="v">{melhor['uf']} · R$ {melhor['cpl']:.2f}</div></div>
    <div class="kpi bad"><div class="l">Pior estado</div><div class="v">{pior['uf']} · R$ {pior['cpl']:.2f}</div></div>
    <div class="kpi"><div class="l">Estados ativos</div><div class="v">{len(estados)}</div></div>
  </div>
  <div class="layout">
    <div>
      <div id="chartdiv"></div>
      <div class="legend"><span>Menor CPL</span><div class="legbar"></div><span>Maior CPL</span></div>
    </div>
    <div class="rank">
      <h3>Ranking por CPL (menor → maior)</h3>
      <div id="ranklist"></div>
    </div>
  </div>
  <div class="foot">Dashboard gerado a partir do nosso painel de gestores · CPL = gasto ÷ mensagens iniciadas (7d) · atualizado em {data.get('updated_at','—')}</div>
</div>

<script>
const ESTADOS = {DATA_JS};
const byId = {{}}; ESTADOS.forEach(e => byId[e.id] = e);
const cpls = ESTADOS.map(e=>e.cpl);
const minC = Math.min(...cpls), maxC = Math.max(...cpls);

function fmt(v){{return 'R$ '+v.toFixed(2).replace('.',',')}}
// cor verde->amarelo->laranja->vermelho conforme CPL
function colorFor(cpl){{
  const t = (cpl-minC)/(maxC-minC||1);
  // 0=verde(0,166,80) .4=amarelo(255,230,0) .7=laranja(255,140,0) 1=vermelho(230,57,70)
  let r,g,b;
  if(t<0.4){{const k=t/0.4; r=0+k*255; g=166+k*(230-166); b=80+k*(0-80);}}
  else if(t<0.7){{const k=(t-0.4)/0.3; r=255; g=230+k*(140-230); b=0;}}
  else{{const k=(t-0.7)/0.3; r=255+k*(230-255); g=140+k*(57-140); b=0+k*70;}}
  return am5.color(Math.round(r),Math.round(g),Math.round(b));
}}

am5.ready(function(){{
  const root = am5.Root.new("chartdiv");
  root.setThemes([am5themes_Animated.new(root)]);
  const chart = root.container.children.push(am5map.MapChart.new(root,{{
    panX:"none",panY:"none",wheelX:"none",wheelY:"none",
    projection:am5map.geoMercator()
  }}));
  const series = chart.series.push(am5map.MapPolygonSeries.new(root,{{
    geoJSON: am5geodata_brazilLow, valueField:"value", calculateAggregates:true
  }}));

  series.mapPolygons.template.setAll({{
    interactive:true, stroke:am5.color(0xffffff), strokeWidth:1.2,
    fill:am5.color(0xeeeeee)
  }});

  // tooltip HTML custom — fundo branco, texto preto (legível)
  series.mapPolygons.template.set("tooltipHTML", "{{tip}}");
  const tt = am5.Tooltip.new(root,{{ getFillFromSprite:false }});
  tt.get("background").setAll({{ fill: am5.color(0xffffff), fillOpacity: 1, stroke: am5.color(0xdddddd), strokeWidth: 1 }});
  series.set("tooltip", tt);

  series.mapPolygons.template.states.create("hover",{{fillOpacity:0.82}});

  // dados
  const mapData = ESTADOS.map(e=>{{
    const cidHtml = e.cidades.slice(0,16).map(c =>
      `<tr><td style='padding:1px 10px 1px 0;color:#222'>${{c.cidade}}</td><td style='text-align:right;font-weight:800;color:#1a1a1a'>${{fmt(c.cpl)}}</td></tr>`).join('');
    const extra = e.cidades.length>16 ? `<div style='color:#888;font-size:10px;margin-top:3px'>+${{e.cidades.length-16}} outras cidades</div>` : '';
    const tip = `<div style='font-family:Mulish;min-width:240px;background:#ffffff;color:#222;padding:10px 12px;border-radius:8px'>
      <div style='font-size:14px;font-weight:900;color:#1a1a1a;border-bottom:3px solid #FFE600;padding-bottom:4px;margin-bottom:6px'>${{e.nome}} (${{e.uf}})</div>
      <div style='font-size:13px;color:#333;margin-bottom:7px'>CPL médio: <b style='color:#E08600'>${{fmt(e.cpl)}}</b> · ${{e.msgs}} leads · ${{e.n_cidades}} cidades</div>
      <table style='font-size:11px;border-collapse:collapse'>${{cidHtml}}</table>${{extra}}
    </div>`;
    return {{ id:e.id, value:e.cpl, fill:colorFor(e.cpl), tip:tip }};
  }});
  series.data.setAll(mapData);

  // aplica cor individual
  series.mapPolygons.template.adapters.add("fill",(fill,target)=>{{
    const di = target.dataItem; if(di && di.dataContext && di.dataContext.fill) return di.dataContext.fill;
    return am5.color(0xe8e8e8);
  }});

  // rótulo da sigla + CPL no centro do estado
  const labelSeries = chart.series.push(am5map.MapPointSeries.new(root,{{}}));
  labelSeries.bullets.push(function(_,__,dataItem){{
    const e = dataItem.dataContext;
    return am5.Bullet.new(root,{{ sprite: am5.Label.new(root,{{
      text:`[bold]${{e.uf}}[/]\\n${{fmt(e.cpl)}}`, fontSize:10, textAlign:"center",
      centerX:am5.p50, centerY:am5.p50, populateText:true, fill:am5.color(0x222222)
    }})}});
  }});
  // posiciona labels nos centroides
  Promise.resolve().then(()=>{{
    series.events.on("datavalidated",()=>{{
      const pts=[];
      series.mapPolygons.each(p=>{{
        const e=byId[p.dataItem.get("id")]; if(!e)return;
        const c=p.geoCentroid(); pts.push({{geometry:{{type:"Point",coordinates:[c.longitude,c.latitude]}},uf:e.uf,cpl:e.cpl}});
      }});
      labelSeries.data.setAll(pts);
    }});
  }});

  // ranking lateral
  const rl=document.getElementById('ranklist');
  ESTADOS.forEach((e,i)=>{{
    const c=colorFor(e.cpl); const rgb=`rgb(${{c.toCSS()}})`;
    const div=document.createElement('div'); div.className='rrow';
    div.innerHTML=`<span class='rpos'>${{i+1}}º</span>
      <span class='rdot' style='background:${{c.toCSS()}}'></span>
      <span class='rname'>${{e.nome}} <span class='rsub'>(${{e.n_cidades}} cid · ${{e.msgs}} leads)</span></span>
      <span class='rcpl'>${{fmt(e.cpl)}}</span>`;
    rl.appendChild(div);
  }});
}});
</script>
</body>
</html>'''

out = BASE/'mapa_cpl_estados.html'
out.write_text(html, encoding='utf-8')
print(f'✅ {out} ({len(html):,} bytes)')
