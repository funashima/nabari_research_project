import {readFile} from 'node:fs/promises';
import {validateDataset} from '../dist/core.mjs';
const file=process.argv[2]||new URL('../dist/data/information.json',import.meta.url);
try {const d=JSON.parse(await readFile(file,'utf8'));const errors=validateDataset(d);if(errors.length){console.error(errors.join('\n'));process.exitCode=1;}else console.log(`VALID: ${d.items.length} records, asOf=${d.asOf}`);}catch(e){console.error(e.message);process.exitCode=1;}
