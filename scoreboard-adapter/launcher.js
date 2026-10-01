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
if (require.main === module) start();
module.exports = {start};
