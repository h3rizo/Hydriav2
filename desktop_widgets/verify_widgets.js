const fs = require('fs');
const vm = require('vm');

for (const folder of [
  'CompteursTeteWidgetElectron',
  'DebitsSourceWidgetElectron',
  'InterventionsWidgetElectron',
  'WeatherWidgetElectron',
]) {
  const path = `desktop_widgets/${folder}/widget.html`;
  const actualPath = folder === 'WeatherWidgetElectron'
    ? `desktop_widgets/${folder}/weather_widget.html`
    : path;
  const html = fs.readFileSync(actualPath, 'utf8');
  const inlineScript = html.match(/<script>([\s\S]*?)<\/script>/);
  if (!inlineScript) throw new Error(`${folder}: script introuvable`);
  new vm.Script(inlineScript[1], { filename: actualPath });
  JSON.parse(fs.readFileSync(`desktop_widgets/${folder}/package.json`, 'utf8'));
  console.log(`${folder}: HTML/JavaScript et package valides`);
}
