'use strict';
const nodeFs = require('node:fs');
const path = require('node:path');

// ---------------------------------------------------------------------------
// Local, versioned state file for the integrated scoreboard.
//
// This module owns disk I/O only: it reads the document written by state.js and
// writes a new one atomically. It never decides anything about the match, never
// touches the network and never keeps secrets: the document contract lives in
// state.js (schema_version 1).
//
// Reading is deliberately suspicious. A missing file means "never initialized",
// but a file that exists and cannot be parsed is a hard error: the caller must
// refuse to start rather than boot an empty tatami over a broken one, and the
// corrupt file is never rewritten.
//
// Writing is atomic: a 0600 temporary file in the same directory, flushed with
// fsync, then renamed over the final path in one step. The final file is never a
// partially written one, and no backup copies are accumulated.
// ---------------------------------------------------------------------------

class StateFileError extends Error {
 constructor(message) {
  super(message);
  this.name = 'StateFileError';
 }
}
let sequence = 0;

function createStateFile(options = {}) {
 const file = options.file;
 if (typeof file !== 'string' || file.length === 0) throw new StateFileError('A non-empty state file path is required');
 // Injectable filesystem: a test seam only, the default is the real one.
 const fs = options.fs || nodeFs;
 // W_OK is 2 on POSIX; read from the injected filesystem when it exposes it, so a
 // test double without `constants` still works.
 const W_OK = fs.constants && typeof fs.constants.W_OK === 'number' ? fs.constants.W_OK : 2;
 // Readiness probe for the health endpoint (P2.5B). Read-only by contract: it
 // creates nothing, moves nothing and never rewrites the document — it only
 // answers whether a save could land right now (directory present and writable,
 // and the existing file writable too).
 function ready() {
  try {
   fs.accessSync(path.dirname(file), W_OK);
   if (fs.existsSync(file)) fs.accessSync(file, W_OK);
   return true;
  } catch (ignored) {
   return false;
  }
 }
 // Missing file => undefined (never initialized). Anything else that goes wrong
 // raises, so the process can fail closed instead of guessing.
 function load() {
  let raw;
  try {
   raw = fs.readFileSync(file, 'utf8');
  } catch (error) {
   if (error && error.code === 'ENOENT') return undefined;
   throw new StateFileError('cannot read ' + file + ': ' + (error && error.message ? error.message : error));
  }
  try {
   return JSON.parse(raw);
  } catch (error) {
   throw new StateFileError(file + ' is not valid JSON; refusing to start and keeping the file: '
    + (error && error.message ? error.message : error));
  }
 }
 function save(document) {
  const directory = path.dirname(file);
  sequence += 1;
  const temporary = path.join(directory, path.basename(file) + '.tmp-' + process.pid + '-' + sequence);
  const text = JSON.stringify(document, null, 1) + '\n';
  let handle = null;
  try {
   handle = fs.openSync(temporary, 'w', 0o600);
   fs.fchmodSync(handle, 0o600);
   fs.writeSync(handle, text, null, 'utf8');
   fs.fsyncSync(handle);
   fs.closeSync(handle);
   handle = null;
   fs.renameSync(temporary, file);
  } catch (error) {
   if (handle !== null) {try {fs.closeSync(handle);} catch (ignored) {}}
   try {fs.unlinkSync(temporary);} catch (ignored) {}
   throw new StateFileError('cannot persist ' + file + ': ' + (error && error.message ? error.message : error));
  }
  // Best effort: make the rename itself durable. Some filesystems refuse this.
  try {
   const directoryHandle = fs.openSync(directory, 'r');
   fs.fsyncSync(directoryHandle);
   fs.closeSync(directoryHandle);
  } catch (ignored) {}
  return true;
 }
 return {load, save, ready, file};
}
module.exports = {createStateFile, StateFileError};
