'use strict';
const path = require('node:path');
function start(legacyRoot = '/app') {
 if (process.env.SCOREBOARD_MODE !== 'integrated') {
  // Default remains the original application, with its original startup/relays.
  return require(path.join(legacyRoot, 'app.js'));
 }
 const {server} = require('./integrated').createServer(legacyRoot);
 server.listen(process.env.PORT || 3000);
 return server;
}
if (require.main === module) {
 try {
  start();
 } catch (error) {
  // Fail closed: a state document that cannot be trusted stops the process with a
  // clear reason instead of starting an empty scoreboard over the stored state.
  console.error('scoreboard: refusing to start:', error && error.message ? error.message : error);
  process.exit(1);
 }
}
module.exports = {start};
