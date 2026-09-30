/**
 * Verificación end-to-end de un plugin de DSH REAL contra el servicio nuevo.
 *
 * No reimplementa el payload: importa el .mjs del plugin, captura la tool que registra y
 * llama a su execute() con el servicio apuntado por LAYA_SERVICE_URL.
 *
 * Uso: LAYA_SERVICE_URL=http://127.0.0.1:8091 node scripts/check_plugin.mjs <ruta-al-plugin.mjs>
 */
const pluginPath = process.argv[2];
if (!pluginPath) {
  console.error('falta la ruta al plugin');
  process.exit(2);
}

const CASES = [
  ['positivo claro', 'I love this product, it changed my life!'],
  ['negativo claro', 'El producto llegó roto y nadie responde. Una estafa.'],
  ['ambiguo (contraste)', 'No está mal, pero esperaba más por el precio'],
  ['sarcasmo', 'Great, another product that broke in a week. Just what I needed.'],
];

const mod = await import(pluginPath);
let tool = null;
const ctx = { tools: { register(t) { tool = t; } } };
mod.apply(ctx);

if (!tool) {
  console.error('el plugin no registró ninguna tool');
  process.exit(3);
}

console.log(`plugin : ${pluginPath.split('/').slice(-2, -1)[0]}/${pluginPath.split('/').pop()}`);
console.log(`modelo : "${mod.name ?? '?'}"  tool: ${tool.name}`);
console.log(`service: ${process.env.LAYA_SERVICE_URL ?? 'http://127.0.0.1:8090 (default del plugin)'}`);
console.log(`params : ${Object.keys(tool.parameters.properties).join(', ')}`);
console.log('');

function buildArgs(state) {
  const props = tool.parameters.properties;
  if (props.questions) {
    return { state, questions: [{ id: 'sentiment', type: 'noul', instructions: 'Does this text express positive sentiment?' }] };
  }
  return { state, instructions: 'Does this text express positive sentiment?' };
}

let fails = 0;
for (const [label, text] of CASES) {
  const t0 = Date.now();
  const out = await tool.execute(buildArgs(text));
  const ms = Date.now() - t0;
  if (out?.error) {
    fails += 1;
    console.log(`  ${label.padEnd(20)} ERROR ${out.error} ${out.message ?? ''} (${ms} ms)`);
    continue;
  }
  const a = out?.answers?.[0];
  if (!a) {
    fails += 1;
    console.log(`  ${label.padEnd(20)} respuesta sin answers[0]: ${JSON.stringify(out).slice(0, 120)}`);
    continue;
  }
  const conf = a.confidence?.toFixed(4);
  const del = a.delegate_to_cloud ? `DERIVA (${a.delegate_reason ?? ''})` : 'local';
  console.log(`  ${label.padEnd(20)} value=${String(a.value).padEnd(5)} conf=${conf} cal=${a.calibrated} ` +
              `T=${a.temperature ?? '-'} -> ${del}  [${ms} ms]`);
}
console.log('');
console.log(`modelo reportado por el servicio: ${(await tool.execute(buildArgs(CASES[0][1])))?.model}`);
console.log(fails === 0 ? 'RESULTADO: las 4 llamadas completaron el camino plugin -> servicio' : `RESULTADO: ${fails} fallos`);
process.exit(fails === 0 ? 0 : 1);
