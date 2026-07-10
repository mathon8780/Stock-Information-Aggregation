import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

global.wx = {
  getStorageSync() {
    return '';
  },
};

const require = createRequire(import.meta.url);
const { formatRequestFailure, normalizeApiBaseUrl } = require('../services/api.js');

assert.equal(normalizeApiBaseUrl(' http://192.168.1.8:8000/api/v1/ '), 'http://192.168.1.8:8000/api/v1');
assert.equal(normalizeApiBaseUrl(''), 'http://127.0.0.1:8000/api/v1');

const message = formatRequestFailure(
  { errCode: 102, errMsg: 'request:fail url not in domain list' },
  'http://127.0.0.1:8000/api/v1/paper/sessions',
);

assert.match(message, /102/);
assert.match(message, /request:fail url not in domain list/);
assert.match(message, /127\.0\.0\.1/);
assert.match(message, /局域网 IP/);

console.log('api network error test passed');
