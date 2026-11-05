import {build} from 'esbuild';
import path from 'node:path';import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
await build({absWorkingDir:root,entryPoints:['server.ts'],outfile:path.join(root,'build/server-update.mjs'),bundle:true,platform:'node',format:'esm',target:'node24',external:['vite'],define:{'process.env.NODE_ENV':'"production"'},banner:{js:"import { createRequire as __createRequire } from 'node:module'; const require = __createRequire(import.meta.url);"},legalComments:'external',logLevel:'warning'});
